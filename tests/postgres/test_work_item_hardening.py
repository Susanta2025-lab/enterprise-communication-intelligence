"""Phase 22F: HTTP concurrency and fresh migration on the guarded local target."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from alembic.config import Config
from sqlalchemy import delete, inspect

from alembic import command
from app.application.services.identity import IdentityResolver
from app.core.security import AuthenticatedPrincipal
from app.domain.exceptions import WorkItemNotFoundError
from app.infrastructure.storage.models import AttachmentAnalysisRow, ConnectorAccount
from app.infrastructure.storage.repositories.business_work_item import (
    SqlAlchemyBusinessWorkItemRepository,
)
from tests.integration import test_work_items as http
from tests.postgres.alembic_checks import assert_at_head, assert_empty
from tests.support.jwt_tokens import TEST_ISSUER, TEST_PERMISSION
from tests.unit.infrastructure.storage.test_business_work_item_repository import counts
from tests.unit.infrastructure.storage.test_work_item_conversion import setup_conversion


@pytest.mark.parametrize("changed", [False, True])
def test_parallel_http_creation_and_lost_response(
    postgres_engine, monkeypatch, log_events, changed
):
    # Reuse the real JWT/side-effect sentinels, replacing only the disposable DB.
    monkeypatch.setattr(http, "create_database_engine", lambda _url: postgres_engine)
    fixture = http.api.__wrapped__(monkeypatch, log_events)
    api = next(fixture)
    client, key, sessions, factory = api
    IdentityResolver(factory).resolve_or_create(
        AuthenticatedPrincipal(TEST_ISSUER, "user-a-subject", frozenset({TEST_PERMISSION}))
    )
    barrier = Barrier(2)
    original = SqlAlchemyBusinessWorkItemRepository._existing_creation

    def synchronized(self, *args):
        result = original(self, *args)
        if not getattr(self, "_http_race_checked", False):
            self._http_race_checked = True
            barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(SqlAlchemyBusinessWorkItemRepository, "_existing_creation", synchronized)
    try:
        def attempt(index):
            return http.create(api, title="Changed" if changed and index else "Reviewed")

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(attempt, range(2)))
        assert sorted(r.status_code for r in responses) == ([201, 409] if changed else [200, 201])
        winner = next(r for r in responses if r.status_code == 201)
        monkeypatch.setattr(SqlAlchemyBusinessWorkItemRepository, "_existing_creation", original)
        replay = http.create(api, title=winner.json()["title"])
        assert replay.status_code == 200
        assert replay.json() == winner.json()
        assert replay.headers["location"] == winner.headers["location"]
        with sessions() as session:
            assert counts(session) == (1, 0, 1)
    finally:
        fixture.close()


@pytest.mark.parametrize("missing", ["analysis", "connector"])
def test_source_disappears_after_candidate_display(session_factory, missing):
    service, principal, request, _ = setup_conversion(session_factory)
    # setup_conversion has already displayed/projected the candidate.
    with session_factory() as session:
        model = AttachmentAnalysisRow if missing == "analysis" else ConnectorAccount
        session.execute(delete(model))
        session.commit()
    with pytest.raises(WorkItemNotFoundError):
        service.create_verified(principal, request)
    with session_factory() as session:
        assert counts(session) == (0, 0, 0)


def test_fresh_migration_chain_on_empty_disposable_database(
    postgres_engine, postgres_test_url, monkeypatch
):
    # The guarded autouse fixture emptied only the dedicated test database.
    # Refuse fresh rehearsal if anything survived; never erase data to downgrade.
    with postgres_engine.connect() as connection:
        from sqlalchemy import text

        for table in inspect(postgres_engine).get_table_names():
            if table != "alembic_version":
                assert connection.scalar(text(f'SELECT count(*) FROM "{table}"')) == 0
    monkeypatch.setattr(
        "app.infrastructure.storage.migration_config.resolve_migration_database_url",
        lambda: postgres_test_url,
    )
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.downgrade(config, "base")
    assert_empty(postgres_test_url)
    command.upgrade(config, "head")
    assert_at_head(postgres_test_url)

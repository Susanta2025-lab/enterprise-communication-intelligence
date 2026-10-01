"""Real disposable PostgreSQL contract and concurrency gates (never SQLite)."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.domain.exceptions import WorkItemConflictError
from app.domain.models.business_work_item import WorkItemCommand
from app.infrastructure.storage.repositories.business_context import (
    SqlAlchemyBusinessContextRepository,
)
from app.infrastructure.storage.repositories.business_work_item import (
    SqlAlchemyBusinessWorkItemRepository,
)
from tests.unit.infrastructure.storage import test_business_work_item_repository as contract
from tests.unit.infrastructure.storage.test_phase22b_migration import exercise_tracking_migration

# Reuse the same portable contract against the guarded, migrated PostgreSQL fixture.
test_roundtrip_noops_and_owner_versions = contract.test_roundtrip_noops_and_owner_versions
test_creation_replay_conflicts_and_retained_sources = (
    contract.test_creation_replay_conflicts_and_retained_sources
)
test_context_move_history_and_archive_policy = contract.test_context_move_history_and_archive_policy
test_creation_failure_rolls_back_whole_aggregate = (
    contract.test_creation_failure_rolls_back_whole_aggregate
)
test_mutation_event_failure_and_outer_rollback = (
    contract.test_mutation_event_failure_and_outer_rollback
)
test_account_erasure_and_context_deletion = contract.test_account_erasure_and_context_deletion
test_root_sql_constraints = contract.test_root_sql_constraints
test_source_sql_constraints = contract.test_source_sql_constraints
test_event_sql_constraints = contract.test_event_sql_constraints
test_foreign_source_and_no_source_write_port = contract.test_foreign_source_and_no_source_write_port


@pytest.mark.parametrize("mode", ["same_key", "changed_intent", "candidate"])
def test_parallel_creation_has_one_durable_winner(session_factory, mode):
    owner, _ = contract.owners(session_factory)
    with session_factory() as session:
        source = contract.analysis_source(session, owner, candidate=True)
        session.commit()
    if mode == "candidate":
        intent = contract.intent(
            creation_origin="ai_confirmed",
            sources=(source,),
            origin_candidate=source.locator(),
            confirmed=True,
        )
    else:
        intent = contract.intent(sources=(source,))
    barrier = Barrier(2)

    def attempt(index):
        with session_factory() as session:
            session.execute(text("SET LOCAL statement_timeout = '10s'"))
            repo = SqlAlchemyBusinessWorkItemRepository(session)
            original = repo._existing_creation
            first = True

            def synchronized(*args):
                nonlocal first
                result = original(*args)
                if first:
                    first = False
                    barrier.wait(timeout=5)
                return result

            repo._existing_creation = synchronized
            request = (
                intent.model_copy(update={"title": "Different"})
                if mode == "changed_intent" and index
                else intent
            )
            try:
                result = repo.create_owned(
                    owner, f"key-{index}" if mode == "candidate" else "key", request
                )
                session.commit()
                return "replay" if result.replayed else "created"
            except WorkItemConflictError as exc:
                # Uniqueness recovery must leave the PostgreSQL transaction usable.
                assert session.execute(text("SELECT 1")).scalar_one() == 1
                session.commit()
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))
    assert outcomes.count("created") == 1
    if mode == "same_key":
        assert outcomes.count("replay") == 1
    else:
        assert sum(o.startswith("work_item_") for o in outcomes) == 1
    with session_factory() as session:
        assert contract.counts(session) == (1, 1, 1)


def test_parallel_expected_versions_have_one_winner(session_factory):
    owner, _ = contract.owners(session_factory)
    with session_factory() as session:
        saved = (
            SqlAlchemyBusinessWorkItemRepository(session)
            .create_owned(owner, "key", contract.intent())
            .item
        )
        session.commit()
    barrier = Barrier(2)

    def attempt(status):
        with session_factory() as session:
            session.execute(text("SET LOCAL statement_timeout = '10s'"))
            barrier.wait(timeout=5)
            try:
                SqlAlchemyBusinessWorkItemRepository(session).mutate_owned(
                    saved.id,
                    owner,
                    WorkItemCommand(operation="status", expected_version=1, status=status),
                )
                session.commit()
                return "saved"
            except WorkItemConflictError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ("completed", "cancelled")))
    assert sorted(outcomes) == ["saved", "work_item_version_conflict"]
    with session_factory() as session:
        assert contract.counts(session) == (1, 0, 2)


@pytest.mark.parametrize("first", ["association", "archive"])
def test_context_archive_association_lock_contract(session_factory, first):
    owner, _ = contract.owners(session_factory)
    with session_factory() as session:
        ctx = contract.context(session, owner)
        session.commit()
    with session_factory() as holder:
        holder.execute(text("SET LOCAL statement_timeout = '10s'"))
        if first == "association":
            saved = (
                SqlAlchemyBusinessWorkItemRepository(holder)
                .create_owned(owner, "key", contract.intent(business_context_id=ctx.id))
                .item
            )
        else:
            ctx.archive()
            SqlAlchemyBusinessContextRepository(holder).save_owned(ctx)

        def blocked_other():
            with session_factory() as session:
                session.execute(text("SET LOCAL lock_timeout = '150ms'"))
                try:
                    if first == "association":
                        loaded = SqlAlchemyBusinessContextRepository(session).get_owned(
                            ctx.id, owner
                        )
                        loaded.archive()
                        SqlAlchemyBusinessContextRepository(session).save_owned(loaded)
                    else:
                        SqlAlchemyBusinessWorkItemRepository(session).create_owned(
                            owner, "key", contract.intent(business_context_id=ctx.id)
                        )
                except Exception as exc:
                    # Public repository failures are sanitized; timeout must leave no writes.
                    from app.core.exceptions import PersistenceError

                    assert isinstance(exc, (PersistenceError, OperationalError))
                    session.rollback()
                    return True
                return False

        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(blocked_other).result(timeout=5)
        holder.commit()
    with session_factory() as session:
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        if first == "archive":
            with pytest.raises(WorkItemConflictError, match="context_archived"):
                repo.create_owned(owner, "key", contract.intent(business_context_id=ctx.id))
            assert contract.counts(session) == (0, 0, 0)
        else:
            ctx = SqlAlchemyBusinessContextRepository(session).get_owned(ctx.id, owner)
            ctx.archive()
            SqlAlchemyBusinessContextRepository(session).save_owned(ctx)
            session.commit()
            assert repo.get_owned(saved.id, owner).status.value == "open"
            assert repo.get_owned(saved.id, owner).archived_at is None


def test_postgres_additive_upgrade_and_guarded_downgrade(
    postgres_engine, postgres_test_url, monkeypatch
):
    exercise_tracking_migration(postgres_engine, postgres_test_url, monkeypatch)


test_due_null_combinations_never_pass_unknown = (
    contract.test_due_null_combinations_never_pass_unknown
)
test_confirmation_null_combinations_never_pass_unknown = (
    contract.test_confirmation_null_combinations_never_pass_unknown
)
test_date_roundtrip_and_replay_returns_current_archived_item = (
    contract.test_date_roundtrip_and_replay_returns_current_archived_item
)
test_work_item_uow_session_and_commit_failure = (
    contract.test_work_item_uow_session_and_commit_failure
)

test_sql_rejects_whitespace_only_text_and_provider_ids = (
    contract.test_sql_rejects_whitespace_only_text_and_provider_ids
)

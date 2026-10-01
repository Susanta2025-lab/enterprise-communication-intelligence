"""Portable SQLite/PostgreSQL aggregate transaction contract."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import PersistenceError
from app.domain.enums import BusinessContextType
from app.domain.exceptions import WorkItemConflictError, WorkItemNotFoundError
from app.domain.models.business_context import BusinessContext
from app.domain.models.business_work_item import WorkItemCommand
from app.domain.models.business_work_item_source import WorkItemSource
from app.domain.models.work_item_intent import CreationIntent
from app.infrastructure.storage.models import (
    Analysis,
    BusinessContextRow,
    BusinessWorkItemEventRow,
    BusinessWorkItemRow,
    BusinessWorkItemSourceRow,
    User,
)
from app.infrastructure.storage.repositories.business_context import (
    SqlAlchemyBusinessContextRepository,
)
from app.infrastructure.storage.repositories.business_work_item import (
    SqlAlchemyBusinessWorkItemRepository,
)
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork

TABLES = (BusinessWorkItemRow, BusinessWorkItemSourceRow, BusinessWorkItemEventRow)


def owners(factory):
    with factory() as session:
        a, b = User(), User(application_role="owner")
        session.add_all([a, b])
        session.flush()
        ids = a.id, b.id
        session.commit()
        return ids


def intent(**kw):
    return CreationIntent(kind="action", title="Track", **kw)


def context(session, owner):
    return SqlAlchemyBusinessContextRepository(session).add(
        BusinessContext(
            owner_user_id=owner,
            type=BusinessContextType.MATTER,
            title="Context",
        )
    )


def analysis_source(session, owner, *, candidate=False):
    row = Analysis(
        user_id=owner,
        provider="mock",
        priority="medium",
        category="general",
        source_type="text",
        summary_text="Stored analysis",
        action_items=[{"description": "Review"}],
    )
    session.add(row)
    session.flush()
    extra = (
        dict(candidate_field="action_items", candidate_index=0, candidate_digest="a" * 64)
        if candidate
        else {}
    )
    return WorkItemSource(source_kind="communication_analysis", analysis_id=row.id, **extra)


def counts(session):
    return tuple(session.scalar(select(func.count()).select_from(t)) for t in TABLES)


def test_roundtrip_noops_and_owner_versions(session_factory):
    owner, foreign = owners(session_factory)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        repo = uow.business_work_items
        created = repo.create_owned(
            owner,
            "key",
            intent(
                due={
                    "kind": "datetime",
                    "at": "2026-11-01T01:30:00-05:00",
                    "timezone": "America/New_York",
                }
            ),
        ).item
        uow.commit()
    with session_factory() as session:
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        assert repo.get_owned(created.id, owner) == created
        assert repo.get_owned(created.id, foreign) is None
        for op in (
            lambda: repo.sources_owned(created.id, foreign),
            lambda: repo.events_owned(created.id, foreign),
            lambda: repo.mutate_owned(
                created.id, foreign, WorkItemCommand(operation="restore", expected_version=1)
            ),
        ):
            with pytest.raises(WorkItemNotFoundError):
                op()
        noop = repo.mutate_owned(
            created.id,
            owner,
            WorkItemCommand(
                operation="edit", expected_version=1, edit={"title": " Track ", "due": created.due}
            ),
        )
        assert noop.version == 1 and counts(session) == (1, 0, 1)
        completed = repo.mutate_owned(
            created.id,
            owner,
            WorkItemCommand(operation="status", expected_version=1, status="completed"),
        )
        assert completed.version == 2 and completed.completed_at
        with pytest.raises(WorkItemConflictError, match="version"):
            repo.mutate_owned(
                created.id,
                owner,
                WorkItemCommand(operation="status", expected_version=1, status="completed"),
            )
        assert counts(session) == (1, 0, 2)
        session.commit()


def test_creation_replay_conflicts_and_retained_sources(session_factory):
    owner, _ = owners(session_factory)
    with session_factory() as session:
        source = analysis_source(session, owner, candidate=True)
        request = intent(
            creation_origin="ai_confirmed",
            sources=(source,),
            origin_candidate=source.locator(),
            confirmed=True,
        )
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        saved = repo.create_owned(owner, "key", request)
        assert not saved.replayed
        session.execute(delete(Analysis).where(Analysis.id == source.analysis_id))
        session.commit()
    with session_factory() as session:
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        replay = repo.create_owned(owner, "key", request)
        assert replay.replayed and replay.item == saved.item
        with pytest.raises(WorkItemConflictError, match="creation_key"):
            repo.create_owned(owner, "key", request.model_copy(update={"title": "Changed"}))
        with pytest.raises(WorkItemConflictError, match="candidate_already") as error:
            repo.create_owned(owner, "new", request)
        assert error.value.existing_item_id == saved.item.id
        assert repo.sources_owned(saved.item.id, owner) == (source,)
        assert counts(session) == (1, 1, 1)
        with pytest.raises(WorkItemNotFoundError):
            repo.create_owned(owner, "manual-new", intent(sources=(source,)))


def test_context_move_history_and_archive_policy(session_factory):
    owner, foreign = owners(session_factory)
    with session_factory() as session:
        a, b, other = context(session, owner), context(session, owner), context(session, foreign)
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        saved = repo.create_owned(owner, "key", intent(business_context_id=a.id)).item
        moved = repo.mutate_owned(
            saved.id,
            owner,
            WorkItemCommand(
                operation="edit",
                expected_version=1,
                edit={"title": "Changed", "business_context_id": b.id},
            ),
        )
        assert moved.version == 2
        events = repo.events_owned(saved.id, owner)
        assert [e.event_ordinal for e in events] == [0, 0, 1, 2]
        assert [e.context_at_event_id for e in events] == [a.id, a.id, a.id, b.id]
        assert len(repo.context_events_owned(a.id, owner)) == 3
        assert len(repo.context_events_owned(b.id, owner)) == 1
        with pytest.raises(WorkItemNotFoundError):
            repo.context_events_owned(a.id, foreign)
        with pytest.raises(WorkItemNotFoundError):
            repo.create_owned(owner, "foreign", intent(business_context_id=other.id))
        b.archive()
        SqlAlchemyBusinessContextRepository(session).save_owned(b)
        assert repo.get_owned(saved.id, owner).status.value == "open"
        with pytest.raises(WorkItemConflictError, match="context_archived"):
            repo.create_owned(owner, "archived", intent(business_context_id=b.id))
        detached = repo.mutate_owned(
            saved.id,
            owner,
            WorkItemCommand(
                operation="edit", expected_version=2, edit={"business_context_id": None}
            ),
        )
        assert detached.business_context_id is None
        session.commit()


@pytest.mark.parametrize("failure", ["source", "event"])
def test_creation_failure_rolls_back_whole_aggregate(session_factory, monkeypatch, failure):
    owner, _ = owners(session_factory)
    with session_factory() as session:
        source = analysis_source(session, owner)
        session.commit()
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        execute = session.execute

        def fail(statement, *args, **kw):
            table = getattr(statement, "table", None)
            if getattr(table, "name", None) == (
                "business_work_item_sources" if failure == "source" else "business_work_item_events"
            ):
                raise IntegrityError("safe injected failure", None, Exception())
            return execute(statement, *args, **kw)

        monkeypatch.setattr(session, "execute", fail)
        with pytest.raises(PersistenceError):
            repo.create_owned(owner, "key", intent(sources=(source,)))
        monkeypatch.setattr(session, "execute", execute)
        assert counts(session) == (0, 0, 0)
        # Savepoint restored a usable transaction, including on PostgreSQL.
        assert repo.create_owned(owner, "key", intent(sources=(source,))).item.version == 1
        session.commit()


def test_mutation_event_failure_and_outer_rollback(session_factory, monkeypatch):
    owner, _ = owners(session_factory)
    with session_factory() as session:
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        saved = repo.create_owned(owner, "key", intent()).item
        session.commit()
        with monkeypatch.context() as patch:

            def fail(events):
                raise IntegrityError("safe failure", None, Exception())

            patch.setattr(repo, "_append_events", fail)
            with pytest.raises(PersistenceError):
                repo.mutate_owned(
                    saved.id, owner, WorkItemCommand(operation="archive", expected_version=1)
                )
        assert repo.get_owned(saved.id, owner) == saved
        assert counts(session) == (1, 0, 1)
        repo.mutate_owned(saved.id, owner, WorkItemCommand(operation="archive", expected_version=1))
        session.rollback()
        assert repo.get_owned(saved.id, owner) == saved and counts(session) == (1, 0, 1)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        uow.business_work_items.create_owned(owner, "uncommitted", intent())
    with session_factory() as session:
        assert counts(session) == (1, 0, 1)


@pytest.mark.parametrize("orm", [False, True])
def test_account_erasure_and_context_deletion(session_factory, orm):
    owner, _ = owners(session_factory)
    with session_factory() as session:
        ctx = context(session, owner)
        source = analysis_source(session, owner)
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        saved = repo.create_owned(
            owner, "key", intent(sources=(source,), business_context_id=ctx.id)
        ).item
        session.execute(delete(BusinessContextRow).where(BusinessContextRow.id == ctx.id))
        current = repo.get_owned(saved.id, owner)
        assert current.owner_user_id == owner and current.business_context_id is None
        assert repo.events_owned(saved.id, owner)[0].context_at_event_id == ctx.id
        if orm:
            session.delete(session.get(User, owner))
        else:
            session.execute(delete(User).where(User.id == owner))
        session.commit()
        assert counts(session) == (0, 0, 0)


@pytest.mark.parametrize(
    "updates",
    [
        {"due_kind": "date"},
        {"due_kind": "datetime"},
        {"due_timezone": "UTC"},
        {"due_kind": "invalid"},
        {"status": "completed"},
        {"status": "cancelled"},
        {"version": 0},
        {"kind": "reply"},
        {"title": " "},
        {"description": ""},
        {"creation_origin": "ai_confirmed"},
        {"creation_origin": "invalid"},
        {"origin_candidate_key": "a" * 64},
        {"creation_request_hash": "z" * 64},
        {"creation_key": "not allowed"},
        {"creation_key": "á"},
        {"confirmed_by_user_id": uuid4()},
    ],
)
def test_root_sql_constraints(session_factory, updates):
    owner, _ = owners(session_factory)
    with session_factory() as session:
        saved = (
            SqlAlchemyBusinessWorkItemRepository(session).create_owned(owner, "key", intent()).item
        )
        session.commit()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                update(BusinessWorkItemRow)
                .where(BusinessWorkItemRow.id == saved.id)
                .values(**updates)
            )
        assert counts(session) == (1, 0, 1)


@pytest.mark.parametrize(
    "updates",
    [
        {"source_kind": "communication"},
        {"source_kind": "invalid"},
        {"analysis_id": None},
        {"attachment_analysis_id": uuid4()},
        {"connector_account_id": uuid4()},
        {"candidate_index": 0},
        {"candidate_field": "action_items", "candidate_digest": "a" * 64},
        {"candidate_field": "action_items", "candidate_index": 0},
        {"candidate_field": "action_items", "candidate_index": -1, "candidate_digest": "a" * 64},
        {"candidate_field": "potential_dates", "candidate_index": 0, "candidate_digest": "a" * 64},
        {"source_key": "g" * 64},
    ],
)
def test_source_sql_constraints(session_factory, updates):
    owner, foreign = owners(session_factory)
    with session_factory() as session:
        source = analysis_source(session, owner)
        saved = (
            SqlAlchemyBusinessWorkItemRepository(session)
            .create_owned(owner, "key", intent(sources=(source,)))
            .item
        )
        session.commit()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                update(BusinessWorkItemSourceRow)
                .where(BusinessWorkItemSourceRow.work_item_id == saved.id)
                .values(**updates)
            )
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                update(BusinessWorkItemSourceRow)
                .where(BusinessWorkItemSourceRow.work_item_id == saved.id)
                .values(user_id=foreign)
            )


@pytest.mark.parametrize(
    "updates",
    [
        {"event_type": "invalid"},
        {"event_ordinal": -1},
        {"item_version": 0},
        {"actor_user_id": uuid4()},
    ],
)
def test_event_sql_constraints(session_factory, updates):
    owner, foreign = owners(session_factory)
    with session_factory() as session:
        saved = (
            SqlAlchemyBusinessWorkItemRepository(session).create_owned(owner, "key", intent()).item
        )
        session.commit()
        table = BusinessWorkItemEventRow.__table__
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(update(table).where(table.c.work_item_id == saved.id).values(**updates))
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                update(table)
                .where(table.c.work_item_id == saved.id)
                .values(user_id=foreign, actor_user_id=foreign)
            )
        row = dict(session.execute(select(table)).mappings().one())
        row["id"] = uuid4()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(insert(table).values(**row))


def test_foreign_source_and_no_source_write_port(session_factory):
    owner, foreign = owners(session_factory)
    with session_factory() as session:
        source = analysis_source(session, foreign)
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        with pytest.raises(WorkItemNotFoundError):
            repo.create_owned(owner, "key", intent(sources=(source,)))
        assert counts(session) == (0, 0, 0)
        assert not hasattr(repo, "add_source") and not hasattr(repo, "delete_event")


@pytest.mark.parametrize("due_kind", ["none", "date", "datetime"])
@pytest.mark.parametrize("present", range(8))
def test_due_null_combinations_never_pass_unknown(session_factory, due_kind, present):
    from datetime import UTC, date, datetime

    owner, _ = owners(session_factory)
    with session_factory() as session:
        saved = (
            SqlAlchemyBusinessWorkItemRepository(session).create_owned(owner, "key", intent()).item
        )
        values = dict(
            due_kind=due_kind,
            due_date=date(2030, 1, 1) if present & 1 else None,
            due_at=datetime(2030, 1, 1, tzinfo=UTC) if present & 2 else None,
            due_timezone="UTC" if present & 4 else None,
        )
        valid = present == {"none": 0, "date": 5, "datetime": 6}[due_kind]
        if valid:
            session.execute(
                update(BusinessWorkItemRow)
                .where(BusinessWorkItemRow.id == saved.id)
                .values(**values)
            )
        else:
            with pytest.raises(IntegrityError), session.begin_nested():
                session.execute(
                    update(BusinessWorkItemRow)
                    .where(BusinessWorkItemRow.id == saved.id)
                    .values(**values)
                )


@pytest.mark.parametrize("origin", ["manual", "ai_confirmed"])
@pytest.mark.parametrize("present", range(8))
def test_confirmation_null_combinations_never_pass_unknown(session_factory, origin, present):
    owner, foreign = owners(session_factory)
    with session_factory() as session:
        saved = (
            SqlAlchemyBusinessWorkItemRepository(session).create_owned(owner, "key", intent()).item
        )
        values = dict(
            creation_origin=origin,
            confirmed_by_user_id=owner if present & 1 else None,
            confirmed_at=saved.created_at if present & 2 else None,
            origin_candidate_key="a" * 64 if present & 4 else None,
        )
        valid = (origin, present) in (("manual", 0), ("ai_confirmed", 7))
        if valid:
            session.execute(
                update(BusinessWorkItemRow)
                .where(BusinessWorkItemRow.id == saved.id)
                .values(**values)
            )
        else:
            with pytest.raises(IntegrityError), session.begin_nested():
                session.execute(
                    update(BusinessWorkItemRow)
                    .where(BusinessWorkItemRow.id == saved.id)
                    .values(**values)
                )


def test_date_roundtrip_and_replay_returns_current_archived_item(session_factory):
    owner, _ = owners(session_factory)
    request = intent(due={"kind": "date", "date": "2030-01-01", "timezone": "Pacific/Apia"})
    with session_factory() as session:
        repo = SqlAlchemyBusinessWorkItemRepository(session)
        saved = repo.create_owned(owner, "key", request).item
        row = session.get(BusinessWorkItemRow, saved.id)
        assert row.due_at is None and str(row.due_date) == "2030-01-01"
        archived = repo.mutate_owned(
            saved.id, owner, WorkItemCommand(operation="archive", expected_version=1)
        )
        session.commit()
        replay = repo.create_owned(owner, "key", request)
        assert replay.item == archived and replay.replayed
        assert counts(session) == (1, 0, 2)


def test_work_item_uow_session_and_commit_failure(session_factory, monkeypatch):
    from sqlalchemy.exc import OperationalError

    owner, _ = owners(session_factory)
    uow = SqlAlchemyPersistenceUnitOfWork(session_factory)
    with pytest.raises(PersistenceError):
        _ = uow.business_work_items
    with uow:
        assert uow.business_work_items._session is uow.identity_repository._session
        uow.business_work_items.create_owned(owner, "key", intent())

        def fail():
            raise OperationalError("SQL", {}, Exception("private input"))

        monkeypatch.setattr(uow._session, "commit", fail)
        with pytest.raises(PersistenceError) as exc:
            uow.commit()
        assert "private" not in str(exc.value)
    with pytest.raises(PersistenceError):
        _ = uow.business_work_items
    with session_factory() as session:
        assert counts(session) == (0, 0, 0)


@pytest.mark.parametrize("whitespace", ["\t\r\n", "\u00a0", "\u2003"])
def test_sql_rejects_whitespace_only_text_and_provider_ids(session_factory, whitespace):
    owner, _ = owners(session_factory)
    with session_factory() as session:
        saved = (
            SqlAlchemyBusinessWorkItemRepository(session).create_owned(owner, "key", intent()).item
        )
        for field in ("title", "description"):
            with pytest.raises(IntegrityError), session.begin_nested():
                session.execute(
                    update(BusinessWorkItemRow)
                    .where(BusinessWorkItemRow.id == saved.id)
                    .values(**{field: whitespace})
                )
        for field in ("provider_message_id", "provider_attachment_id"):
            values = dict(
                id=uuid4(),
                work_item_id=saved.id,
                user_id=owner,
                source_kind="attachment_analysis",
                attachment_analysis_id=uuid4(),
                connector_account_id=uuid4(),
                provider_message_id="Message",
                provider_attachment_id="Attachment",
                source_key="a" * 64,
                linked_at=saved.created_at,
            )
            values[field] = whitespace
            with pytest.raises(IntegrityError), session.begin_nested():
                session.execute(insert(BusinessWorkItemSourceRow).values(**values))

"""Workflow action repository tests using isolated SQLite."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import PersistenceError
from app.domain.enums import WorkflowActionStatus, WorkflowActionType
from app.domain.interfaces.analysis_repository import NewAnalysis
from app.domain.interfaces.workflow_action_repository import WorkflowActionSaveOutcome
from app.domain.models.workflow import WorkflowAction
from app.infrastructure.storage.models import (
    Analysis,
    User,
    utc_now,
)
from app.infrastructure.storage.models import (
    WorkflowAction as WorkflowActionRow,
)
from app.infrastructure.storage.repositories.analysis import SqlAlchemyAnalysisRepository
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository
from app.infrastructure.storage.repositories.workflow_action import (
    SqlAlchemyWorkflowActionRepository,
)
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork

_ISSUER = "https://issuer.example.invalid/"
_PROPOSAL = "Thanks, I will review the report and respond by Friday."
_REPO_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "app"
    / "infrastructure"
    / "storage"
    / "repositories"
    / "workflow_action.py"
)


def _pending(
    owner_user_id: UUID,
    *,
    analysis_id: UUID | None = None,
    proposed_reply_body: str = _PROPOSAL,
) -> WorkflowAction:
    return WorkflowAction(
        action_type=WorkflowActionType.REPLY,
        analysis_id=analysis_id or uuid4(),
        owner_user_id=owner_user_id,
        proposed_reply_body=proposed_reply_body,
    )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _create_users(session_factory: sessionmaker) -> tuple[UUID, UUID]:
    with session_factory() as session:
        identities = SqlAlchemyIdentityRepository(session)
        user_a = identities.create_user_with_external_identity(_ISSUER, "owner-a")
        user_b = identities.create_user_with_external_identity(_ISSUER, "owner-b")
        session.commit()
    return user_a, user_b


def test_add_and_get_owned_round_trips_pending(session_factory: sessionmaker) -> None:
    """Creating a PENDING action should make the same UUID retrievable for the owner."""
    user_a, _user_b = _create_users(session_factory)
    analysis_id = uuid4()
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        created = repository.add(_pending(user_a, analysis_id=analysis_id))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        found = repository.get_owned(created.id, user_a)
        assert found is not None
        assert found.id == created.id
        assert found.analysis_id == analysis_id
        assert found.owner_user_id == user_a
        assert found.status is WorkflowActionStatus.PENDING
        assert found.proposed_reply_body == _PROPOSAL
        assert found.approved_reply_body is None
        assert _aware(found.created_at) == _aware(created.created_at)


def test_get_requires_matching_user_id(session_factory: sessionmaker) -> None:
    """get_owned must not return another user's workflow action."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        owned = repository.add(_pending(user_a))
        session.commit()
        action_id = owned.id

    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        assert repository.get_owned(action_id, user_a) is not None
        assert repository.get_owned(action_id, user_b) is None
        assert repository.get_owned(uuid4(), user_a) is None


def test_list_owned_excludes_other_users_and_is_newest_first(
    session_factory: sessionmaker,
) -> None:
    """Each user should see only their own actions, newest first."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        first = repository.add(_pending(user_a, proposed_reply_body="First proposal"))
        session.commit()
        second = repository.add(_pending(user_a, proposed_reply_body="Second proposal"))
        session.commit()
        other = repository.add(_pending(user_b, proposed_reply_body="Other proposal"))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        owned_a = repository.list_owned(user_a, limit=20, offset=0)
        owned_b = repository.list_owned(user_b, limit=20, offset=0)
        empty = repository.list_owned(user_a, limit=0, offset=0)

    assert [item.id for item in owned_a] == [second.id, first.id]
    assert [item.id for item in owned_b] == [other.id]
    assert empty == []


def test_save_owned_approves_when_expected_status_matches(
    session_factory: sessionmaker,
) -> None:
    """Conditional update persists APPROVED fields when the row is still PENDING."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        created = repository.add(_pending(user_a))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        loaded = repository.get_owned(created.id, user_a)
        assert loaded is not None
        loaded.approve()
        result = repository.save_owned(loaded, expected_status=WorkflowActionStatus.PENDING)
        session.commit()

    assert result.outcome is WorkflowActionSaveOutcome.SUCCESS
    assert result.action is not None
    assert result.action.status is WorkflowActionStatus.APPROVED
    assert result.action.approved_reply_body == _PROPOSAL
    assert result.action.proposed_reply_body == _PROPOSAL
    assert result.action.approved_at is not None


def test_save_owned_conflict_when_status_changed(
    session_factory: sessionmaker,
) -> None:
    """A second PENDING expected-status write is a conflict after approval."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        created = repository.add(_pending(user_a))
        created.approve()
        first = repository.save_owned(created, expected_status=WorkflowActionStatus.PENDING)
        session.commit()
        assert first.outcome is WorkflowActionSaveOutcome.SUCCESS

        stale = repository.get_owned(created.id, user_a)
        assert stale is not None
        conflict = repository.save_owned(stale, expected_status=WorkflowActionStatus.PENDING)
        assert conflict.outcome is WorkflowActionSaveOutcome.CONFLICT
        assert conflict.action is None


def test_save_owned_not_found_for_unknown_or_cross_user(
    session_factory: sessionmaker,
) -> None:
    """Zero-row updates for missing or foreign rows are not-found, not conflict."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        created = repository.add(_pending(user_a))
        session.commit()
        missing = repository.save_owned(
            WorkflowAction(
                id=uuid4(),
                action_type=WorkflowActionType.REPLY,
                analysis_id=uuid4(),
                owner_user_id=user_a,
                proposed_reply_body=_PROPOSAL,
            ),
            expected_status=WorkflowActionStatus.PENDING,
        )
        foreign = WorkflowAction(
            id=created.id,
            action_type=WorkflowActionType.REPLY,
            analysis_id=created.analysis_id,
            owner_user_id=user_b,
            proposed_reply_body=_PROPOSAL,
        )
        cross = repository.save_owned(foreign, expected_status=WorkflowActionStatus.PENDING)

    assert missing.outcome is WorkflowActionSaveOutcome.NOT_FOUND
    assert cross.outcome is WorkflowActionSaveOutcome.NOT_FOUND


def test_round_trip_every_valid_status(session_factory: sessionmaker) -> None:
    """Every lifecycle status survives persistence and validated rehydrate."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        action = repository.add(_pending(user_a))
        action.approve()
        approved = repository.save_owned(action, expected_status=WorkflowActionStatus.PENDING)
        assert approved.action is not None
        approved.action.mark_executing()
        executing = repository.save_owned(
            approved.action,
            expected_status=WorkflowActionStatus.APPROVED,
        )
        assert executing.action is not None
        executing.action.mark_executed()
        executed = repository.save_owned(
            executing.action,
            expected_status=WorkflowActionStatus.EXECUTING,
        )
        session.commit()

    assert executed.action is not None
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        loaded = repository.get_owned(executed.action.id, user_a)
        assert loaded is not None
        assert loaded.status is WorkflowActionStatus.EXECUTED
        assert loaded.proposed_reply_body == _PROPOSAL
        assert loaded.approved_reply_body == _PROPOSAL
        assert loaded.approved_at is not None
        assert loaded.executed_at is not None
        assert loaded.failed_at is None
        assert loaded.rejected_at is None

    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        failed_source = repository.add(_pending(user_a, proposed_reply_body="Fail path"))
        failed_source.approve()
        repository.save_owned(failed_source, expected_status=WorkflowActionStatus.PENDING)
        failed_source.mark_executing()
        repository.save_owned(failed_source, expected_status=WorkflowActionStatus.APPROVED)
        failed_source.mark_failed()
        failed = repository.save_owned(
            failed_source,
            expected_status=WorkflowActionStatus.EXECUTING,
        )
        session.commit()

    assert failed.action is not None
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        loaded_failed = repository.get_owned(failed.action.id, user_a)
        loaded_rejected_source = repository.add(_pending(user_a, proposed_reply_body="Reject"))
        loaded_rejected_source.reject()
        rejected = repository.save_owned(
            loaded_rejected_source,
            expected_status=WorkflowActionStatus.PENDING,
        )
        session.commit()

    assert loaded_failed is not None
    assert loaded_failed.status is WorkflowActionStatus.FAILED
    assert loaded_failed.failed_at is not None
    assert loaded_failed.executed_at is None
    assert rejected.action is not None
    assert rejected.action.status is WorkflowActionStatus.REJECTED
    assert rejected.action.proposed_reply_body == "Reject"
    assert rejected.action.approved_reply_body is None


def test_corrupt_row_fails_closed(session_factory: sessionmaker) -> None:
    """Stored lifecycle combinations that violate domain invariants raise PersistenceError."""
    user_a, _user_b = _create_users(session_factory)
    action_id = uuid4()
    with session_factory() as session:
        session.add(
            WorkflowActionRow(
                id=action_id,
                user_id=user_a,
                analysis_id=uuid4(),
                action_type="reply",
                status="approved",
                proposed_reply_body=_PROPOSAL,
                approved_reply_body=None,
                created_at=utc_now(),
            )
        )
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        with pytest.raises(PersistenceError) as exc_info:
            repository.get_owned(action_id, user_a)
        assert exc_info.value.message == "Stored workflow action is invalid."
        assert "SELECT" not in str(exc_info.value)
        assert _PROPOSAL not in str(exc_info.value)


def test_analysis_delete_leaves_workflow_action(session_factory: sessionmaker) -> None:
    """Hard-deleting an analysis must not remove or alter the workflow action."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        analyses = SqlAlchemyAnalysisRepository(session)
        stored_analysis = analyses.save(
            NewAnalysis(
                user_id=user_a,
                provider="mock",
                priority="medium",
                category="general",
                source_type="email",
                summary_text="Status summary",
                action_items=[],
                draft_reply={"body": _PROPOSAL},
            )
        )
        repository = SqlAlchemyWorkflowActionRepository(session)
        created = repository.add(_pending(user_a, analysis_id=stored_analysis.id))
        session.commit()
        analysis_id = stored_analysis.id
        action_id = created.id

    with session_factory() as session:
        analyses = SqlAlchemyAnalysisRepository(session)
        assert analyses.delete_for_user(analysis_id, user_a) is True
        session.commit()
        remaining_analyses = session.scalars(
            select(Analysis).where(Analysis.id == analysis_id)
        ).all()
        assert remaining_analyses == []
        repository = SqlAlchemyWorkflowActionRepository(session)
        remaining = repository.get_owned(action_id, user_a)
        assert remaining is not None
        assert remaining.analysis_id == analysis_id
        assert remaining.proposed_reply_body == _PROPOSAL
        remaining.approve()
        result = repository.save_owned(
            remaining,
            expected_status=WorkflowActionStatus.PENDING,
        )
        session.commit()

    assert result.outcome is WorkflowActionSaveOutcome.SUCCESS
    assert result.action is not None
    assert result.action.approved_reply_body == _PROPOSAL


def test_no_analysis_foreign_key(sqlite_engine: Engine) -> None:
    """workflow_actions.analysis_id must not reference analyses.id."""
    inspector = inspect(sqlite_engine)
    fks = inspector.get_foreign_keys("workflow_actions")
    assert all(fk["referred_table"] != "analyses" for fk in fks)
    assert all("analysis_id" not in fk["constrained_columns"] for fk in fks)


def test_deleting_user_cascades_workflow_actions(session_factory: sessionmaker) -> None:
    """SQLite FK enforcement should remove workflow actions when the user is deleted."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        saved = repository.add(_pending(user_a))
        session.commit()
        action_id = saved.id

        user = session.get(User, user_a)
        assert user is not None
        session.delete(user)
        session.commit()

        remaining = session.scalars(
            select(WorkflowActionRow).where(WorkflowActionRow.id == action_id)
        ).all()
        assert remaining == []
        assert repository.get_owned(action_id, user_a) is None


def test_uow_exposes_workflow_actions_and_does_not_autocommit(
    session_factory: sessionmaker,
) -> None:
    """Workflow writes follow the same unit-of-work commit rules."""
    user_a, _user_b = _create_users(session_factory)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        created = uow.workflow_actions.add(_pending(user_a))
        uow.commit()

    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        assert repository.get_owned(created.id, user_a) is not None

    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        uow.workflow_actions.add(_pending(user_a, proposed_reply_body="Uncommitted"))

    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        listed = repository.list_owned(user_a, limit=20, offset=0)
        assert [item.id for item in listed] == [created.id]


def test_status_and_action_type_checks_reject_unknown_values(
    session_factory: sessionmaker,
) -> None:
    """SQL membership checks reject unsupported action types and statuses."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO workflow_actions "
                    "(id, user_id, analysis_id, action_type, status, proposed_reply_body, "
                    "created_at) VALUES (:id, :user_id, :analysis_id, :action_type, "
                    "'pending', :proposal, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid4()),
                    "user_id": str(user_a),
                    "analysis_id": str(uuid4()),
                    "action_type": "calendar_event",
                    "proposal": _PROPOSAL,
                },
            )
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO workflow_actions "
                    "(id, user_id, analysis_id, action_type, status, proposed_reply_body, "
                    "created_at) VALUES (:id, :user_id, :analysis_id, 'reply', "
                    ":status, :proposal, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid4()),
                    "user_id": str(user_a),
                    "analysis_id": str(uuid4()),
                    "status": "execution_unknown",
                    "proposal": _PROPOSAL,
                },
            )
            session.commit()


def test_ownership_is_enforced_in_sql() -> None:
    """Get, list, and save must filter user_id in SQL, not after fetch."""
    source = _REPO_SOURCE.read_text(encoding="utf-8")
    assert "session.get(" not in source
    assert "WorkflowActionRow.user_id == user_id" in source
    assert "WorkflowActionRow.user_id == action.owner_user_id" in source
    assert "row.user_id !=" not in source

"""PostgreSQL workflow action schema, ownership, cascade, and constraint tests."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, inspect, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.domain.enums import WorkflowActionStatus, WorkflowActionType
from app.domain.interfaces.analysis_repository import NewAnalysis
from app.domain.interfaces.workflow_action_repository import WorkflowActionSaveOutcome
from app.domain.models.workflow import WorkflowAction
from app.infrastructure.storage.models import (
    Analysis,
    User,
)
from app.infrastructure.storage.models import (
    WorkflowAction as WorkflowActionRow,
)
from app.infrastructure.storage.repositories.analysis import SqlAlchemyAnalysisRepository
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository
from app.infrastructure.storage.repositories.workflow_action import (
    SqlAlchemyWorkflowActionRepository,
)

_ISSUER = "https://issuer.example.invalid/"
_PROPOSAL = "Thanks, I will review the report and respond by Friday."
_FORBIDDEN_COLUMNS = frozenset(
    {
        "body",
        "raw_body",
        "message_body",
        "email_body",
        "subject",
        "subject_line",
        "sender",
        "recipient",
        "recipients",
        "token",
        "access_token",
        "refresh_token",
        "jwt",
        "credential",
        "credential_ref",
    }
)


def _pending(owner_user_id: UUID, *, analysis_id: UUID | None = None) -> WorkflowAction:
    return WorkflowAction(
        action_type=WorkflowActionType.REPLY,
        analysis_id=analysis_id or uuid4(),
        owner_user_id=owner_user_id,
        proposed_reply_body=_PROPOSAL,
    )


def _create_users(session_factory: sessionmaker) -> tuple[UUID, UUID]:
    with session_factory() as session:
        identities = SqlAlchemyIdentityRepository(session)
        user_a = identities.create_user_with_external_identity(_ISSUER, "owner-a")
        user_b = identities.create_user_with_external_identity(_ISSUER, "owner-b")
        session.commit()
    return user_a, user_b


def test_workflow_actions_table_exists(postgres_engine: Engine) -> None:
    """workflow_actions is present and the forbidden generic table is not."""
    tables = set(inspect(postgres_engine).get_table_names())
    assert "workflow_actions" in tables
    assert "workflows" not in tables


def test_workflow_action_column_types(postgres_engine: Engine) -> None:
    """UUID, timestamptz, and TEXT action/status columns match the intended schema."""
    types = _udt_types(postgres_engine)
    assert types[("workflow_actions", "id")] == "uuid"
    assert types[("workflow_actions", "user_id")] == "uuid"
    assert types[("workflow_actions", "analysis_id")] == "uuid"
    assert types[("workflow_actions", "created_at")] == "timestamptz"
    assert types[("workflow_actions", "approved_at")] == "timestamptz"
    assert types[("workflow_actions", "rejected_at")] == "timestamptz"
    assert types[("workflow_actions", "executed_at")] == "timestamptz"
    assert types[("workflow_actions", "failed_at")] == "timestamptz"
    assert types[("workflow_actions", "action_type")] == "text"
    assert types[("workflow_actions", "status")] == "text"
    assert types[("workflow_actions", "proposed_reply_body")] == "text"
    assert types[("workflow_actions", "approved_reply_body")] == "text"
    inspector = inspect(postgres_engine)
    columns = {
        column["name"]: column["nullable"]
        for column in inspector.get_columns("workflow_actions")
    }
    assert columns["proposed_reply_body"] is False
    assert columns["approved_reply_body"] is True
    assert columns["analysis_id"] is False
    assert columns["user_id"] is False
    assert set(columns).isdisjoint(_FORBIDDEN_COLUMNS)
    assert "proposed_reply_body" in columns
    assert "approved_reply_body" in columns
    assert "body" not in columns
    assert "updated_at" not in columns


def test_user_foreign_key_cascades(postgres_engine: Engine) -> None:
    """workflow_actions.user_id references users.id with ON DELETE CASCADE."""
    inspector = inspect(postgres_engine)
    fks = inspector.get_foreign_keys("workflow_actions")
    assert any(
        fk["referred_table"] == "users"
        and fk["constrained_columns"] == ["user_id"]
        and str((fk.get("options") or {}).get("ondelete", "")).upper() == "CASCADE"
        for fk in fks
    )


def test_no_analysis_foreign_key(postgres_engine: Engine) -> None:
    """analysis_id is provenance only and must not reference analyses."""
    inspector = inspect(postgres_engine)
    fks = inspector.get_foreign_keys("workflow_actions")
    assert all(fk["referred_table"] != "analyses" for fk in fks)
    assert all("analysis_id" not in fk["constrained_columns"] for fk in fks)


def test_check_constraints_and_list_index(postgres_engine: Engine) -> None:
    """Action type and status are constrained; the ownership list index exists."""
    inspector = inspect(postgres_engine)
    checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("workflow_actions")
    }
    assert "ck_workflow_actions_action_type" in checks
    assert "ck_workflow_actions_status" in checks
    indexes = {index["name"] for index in inspector.get_indexes("workflow_actions")}
    assert "ix_workflow_actions_user_id_created_at_id" in indexes


def test_create_lookup_ownership_and_python_uuid(session_factory: sessionmaker) -> None:
    """PostgreSQL UUID columns round-trip and ownership is enforced in SQL."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        created = repository.add(_pending(user_a))
        session.commit()

    assert isinstance(created.id, UUID)
    assert created.created_at.tzinfo is not None

    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        owned = repository.get_owned(created.id, user_a)
        assert owned is not None
        assert owned.id == created.id
        assert owned.proposed_reply_body == _PROPOSAL
        assert repository.get_owned(created.id, user_b) is None
        assert repository.list_owned(user_b, limit=20, offset=0) == []


def test_proposal_and_approved_body_persist(session_factory: sessionmaker) -> None:
    """Proposed and approved snapshots survive PostgreSQL round-trip."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        created = repository.add(_pending(user_a))
        created.approve()
        result = repository.save_owned(created, expected_status=WorkflowActionStatus.PENDING)
        session.commit()

    assert result.action is not None
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        loaded = repository.get_owned(result.action.id, user_a)
        assert loaded is not None
        assert loaded.proposed_reply_body == _PROPOSAL
        assert loaded.approved_reply_body == _PROPOSAL
        assert loaded.approved_at is not None
        assert loaded.approved_at.tzinfo is not None


def test_conditional_update_rowcount_conflict(session_factory: sessionmaker) -> None:
    """A second PENDING update affects zero rows and is classified as conflict."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        created = repository.add(_pending(user_a))
        created.approve()
        first = repository.save_owned(created, expected_status=WorkflowActionStatus.PENDING)
        session.commit()
        assert first.outcome is WorkflowActionSaveOutcome.SUCCESS

        result = session.execute(
            update(WorkflowActionRow)
            .where(
                WorkflowActionRow.id == created.id,
                WorkflowActionRow.user_id == user_a,
                WorkflowActionRow.status == WorkflowActionStatus.PENDING.value,
            )
            .values(status=WorkflowActionStatus.REJECTED.value)
        )
        assert result.rowcount == 0
        conflict = repository.save_owned(created, expected_status=WorkflowActionStatus.PENDING)
        assert conflict.outcome is WorkflowActionSaveOutcome.CONFLICT


def test_check_constraints_reject_unknown_values(session_factory: sessionmaker) -> None:
    """PostgreSQL CHECK constraints reject unsupported action types and statuses."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO workflow_actions "
                    "(id, user_id, analysis_id, action_type, status, proposed_reply_body, "
                    "created_at) VALUES (:id, :user_id, :analysis_id, 'calendar_event', "
                    "'pending', :proposal, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid4()),
                    "user_id": str(user_a),
                    "analysis_id": str(uuid4()),
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
                    "'execution_unknown', :proposal, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid4()),
                    "user_id": str(user_a),
                    "analysis_id": str(uuid4()),
                    "proposal": _PROPOSAL,
                },
            )
            session.commit()


def test_analysis_delete_leaves_workflow_action(session_factory: sessionmaker) -> None:
    """Deleting an analysis must leave the workflow row and its proposal intact."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        analyses = SqlAlchemyAnalysisRepository(session)
        stored = analyses.save(
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
        created = repository.add(_pending(user_a, analysis_id=stored.id))
        session.commit()
        analysis_id = stored.id
        action_id = created.id

        assert analyses.delete_for_user(analysis_id, user_a) is True
        session.commit()
        assert session.scalars(select(Analysis).where(Analysis.id == analysis_id)).all() == []
        remaining = repository.get_owned(action_id, user_a)
        assert remaining is not None
        assert remaining.analysis_id == analysis_id
        assert remaining.proposed_reply_body == _PROPOSAL
        remaining.approve()
        result = repository.save_owned(remaining, expected_status=WorkflowActionStatus.PENDING)
        session.commit()

    assert result.outcome is WorkflowActionSaveOutcome.SUCCESS
    assert result.action is not None
    assert result.action.approved_reply_body == _PROPOSAL


def test_deleting_user_cascades_workflow_actions(session_factory: sessionmaker) -> None:
    """PostgreSQL ON DELETE CASCADE must remove workflow action rows."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        created = repository.add(_pending(user_a))
        session.commit()
        session.execute(delete(User).where(User.id == user_a))
        session.commit()
        remaining = session.scalars(
            select(WorkflowActionRow).where(WorkflowActionRow.id == created.id)
        ).all()
        assert remaining == []


def test_orphan_analysis_id_is_allowed(session_factory: sessionmaker) -> None:
    """An analysis_id with no matching analyses row is valid provenance."""
    user_a, _user_b = _create_users(session_factory)
    missing_analysis_id = uuid4()
    with session_factory() as session:
        repository = SqlAlchemyWorkflowActionRepository(session)
        created = repository.add(_pending(user_a, analysis_id=missing_analysis_id))
        session.commit()
        loaded = repository.get_owned(created.id, user_a)
        assert loaded is not None
        assert loaded.analysis_id == missing_analysis_id
        count = session.scalar(select(func.count()).select_from(Analysis))
        assert count == 0


def _udt_types(engine: Engine) -> dict[tuple[str, str], str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT table_name, column_name, udt_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'workflow_actions'
                """
            )
        ).all()
    return {(row.table_name, row.column_name): row.udt_name for row in rows}

"""PostgreSQL attachment-analysis ownership, JSONB, cascade, and isolation."""

from uuid import UUID, uuid4

from sqlalchemy import inspect, select
from sqlalchemy.orm import sessionmaker

from app.domain.interfaces.attachment_analysis_repository import NewAttachmentAnalysis
from app.infrastructure.storage.models import AttachmentAnalysisRow, User
from app.infrastructure.storage.repositories.attachment_analysis import (
    SqlAlchemyAttachmentAnalysisRepository,
)
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository

_ISSUER = "https://issuer.example.invalid/"


def _new_row(
    user_id: UUID,
    *,
    summary_text: str = "Attachment summary",
    connector_account_id: UUID | None = None,
    provider_message_id: str = "msg-1",
    truncated: bool = False,
    warnings: list[str] | None = None,
) -> NewAttachmentAnalysis:
    return NewAttachmentAnalysis(
        user_id=user_id,
        connector_account_id=connector_account_id or uuid4(),
        provider_message_id=provider_message_id,
        provider_attachment_id="att-1",
        filename="notes.txt",
        media_type="text/plain",
        kind="txt",
        extracted_content_status="text",
        truncated=truncated,
        warnings=warnings if warnings is not None else ["bounded"],
        summary_text=summary_text,
        summary_confidence=0.8,
        priority="medium",
        category="general",
        action_items=[{"description": "Review the attachment"}],
        provider="mock",
        character_count=12,
    )


def _create_users(session_factory: sessionmaker) -> tuple[UUID, UUID]:
    with session_factory() as session:
        identities = SqlAlchemyIdentityRepository(session)
        user_a = identities.create_user_with_external_identity(_ISSUER, "owner-a")
        user_b = identities.create_user_with_external_identity(_ISSUER, "owner-b")
        session.commit()
    return user_a, user_b


def test_postgres_owner_isolation_and_filters(session_factory: sessionmaker) -> None:
    """PostgreSQL list/get honor owner and bounded connector/message filters."""
    user_a, user_b = _create_users(session_factory)
    connector_a = uuid4()
    with session_factory() as session:
        repository = SqlAlchemyAttachmentAnalysisRepository(session)
        first = repository.save(
            _new_row(user_a, summary_text="Alpha one", connector_account_id=connector_a)
        )
        session.commit()
        second = repository.save(
            _new_row(
                user_a,
                summary_text="Alpha two",
                connector_account_id=connector_a,
                provider_message_id="msg-2",
                truncated=True,
                warnings=["hit_character_bound"],
            )
        )
        session.commit()
        repository.save(_new_row(user_b, summary_text="Beta one"))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyAttachmentAnalysisRepository(session)
        owned_a = repository.list_for_user(user_a, limit=20, offset=0)
        owned_b = repository.list_for_user(user_b, limit=20, offset=0)
        filtered = repository.list_for_user(
            user_a,
            limit=20,
            offset=0,
            connector_account_id=connector_a,
            provider_message_id="msg-2",
        )
        assert repository.get_by_id_for_user(first.id, user_b) is None
        loaded = repository.get_by_id_for_user(second.id, user_a)

    assert [record.id for record in owned_a] == [second.id, first.id]
    assert len(owned_b) == 1
    assert [record.id for record in filtered] == [second.id]
    assert loaded is not None
    assert loaded.truncated is True
    assert loaded.warnings == ["hit_character_bound"]
    assert loaded.action_items == [{"description": "Review the attachment"}]


def test_postgres_user_delete_cascades(session_factory: sessionmaker) -> None:
    """User delete cascades attachment analyses on PostgreSQL."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAttachmentAnalysisRepository(session)
        saved = repository.save(_new_row(user_a))
        session.commit()
        row_id = saved.id
        user = session.get(User, user_a)
        assert user is not None
        session.delete(user)
        session.commit()
        remaining = session.scalars(
            select(AttachmentAnalysisRow).where(AttachmentAnalysisRow.id == row_id)
        ).all()
        assert remaining == []


def test_postgres_table_has_no_content_columns(postgres_engine) -> None:
    """PostgreSQL attachment_analyses stores structured result columns only."""
    columns = {
        column["name"] for column in inspect(postgres_engine).get_columns("attachment_analyses")
    }
    assert "content" not in columns
    assert "extracted_text" not in columns
    assert "draft_reply" not in columns
    workflow_fks = inspect(postgres_engine).get_foreign_keys("workflow_actions")
    assert all(fk["referred_table"] != "attachment_analyses" for fk in workflow_fks)

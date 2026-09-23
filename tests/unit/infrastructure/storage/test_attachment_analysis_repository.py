"""Attachment-analysis repository ownership and cascade tests using SQLite."""

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import PersistenceError
from app.domain.interfaces.attachment_analysis_repository import NewAttachmentAnalysis
from app.domain.schemas import TabularAnalysisResult
from app.infrastructure.storage.models import AttachmentAnalysisRow, User, WorkflowAction
from app.infrastructure.storage.repositories.attachment_analysis import (
    SqlAlchemyAttachmentAnalysisRepository,
)
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository

_ISSUER = "https://issuer.example.invalid/"


def test_complete_tabular_result_roundtrip(session_factory):
    user_id, other_id = _create_users(session_factory)
    result = TabularAnalysisResult(
        summary="Budget sample",
        sheet_summaries=[{"sheet_name": "Budget", "summary": "Quoted totals"}],
        important_fields=["Amount"],
        notable_values_or_patterns=["Two totals"],
        data_quality_observations=["Currency not specified"],
        potential_dates=["2030-01-01"],
        potential_amounts=["42"],
        potential_action_mentions=["Review totals"],
        warnings=["Formula text is inert"],
        limitations=["Sample only"],
        source_truncated=True,
        provider="mock",
    )
    with session_factory() as session:
        repo = SqlAlchemyAttachmentAnalysisRepository(session)
        saved = repo.save(replace(_new_row(user_id), kind="xlsx", tabular_result=result))
        session.commit()
    with session_factory() as session:
        repo = SqlAlchemyAttachmentAnalysisRepository(session)
        loaded = repo.get_by_id_for_user(saved.id, user_id)
        assert isinstance(loaded.tabular_result, TabularAnalysisResult)
        assert loaded.tabular_result.model_dump() == result.model_dump()
        assert repo.list_for_user(user_id, 20, 0)[0].tabular_result == result
        assert repo.get_by_id_for_user(saved.id, other_id) is None


def test_corrupt_tabular_json_is_not_trusted_on_read(session_factory):
    user_id, _ = _create_users(session_factory)
    secret = "PRIVATE_CORRUPT_WORKBOOK_CONTENT"
    with session_factory() as session:
        repo = SqlAlchemyAttachmentAnalysisRepository(session)
        saved = repo.save(replace(_new_row(user_id), kind="xlsx"))
        row = session.get(AttachmentAnalysisRow, saved.id)
        row.tabular_result = {"summary": "Allowed", "raw_workbook": secret}
        session.commit()
    with session_factory() as session:
        repo = SqlAlchemyAttachmentAnalysisRepository(session)
        for read in (
            lambda: repo.get_by_id_for_user(saved.id, user_id),
            lambda: repo.list_for_user(user_id, 20, 0),
        ):
            with pytest.raises(PersistenceError) as error:
                read()
            assert secret not in str(error.value)


def test_unbounded_tabular_result_is_rejected_before_insert(session_factory):
    user_id, _ = _create_users(session_factory)
    result = TabularAnalysisResult(summary="Bounded").model_copy(
        update={"potential_dates": ["x" * 201]}
    )
    with session_factory() as session:
        repo = SqlAlchemyAttachmentAnalysisRepository(session)
        with pytest.raises(PersistenceError):
            repo.save(replace(_new_row(user_id), kind="xlsx", tabular_result=result))
        assert repo.list_for_user(user_id, 20, 0) == []


def _new_row(
    user_id: UUID,
    *,
    summary_text: str = "Attachment summary",
    connector_account_id: UUID | None = None,
    provider_message_id: str = "msg-1",
    provider_attachment_id: str = "att-1",
    truncated: bool = False,
    warnings: list[str] | None = None,
) -> NewAttachmentAnalysis:
    return NewAttachmentAnalysis(
        user_id=user_id,
        connector_account_id=connector_account_id or uuid4(),
        provider_message_id=provider_message_id,
        provider_attachment_id=provider_attachment_id,
        filename="notes.txt",
        media_type="text/plain",
        kind="txt",
        extracted_content_status="text",
        truncated=truncated,
        warnings=warnings if warnings is not None else ["truncated_text"],
        summary_text=summary_text,
        summary_confidence=0.8,
        priority="medium",
        category="general",
        action_items=[{"description": "Review the attachment"}],
        provider="mock",
        page_count=None,
        character_count=12,
    )


def _create_users(session_factory: sessionmaker) -> tuple[UUID, UUID]:
    with session_factory() as session:
        identities = SqlAlchemyIdentityRepository(session)
        user_a = identities.create_user_with_external_identity(_ISSUER, "owner-a")
        user_b = identities.create_user_with_external_identity(_ISSUER, "owner-b")
        session.commit()
    return user_a, user_b


def test_owner_lists_only_owned_rows(session_factory: sessionmaker) -> None:
    """User A must not see user B attachment analyses."""
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
            )
        )
        session.commit()
        other = repository.save(_new_row(user_b, summary_text="Beta one"))
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

    assert [record.id for record in owned_a] == [second.id, first.id]
    assert [record.id for record in owned_b] == [other.id]
    assert [record.id for record in filtered] == [second.id]


def test_get_requires_matching_user_id(session_factory: sessionmaker) -> None:
    """Unknown and cross-user ids are indistinguishable Nones."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAttachmentAnalysisRepository(session)
        owned = repository.save(_new_row(user_a))
        session.commit()
        row_id = owned.id

    with session_factory() as session:
        repository = SqlAlchemyAttachmentAnalysisRepository(session)
        assert repository.get_by_id_for_user(row_id, user_a) is not None
        assert repository.get_by_id_for_user(row_id, user_b) is None
        assert repository.get_by_id_for_user(uuid4(), user_a) is None


def test_structured_fields_round_trip(session_factory: sessionmaker) -> None:
    """Truncation and warnings persist without extracted text or bytes."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAttachmentAnalysisRepository(session)
        stored = repository.save(
            _new_row(user_a, truncated=True, warnings=["hit_character_bound"])
        )
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyAttachmentAnalysisRepository(session)
        loaded = repository.get_by_id_for_user(stored.id, user_a)

    assert loaded is not None
    assert loaded.truncated is True
    assert loaded.warnings == ["hit_character_bound"]
    assert loaded.summary_text == "Attachment summary"
    assert loaded.character_count == 12
    assert not hasattr(loaded, "extracted_text")
    assert not hasattr(loaded, "content")


def test_schema_excludes_raw_and_extracted_columns(sqlite_engine) -> None:
    """The table must not have content or extracted-text columns."""
    columns = {
        column["name"] for column in inspect(sqlite_engine).get_columns("attachment_analyses")
    }
    assert "content" not in columns
    assert "content_bytes" not in columns
    assert "extracted_text" not in columns
    assert "draft_reply" not in columns
    assert "raw_bytes" not in columns


def test_no_workflow_foreign_key(sqlite_engine) -> None:
    """workflow_actions must not reference attachment_analyses."""
    inspector = inspect(sqlite_engine)
    workflow_fks = inspector.get_foreign_keys("workflow_actions")
    attachment_fks = inspector.get_foreign_keys("attachment_analyses")
    assert all(fk["referred_table"] != "attachment_analyses" for fk in workflow_fks)
    assert all(fk["referred_table"] != "workflow_actions" for fk in attachment_fks)
    assert WorkflowAction.__table__.c.analysis_id.foreign_keys == set()


def test_deleting_user_cascades_attachment_analyses(session_factory: sessionmaker) -> None:
    """Deleting a user removes owned attachment analyses."""
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

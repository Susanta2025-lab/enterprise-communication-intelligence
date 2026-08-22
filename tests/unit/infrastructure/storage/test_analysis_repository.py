"""Analysis repository ownership, JSON, and cascade tests using SQLite."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.domain.interfaces.analysis_repository import NewAnalysis
from app.infrastructure.storage.models import Analysis, User
from app.infrastructure.storage.repositories.analysis import SqlAlchemyAnalysisRepository
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository

_ISSUER = "https://issuer.example.invalid/"


def _new_analysis(
    user_id: UUID,
    *,
    summary_text: str = "Status summary",
    action_items: list[dict] | None = None,
    draft_reply: dict | None = None,
    summary_confidence: float | None = 0.9,
    message_id: str | None = "msg-100",
    request_id: UUID | None = None,
    analysis_id: UUID | None = None,
    connector_account_id: UUID | None = None,
) -> NewAnalysis:
    return NewAnalysis(
        user_id=user_id,
        provider="mock",
        priority="medium",
        category="general",
        source_type="email",
        summary_text=summary_text,
        action_items=(
            action_items if action_items is not None else [{"description": "Review notes"}]
        ),
        request_id=request_id,
        message_id=message_id,
        summary_confidence=summary_confidence,
        draft_reply=draft_reply,
        analysis_id=analysis_id,
        connector_account_id=connector_account_id,
    )


def _create_users(session_factory: sessionmaker) -> tuple[UUID, UUID]:
    with session_factory() as session:
        identities = SqlAlchemyIdentityRepository(session)
        user_a = identities.create_user_with_external_identity(_ISSUER, "owner-a")
        user_b = identities.create_user_with_external_identity(_ISSUER, "owner-b")
        session.commit()
    return user_a, user_b


def test_owner_lists_only_owned_analyses(session_factory: sessionmaker) -> None:
    """Each user should see only their own analyses."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        first = repository.save(_new_analysis(user_a, summary_text="Alpha one"))
        session.commit()
        second = repository.save(_new_analysis(user_a, summary_text="Alpha two"))
        session.commit()
        other = repository.save(_new_analysis(user_b, summary_text="Beta one"))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        owned_a = repository.list_for_user(user_a, limit=20, offset=0)
        owned_b = repository.list_for_user(user_b, limit=20, offset=0)

    assert [record.id for record in owned_a] == [second.id, first.id]
    assert [record.summary_text for record in owned_a] == ["Alpha two", "Alpha one"]
    assert [record.id for record in owned_b] == [other.id]


def test_get_requires_matching_user_id(session_factory: sessionmaker) -> None:
    """get_by_id_for_user must not return another user's analysis."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        owned = repository.save(_new_analysis(user_a))
        session.commit()
        analysis_id = owned.id

    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        assert repository.get_by_id_for_user(analysis_id, user_a) is not None
        assert repository.get_by_id_for_user(analysis_id, user_b) is None
        assert repository.get_by_id_for_user(uuid4(), user_a) is None


def test_cross_user_delete_matches_unknown_and_does_not_remove(
    session_factory: sessionmaker,
) -> None:
    """Cross-user delete is indistinguishable from unknown and leaves the row."""
    user_a, user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        owned = repository.save(_new_analysis(user_a))
        session.commit()
        analysis_id = owned.id

    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        unknown = repository.delete_for_user(uuid4(), user_a)
        cross_user = repository.delete_for_user(analysis_id, user_b)
        session.commit()
        remaining = repository.get_by_id_for_user(analysis_id, user_a)

    assert unknown is False
    assert cross_user is False
    assert remaining is not None
    assert remaining.id == analysis_id


def test_owned_delete_removes_record(session_factory: sessionmaker) -> None:
    """An owner can delete their analysis."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        owned = repository.save(_new_analysis(user_a))
        session.commit()
        analysis_id = owned.id

    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        assert repository.delete_for_user(analysis_id, user_a) is True
        session.commit()
        assert repository.get_by_id_for_user(analysis_id, user_a) is None


def test_list_is_bounded_and_offset(session_factory: sessionmaker) -> None:
    """List must honor limit and offset."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        first = repository.save(_new_analysis(user_a, summary_text="First"))
        session.commit()
        second = repository.save(_new_analysis(user_a, summary_text="Second"))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        page = repository.list_for_user(user_a, limit=1, offset=0)
        rest = repository.list_for_user(user_a, limit=1, offset=1)

    assert [record.id for record in page] == [second.id]
    assert [record.id for record in rest] == [first.id]


def test_list_does_not_pass_invalid_limit_or_offset_to_sql(
    session_factory: sessionmaker,
) -> None:
    """Negative or empty pages must return no rows rather than unbounded SQL."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        repository.save(_new_analysis(user_a, summary_text="Kept"))
        session.commit()
        assert repository.list_for_user(user_a, limit=0, offset=0) == []
        assert repository.list_for_user(user_a, limit=-1, offset=0) == []
        assert repository.list_for_user(user_a, limit=20, offset=-1) == []
        assert len(repository.list_for_user(user_a, limit=20, offset=0)) == 1


def test_json_and_nullable_fields_round_trip(session_factory: sessionmaker) -> None:
    """JSON fragments and nullable columns must survive save/load."""
    user_a, _user_b = _create_users(session_factory)
    request_id = uuid4()
    action_items = [{"description": "Schedule follow-up", "priority": "high"}]
    draft_reply = {"body": "Thanks, I will review.", "tone": "professional"}

    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        stored = repository.save(
            _new_analysis(
                user_a,
                action_items=action_items,
                draft_reply=draft_reply,
                summary_confidence=0.42,
                message_id="msg-round-trip",
                request_id=request_id,
            )
        )
        nullish = repository.save(
            _new_analysis(
                user_a,
                action_items=[],
                draft_reply=None,
                summary_confidence=None,
                message_id=None,
                request_id=None,
            )
        )
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        loaded = repository.get_by_id_for_user(stored.id, user_a)
        loaded_null = repository.get_by_id_for_user(nullish.id, user_a)

    assert loaded is not None
    assert loaded.action_items == action_items
    assert loaded.draft_reply == draft_reply
    assert loaded.summary_confidence == pytest.approx(0.42)
    assert loaded.message_id == "msg-round-trip"
    assert loaded.request_id == request_id
    assert loaded.connector_account_id is None

    assert loaded_null is not None
    assert loaded_null.action_items == []
    assert loaded_null.draft_reply is None
    assert loaded_null.summary_confidence is None
    assert loaded_null.message_id is None
    assert loaded_null.request_id is None


def test_deleting_user_cascades_analyses(session_factory: sessionmaker) -> None:
    """Deleting a user should remove owned analyses when FKs are enforced."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        saved = repository.save(_new_analysis(user_a))
        session.commit()
        analysis_id = saved.id

        user = session.get(User, user_a)
        assert user is not None
        session.delete(user)
        session.commit()

        remaining = session.scalars(select(Analysis).where(Analysis.id == analysis_id)).all()
        assert remaining == []
        assert repository.get_by_id_for_user(analysis_id, user_a) is None


def test_connector_account_id_round_trips_without_foreign_key(
    session_factory: sessionmaker,
) -> None:
    """Mailbox provenance is stored as an opaque UUID, including unknown ids."""
    user_a, _user_b = _create_users(session_factory)
    orphan_account_id = uuid4()
    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        stored = repository.save(
            _new_analysis(user_a, connector_account_id=orphan_account_id)
        )
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        loaded = repository.get_by_id_for_user(stored.id, user_a)
        listed = repository.list_for_user(user_a, limit=20, offset=0)

    assert loaded is not None
    assert loaded.connector_account_id == orphan_account_id
    assert listed[0].connector_account_id == orphan_account_id

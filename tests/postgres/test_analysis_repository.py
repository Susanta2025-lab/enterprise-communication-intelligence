"""PostgreSQL analysis ownership, JSONB, DELETE rowcount, ordering, and cascade tests."""

from datetime import UTC
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from app.domain.interfaces.analysis_repository import NewAnalysis
from app.infrastructure.storage.models import Analysis, User
from app.infrastructure.storage.repositories.analysis import SqlAlchemyAnalysisRepository
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository

_ISSUER = "https://issuer.example.invalid/"


def _new_analysis(
    user_id: UUID,
    *,
    summary_text: str = "Synthetic status summary",
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
    """User A must not see user B analyses, and vice versa."""
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
    assert all(record.user_id == user_a for record in owned_a)
    assert all(record.user_id == user_b for record in owned_b)


def test_get_requires_matching_user_id(session_factory: sessionmaker) -> None:
    """A cannot get B; B cannot get A; unknown id is None."""
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


def test_delete_rowcount_owned_unknown_and_cross_user(session_factory: sessionmaker) -> None:
    """PostgreSQL DELETE rowcount: owned True, unknown False, cross-user False."""
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
        assert unknown is False
        assert cross_user is False
        remaining = repository.get_by_id_for_user(analysis_id, user_a)
        assert remaining is not None
        owned_deleted = repository.delete_for_user(analysis_id, user_a)
        assert owned_deleted is True
        session.commit()
        assert repository.get_by_id_for_user(analysis_id, user_a) is None


def test_list_ordering_created_at_desc_id_desc(session_factory: sessionmaker) -> None:
    """Listing remains created_at DESC, id DESC on PostgreSQL."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        first = repository.save(_new_analysis(user_a, summary_text="First"))
        session.commit()
        second = repository.save(_new_analysis(user_a, summary_text="Second"))
        session.commit()
        third = repository.save(_new_analysis(user_a, summary_text="Third"))
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        listed = repository.list_for_user(user_a, limit=20, offset=0)

    assert [record.id for record in listed] == [third.id, second.id, first.id]
    created = [record.created_at for record in listed]
    assert created == sorted(created, reverse=True)
    assert all(moment.tzinfo is not None for moment in created)
    assert all(moment.tzinfo == UTC or moment.utcoffset() is not None for moment in created)


def test_jsonb_list_object_and_null_round_trip(session_factory: sessionmaker) -> None:
    """JSONB list, object, and null draft_reply round-trip as Python values."""
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
    assert isinstance(loaded.id, UUID)
    assert isinstance(loaded.user_id, UUID)
    assert isinstance(loaded.request_id, UUID)
    assert loaded.request_id == request_id
    assert loaded.action_items == action_items
    assert loaded.draft_reply == draft_reply
    assert loaded.created_at.tzinfo is not None

    assert loaded_null is not None
    assert loaded_null.action_items == []
    assert loaded_null.draft_reply is None
    assert loaded_null.request_id is None


def test_deleting_user_cascades_analyses(session_factory: sessionmaker) -> None:
    """PostgreSQL ON DELETE CASCADE must remove owned analyses."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        saved = repository.save(_new_analysis(user_a))
        session.commit()
        analysis_id = saved.id

        session.execute(delete(User).where(User.id == user_a))
        session.commit()

        remaining = session.scalars(select(Analysis).where(Analysis.id == analysis_id)).all()
        assert remaining == []
        assert repository.get_by_id_for_user(analysis_id, user_a) is None


def test_analysis_does_not_store_raw_message_or_tokens(session_factory: sessionmaker) -> None:
    """Stored analysis records expose no raw body, sender, recipients, or tokens."""
    user_a, _user_b = _create_users(session_factory)
    with session_factory() as session:
        repository = SqlAlchemyAnalysisRepository(session)
        stored = repository.save(_new_analysis(user_a))
        session.commit()
        loaded = repository.get_by_id_for_user(stored.id, user_a)

    assert loaded is not None
    assert not hasattr(loaded, "raw_body")
    assert not hasattr(loaded, "sender")
    assert not hasattr(loaded, "recipients")
    assert not hasattr(loaded, "access_token")
    assert not hasattr(loaded, "refresh_token")
    assert not hasattr(loaded, "email")
    assert "Authorization" not in loaded.summary_text


def test_connector_account_id_round_trips(session_factory: sessionmaker) -> None:
    """PostgreSQL stores nullable mailbox provenance without a connector FK."""
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

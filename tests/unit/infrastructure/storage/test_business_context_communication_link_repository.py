"""BusinessContext communication-link repository tests using isolated SQLite."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import PersistenceError
from app.domain.enums import (
    AssociationSource,
    BusinessContextType,
    CommunicationCapability,
)
from app.domain.interfaces.analysis_repository import NewAnalysis
from app.domain.interfaces.connector_account_repository import NewConnectorAccount
from app.domain.models.business_context import BusinessContext
from app.domain.models.business_context_communication_link import (
    BusinessContextCommunicationLink,
)
from app.infrastructure.storage.models import Analysis
from app.infrastructure.storage.repositories.analysis import SqlAlchemyAnalysisRepository
from app.infrastructure.storage.repositories.business_context import (
    SqlAlchemyBusinessContextRepository,
)
from app.infrastructure.storage.repositories.business_context_communication_link import (
    SqlAlchemyBusinessContextCommunicationLinkRepository,
)
from app.infrastructure.storage.repositories.connector_account import (
    SqlAlchemyConnectorAccountRepository,
)
from app.infrastructure.storage.repositories.identity import SqlAlchemyIdentityRepository
from app.infrastructure.storage.unit_of_work import SqlAlchemyPersistenceUnitOfWork

_ISSUER = "https://issuer.example.invalid/"


def _context(owner_user_id: UUID, *, title: str = "Matter") -> BusinessContext:
    return BusinessContext(
        owner_user_id=owner_user_id,
        type=BusinessContextType.MATTER,
        title=title,
    )


def _link(
    *,
    business_context_id: UUID,
    owner_user_id: UUID,
    connector_account_id: UUID,
    provider_message_id: str = "msg-1",
    analysis_id: UUID | None = None,
) -> BusinessContextCommunicationLink:
    return BusinessContextCommunicationLink(
        business_context_id=business_context_id,
        owner_user_id=owner_user_id,
        connector_account_id=connector_account_id,
        provider_message_id=provider_message_id,
        associated_by_user_id=owner_user_id,
        association_source=AssociationSource.MANUAL,
        analysis_id=analysis_id,
    )


def _create_users(session_factory: sessionmaker) -> tuple[UUID, UUID]:
    with session_factory() as session:
        identities = SqlAlchemyIdentityRepository(session)
        user_a = identities.create_user_with_external_identity(_ISSUER, "owner-a")
        user_b = identities.create_user_with_external_identity(_ISSUER, "owner-b")
        session.commit()
    return user_a, user_b


def _seed_context_and_connector(
    session_factory: sessionmaker,
    user_id: UUID,
) -> tuple[UUID, UUID]:
    with session_factory() as session:
        contexts = SqlAlchemyBusinessContextRepository(session)
        connectors = SqlAlchemyConnectorAccountRepository(session)
        context = contexts.add(_context(user_id))
        connector = connectors.create(
            NewConnectorAccount(
                user_id=user_id,
                provider="fake",
                external_account_id=f"mailbox-{user_id}",
                credential_ref="cred-ref",
                granted_capabilities=(CommunicationCapability.MAIL_READ,),
            )
        )
        session.commit()
    return context.id, connector.id


def test_add_and_get_owned_round_trips(session_factory: sessionmaker) -> None:
    """Creating a link makes the same UUID retrievable for the owner."""
    user_a, _user_b = _create_users(session_factory)
    context_id, connector_id = _seed_context_and_connector(session_factory, user_a)
    with session_factory() as session:
        repository = SqlAlchemyBusinessContextCommunicationLinkRepository(session)
        created = repository.add(
            _link(
                business_context_id=context_id,
                owner_user_id=user_a,
                connector_account_id=connector_id,
                provider_message_id="provider-msg-abc",
            )
        )
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextCommunicationLinkRepository(session)
        found = repository.get_owned(created.id, user_a)
        assert found is not None
        assert found.id == created.id
        assert found.owner_user_id == user_a
        assert found.provider_message_id == "provider-msg-abc"
        assert found.association_source is AssociationSource.MANUAL
        assert found.analysis_id is None


def test_get_owned_requires_matching_user_id(session_factory: sessionmaker) -> None:
    """get_owned must not return another user's link."""
    user_a, user_b = _create_users(session_factory)
    context_id, connector_id = _seed_context_and_connector(session_factory, user_a)
    with session_factory() as session:
        repository = SqlAlchemyBusinessContextCommunicationLinkRepository(session)
        created = repository.add(
            _link(
                business_context_id=context_id,
                owner_user_id=user_a,
                connector_account_id=connector_id,
            )
        )
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextCommunicationLinkRepository(session)
        assert repository.get_owned(created.id, user_a) is not None
        assert repository.get_owned(created.id, user_b) is None


def test_unique_provenance_triple_and_many_to_many(session_factory: sessionmaker) -> None:
    """Duplicate triples fail; many-to-many cardinality is allowed."""
    user_a, _user_b = _create_users(session_factory)
    first_id, connector_id = _seed_context_and_connector(session_factory, user_a)
    with session_factory() as session:
        contexts = SqlAlchemyBusinessContextRepository(session)
        second = contexts.add(_context(user_a, title="Second"))
        session.commit()
        second_id = second.id

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextCommunicationLinkRepository(session)
        repository.add(
            _link(
                business_context_id=first_id,
                owner_user_id=user_a,
                connector_account_id=connector_id,
                provider_message_id="shared",
            )
        )
        repository.add(
            _link(
                business_context_id=second_id,
                owner_user_id=user_a,
                connector_account_id=connector_id,
                provider_message_id="shared",
            )
        )
        repository.add(
            _link(
                business_context_id=first_id,
                owner_user_id=user_a,
                connector_account_id=connector_id,
                provider_message_id="other",
            )
        )
        session.commit()

    with session_factory() as session:
        repository = SqlAlchemyBusinessContextCommunicationLinkRepository(session)
        with pytest.raises(PersistenceError, match="Duplicate communication link"):
            repository.add(
                _link(
                    business_context_id=first_id,
                    owner_user_id=user_a,
                    connector_account_id=connector_id,
                    provider_message_id="shared",
                )
            )
        listed = repository.list_for_context_owned(first_id, user_a, limit=20, offset=0)
        assert {item.provider_message_id for item in listed} == {"shared", "other"}


def test_remove_owned_deletes_only_the_link(
    session_factory: sessionmaker,
) -> None:
    """Removing a link must not delete connector or analysis rows."""
    user_a, _user_b = _create_users(session_factory)
    context_id, connector_id = _seed_context_and_connector(session_factory, user_a)
    with session_factory() as session:
        analyses = SqlAlchemyAnalysisRepository(session)
        analysis = analyses.save(
            NewAnalysis(
                user_id=user_a,
                provider="mock",
                priority="medium",
                category="general",
                source_type="email",
                summary_text="Summary",
                action_items=[],
                message_id="msg-keep",
                connector_account_id=connector_id,
            )
        )
        links = SqlAlchemyBusinessContextCommunicationLinkRepository(session)
        link = links.add(
            _link(
                business_context_id=context_id,
                owner_user_id=user_a,
                connector_account_id=connector_id,
                provider_message_id="msg-keep",
                analysis_id=analysis.id,
            )
        )
        session.commit()
        analysis_id = analysis.id
        link_id = link.id

    with session_factory() as session:
        links = SqlAlchemyBusinessContextCommunicationLinkRepository(session)
        assert links.remove_owned(link_id, user_a) is True
        session.commit()

    with session_factory() as session:
        assert session.get(Analysis, analysis_id) is not None
        connectors = SqlAlchemyConnectorAccountRepository(session)
        assert connectors.get_owned(connector_id, user_a) is not None
        links = SqlAlchemyBusinessContextCommunicationLinkRepository(session)
        assert links.get_owned(link_id, user_a) is None


def test_schema_has_expected_constraints_and_indexes(sqlite_engine: Engine) -> None:
    """business_context_communication_links matches ADR-029."""
    inspector = inspect(sqlite_engine)
    assert "business_context_communication_links" in inspector.get_table_names()
    assert "communications" not in inspector.get_table_names()
    columns = {
        column["name"]
        for column in inspector.get_columns("business_context_communication_links")
    }
    assert columns == {
        "id",
        "business_context_id",
        "user_id",
        "connector_account_id",
        "provider_message_id",
        "analysis_id",
        "associated_by_user_id",
        "associated_at",
        "association_source",
    }
    indexes = {
        index["name"]
        for index in inspector.get_indexes("business_context_communication_links")
    }
    assert (
        "ix_bcc_links_context_associated_at_id" in indexes
    )
    assert "ix_bcc_links_user_connector_message" in indexes
    unique = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(
            "business_context_communication_links"
        )
    }
    assert (
        "uq_bcc_links_context_connector_message" in unique
    )
    fks = inspector.get_foreign_keys("business_context_communication_links")
    referred = {(fk["referred_table"], tuple(fk["constrained_columns"])) for fk in fks}
    assert ("business_contexts", ("business_context_id",)) in referred
    assert ("users", ("user_id",)) in referred
    for fk in fks:
        assert fk["referred_table"] not in {
            "analyses",
            "connector_accounts",
            "workflow_actions",
            "attachment_analyses",
        }


def test_unit_of_work_exposes_communication_links(
    session_factory: sessionmaker,
) -> None:
    """UoW exposes the link repository on the shared session."""
    user_a, _user_b = _create_users(session_factory)
    context_id, connector_id = _seed_context_and_connector(session_factory, user_a)
    with SqlAlchemyPersistenceUnitOfWork(session_factory) as uow:
        created = uow.business_context_communication_links.add(
            _link(
                business_context_id=context_id,
                owner_user_id=user_a,
                connector_account_id=connector_id,
            )
        )
        uow.commit()
        found = uow.business_context_communication_links.get_owned(created.id, user_a)
        assert found is not None
        assert found.id == created.id


def test_blank_provider_message_id_rejected_at_database(
    session_factory: sessionmaker,
) -> None:
    """Check constraint rejects blank provider_message_id when inserted raw."""
    user_a, _user_b = _create_users(session_factory)
    context_id, connector_id = _seed_context_and_connector(session_factory, user_a)
    with session_factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO business_context_communication_links ("
                    "id, business_context_id, user_id, connector_account_id, "
                    "provider_message_id, associated_by_user_id, associated_at, "
                    "association_source"
                    ") VALUES ("
                    ":id, :context_id, :user_id, :connector_id, '   ', :user_id, "
                    "CURRENT_TIMESTAMP, 'manual')"
                ),
                {
                    "id": uuid4().hex,
                    "context_id": context_id.hex,
                    "user_id": user_a.hex,
                    "connector_id": connector_id.hex,
                },
            )
            session.commit()

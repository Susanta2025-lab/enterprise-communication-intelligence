"""Unit tests for AnalysisHistoryService."""

from uuid import uuid4

import pytest

from app.application.exceptions import AnalysisNotFoundError, ConnectorAccountNotFoundError
from app.application.services.analysis_history import AnalysisHistoryService
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.domain.enums import ConnectorAccountStatus, MessageCategory, PriorityLevel, SourceType
from app.domain.models import (
    ActionItem,
    CommunicationAnalysis,
    DraftReply,
    Priority,
    Summary,
)
from app.domain.schemas import CommunicationAnalysisResult
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_analysis_record,
    sample_connector_account,
)
from tests.unit.application.conftest import RequestFactory


def _result() -> CommunicationAnalysisResult:
    return CommunicationAnalysisResult(
        analysis=CommunicationAnalysis(
            summary=Summary(text="Status summary", confidence=0.9),
            priority=Priority(level=PriorityLevel.MEDIUM),
            category=MessageCategory.GENERAL,
            action_items=[ActionItem(description="Review notes")],
            draft_reply=DraftReply(body="Thank you for the update."),
            message_id="msg-001",
        ),
        provider="mock",
    )


def test_list_returns_only_owned_analyses() -> None:
    """List must not include another user's records."""
    user_a = uuid4()
    user_b = uuid4()
    owned = sample_analysis_record(user_a, summary_text="Owned summary")
    other = sample_analysis_record(user_b, summary_text="Other summary")
    unit = InMemoryUnitOfWork(analyses={owned.id: owned, other.id: other})
    service = AnalysisHistoryService(UnitOfWorkFactory(unit))

    items = service.list_for_user(user_a, limit=20, offset=0)

    assert [item.id for item in items] == [owned.id]
    assert all(item.user_id == user_a for item in items)


def test_get_owned_analysis() -> None:
    """An owned analysis is returned."""
    user_a = uuid4()
    record = sample_analysis_record(user_a)
    unit = InMemoryUnitOfWork(analyses={record.id: record})
    service = AnalysisHistoryService(UnitOfWorkFactory(unit))

    found = service.get_for_user(record.id, user_a)

    assert found.id == record.id
    assert "raw_body" not in found.summary_text


def test_get_unknown_and_cross_user_are_not_found() -> None:
    """Unknown and cross-user gets must be indistinguishable."""
    user_a = uuid4()
    user_b = uuid4()
    record = sample_analysis_record(user_a)
    unit = InMemoryUnitOfWork(analyses={record.id: record})
    service = AnalysisHistoryService(UnitOfWorkFactory(unit))

    with pytest.raises(AnalysisNotFoundError):
        service.get_for_user(uuid4(), user_a)
    with pytest.raises(AnalysisNotFoundError):
        service.get_for_user(record.id, user_b)


def test_delete_owned_unknown_and_cross_user() -> None:
    """Owned delete succeeds; unknown and cross-user raise not-found."""
    user_a = uuid4()
    user_b = uuid4()
    record = sample_analysis_record(user_a)
    analyses = {record.id: record}
    unit = InMemoryUnitOfWork(analyses=analyses)
    service = AnalysisHistoryService(UnitOfWorkFactory(unit))

    service.delete_for_user(record.id, user_a)
    assert record.id not in analyses

    with pytest.raises(AnalysisNotFoundError):
        service.delete_for_user(uuid4(), user_a)
    with pytest.raises(AnalysisNotFoundError):
        service.delete_for_user(record.id, user_b)


def test_database_failure_becomes_unavailable() -> None:
    """Persistence failures on history reads become ServiceUnavailableError."""
    unit = InMemoryUnitOfWork(fail_on_enter=PersistenceError("Could not persist analysis."))
    service = AnalysisHistoryService(UnitOfWorkFactory(unit))

    with pytest.raises(ServiceUnavailableError) as exc_info:
        service.list_for_user(uuid4(), limit=20, offset=0)

    assert exc_info.value.message == "Persistence is currently unavailable."
    assert exc_info.value.__cause__ is None


def test_save_maps_analysis_without_raw_body(make_request: RequestFactory) -> None:
    """Persisted records must not include the communication body."""
    user_id = uuid4()
    unit = InMemoryUnitOfWork()
    service = AnalysisHistoryService(UnitOfWorkFactory(unit))
    request = make_request("SECRET_RAW_BODY_SENTINEL")

    saved = service.save(user_id, request, _result())

    assert saved.user_id == user_id
    assert saved.summary_text == "Status summary"
    assert saved.provider == "mock"
    assert saved.source_type == SourceType.EMAIL.value
    assert saved.connector_account_id is None
    assert saved.action_items[0]["description"] == "Review notes"
    assert saved.draft_reply is not None
    assert "SECRET_RAW_BODY_SENTINEL" not in saved.summary_text
    assert unit.commit_calls == 1


def test_no_identity_mapping_is_represented_by_empty_or_not_found() -> None:
    """Callers without a user mapping have no history rows."""
    user_id = uuid4()
    unit = InMemoryUnitOfWork()
    service = AnalysisHistoryService(UnitOfWorkFactory(unit))

    assert service.list_for_user(user_id, limit=20, offset=0) == []
    with pytest.raises(AnalysisNotFoundError):
        service.get_for_user(uuid4(), user_id)
    with pytest.raises(AnalysisNotFoundError):
        service.delete_for_user(uuid4(), user_id)


def test_save_persists_owned_connector_account_provenance(
    make_request: RequestFactory,
) -> None:
    """Owned connector-account ids round-trip into analysis history."""
    user_id = uuid4()
    account = sample_connector_account(user_id)
    unit = InMemoryUnitOfWork(connector_accounts={account.id: account})
    service = AnalysisHistoryService(UnitOfWorkFactory(unit))
    request = make_request("Please review the Q3 budget proposal before Friday.")

    saved = service.save(
        user_id,
        request,
        _result(),
        connector_account_id=account.id,
    )

    assert saved.connector_account_id == account.id
    stored = unit.analyses[saved.id]
    assert stored.connector_account_id == account.id


def test_save_persists_disconnected_owned_connector_account_provenance(
    make_request: RequestFactory,
) -> None:
    """Analysis provenance is not execution eligibility; ACTIVE is not required at save."""
    user_id = uuid4()
    account = sample_connector_account(
        user_id,
        status=ConnectorAccountStatus.DISCONNECTED,
        credential_ref=None,
    )
    unit = InMemoryUnitOfWork(connector_accounts={account.id: account})
    service = AnalysisHistoryService(UnitOfWorkFactory(unit))
    request = make_request("Please review the Q3 budget proposal before Friday.")

    saved = service.save(
        user_id,
        request,
        _result(),
        connector_account_id=account.id,
    )

    assert saved.connector_account_id == account.id
    assert unit.commit_calls == 1


def test_save_rejects_unowned_connector_account_id(
    make_request: RequestFactory,
) -> None:
    """Arbitrary unowned account ids must not enter analysis persistence."""
    user_id = uuid4()
    other = uuid4()
    account = sample_connector_account(other)
    unit = InMemoryUnitOfWork(connector_accounts={account.id: account})
    service = AnalysisHistoryService(UnitOfWorkFactory(unit))
    request = make_request("Please review the Q3 budget proposal before Friday.")

    with pytest.raises(ConnectorAccountNotFoundError):
        service.save(
            user_id,
            request,
            _result(),
            connector_account_id=account.id,
        )

    assert unit.analyses == {}
    assert unit.commit_calls == 0


def test_save_rejects_missing_connector_account_id(
    make_request: RequestFactory,
) -> None:
    """Unknown account ids are the same not-found outcome as unowned ids."""
    user_id = uuid4()
    unit = InMemoryUnitOfWork()
    service = AnalysisHistoryService(UnitOfWorkFactory(unit))
    request = make_request("Please review the Q3 budget proposal before Friday.")

    with pytest.raises(ConnectorAccountNotFoundError):
        service.save(
            user_id,
            request,
            _result(),
            connector_account_id=uuid4(),
        )

    assert unit.analyses == {}
    assert unit.commit_calls == 0

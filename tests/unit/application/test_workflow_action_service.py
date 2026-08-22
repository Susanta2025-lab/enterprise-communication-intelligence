"""Unit tests for WorkflowActionService."""

from uuid import UUID, uuid4

import pytest

from app.application.exceptions import (
    AnalysisHasNoDraftReplyError,
    AnalysisNotFoundError,
    WorkflowActionConflictError,
    WorkflowActionNotFoundError,
)
from app.application.services.identity import IdentityResolver
from app.application.services.workflow_actions import WorkflowActionService
from app.core.exceptions import PersistenceError, ServiceUnavailableError
from app.core.security import AuthenticatedPrincipal
from app.domain.enums import WorkflowActionStatus, WorkflowActionType
from app.domain.exceptions import InvalidWorkflowTransitionError
from app.domain.interfaces.workflow_action_repository import (
    WorkflowActionSaveOutcome,
    WorkflowActionSaveResult,
)
from app.domain.models.workflow import WorkflowAction
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_analysis_record,
    sample_connector_account,
)
from tests.support.jwt_tokens import TEST_PERMISSION

_ISSUER_A = "https://issuer-a.example.invalid/"
_ISSUER_B = "https://issuer-b.example.invalid/"
_SUBJECT_A = "subject-a"
_SUBJECT_B = "subject-b"
_DRAFT_BODY = "Thanks, I will review the report and respond by Friday."
_RAW_MAIL = "SECRET_INBOUND_BODY"


def _principal(
    *,
    issuer: str = _ISSUER_A,
    subject: str = _SUBJECT_A,
) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        issuer=issuer,
        subject=subject,
        permissions=frozenset({TEST_PERMISSION}),
    )


def _analysis(user_id: UUID, *, draft_body: str | None = _DRAFT_BODY, **extra: object):
    payload = dict(extra)
    if draft_body is None:
        payload["draft_reply"] = None
    else:
        payload.setdefault(
            "draft_reply",
            {"body": draft_body, "tone": "professional", "confidence": 0.8},
        )
    return sample_analysis_record(user_id, extra=payload)


def _service(
    unit: InMemoryUnitOfWork,
) -> WorkflowActionService:
    factory = UnitOfWorkFactory(unit)
    return WorkflowActionService(IdentityResolver(factory), factory)


def _seeded(
    *,
    draft_body: str | None = _DRAFT_BODY,
) -> tuple[WorkflowActionService, InMemoryUnitOfWork, UUID, UUID]:
    user_id = uuid4()
    analysis = _analysis(user_id, draft_body=draft_body)
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        analyses={analysis.id: analysis},
    )
    return _service(unit), unit, user_id, analysis.id


def test_create_snapshots_owned_draft_into_pending_action() -> None:
    """Owned analysis with a draft becomes a PENDING workflow action."""
    service, unit, user_id, analysis_id = _seeded()

    action = service.create(_principal(), analysis_id)

    assert action.status is WorkflowActionStatus.PENDING
    assert action.action_type is WorkflowActionType.REPLY
    assert action.analysis_id == analysis_id
    assert action.owner_user_id == user_id
    assert action.proposed_reply_body == _DRAFT_BODY
    assert action.approved_reply_body is None
    assert action.has_execution_target is False
    assert action.connector_account_id is None
    assert action.provider_message_id is None
    stored = unit.workflow_action_store[action.id]
    assert stored.proposed_reply_body == _DRAFT_BODY
    assert unit.commit_calls >= 1


def test_create_does_not_copy_tone_confidence_or_raw_mail() -> None:
    """Only draft_reply.body is snapshotted; inbound mail is not stored."""
    user_id = uuid4()
    analysis = sample_analysis_record(
        user_id,
        extra={
            "draft_reply": {
                "body": _DRAFT_BODY,
                "tone": "professional",
                "confidence": 0.8,
            },
            "summary_text": _RAW_MAIL,
        },
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        analyses={analysis.id: analysis},
    )
    service = _service(unit)

    action = service.create(_principal(), analysis.id)

    dumped = action.model_dump()
    assert dumped["proposed_reply_body"] == _DRAFT_BODY
    assert "tone" not in dumped
    assert "confidence" not in dumped
    assert "body" not in dumped
    assert _RAW_MAIL not in str(dumped)
    assert "sender" not in dumped
    assert "recipient" not in dumped
    assert "subject" not in dumped


def test_create_missing_analysis_is_not_found() -> None:
    """Unknown analysis ids raise AnalysisNotFoundError."""
    service, _unit, _user_id, _analysis_id = _seeded()
    with pytest.raises(AnalysisNotFoundError):
        service.create(_principal(), uuid4())


def test_create_cross_user_analysis_is_not_found() -> None:
    """Another user's analysis is indistinguishable from unknown."""
    owner = uuid4()
    other = uuid4()
    analysis = _analysis(owner)
    unit = InMemoryUnitOfWork(
        identities={
            (_ISSUER_A, _SUBJECT_A): other,
            (_ISSUER_B, _SUBJECT_B): owner,
        },
        analyses={analysis.id: analysis},
    )
    service = _service(unit)

    with pytest.raises(AnalysisNotFoundError):
        service.create(_principal(), analysis.id)
    assert unit.workflow_action_store == {}


def test_create_without_identity_mapping_is_not_found() -> None:
    """Missing identity mapping must not create a user or a workflow action."""
    unit = InMemoryUnitOfWork()
    service = _service(unit)

    with pytest.raises(AnalysisNotFoundError):
        service.create(_principal(), uuid4())
    assert unit.identity_repository.create_calls == 0
    assert unit.workflow_action_store == {}


def test_create_analysis_without_draft_raises_bounded_error() -> None:
    """An owned analysis without a draft cannot create a workflow action."""
    service, unit, _user_id, analysis_id = _seeded(draft_body=None)

    with pytest.raises(AnalysisHasNoDraftReplyError) as exc_info:
        service.create(_principal(), analysis_id)

    assert exc_info.value.message == "Analysis has no usable draft reply."
    assert unit.workflow_action_store == {}


@pytest.mark.parametrize("body", ["", "   ", "\n\t"])
def test_create_invalid_draft_raises_bounded_error(body: str) -> None:
    """Empty or whitespace draft bodies are not usable snapshots."""
    service, unit, _user_id, analysis_id = _seeded(draft_body=body)

    with pytest.raises(AnalysisHasNoDraftReplyError):
        service.create(_principal(), analysis_id)
    assert unit.workflow_action_store == {}


def test_get_and_list_are_owner_scoped() -> None:
    """Get and list must not expose another user's workflow actions."""
    owner = uuid4()
    other = uuid4()
    analysis = _analysis(owner)
    unit = InMemoryUnitOfWork(
        identities={
            (_ISSUER_A, _SUBJECT_A): owner,
            (_ISSUER_B, _SUBJECT_B): other,
        },
        analyses={analysis.id: analysis},
    )
    service = _service(unit)
    created = service.create(_principal(), analysis.id)

    found = service.get(_principal(), created.id)
    listed = service.list(_principal())
    assert found.id == created.id
    assert [item.id for item in listed] == [created.id]

    other_principal = _principal(issuer=_ISSUER_B, subject=_SUBJECT_B)
    with pytest.raises(WorkflowActionNotFoundError):
        service.get(other_principal, created.id)
    assert service.list(other_principal) == []


def test_get_unknown_and_missing_identity_are_not_found() -> None:
    """Unknown actions and missing identity mappings raise the same not-found."""
    service, _unit, _user_id, analysis_id = _seeded()
    created = service.create(_principal(), analysis_id)

    with pytest.raises(WorkflowActionNotFoundError):
        service.get(_principal(), uuid4())

    empty = InMemoryUnitOfWork()
    with pytest.raises(WorkflowActionNotFoundError):
        _service(empty).get(_principal(), created.id)
    assert empty.identity_repository.create_calls == 0


def test_list_without_identity_returns_empty() -> None:
    """List is empty when the principal has no internal user mapping."""
    assert _service(InMemoryUnitOfWork()).list(_principal()) == []


def test_approve_copies_proposal_and_does_not_load_analysis() -> None:
    """PENDING → APPROVED copies the proposal without using the analysis repository."""
    service, unit, _user_id, analysis_id = _seeded()
    created = service.create(_principal(), analysis_id)
    unit.analysis_repository.get_calls = 0

    approved = service.approve(_principal(), created.id)

    assert approved.status is WorkflowActionStatus.APPROVED
    assert approved.approved_reply_body == created.proposed_reply_body
    assert approved.proposed_reply_body == created.proposed_reply_body
    assert approved.approved_at is not None
    assert unit.analysis_repository.get_calls == 0


def test_reject_retains_proposal_and_does_not_load_analysis() -> None:
    """PENDING → REJECTED keeps the proposal and leaves approved body unset."""
    service, unit, _user_id, analysis_id = _seeded()
    created = service.create(_principal(), analysis_id)
    unit.analysis_repository.get_calls = 0

    rejected = service.reject(_principal(), created.id)

    assert rejected.status is WorkflowActionStatus.REJECTED
    assert rejected.proposed_reply_body == created.proposed_reply_body
    assert rejected.approved_reply_body is None
    assert rejected.rejected_at is not None
    assert unit.analysis_repository.get_calls == 0


def test_approve_after_analysis_hard_delete_succeeds() -> None:
    """A PENDING action remains approvable after the source analysis is deleted."""
    service, unit, user_id, analysis_id = _seeded()
    created = service.create(_principal(), analysis_id)
    proposal = created.proposed_reply_body

    deleted = unit.analysis_repository.delete_for_user(analysis_id, user_id)
    assert deleted is True
    assert analysis_id not in unit.analyses

    approved = service.approve(_principal(), created.id)

    assert approved.status is WorkflowActionStatus.APPROVED
    assert approved.analysis_id == analysis_id
    assert approved.proposed_reply_body == proposal
    assert approved.approved_reply_body == proposal


def test_reject_after_analysis_hard_delete_succeeds() -> None:
    """A PENDING action remains rejectable after the source analysis is deleted."""
    service, unit, user_id, analysis_id = _seeded()
    created = service.create(_principal(), analysis_id)

    assert unit.analysis_repository.delete_for_user(analysis_id, user_id) is True

    rejected = service.reject(_principal(), created.id)

    assert rejected.status is WorkflowActionStatus.REJECTED
    assert rejected.analysis_id == analysis_id
    assert rejected.proposed_reply_body == created.proposed_reply_body
    assert rejected.approved_reply_body is None


def test_approve_non_pending_raises_invalid_transition() -> None:
    """Domain transition errors propagate without a persistence conflict."""
    service, _unit, _user_id, analysis_id = _seeded()
    created = service.create(_principal(), analysis_id)
    service.approve(_principal(), created.id)

    with pytest.raises(InvalidWorkflowTransitionError):
        service.approve(_principal(), created.id)


def test_stale_expected_status_becomes_conflict() -> None:
    """A conditional update that no longer matches stored status is a conflict."""
    service, unit, _user_id, analysis_id = _seeded()
    created = service.create(_principal(), analysis_id)

    def _conflict(
        action: WorkflowAction,
        expected_status: object,
    ) -> WorkflowActionSaveResult:
        return WorkflowActionSaveResult(outcome=WorkflowActionSaveOutcome.CONFLICT)

    unit.workflow_actions.save_owned = _conflict  # type: ignore[method-assign]

    with pytest.raises(WorkflowActionConflictError) as exc_info:
        service.approve(_principal(), created.id)
    assert exc_info.value.message == "Workflow action was updated concurrently."


def test_persistence_failure_becomes_unavailable() -> None:
    """Database failures on workflow reads become ServiceUnavailableError."""
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): uuid4()},
        fail_on_enter=PersistenceError("Could not persist workflow action."),
    )
    service = _service(unit)

    with pytest.raises(ServiceUnavailableError) as exc_info:
        service.list(_principal())

    assert exc_info.value.message == "Persistence is currently unavailable."
    assert exc_info.value.__cause__ is None


def test_create_snapshots_mailbox_execution_target() -> None:
    """Create copies analysis connector_account_id and message_id onto the action."""
    user_id = uuid4()
    account = sample_connector_account(user_id)
    analysis = _analysis(
        user_id,
        connector_account_id=account.id,
        message_id="provider-msg-001",
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        analyses={analysis.id: analysis},
        connector_accounts={account.id: account},
    )
    service = _service(unit)

    action = service.create(_principal(), analysis.id)

    assert action.connector_account_id == account.id
    assert action.provider_message_id == "provider-msg-001"
    assert action.has_execution_target is True


def test_create_does_not_snapshot_incomplete_direct_text_target() -> None:
    """Direct-text analyses with only message_id remain non-executable."""
    service, _unit, _user_id, analysis_id = _seeded()
    action = service.create(_principal(), analysis_id)
    assert action.connector_account_id is None
    assert action.provider_message_id is None
    assert action.has_execution_target is False


def test_execution_target_survives_analysis_change_and_delete() -> None:
    """Later analysis mutation or deletion must not alter the workflow snapshot."""
    user_id = uuid4()
    account = sample_connector_account(user_id)
    analysis = _analysis(
        user_id,
        connector_account_id=account.id,
        message_id="provider-msg-001",
    )
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
        analyses={analysis.id: analysis},
        connector_accounts={account.id: account},
    )
    service = _service(unit)
    created = service.create(_principal(), analysis.id)
    original_account_id = created.connector_account_id
    original_message_id = created.provider_message_id

    mutated = sample_analysis_record(
        user_id,
        analysis_id=analysis.id,
        extra={
            "connector_account_id": uuid4(),
            "message_id": "changed-message",
            "draft_reply": {"body": _DRAFT_BODY},
        },
    )
    unit.analyses[analysis.id] = mutated
    approved = service.approve(_principal(), created.id)
    assert approved.connector_account_id == original_account_id
    assert approved.provider_message_id == original_message_id

    assert unit.analysis_repository.delete_for_user(analysis.id, user_id) is True
    loaded = service.get(_principal(), created.id)
    assert loaded.connector_account_id == original_account_id
    assert loaded.provider_message_id == original_message_id
    assert loaded.has_execution_target is True


def test_in_memory_save_owned_does_not_rewrite_execution_target() -> None:
    """Test doubles must keep the creation snapshot, matching SQL save_owned."""
    user_id = uuid4()
    account_id = uuid4()
    unit = InMemoryUnitOfWork(
        identities={(_ISSUER_A, _SUBJECT_A): user_id},
    )
    stored = unit.workflow_actions.add(
        WorkflowAction(
            action_type=WorkflowActionType.REPLY,
            analysis_id=uuid4(),
            owner_user_id=user_id,
            proposed_reply_body=_DRAFT_BODY,
            connector_account_id=account_id,
            provider_message_id="provider-msg-001",
        )
    )
    loaded = unit.workflow_actions.get_owned(stored.id, user_id)
    assert loaded is not None
    loaded.connector_account_id = uuid4()
    loaded.provider_message_id = "mutated-message"
    loaded.approve()

    result = unit.workflow_actions.save_owned(
        loaded,
        expected_status=WorkflowActionStatus.PENDING,
    )

    assert result.action is not None
    assert result.action.connector_account_id == account_id
    assert result.action.provider_message_id == "provider-msg-001"
    persisted = unit.workflow_action_store[stored.id]
    assert persisted.connector_account_id == account_id
    assert persisted.provider_message_id == "provider-msg-001"

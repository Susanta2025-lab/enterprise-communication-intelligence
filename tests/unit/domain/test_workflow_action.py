"""Unit tests for approval-gated workflow actions and the state machine."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import WorkflowActionStatus, WorkflowActionType
from app.domain.exceptions import InvalidWorkflowTransitionError
from app.domain.models import ActionItem, DraftReply, WorkflowAction

_APPROVED_REPLY = "Thanks, I will review the report and respond by Friday."
_NON_PENDING_STATUSES = [
    status
    for status in WorkflowActionStatus
    if status is not WorkflowActionStatus.PENDING
]


def _pending_action(**overrides: object) -> WorkflowAction:
    payload: dict[str, object] = {
        "action_type": WorkflowActionType.REPLY,
        "analysis_id": uuid4(),
        "owner_user_id": uuid4(),
    }
    payload.update(overrides)
    return WorkflowAction.model_validate(payload)


def _snapshot(action: WorkflowAction) -> tuple[object, ...]:
    return (
        action.id,
        action.action_type,
        action.analysis_id,
        action.owner_user_id,
        action.status,
        action.created_at,
        action.approved_at,
        action.rejected_at,
        action.executed_at,
        action.failed_at,
        action.approved_reply_body,
    )


def test_workflow_action_is_distinct_from_action_item() -> None:
    """WorkflowAction is not AI-extracted ActionItem output."""
    action = _pending_action()
    assert not isinstance(action, ActionItem)
    assert ActionItem is not WorkflowAction
    assert "status" not in DraftReply.model_fields
    assert "approval" not in DraftReply.model_fields
    assert set(DraftReply.model_fields) == {"body", "tone", "confidence"}


def test_valid_workflow_action_starts_pending() -> None:
    """A well-formed workflow action is created in PENDING with REPLY type."""
    analysis_id = uuid4()
    owner_user_id = uuid4()
    action = WorkflowAction(
        action_type=WorkflowActionType.REPLY,
        analysis_id=analysis_id,
        owner_user_id=owner_user_id,
    )

    assert action.action_type is WorkflowActionType.REPLY
    assert action.status is WorkflowActionStatus.PENDING
    assert action.analysis_id == analysis_id
    assert action.owner_user_id == owner_user_id
    assert action.id is not None
    assert action.created_at.tzinfo is not None
    assert action.approved_at is None
    assert action.rejected_at is None
    assert action.executed_at is None
    assert action.failed_at is None
    assert action.approved_reply_body is None
    assert action.is_terminal is False


def test_missing_analysis_id_is_rejected() -> None:
    """Analysis provenance is required."""
    with pytest.raises(ValidationError):
        WorkflowAction.model_validate(
            {
                "action_type": WorkflowActionType.REPLY,
                "owner_user_id": uuid4(),
            }
        )


def test_missing_owner_user_id_is_rejected() -> None:
    """Ownership is required."""
    with pytest.raises(ValidationError):
        WorkflowAction.model_validate(
            {
                "action_type": WorkflowActionType.REPLY,
                "analysis_id": uuid4(),
            }
        )


def test_missing_action_type_is_rejected() -> None:
    """Action type is required."""
    with pytest.raises(ValidationError):
        WorkflowAction.model_validate(
            {
                "analysis_id": uuid4(),
                "owner_user_id": uuid4(),
            }
        )


def test_invalid_action_type_is_rejected() -> None:
    """Unsupported workflow action types must fail validation."""
    with pytest.raises(ValidationError):
        WorkflowAction.model_validate(
            {
                "action_type": "calendar_event",
                "analysis_id": uuid4(),
                "owner_user_id": uuid4(),
            }
        )


@pytest.mark.parametrize("status", _NON_PENDING_STATUSES)
def test_non_pending_construction_is_rejected(status: WorkflowActionStatus) -> None:
    """Workflow actions cannot be constructed already approved or executed."""
    with pytest.raises(ValidationError):
        WorkflowAction.model_validate(
            {
                "action_type": WorkflowActionType.REPLY,
                "analysis_id": uuid4(),
                "owner_user_id": uuid4(),
                "status": status,
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("approved_at", datetime.now(UTC)),
        ("rejected_at", datetime.now(UTC)),
        ("executed_at", datetime.now(UTC)),
        ("failed_at", datetime.now(UTC)),
        ("approved_reply_body", _APPROVED_REPLY),
    ],
)
def test_pending_construction_rejects_later_lifecycle_fields(
    field: str,
    value: object,
) -> None:
    """PENDING construction cannot carry later timestamps or an approved body."""
    with pytest.raises(ValidationError):
        _pending_action(**{field: value})


def test_unknown_fields_are_rejected() -> None:
    """WorkflowAction must not accept persistence or transport extras."""
    with pytest.raises(ValidationError):
        WorkflowAction.model_validate(
            {
                "action_type": WorkflowActionType.REPLY,
                "analysis_id": uuid4(),
                "owner_user_id": uuid4(),
                "table": "workflow_actions",
            }
        )


@pytest.mark.parametrize("field", ["body", "sender", "recipient", "subject"])
def test_message_content_fields_are_rejected(field: str) -> None:
    """WorkflowAction must not store inbound message content."""
    with pytest.raises(ValidationError):
        _pending_action(**{field: "should-not-be-stored"})


def test_pending_to_approved() -> None:
    """PENDING → APPROVED snapshots the approved reply body."""
    action = _pending_action()
    created_at = action.created_at
    action.approve(approved_reply_body=_APPROVED_REPLY)

    assert action.status is WorkflowActionStatus.APPROVED
    assert action.approved_at is not None
    assert action.approved_at.tzinfo is not None
    assert action.approved_reply_body == _APPROVED_REPLY
    assert action.rejected_at is None
    assert action.created_at == created_at
    assert action.is_terminal is False


@pytest.mark.parametrize("body", ["", "   ", "\n\t"])
def test_approve_rejects_empty_reply_body_without_mutating(body: str) -> None:
    """An empty approved reply is invalid and must not change status."""
    action = _pending_action()
    before = _snapshot(action)

    with pytest.raises(ValueError, match="approved_reply_body must not be empty"):
        action.approve(approved_reply_body=body)

    assert _snapshot(action) == before
    assert action.status is WorkflowActionStatus.PENDING


def test_approve_strips_whitespace_and_does_not_mutate_draft_reply() -> None:
    """Approval snapshots the caller-supplied body and leaves DraftReply unchanged."""
    draft = DraftReply(body="AI suggested reply")
    action = _pending_action()

    action.approve(approved_reply_body="  Approved edited reply  ")

    assert action.approved_reply_body == "Approved edited reply"
    assert draft.body == "AI suggested reply"
    assert action.status is WorkflowActionStatus.APPROVED


def test_pending_to_rejected() -> None:
    """PENDING → REJECTED is terminal."""
    action = _pending_action()
    action.reject()

    assert action.status is WorkflowActionStatus.REJECTED
    assert action.rejected_at is not None
    assert action.rejected_at.tzinfo is not None
    assert action.approved_at is None
    assert action.approved_reply_body is None
    assert action.is_terminal is True


def test_approved_to_executing() -> None:
    """APPROVED → EXECUTING is allowed."""
    action = _pending_action()
    action.approve(approved_reply_body=_APPROVED_REPLY)
    action.mark_executing()

    assert action.status is WorkflowActionStatus.EXECUTING
    assert action.executed_at is None
    assert action.failed_at is None
    assert action.is_terminal is False


def test_executing_to_executed() -> None:
    """EXECUTING → EXECUTED is terminal success."""
    action = _pending_action()
    action.approve(approved_reply_body=_APPROVED_REPLY)
    action.mark_executing()
    action.mark_executed()

    assert action.status is WorkflowActionStatus.EXECUTED
    assert action.executed_at is not None
    assert action.executed_at.tzinfo is not None
    assert action.failed_at is None
    assert action.approved_reply_body == _APPROVED_REPLY
    assert action.is_terminal is True


def test_executing_to_failed() -> None:
    """EXECUTING → FAILED is terminal failure."""
    action = _pending_action()
    action.approve(approved_reply_body=_APPROVED_REPLY)
    action.mark_executing()
    action.mark_failed()

    assert action.status is WorkflowActionStatus.FAILED
    assert action.failed_at is not None
    assert action.failed_at.tzinfo is not None
    assert action.executed_at is None
    assert action.approved_reply_body == _APPROVED_REPLY
    assert action.is_terminal is True


@pytest.mark.parametrize(
    ("setup", "attempt"),
    [
        (lambda action: None, lambda action: action.mark_executed()),
        (lambda action: None, lambda action: action.mark_failed()),
        (lambda action: None, lambda action: action.mark_executing()),
        (
            lambda action: action.approve(approved_reply_body=_APPROVED_REPLY),
            lambda action: action.reject(),
        ),
        (
            lambda action: action.approve(approved_reply_body=_APPROVED_REPLY),
            lambda action: action.mark_executed(),
        ),
        (
            lambda action: action.approve(approved_reply_body=_APPROVED_REPLY),
            lambda action: action.approve(approved_reply_body=_APPROVED_REPLY),
        ),
        (
            lambda action: (
                action.approve(approved_reply_body=_APPROVED_REPLY),
                action.mark_executing(),
            ),
            lambda action: action.approve(approved_reply_body=_APPROVED_REPLY),
        ),
        (
            lambda action: (
                action.approve(approved_reply_body=_APPROVED_REPLY),
                action.mark_executing(),
            ),
            lambda action: action.reject(),
        ),
        (
            lambda action: action.reject(),
            lambda action: action.approve(approved_reply_body=_APPROVED_REPLY),
        ),
        (
            lambda action: action.reject(),
            lambda action: action.mark_executing(),
        ),
        (
            lambda action: (
                action.approve(approved_reply_body=_APPROVED_REPLY),
                action.mark_executing(),
                action.mark_executed(),
            ),
            lambda action: action.mark_executing(),
        ),
        (
            lambda action: (
                action.approve(approved_reply_body=_APPROVED_REPLY),
                action.mark_executing(),
                action.mark_executed(),
            ),
            lambda action: action.approve(approved_reply_body=_APPROVED_REPLY),
        ),
        (
            lambda action: (
                action.approve(approved_reply_body=_APPROVED_REPLY),
                action.mark_executing(),
                action.mark_failed(),
            ),
            lambda action: action.mark_executing(),
        ),
        (
            lambda action: (
                action.approve(approved_reply_body=_APPROVED_REPLY),
                action.mark_executing(),
                action.mark_failed(),
            ),
            lambda action: action.mark_executed(),
        ),
    ],
)
def test_illegal_transitions_raise_and_do_not_mutate(setup, attempt) -> None:
    """Illegal transitions raise InvalidWorkflowTransitionError without mutation."""
    action = _pending_action()
    setup(action)
    before = _snapshot(action)

    with pytest.raises(InvalidWorkflowTransitionError) as exc_info:
        attempt(action)

    assert exc_info.value.message == "Invalid workflow state transition."
    assert str(exc_info.value) == "Invalid workflow state transition."
    assert _snapshot(action) == before


def test_terminal_rejected_cannot_transition_further() -> None:
    """REJECTED is terminal in Phase 11."""
    action = _pending_action()
    action.reject()
    before = _snapshot(action)

    for attempt in (
        lambda: action.approve(approved_reply_body=_APPROVED_REPLY),
        action.reject,
        action.mark_executing,
        action.mark_executed,
        action.mark_failed,
    ):
        with pytest.raises(InvalidWorkflowTransitionError):
            attempt()
        assert _snapshot(action) == before


def test_terminal_executed_cannot_transition_further() -> None:
    """EXECUTED is terminal in Phase 11."""
    action = _pending_action()
    action.approve(approved_reply_body=_APPROVED_REPLY)
    action.mark_executing()
    action.mark_executed()
    before = _snapshot(action)

    for attempt in (
        lambda: action.approve(approved_reply_body=_APPROVED_REPLY),
        action.reject,
        action.mark_executing,
        action.mark_executed,
        action.mark_failed,
    ):
        with pytest.raises(InvalidWorkflowTransitionError):
            attempt()
        assert _snapshot(action) == before


def test_terminal_failed_cannot_transition_further() -> None:
    """FAILED is terminal in Phase 11 and has no retry path."""
    action = _pending_action()
    action.approve(approved_reply_body=_APPROVED_REPLY)
    action.mark_executing()
    action.mark_failed()
    before = _snapshot(action)

    for attempt in (
        lambda: action.approve(approved_reply_body=_APPROVED_REPLY),
        action.reject,
        action.mark_executing,
        action.mark_executed,
        action.mark_failed,
    ):
        with pytest.raises(InvalidWorkflowTransitionError):
            attempt()
        assert _snapshot(action) == before

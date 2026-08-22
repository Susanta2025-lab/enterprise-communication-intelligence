"""Unit tests for workflow-action HTTP schemas and mapping."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import WorkflowActionStatus, WorkflowActionType
from app.domain.models.workflow import WorkflowAction
from app.schemas.workflow import (
    WorkflowActionCreateRequest,
    workflow_action_response,
)


def test_create_request_accepts_only_analysis_id() -> None:
    """The HTTP create body must accept analysis_id and reject extra fields."""
    analysis_id = uuid4()
    request = WorkflowActionCreateRequest(analysis_id=analysis_id)
    assert request.analysis_id == analysis_id

    with pytest.raises(ValidationError):
        WorkflowActionCreateRequest.model_validate(
            {"analysis_id": str(analysis_id), "action_type": "reply"}
        )
    with pytest.raises(ValidationError):
        WorkflowActionCreateRequest.model_validate(
            {"analysis_id": str(analysis_id), "proposed_reply_body": "Hello"}
        )
    with pytest.raises(ValidationError):
        WorkflowActionCreateRequest.model_validate(
            {"analysis_id": str(analysis_id), "approved_reply_body": "Hello"}
        )
    with pytest.raises(ValidationError):
        WorkflowActionCreateRequest.model_validate(
            {"analysis_id": str(analysis_id), "status": "pending"}
        )
    with pytest.raises(ValidationError):
        WorkflowActionCreateRequest.model_validate(
            {"analysis_id": str(analysis_id), "connector_account_id": str(uuid4())}
        )
    with pytest.raises(ValidationError):
        WorkflowActionCreateRequest.model_validate(
            {"analysis_id": str(analysis_id), "provider_message_id": "msg-1"}
        )


def test_workflow_action_response_omits_owner_and_serializes_enums() -> None:
    """HTTP mapping must not expose ownership and must use lowercase enum values."""
    now = datetime.now(UTC)
    owner_user_id = uuid4()
    action = WorkflowAction(
        action_type=WorkflowActionType.REPLY,
        analysis_id=uuid4(),
        owner_user_id=owner_user_id,
        proposed_reply_body="Thank you. I will follow up shortly.",
        created_at=now,
    )
    response = workflow_action_response(action)
    payload = response.model_dump(mode="json")

    assert payload["action_type"] == "reply"
    assert payload["status"] == "pending"
    assert payload["analysis_id"] == str(action.analysis_id)
    assert payload["proposed_reply_body"] == action.proposed_reply_body
    assert payload["approved_reply_body"] is None
    assert payload["has_execution_target"] is False
    assert "owner_user_id" not in payload
    assert "user_id" not in payload
    assert "connector_account_id" not in payload
    assert "provider_message_id" not in payload
    assert "credential_ref" not in payload


def test_workflow_action_response_supports_execution_statuses() -> None:
    """Persisted execution states must serialize even though 11C does not create them."""
    now = datetime.now(UTC)
    action = WorkflowAction.rehydrate(
        id=uuid4(),
        action_type=WorkflowActionType.REPLY,
        analysis_id=uuid4(),
        owner_user_id=uuid4(),
        proposed_reply_body="Thank you. I will follow up shortly.",
        approved_reply_body="Thank you. I will follow up shortly.",
        status=WorkflowActionStatus.EXECUTED,
        created_at=now,
        approved_at=now,
        executed_at=now,
    )
    payload = workflow_action_response(action).model_dump(mode="json")
    assert payload["status"] == "executed"
    assert payload["approved_reply_body"] == action.proposed_reply_body
    assert payload["executed_at"] is not None
    assert payload["has_execution_target"] is False
    assert "owner_user_id" not in payload
    assert "connector_account_id" not in payload
    assert "provider_message_id" not in payload


def test_workflow_action_response_exposes_executability_not_routing_ids() -> None:
    """Callers see has_execution_target without mailbox routing identifiers."""
    now = datetime.now(UTC)
    action = WorkflowAction(
        action_type=WorkflowActionType.REPLY,
        analysis_id=uuid4(),
        owner_user_id=uuid4(),
        proposed_reply_body="Thank you. I will follow up shortly.",
        created_at=now,
        connector_account_id=uuid4(),
        provider_message_id="provider-msg-001",
    )
    payload = workflow_action_response(action).model_dump(mode="json")
    assert payload["has_execution_target"] is True
    assert "connector_account_id" not in payload
    assert "provider_message_id" not in payload
    assert "credential_ref" not in payload

"""API schemas for workflow-action proposal and approval responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.enums import WorkflowActionStatus, WorkflowActionType
from app.domain.models.workflow import WorkflowAction


class WorkflowActionCreateRequest(BaseModel):
    """Create a reply workflow proposal from an owned analysis."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: UUID


class WorkflowActionResponse(BaseModel):
    """Owned workflow-action resource. Does not include identity fields."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    action_type: WorkflowActionType
    analysis_id: UUID
    status: WorkflowActionStatus
    proposed_reply_body: str
    approved_reply_body: str | None = None
    created_at: datetime
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    executed_at: datetime | None = None
    failed_at: datetime | None = None


class WorkflowActionListResponse(BaseModel):
    """Bounded page of owned workflow actions. Total count is omitted."""

    model_config = ConfigDict(extra="forbid")

    items: list[WorkflowActionResponse]
    limit: int
    offset: int


def workflow_action_response(action: WorkflowAction) -> WorkflowActionResponse:
    """Map a domain workflow action onto the HTTP response schema."""
    return WorkflowActionResponse(
        id=action.id,
        action_type=action.action_type,
        analysis_id=action.analysis_id,
        status=action.status,
        proposed_reply_body=action.proposed_reply_body,
        approved_reply_body=action.approved_reply_body,
        created_at=action.created_at,
        approved_at=action.approved_at,
        rejected_at=action.rejected_at,
        executed_at=action.executed_at,
        failed_at=action.failed_at,
    )

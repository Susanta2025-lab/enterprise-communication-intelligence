"""Strict manual tracking contracts. Authority fields are never client inputs."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.enums import WorkItemEventType, WorkItemKind, WorkItemOrigin, WorkItemStatus
from app.domain.models.business_work_item import BusinessWorkItem, WorkItemEdit
from app.domain.models.business_work_item_event import (
    ContextMetadata,
    CreatedMetadata,
    EditedMetadata,
    EmptyMetadata,
    StatusMetadata,
)
from app.domain.models.work_item_due import DueValue, FrozenValue, NoDue, due_json
from app.domain.models.work_item_intent import (
    canonical_json,
    creation_request_hash,
    description_text,
    title_text,
    validate_creation_key,
)
from app.domain.models.work_item_provenance import (
    AnalysisReference,
    CandidateSelection,
    SourceReference,
    WorkItemCandidate,
    WorkItemSourceDetail,
)


class WorkItemCreateRequest(FrozenValue):
    creation_key: str
    kind: WorkItemKind
    title: str
    description: str | None = None
    due: DueValue = NoDue()
    business_context_id: UUID | None = None
    sources: tuple[SourceReference, ...] = Field(default=(), max_length=10)

    _key = field_validator("creation_key")(validate_creation_key)
    _title = field_validator("title")(title_text)
    _description = field_validator("description")(description_text)

    def references(self):
        return self.sources

    @model_validator(mode="after")
    def distinct_sources(self):
        values = [canonical_json(s.source_values()) for s in self.references()]
        if len(values) != len(set(values)):
            raise ValueError("duplicate sources are not allowed")
        return self

    def request_hash(self):
        values = self.model_dump(mode="json", exclude={"creation_key", "candidate"})
        values.update(
            creation_origin="ai_confirmed"
            if isinstance(self, WorkItemFromAnalysisRequest)
            else "manual",
            confirmed=getattr(self, "confirmed", False),
            origin_candidate=(
                self.candidate.model_dump(mode="json")
                if isinstance(self, WorkItemFromAnalysisRequest)
                else None
            ),
            sources=[s.source_values() for s in self.references()],
            due=due_json(self.due),
        )
        return creation_request_hash(values)


class WorkItemFromAnalysisRequest(WorkItemCreateRequest):
    candidate: CandidateSelection
    confirmed: bool = Field(strict=True)
    due: DueValue
    sources: tuple[SourceReference, ...] = Field(default=(), max_length=9)

    @field_validator("confirmed")
    @classmethod
    def require_confirmation(cls, value):
        if not value:
            raise ValueError("explicit confirmation is required")
        return value

    def references(self):
        return (
            AnalysisReference(
                source_kind=self.candidate.source_kind,
                source_id=self.candidate.source_id,
                candidate=self.candidate,
            ),
            *self.sources,
        )


class WorkItemCandidateListResponse(FrozenValue):
    items: list[WorkItemCandidate]
    limit: int
    offset: int


class WorkItemPatchRequest(WorkItemEdit):
    expected_version: int = Field(ge=1, strict=True)


class WorkItemVersionRequest(FrozenValue):
    expected_version: int = Field(ge=1, strict=True)


class WorkItemStatusRequest(WorkItemVersionRequest):
    status: WorkItemStatus
    reopen: bool = Field(default=False, strict=True)


class WorkItemResponse(FrozenValue):
    id: UUID
    kind: WorkItemKind
    title: str
    description: str | None
    due: DueValue
    business_context_id: UUID | None
    status: WorkItemStatus
    completed_at: datetime | None
    cancelled_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
    creation_origin: WorkItemOrigin
    confirmed_at: datetime | None
    overdue: bool


class WorkItemDetailResponse(WorkItemResponse):
    sources: tuple[WorkItemSourceDetail, ...] = ()


class WorkItemListResponse(FrozenValue):
    items: list[WorkItemResponse]
    limit: int
    offset: int


class WorkItemEventResponse(FrozenValue):
    id: UUID
    work_item_id: UUID
    event_type: WorkItemEventType
    occurred_at: datetime
    item_version: int
    event_ordinal: int
    context_at_event_id: UUID | None
    metadata: CreatedMetadata | EditedMetadata | StatusMetadata | ContextMetadata | EmptyMetadata


class WorkItemEventListResponse(FrozenValue):
    items: list[WorkItemEventResponse]
    limit: int
    offset: int


def item_response(item: BusinessWorkItem, now: datetime, *, detail=False):
    model = WorkItemDetailResponse if detail else WorkItemResponse
    values = {f: getattr(item, f) for f in WorkItemResponse.model_fields if f != "overdue"}
    return model(**values, overdue=item.overdue(now))

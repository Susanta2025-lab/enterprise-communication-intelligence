"""Typed requested references and read-only candidate values; no content retrieval."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.models.business_work_item_source import CandidateLocator, WorkItemSource
from app.domain.models.work_item_due import FrozenValue


class CandidateSelection(CandidateLocator):
    """Public selections must explicitly state their projection version."""

    projection_version: Literal[1]


class CommunicationReference(FrozenValue):
    source_kind: Literal["communication"]
    connector_account_id: UUID
    provider_message_id: str

    _opaque = field_validator("provider_message_id")(WorkItemSource.opaque_id.__func__)

    def source_values(self):
        return WorkItemSource(**self.model_dump()).model_dump(mode="json")


class AnalysisReference(FrozenValue):
    source_kind: Literal["communication_analysis", "attachment_analysis"]
    source_id: UUID
    candidate: CandidateSelection | None = None

    @model_validator(mode="after")
    def matching_candidate(self) -> Self:
        if self.candidate and (
            self.candidate.source_kind != self.source_kind
            or self.candidate.source_id != self.source_id
        ):
            raise ValueError("candidate must reference the selected source")
        return self

    def source_values(self):
        values = {name: None for name in WorkItemSource.model_fields}
        values["source_kind"] = self.source_kind
        values[
            "analysis_id"
            if self.source_kind == "communication_analysis"
            else "attachment_analysis_id"
        ] = str(self.source_id)
        if self.candidate:
            values.update(
                candidate_field=self.candidate.field,
                candidate_index=self.candidate.index,
                candidate_digest=self.candidate.digest,
            )
        return values


SourceReference = Annotated[
    CommunicationReference | AnalysisReference, Field(discriminator="source_kind")
]


class CandidateQuery(FrozenValue):
    source_kind: Literal["communication_analysis", "attachment_analysis"]
    source_id: UUID
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class WorkItemCandidate(FrozenValue):
    candidate: CandidateLocator
    value: dict[str, object] | str
    advisory: Literal[True] = True
    truncated: bool = False
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class WorkItemSourceDetail(FrozenValue):
    source_kind: Literal["communication", "communication_analysis", "attachment_analysis"]
    analysis_id: UUID | None = None
    attachment_analysis_id: UUID | None = None
    connector_account_id: UUID | None = None
    provider_message_id: str | None = None
    provider_attachment_id: str | None = None
    candidate_field: str | None = None
    candidate_index: int | None = None
    availability: Literal["available", "unavailable"]
    # Metadata verification never asserts continued provider-content existence.
    provider_content_verified: Literal[False] = False

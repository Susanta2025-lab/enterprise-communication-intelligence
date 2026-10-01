"""Immutable typed provenance. Opaque references intentionally outlive sources."""

from typing import Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.enums import WorkItemSourceKind
from app.domain.models.work_item_due import FrozenValue

Digest = str
CandidateField = Literal["action_items", "potential_action_mentions", "potential_dates"]


def validate_digest(value: str) -> str:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid SHA-256 digest")
    return value


class CandidateLocator(FrozenValue):
    projection_version: Literal[1] = 1
    source_kind: Literal["communication_analysis", "attachment_analysis"]
    source_id: UUID
    field: CandidateField
    index: int = Field(ge=0, strict=True)
    digest: str

    @field_validator("projection_version", mode="before")
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("unsupported projection version")
        return value

    _digest = field_validator("digest")(validate_digest)

    @model_validator(mode="after")
    def field_matches(self) -> Self:
        if self.source_kind == "communication_analysis" and self.field != "action_items":
            raise ValueError("invalid candidate field")
        return self


class WorkItemSource(FrozenValue):
    source_kind: WorkItemSourceKind
    analysis_id: UUID | None = None
    attachment_analysis_id: UUID | None = None
    connector_account_id: UUID | None = None
    provider_message_id: str | None = None
    provider_attachment_id: str | None = None
    candidate_field: CandidateField | None = None
    candidate_index: int | None = Field(default=None, ge=0, strict=True)
    candidate_digest: str | None = None

    @field_validator("provider_message_id", "provider_attachment_id")
    @classmethod
    def opaque_id(cls, value):
        if value is not None and (not value.strip() or len(value) > 2048):
            raise ValueError("invalid provider identifier")
        return value  # Never trim or case-fold provider identity.

    @field_validator("candidate_digest")
    @classmethod
    def digest(cls, value):
        return None if value is None else validate_digest(value)

    @model_validator(mode="after")
    def typed_reference(self) -> Self:
        pair = (self.connector_account_id is not None, self.provider_message_id is not None)
        locator = (self.candidate_field, self.candidate_index, self.candidate_digest)
        if any(v is not None for v in locator) and not all(v is not None for v in locator):
            raise ValueError("incomplete candidate locator")
        if pair[0] != pair[1]:
            raise ValueError("incomplete mailbox provenance")
        if self.source_kind == WorkItemSourceKind.COMMUNICATION:
            valid = (
                all(pair)
                and self.analysis_id is None
                and self.attachment_analysis_id is None
                and self.provider_attachment_id is None
                and self.candidate_field is None
            )
        elif self.source_kind == WorkItemSourceKind.COMMUNICATION_ANALYSIS:
            valid = (
                self.analysis_id is not None
                and self.attachment_analysis_id is None
                and self.provider_attachment_id is None
                and self.candidate_field in (None, "action_items")
            )
        else:
            valid = (
                self.analysis_id is None
                and self.attachment_analysis_id is not None
                and all(pair)
                and self.provider_attachment_id is not None
            )
        if not valid:
            raise ValueError("invalid typed source reference")
        return self

    def locator(self) -> CandidateLocator | None:
        if self.candidate_field is None:
            return None
        return CandidateLocator(
            source_kind=self.source_kind.value,
            source_id=self.analysis_id or self.attachment_analysis_id,
            field=self.candidate_field,
            index=self.candidate_index,
            digest=self.candidate_digest,
        )

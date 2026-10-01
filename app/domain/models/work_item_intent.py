"""Validated, versioned creation intent and deterministic identity helpers."""

import hashlib
import json
import re
from typing import Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.enums import WorkItemKind, WorkItemOrigin
from app.domain.models.business_work_item_source import CandidateLocator, WorkItemSource
from app.domain.models.work_item_due import DueValue, FrozenValue, NoDue, due_json


def canonical_json(value: object) -> str:
    """Internal canonical encoding; callers supply validated typed values only."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def source_key(source: WorkItemSource) -> str:
    source = WorkItemSource.model_validate(source.model_dump())
    return _hash({"canonicalization_version": 1, "source": source.model_dump(mode="json")})


def origin_candidate_key(locator: CandidateLocator) -> str:
    locator = CandidateLocator.model_validate(locator.model_dump())
    return _hash(locator.model_dump(mode="json"))


def validate_creation_key(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._~-]{1,128}", value, flags=re.ASCII):
        raise ValueError("invalid creation key")
    return value


def title_text(value: str) -> str:
    value = value.strip()
    if not 1 <= len(value) <= 200:
        raise ValueError("title must contain 1–200 characters")
    return value


def description_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) > 4000:
        raise ValueError("description exceeds 4000 characters")
    return value or None


class CreationIntent(FrozenValue):
    """No owner, actor, key, server timestamp or unvalidated arbitrary payload."""

    creation_origin: WorkItemOrigin = WorkItemOrigin.MANUAL
    kind: WorkItemKind
    title: str
    description: str | None = None
    due: DueValue = NoDue()
    business_context_id: UUID | None = None
    sources: tuple[WorkItemSource, ...] = ()
    origin_candidate: CandidateLocator | None = None
    confirmed: bool = Field(default=False, strict=True)

    _title = field_validator("title")(title_text)
    _description = field_validator("description")(description_text)

    @model_validator(mode="after")
    def provenance(self) -> Self:
        if len(self.sources) > 10 or len({source_key(s) for s in self.sources}) != len(
            self.sources
        ):
            raise ValueError("at most ten distinct sources are allowed")
        if self.creation_origin == WorkItemOrigin.MANUAL:
            if self.confirmed or self.origin_candidate is not None:
                raise ValueError("manual creation cannot claim AI confirmation")
        elif (
            not self.confirmed
            or self.origin_candidate is None
            or not any(s.locator() == self.origin_candidate for s in self.sources)
        ):
            raise ValueError("AI confirmation requires its designated origin source")
        return self

    def request_hash(self) -> str:
        validated = CreationIntent.model_validate(self.model_dump())
        intent = validated.model_dump(mode="json")
        intent["due"] = due_json(validated.due)
        return creation_request_hash(intent)


def creation_request_hash(intent: dict) -> str:
    """Hash requested references, excluding provenance loaded by the server later."""
    intent = dict(intent)
    sources = []
    for value in intent["sources"]:
        value = dict(value)
        if value["source_kind"] != "communication":
            for field in ("connector_account_id", "provider_message_id", "provider_attachment_id"):
                value[field] = None
        sources.append(value)
    intent["sources"] = sorted(sources, key=canonical_json)
    return _hash({"canonicalization_version": 1, "intent": intent})


def candidate_digest(value: dict[str, object] | str, *, field: str | None = None) -> str:
    """Hash a validated persisted observation without altering its stored JSON.

    Validation does not substitute a normalized model dump: absent optional keys,
    advisory date spelling and the exact stored string remain part of identity.
    This helper does not project, locate or confirm candidates.
    """
    from app.domain.models.analysis import ActionItem

    if isinstance(value, dict):
        if field not in (None, "action_items"):
            raise ValueError("invalid candidate field")
        ActionItem.model_validate(value)
    elif isinstance(value, str):
        if field not in (None, "potential_action_mentions", "potential_dates"):
            raise ValueError("invalid candidate field")
        maximum = 300 if field == "potential_action_mentions" else 200
        if not value.strip() or len(value) > maximum:
            raise ValueError("invalid persisted tabular observation")
    else:
        raise ValueError("unsupported persisted candidate value")
    return _hash(value)

"""Structured output schema and mapping for LLM tabular / XLSX analysis."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.schemas.tabular_analysis import (
    TabularAnalysisRequest,
    TabularAnalysisResult,
    TabularSheetSummary,
)

_MAX_SHEET_SUMMARIES = 10
_MAX_IMPORTANT_FIELDS = 20
_MAX_NOTABLE = 20
_MAX_DATA_QUALITY = 15
_MAX_DATES = 15
_MAX_AMOUNTS = 15
_MAX_ACTIONS = 15
_MAX_WARNINGS = 20
_MAX_LIMITATIONS = 10


class TabularAnalysisOutputError(ValueError):
    """Raised when an AI provider returns unusable tabular analysis output."""


class TabularSheetSummaryOutput(BaseModel):
    """Sheet summary fields requested from the model."""

    model_config = ConfigDict(extra="forbid")

    sheet_name: str = ""
    summary: str


class TabularAnalysisOutput(BaseModel):
    """Strict JSON shape requested from an LLM tabular analysis provider."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    sheet_summaries: list[TabularSheetSummaryOutput] = Field(default_factory=list)
    important_fields: list[str] = Field(default_factory=list)
    notable_values_or_patterns: list[str] = Field(default_factory=list)
    data_quality_observations: list[str] = Field(default_factory=list)
    potential_dates: list[str] = Field(default_factory=list)
    potential_amounts: list[str] = Field(default_factory=list)
    potential_action_mentions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_truncated: bool


def parse_tabular_analysis_output(output_text: str) -> TabularAnalysisOutput:
    """Parse and validate model output against the tabular analysis schema."""
    if not output_text.strip():
        raise TabularAnalysisOutputError(
            "AI provider returned an empty tabular analysis response."
        )

    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise TabularAnalysisOutputError(
            "AI provider returned malformed JSON."
        ) from exc

    try:
        return TabularAnalysisOutput.model_validate(payload)
    except ValidationError as exc:
        raise TabularAnalysisOutputError(
            "AI provider returned JSON that does not match the tabular analysis schema."
        ) from exc


def to_tabular_analysis_result(
    output: TabularAnalysisOutput,
    request: TabularAnalysisRequest,
    *,
    provider: str,
) -> TabularAnalysisResult:
    """Map validated LLM output onto the domain tabular analysis result.

    Applies provider-neutral output bounds. Forces ``source_truncated`` true when
    the request already indicated truncation, even if the model omits it.
    """
    try:
        sheet_summaries = [
            TabularSheetSummary(
                sheet_name=(item.sheet_name or "").strip()[:200],
                summary=_bounded_text(item.summary, 500) or "Sheet summary unavailable.",
            )
            for item in output.sheet_summaries[:_MAX_SHEET_SUMMARIES]
            if (item.summary or "").strip()
        ]
        summary = _bounded_text(output.summary, 2_000)
        if not summary:
            raise TabularAnalysisOutputError(
                "AI provider returned an empty tabular summary."
            )

        source_truncated = bool(output.source_truncated or request.source_truncated)
        return TabularAnalysisResult(
            summary=summary,
            sheet_summaries=sheet_summaries,
            important_fields=_bounded_string_list(
                output.important_fields, _MAX_IMPORTANT_FIELDS, 200
            ),
            notable_values_or_patterns=_bounded_string_list(
                output.notable_values_or_patterns, _MAX_NOTABLE, 300
            ),
            data_quality_observations=_bounded_string_list(
                output.data_quality_observations, _MAX_DATA_QUALITY, 300
            ),
            potential_dates=_bounded_string_list(
                output.potential_dates, _MAX_DATES, 200
            ),
            potential_amounts=_bounded_string_list(
                output.potential_amounts, _MAX_AMOUNTS, 200
            ),
            potential_action_mentions=_bounded_string_list(
                output.potential_action_mentions, _MAX_ACTIONS, 300
            ),
            warnings=_bounded_string_list(output.warnings, _MAX_WARNINGS, 200),
            limitations=_bounded_string_list(
                output.limitations, _MAX_LIMITATIONS, 300
            ),
            source_truncated=source_truncated,
            provider=provider,
        )
    except TabularAnalysisOutputError:
        raise
    except ValidationError as exc:
        raise TabularAnalysisOutputError(
            "AI provider returned tabular analysis that failed domain validation."
        ) from exc


def _bounded_text(value: str, max_length: int) -> str:
    text = (value or "").strip()
    if len(text) > max_length:
        return text[:max_length].rstrip()
    return text


def _bounded_string_list(
    values: list[str],
    max_items: int,
    max_length: int,
) -> list[str]:
    result: list[str] = []
    for raw in values[:max_items]:
        item = _bounded_text(raw, max_length)
        if item:
            result.append(item)
    return result

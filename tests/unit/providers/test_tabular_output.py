"""Structured-output validation tests for Phase 21C tabular analysis."""

from __future__ import annotations

import json

import pytest

from app.providers.common.tabular_input import prepare_tabular_analysis_request_from_text
from app.providers.common.tabular_output import (
    TabularAnalysisOutputError,
    parse_tabular_analysis_output,
    to_tabular_analysis_result,
)


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "summary": "Bounded workbook sample covering sales figures.",
        "sheet_summaries": [{"sheet_name": "Sales", "summary": "Two product rows."}],
        "important_fields": ["Item", "Amount"],
        "notable_values_or_patterns": ["Repeated product names"],
        "data_quality_observations": ["One blank amount cell"],
        "potential_dates": ["2026-09-01 observed in sample"],
        "potential_amounts": ["€50,000 mentioned in a cell"],
        "potential_action_mentions": ["Text resembling approve payment"],
        "warnings": ["xlsx_formulas_present"],
        "limitations": ["Sample may be truncated"],
        "source_truncated": False,
    }
    payload.update(overrides)
    return payload


def _request(*, truncated: bool = False):
    return prepare_tabular_analysis_request_from_text(
        "WORKBOOK\nSHEET 1\nname: Sales\n---\nA | 1\n",
        parser_truncated=truncated,
    )


def test_parse_valid_tabular_output() -> None:
    output = parse_tabular_analysis_output(json.dumps(_valid_payload()))
    result = to_tabular_analysis_result(output, _request(), provider="test")
    assert result.summary.startswith("Bounded workbook")
    assert len(result.sheet_summaries) == 1
    assert result.sheet_summaries[0].sheet_name == "Sales"
    assert result.source_truncated is False
    assert result.provider == "test"


def test_request_truncation_forces_result_flag() -> None:
    output = parse_tabular_analysis_output(
        json.dumps(_valid_payload(source_truncated=False))
    )
    result = to_tabular_analysis_result(
        output, _request(truncated=True), provider="test"
    )
    assert result.source_truncated is True


def test_empty_and_malformed_and_prose_fail() -> None:
    with pytest.raises(TabularAnalysisOutputError, match="empty"):
        parse_tabular_analysis_output("   ")
    with pytest.raises(TabularAnalysisOutputError, match="malformed"):
        parse_tabular_analysis_output("{not-json")
    with pytest.raises(TabularAnalysisOutputError, match="malformed"):
        parse_tabular_analysis_output("Here is a prose answer instead of JSON.")
    with pytest.raises(TabularAnalysisOutputError, match="malformed"):
        parse_tabular_analysis_output('{"summary": "partial"')


def test_missing_required_field_and_wrong_types() -> None:
    with pytest.raises(TabularAnalysisOutputError, match="does not match"):
        parse_tabular_analysis_output(json.dumps({"summary": "only"}))
    with pytest.raises(TabularAnalysisOutputError, match="does not match"):
        parse_tabular_analysis_output(
            json.dumps(_valid_payload(source_truncated=["not-a-bool"]))
        )
    with pytest.raises(TabularAnalysisOutputError, match="does not match"):
        parse_tabular_analysis_output(
            json.dumps(_valid_payload(important_fields="Item"))
        )


def test_unexpected_field_rejected() -> None:
    payload = _valid_payload()
    payload["extra_secret"] = "nope"
    with pytest.raises(TabularAnalysisOutputError, match="does not match"):
        parse_tabular_analysis_output(json.dumps(payload))


def test_excessive_lists_and_strings_are_bounded() -> None:
    payload = _valid_payload(
        important_fields=[f"field-{i}" for i in range(50)],
        potential_dates=[f"date-{i}" for i in range(40)],
        summary="S" * 5_000,
        sheet_summaries=[
            {"sheet_name": f"S{i}", "summary": "ok"} for i in range(25)
        ],
    )
    output = parse_tabular_analysis_output(json.dumps(payload))
    result = to_tabular_analysis_result(output, _request(), provider="test")
    assert len(result.important_fields) <= 20
    assert len(result.potential_dates) <= 15
    assert len(result.summary) <= 2_000
    assert len(result.sheet_summaries) <= 10

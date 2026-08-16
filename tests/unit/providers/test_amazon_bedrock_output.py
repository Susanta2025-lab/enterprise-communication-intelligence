"""Unit tests for Amazon Bedrock schema serialization and Converse extraction."""

import json

import pytest

from app.providers.amazon_bedrock.output import (
    BEDROCK_ANALYSIS_JSON_SCHEMA,
    BedrockOutputError,
    extract_converse_output_text,
)
from app.providers.common.output import AnalysisOutput

_EXPECTED_FIELDS = (
    "summary_text",
    "summary_confidence",
    "priority_level",
    "priority_rationale",
    "priority_confidence",
    "category",
    "action_items",
    "draft_reply",
)


def test_bedrock_schema_is_json_string_from_shared_analysis_output() -> None:
    """The Bedrock schema must be a JSON string derived from AnalysisOutput."""
    parsed = json.loads(BEDROCK_ANALYSIS_JSON_SCHEMA)

    assert isinstance(BEDROCK_ANALYSIS_JSON_SCHEMA, str)
    assert parsed == AnalysisOutput.model_json_schema()
    assert parsed["type"] == "object"
    assert parsed.get("additionalProperties") is False
    for field_name in _EXPECTED_FIELDS:
        assert field_name in parsed["properties"]


def test_bedrock_schema_nested_objects_forbid_additional_properties() -> None:
    """Nested object definitions used by Bedrock should reject extra fields."""
    parsed = json.loads(BEDROCK_ANALYSIS_JSON_SCHEMA)
    definitions = parsed.get("$defs", {})

    for name in ("AnalysisActionItemOutput", "AnalysisDraftReplyOutput"):
        assert definitions[name]["type"] == "object"
        assert definitions[name].get("additionalProperties") is False


def test_extract_converse_output_text_returns_first_valid_text() -> None:
    """The first usable text block should be returned."""
    response = {"output": {"message": {"content": [{"text": '{"ok": true}'}]}}}

    assert extract_converse_output_text(response) == '{"ok": true}'


def test_extract_converse_output_text_skips_non_text_blocks() -> None:
    """Non-text content blocks should be ignored until a text block is found."""
    response = {
        "output": {
            "message": {
                "content": [
                    {"toolUse": {"name": "unused"}},
                    {"text": "usable analysis json"},
                ]
            }
        }
    }

    assert extract_converse_output_text(response) == "usable analysis json"


@pytest.mark.parametrize("skipped_text", ["", "   ", "\n\t"])
def test_extract_converse_output_text_skips_empty_or_whitespace_text(
    skipped_text: str,
) -> None:
    """Empty and whitespace-only text blocks must not be treated as output."""
    response = {
        "output": {
            "message": {
                "content": [
                    {"text": skipped_text},
                    {"text": "usable analysis json"},
                ]
            }
        }
    }

    assert extract_converse_output_text(response) == "usable analysis json"


@pytest.mark.parametrize(
    "response",
    [
        None,
        "not-a-mapping",
        [],
        {},
        {"output": None},
        {"output": []},
        {"output": {}},
        {"output": {"message": None}},
        {"output": {"message": []}},
        {"output": {"message": {}}},
        {"output": {"message": {"content": None}}},
        {"output": {"message": {"content": "not-a-list"}}},
        {"output": {"message": {"content": []}}},
        {"output": {"message": {"content": [{"toolUse": {"name": "unused"}}]}}},
        {"output": {"message": {"content": [{"text": ""}]}}},
        {"output": {"message": {"content": [{"text": "   "}]}}},
    ],
)
def test_extract_converse_output_text_rejects_unusable_responses(response: object) -> None:
    """Missing or unusable Converse shapes must raise BedrockOutputError."""
    with pytest.raises(BedrockOutputError):
        extract_converse_output_text(response)

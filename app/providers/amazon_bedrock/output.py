"""Bedrock-specific structured-output schema and Converse response extraction."""

import json
from collections.abc import Mapping
from typing import Any

from app.providers.common.output import AnalysisOutput

# Pydantic already emits additionalProperties=false for extra="forbid" models,
# which Amazon Bedrock structured output requires. The schema is serialized as
# a JSON string because Converse outputConfig.textFormat.structure.jsonSchema.schema
# is a string field, not a Python dict.


class BedrockOutputError(ValueError):
    """Raised when Amazon Bedrock returns an unusable Converse response shape."""


def build_bedrock_json_schema() -> str:
    """Serialize the shared analysis schema for Bedrock Converse structured output."""
    return json.dumps(AnalysisOutput.model_json_schema(), separators=(",", ":"), sort_keys=True)


def extract_converse_output_text(response: Any) -> str:
    """Return the first text block from a Converse response.

    Expected shape::

        response["output"]["message"]["content"][*]["text"]
    """
    if not isinstance(response, Mapping):
        raise BedrockOutputError(
            "Amazon Bedrock returned a response without structured text output."
        )

    output = response.get("output")
    if not isinstance(output, Mapping):
        raise BedrockOutputError(
            "Amazon Bedrock returned a response without structured text output."
        )

    message = output.get("message")
    if not isinstance(message, Mapping):
        raise BedrockOutputError(
            "Amazon Bedrock returned a response without structured text output."
        )

    content = message.get("content")
    if not isinstance(content, list):
        raise BedrockOutputError(
            "Amazon Bedrock returned a response without structured text output."
        )

    for block in content:
        if not isinstance(block, Mapping):
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            return text

    raise BedrockOutputError("Amazon Bedrock returned a response without structured text output.")


BEDROCK_ANALYSIS_JSON_SCHEMA = build_bedrock_json_schema()

"""OpenAI-strict JSON Schema transformation for Microsoft Foundry."""

from typing import Any

from pydantic import BaseModel

from app.providers.common.output import AnalysisOutput

_UNSUPPORTED_SCHEMA_KEYS = (
    "title",
    "default",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "pattern",
    "format",
)


def build_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic model into an OpenAI-strict JSON schema."""
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})
    _make_schema_strict(schema)
    for definition in definitions.values():
        if isinstance(definition, dict):
            _make_schema_strict(definition)
    if definitions:
        schema["$defs"] = definitions
    return schema


def _make_schema_strict(schema: dict[str, Any]) -> None:
    """Normalize a JSON schema fragment for strict structured output."""
    for key in _UNSUPPORTED_SCHEMA_KEYS:
        schema.pop(key, None)

    if "properties" in schema:
        schema["type"] = "object"
        schema["additionalProperties"] = False
        properties = schema["properties"]
        schema["required"] = list(properties)
        for subschema in properties.values():
            if isinstance(subschema, dict):
                _make_schema_strict(subschema)

    items = schema.get("items")
    if isinstance(items, dict):
        _make_schema_strict(items)

    for combinator in ("anyOf", "oneOf", "allOf"):
        for subschema in schema.get(combinator, []):
            if isinstance(subschema, dict):
                _make_schema_strict(subschema)


FOUNDRY_ANALYSIS_JSON_SCHEMA = build_strict_json_schema(AnalysisOutput)

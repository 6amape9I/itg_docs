from __future__ import annotations

from copy import deepcopy
from typing import Any


GEMINI_SCHEMA_META_KEYS = {"$schema", "$id", "schema_version"}
GEMINI_SCHEMA_UNSUPPORTED_KEYS = {
    "additionalProperties",
    "patternProperties",
    "unevaluatedProperties",
    "propertyNames",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
    "dependentRequired",
    "dependentSchemas",
    "examples",
    "default",
}
GEMINI_SCHEMA_LITE_KEYS = {
    "title",
    "description",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
}


def schema_for_gemini(schema: dict[str, Any], *, lite: bool = False) -> dict[str, Any]:
    """Return the Gemini structured-output subset of the local strict schema."""
    cleaned = _clean_schema(deepcopy(schema), lite=lite)
    if not isinstance(cleaned, dict):
        raise ValueError("Gemini schema must be an object")
    return cleaned


def _clean_schema(value: Any, *, lite: bool) -> Any:
    if isinstance(value, list):
        return [_clean_schema(item, lite=lite) for item in value]
    if not isinstance(value, dict):
        return value

    dropped = set(GEMINI_SCHEMA_META_KEYS) | set(GEMINI_SCHEMA_UNSUPPORTED_KEYS) | set(GEMINI_SCHEMA_LITE_KEYS)
    if lite:
        dropped |= GEMINI_SCHEMA_LITE_KEYS

    result: dict[str, Any] = {}
    for key, item in value.items():
        if key in dropped:
            continue
        if key == "properties" and isinstance(item, dict):
            result[key] = {prop_name: _clean_schema(prop_schema, lite=lite) for prop_name, prop_schema in item.items()}
            continue
        result[key] = _clean_schema(item, lite=lite)
    return result

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ENTITY_FIELDS = {
    "surface",
    "canonical_candidate_ru",
    "canonical_candidate_latin",
    "entity_type",
    "is_primary",
    "confidence",
    "evidence_quotes",
    "comment",
}


def load_document_tagging_schema(schema_path: Path | None = None) -> dict[str, Any]:
    if schema_path is None:
        schema_path = Path(__file__).parent / "schemas" / "document_tagging.schema.json"
    with schema_path.open("r", encoding="utf-8") as fh:
        schema = json.load(fh)
    if not isinstance(schema, dict):
        raise ValueError(f"schema must be an object: {schema_path}")
    return schema


def schema_version(schema: dict[str, Any]) -> str:
    value = schema.get("schema_version")
    if not isinstance(value, str) or not value:
        raise ValueError("document tagging schema must contain schema_version")
    return value


def schema_for_openrouter(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in schema.items()
        if key not in {"$schema", "$id", "schema_version"}
    }


def allowed_entity_types(schema: dict[str, Any]) -> set[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return set()
    entities = properties.get("entities")
    if not isinstance(entities, dict):
        return set()
    items = entities.get("items")
    if not isinstance(items, dict):
        return set()
    item_properties = items.get("properties")
    if not isinstance(item_properties, dict):
        return set()
    entity_type = item_properties.get("entity_type")
    if not isinstance(entity_type, dict):
        return set()
    enum = entity_type.get("enum")
    if not isinstance(enum, list):
        return set()
    return {value for value in enum if isinstance(value, str)}


def validate_tagging_response(
    value: Any,
    schema: dict[str, Any],
    expected_doc_id: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["response must be an object"]

    allowed_top_fields = {"doc_id", "entities"}
    for field_name in value:
        if field_name not in allowed_top_fields:
            errors.append(f"unexpected top-level field: {field_name}")

    doc_id = value.get("doc_id")
    if not isinstance(doc_id, str) or not doc_id:
        errors.append("doc_id must be a non-empty string")
    elif expected_doc_id is not None and doc_id != expected_doc_id:
        errors.append(f"doc_id mismatch: expected {expected_doc_id}, got {doc_id}")

    entities = value.get("entities")
    if not isinstance(entities, list):
        errors.append("entities must be an array")
        return errors
    if len(entities) > 20:
        errors.append("entities must contain no more than 20 items")

    allowed_types = allowed_entity_types(schema)
    for index, entity in enumerate(entities):
        context = f"entities[{index}]"
        if not isinstance(entity, dict):
            errors.append(f"{context} must be an object")
            continue
        for field_name in entity:
            if field_name not in ENTITY_FIELDS:
                errors.append(f"{context}: unexpected field {field_name}")
        _validate_string(entity, "surface", context, errors, min_length=1)
        _validate_string(entity, "canonical_candidate_ru", context, errors, min_length=1)
        _validate_string(entity, "canonical_candidate_latin", context, errors, min_length=0)
        entity_type = entity.get("entity_type")
        if not isinstance(entity_type, str) or entity_type not in allowed_types:
            errors.append(f"{context}: invalid entity_type {entity_type!r}")
        if not isinstance(entity.get("is_primary"), bool):
            errors.append(f"{context}: is_primary must be boolean")
        confidence = entity.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            errors.append(f"{context}: confidence must be number")
        elif confidence < 0 or confidence > 1:
            errors.append(f"{context}: confidence must be between 0 and 1")
        quotes = entity.get("evidence_quotes")
        if not isinstance(quotes, list):
            errors.append(f"{context}: evidence_quotes must be array")
        else:
            if not quotes:
                errors.append(f"{context}: evidence_quotes must contain at least one quote")
            for quote_index, quote in enumerate(quotes):
                if not isinstance(quote, str) or not quote.strip():
                    errors.append(f"{context}.evidence_quotes[{quote_index}] must be non-empty string")
        _validate_string(entity, "comment", context, errors, min_length=1)

    return errors


def _validate_string(
    entity: dict[str, Any],
    field_name: str,
    context: str,
    errors: list[str],
    min_length: int,
) -> None:
    value = entity.get(field_name)
    if not isinstance(value, str):
        errors.append(f"{context}: {field_name} must be string")
    elif len(value.strip()) < min_length:
        errors.append(f"{context}: {field_name} is too short")


from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ENTITY_FIELDS = {
    "surface",
    "canonical_candidate_ru",
    "canonical_candidate_latin",
    "entity_type",
    "article_candidate",
    "tag_role",
    "is_primary",
    "confidence",
    "evidence_quotes",
    "comment",
}


def load_document_tagging_schema(schema_path: Path | None = None) -> dict[str, Any]:
    if schema_path is None:
        schema_path = Path(__file__).parent / "schemas" / "document_tagging.schema.json"
    return _load_schema(schema_path)


def load_document_tagging_v2_schema() -> dict[str, Any]:
    return _load_schema(Path(__file__).parent / "schemas" / "document_tagging_v2.schema.json")


def load_document_tagging_batch_v2_schema() -> dict[str, Any]:
    return _load_schema(Path(__file__).parent / "schemas" / "document_tagging_batch_v2.schema.json")


def load_compact_document_tagging_schema() -> dict[str, Any]:
    return _load_schema(Path(__file__).parent / "schemas" / "compact_document_tagging.schema.json")


def _load_schema(schema_path: Path) -> dict[str, Any]:
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


def schema_for_openrouter_lite(schema: dict[str, Any]) -> dict[str, Any]:
    return _schema_lite(schema_for_openrouter(schema))


def _schema_lite(value: Any) -> Any:
    if isinstance(value, list):
        return [_schema_lite(item) for item in value]
    if not isinstance(value, dict):
        return value
    stripped = {
        key: _schema_lite(item)
        for key, item in value.items()
        if key not in {"minLength", "maxLength", "minItems", "maxItems", "minimum", "maximum", "additionalProperties"}
    }
    return stripped


def allowed_entity_types(schema: dict[str, Any]) -> set[str]:
    item_properties = _entity_properties(schema)
    entity_type = item_properties.get("entity_type")
    if not isinstance(entity_type, dict):
        return set()
    enum = entity_type.get("enum")
    if not isinstance(enum, list):
        return set()
    return {value for value in enum if isinstance(value, str)}


def allowed_tag_roles(schema: dict[str, Any]) -> set[str]:
    item_properties = _entity_properties(schema)
    tag_role = item_properties.get("tag_role")
    if not isinstance(tag_role, dict):
        return set()
    enum = tag_role.get("enum")
    if not isinstance(enum, list):
        return set()
    return {value for value in enum if isinstance(value, str)}


def _entity_properties(schema: dict[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    documents = properties.get("documents")
    if isinstance(documents, dict):
        document_items = documents.get("items")
        if isinstance(document_items, dict):
            properties = document_items.get("properties")
            if not isinstance(properties, dict):
                return {}
    entities = properties.get("entities")
    if not isinstance(entities, dict):
        return {}
    items = entities.get("items")
    if not isinstance(items, dict):
        return {}
    item_properties = items.get("properties")
    if not isinstance(item_properties, dict):
        return {}
    return item_properties


def required_entity_fields(schema: dict[str, Any]) -> set[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return set()
    documents = properties.get("documents")
    if isinstance(documents, dict):
        document_items = documents.get("items")
        if isinstance(document_items, dict):
            properties = document_items.get("properties")
            if not isinstance(properties, dict):
                return set()
    entities = properties.get("entities")
    if not isinstance(entities, dict):
        return set()
    items = entities.get("items")
    if not isinstance(items, dict):
        return set()
    required = items.get("required")
    if not isinstance(required, list):
        return set()
    return {field for field in required if isinstance(field, str)}


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

    allowed_fields = set(_entity_properties(schema)) or ENTITY_FIELDS
    allowed_types = allowed_entity_types(schema)
    allowed_roles = allowed_tag_roles(schema)
    required_fields = required_entity_fields(schema)
    for index, entity in enumerate(entities):
        context = f"entities[{index}]"
        if not isinstance(entity, dict):
            errors.append(f"{context} must be an object")
            continue
        for field_name in entity:
            if field_name not in allowed_fields:
                errors.append(f"{context}: unexpected field {field_name}")
        for field_name in sorted(required_fields):
            if field_name not in entity:
                errors.append(f"{context}: missing required field {field_name}")
        _validate_string(entity, "surface", context, errors, min_length=1)
        _validate_string(entity, "canonical_candidate_ru", context, errors, min_length=1)
        _validate_string(entity, "canonical_candidate_latin", context, errors, min_length=0)
        entity_type = entity.get("entity_type")
        if not isinstance(entity_type, str) or entity_type not in allowed_types:
            errors.append(f"{context}: invalid entity_type {entity_type!r}")
        if allowed_roles:
            tag_role = entity.get("tag_role")
            if not isinstance(tag_role, str) or tag_role not in allowed_roles:
                errors.append(f"{context}: invalid tag_role {tag_role!r}")
        if "article_candidate" in required_fields and not isinstance(entity.get("article_candidate"), bool):
            errors.append(f"{context}: article_candidate must be boolean")
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


def validate_tagging_batch_response(
    value: Any,
    schema: dict[str, Any],
    expected_doc_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["batch response must be an object"]
    for field_name in value:
        if field_name != "documents":
            errors.append(f"unexpected top-level field: {field_name}")
    documents = value.get("documents")
    if not isinstance(documents, list):
        return errors + ["documents must be an array"]
    seen_doc_ids: set[str] = set()
    document_schema = {
        key: schema[key]
        for key in ("$schema", "$id", "schema_version", "title")
        if key in schema
    }
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        documents_property = properties.get("documents", {})
        if isinstance(documents_property, dict):
            document_items = documents_property.get("items", {})
            if isinstance(document_items, dict):
                document_schema.update(document_items)
    for index, document in enumerate(documents):
        doc_id = document.get("doc_id") if isinstance(document, dict) else None
        context = f"documents[{index}]"
        if isinstance(doc_id, str):
            if doc_id in seen_doc_ids:
                errors.append(f"{context}: duplicate doc_id {doc_id}")
            seen_doc_ids.add(doc_id)
            if doc_id not in expected_doc_ids:
                errors.append(f"{context}: unexpected doc_id {doc_id}")
        errors.extend(f"{context}: {error}" for error in validate_tagging_response(document, document_schema))
    missing = expected_doc_ids - seen_doc_ids
    for doc_id in sorted(missing):
        errors.append(f"missing doc_id {doc_id}")
    return errors


def validate_compact_batch_response(
    value: Any,
    schema: dict[str, Any],
    expected_doc_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["compact batch response must be an object"]
    for field_name in value:
        if field_name != "docs":
            errors.append(f"unexpected top-level field: {field_name}")
    docs = value.get("docs")
    if not isinstance(docs, list):
        return errors + ["docs must be an array"]
    allowed_types = _compact_allowed_values(schema, "t")
    allowed_roles = _compact_allowed_values(schema, "r")
    seen_doc_ids: set[str] = set()
    for doc_index, document in enumerate(docs):
        context = f"docs[{doc_index}]"
        if not isinstance(document, dict):
            errors.append(f"{context} must be an object")
            continue
        for field_name in document:
            if field_name not in {"d", "e"}:
                errors.append(f"{context}: unexpected field {field_name}")
        doc_id = document.get("d")
        if not isinstance(doc_id, str) or not doc_id:
            errors.append(f"{context}: d must be non-empty string")
        else:
            if doc_id in seen_doc_ids:
                errors.append(f"{context}: duplicate doc_id {doc_id}")
            seen_doc_ids.add(doc_id)
            if doc_id not in expected_doc_ids:
                errors.append(f"{context}: unexpected doc_id {doc_id}")
        entities = document.get("e")
        if not isinstance(entities, list):
            errors.append(f"{context}: e must be an array")
            continue
        for entity_index, entity in enumerate(entities):
            entity_context = f"{context}.e[{entity_index}]"
            if not isinstance(entity, dict):
                errors.append(f"{entity_context} must be an object")
                continue
            for field_name in entity:
                if field_name not in {"s", "ru", "t", "r", "c", "q"}:
                    errors.append(f"{entity_context}: unexpected field {field_name}")
            for field_name in ("s", "ru", "t", "r", "c", "q"):
                if field_name not in entity:
                    errors.append(f"{entity_context}: missing required field {field_name}")
            if not isinstance(entity.get("s"), str) or not entity.get("s", "").strip():
                errors.append(f"{entity_context}: s must be non-empty string")
            if not isinstance(entity.get("ru"), str) or not entity.get("ru", "").strip():
                errors.append(f"{entity_context}: ru must be non-empty string")
            if entity.get("t") not in allowed_types:
                errors.append(f"{entity_context}: invalid t {entity.get('t')!r}")
            if entity.get("r") not in allowed_roles:
                errors.append(f"{entity_context}: invalid r {entity.get('r')!r}")
            confidence = entity.get("c")
            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
                errors.append(f"{entity_context}: c must be number")
            elif confidence < 0 or confidence > 1:
                errors.append(f"{entity_context}: c must be between 0 and 1")
            if not isinstance(entity.get("q"), str) or not entity.get("q", "").strip():
                errors.append(f"{entity_context}: q must be non-empty string")
    for doc_id in sorted(expected_doc_ids - seen_doc_ids):
        errors.append(f"missing doc_id {doc_id}")
    return errors


def expand_compact_batch_response(value: dict[str, Any]) -> dict[str, Any]:
    docs = []
    for document in value.get("docs", []):
        if not isinstance(document, dict):
            continue
        entities = []
        for entity in document.get("e", []):
            if not isinstance(entity, dict):
                continue
            role = str(entity.get("r", "context"))
            tag_role = {
                "article": "article_candidate",
                "context": "context_only",
                "folder": "folder_candidate",
            }.get(role, "context_only")
            entities.append(
                {
                    "surface": str(entity.get("s", "")),
                    "canonical_candidate_ru": str(entity.get("ru", "")),
                    "canonical_candidate_latin": "",
                    "entity_type": str(entity.get("t", "")),
                    "article_candidate": role == "article",
                    "tag_role": tag_role,
                    "is_primary": True,
                    "confidence": float(entity.get("c", 0.0) or 0.0),
                    "evidence_quotes": [str(entity.get("q", ""))],
                    "comment": "",
                }
            )
        docs.append({"doc_id": str(document.get("d", "")), "entities": entities})
    return {"documents": docs}


def _compact_allowed_values(schema: dict[str, Any], field_name: str) -> set[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return set()
    docs = properties.get("docs")
    if not isinstance(docs, dict):
        return set()
    doc_items = docs.get("items")
    if not isinstance(doc_items, dict):
        return set()
    doc_properties = doc_items.get("properties")
    if not isinstance(doc_properties, dict):
        return set()
    entities = doc_properties.get("e")
    if not isinstance(entities, dict):
        return set()
    entity_items = entities.get("items")
    if not isinstance(entity_items, dict):
        return set()
    entity_properties = entity_items.get("properties")
    if not isinstance(entity_properties, dict):
        return set()
    field = entity_properties.get(field_name)
    if not isinstance(field, dict):
        return set()
    enum = field.get("enum")
    if not isinstance(enum, list):
        return set()
    return {value for value in enum if isinstance(value, str)}


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

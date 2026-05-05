from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kb_rebuild.normalization.models import NormalizedMention, TagMention, TaggingRecord
from kb_rebuild.normalization.text import (
    detect_suspicious_flags,
    diagnostic_abbreviation_candidate,
    normalize_basic_text,
    normalize_drug_class,
    normalize_latin_text,
    normalize_microorganism_text,
    normalize_product_name,
    normalization_flags_for_values,
    risk_flags_from_flags,
    routing_flags_for_mention,
    subtype_signature,
)


def load_tagging_records(path: Path) -> tuple[list[TaggingRecord], list[dict[str, Any]], list[str]]:
    records: list[TaggingRecord] = []
    invalid_records: list[dict[str, Any]] = []
    warnings: list[str] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                invalid_records.append(
                    _invalid_record(path, line_number, "invalid_json", raw_line=stripped, error=str(exc))
                )
                continue
            if not isinstance(value, dict):
                invalid_records.append(_invalid_record(path, line_number, "record_not_object", raw_value=value))
                continue
            records.append(TaggingRecord(line_number=line_number, data=value))
    if invalid_records:
        warnings.append(f"{path}: invalid JSONL/object records skipped: {len(invalid_records)}")
    return records, invalid_records, warnings


def flatten_mentions(
    records: list[TaggingRecord],
    *,
    source_file: Path,
) -> tuple[list[TagMention], list[dict[str, Any]], list[str]]:
    mentions: list[TagMention] = []
    invalid_records: list[dict[str, Any]] = []
    warnings: list[str] = []
    source_file_text = str(source_file)

    for tagging_record in records:
        record = tagging_record.data
        line_number = tagging_record.line_number
        doc_id = _as_str(record.get("doc_id"))
        if not doc_id:
            invalid_records.append(_invalid_record(source_file, line_number, "missing_doc_id", record=record))
            continue

        entities = record.get("entities")
        if entities is None:
            warnings.append(f"{source_file}:{line_number}: missing entities; record skipped")
            continue
        if not isinstance(entities, list):
            invalid_records.append(_invalid_record(source_file, line_number, "entities_not_list", record=record))
            continue

        for entity_index, entity in enumerate(entities):
            mention_id = f"m_{line_number:07d}_{entity_index:02d}"
            if not isinstance(entity, dict):
                invalid_records.append(
                    _invalid_record(
                        source_file,
                        line_number,
                        "entity_not_object",
                        entity_index=entity_index,
                        raw_value=entity,
                    )
                )
                continue
            mentions.append(
                TagMention(
                    mention_id=mention_id,
                    doc_id=doc_id,
                    document_name=_as_str(record.get("document_name")),
                    entity_index=entity_index,
                    surface=_as_str(entity.get("surface")),
                    canonical_candidate_ru=_as_str(entity.get("canonical_candidate_ru")),
                    canonical_candidate_latin=_as_str(entity.get("canonical_candidate_latin")),
                    entity_type=_as_str(entity.get("entity_type")),
                    tag_role=_as_str(entity.get("tag_role")),
                    article_candidate=_as_bool(entity.get("article_candidate")),
                    is_primary=_as_bool(entity.get("is_primary")),
                    confidence=_as_float(entity.get("confidence"), default=0.0),
                    evidence_quotes=_as_str_list(entity.get("evidence_quotes")),
                    quote_validation_status=_as_str(entity.get("quote_validation_status")),
                    quote_validation_details=_as_list(entity.get("quote_validation_details")),
                    provider=_as_str(record.get("provider")),
                    model=_as_str(record.get("model")),
                    prompt_version=_as_str(record.get("prompt_version")),
                    schema_version=_as_str(record.get("schema_version")),
                    source_file=source_file_text,
                )
            )

    if invalid_records:
        warnings.append(f"{source_file}: invalid tagging records/mentions skipped: {len(invalid_records)}")
    return mentions, invalid_records, warnings


def normalize_mention(mention: TagMention) -> NormalizedMention:
    surface_norm = normalize_basic_text(mention.surface)
    candidate_ru_norm = normalize_basic_text(mention.canonical_candidate_ru)
    candidate_latin_norm = normalize_latin_text(mention.canonical_candidate_latin)
    primary_raw = mention.canonical_candidate_ru.strip() or mention.surface.strip()
    primary_norm = normalize_basic_text(primary_raw)

    product_result = None
    if mention.entity_type in {"drug_trade_name", "supplement"}:
        product_result = normalize_product_name(primary_raw, mention.entity_type)
    if mention.entity_type == "drug_class":
        primary_norm = normalize_drug_class(primary_raw)
    if mention.entity_type == "microorganism":
        surface_norm = normalize_microorganism_text(mention.surface)
        candidate_ru_norm = normalize_microorganism_text(mention.canonical_candidate_ru)
        candidate_latin_norm = normalize_microorganism_text(mention.canonical_candidate_latin)
        primary_norm = normalize_microorganism_text(primary_raw)

    normalized: dict[str, Any] = {
        "surface_norm": surface_norm,
        "candidate_ru_norm": candidate_ru_norm,
        "candidate_latin_norm": candidate_latin_norm,
        "primary_norm": primary_norm,
        "display_candidate_ru": mention.canonical_candidate_ru.strip() or mention.surface.strip(),
        "display_candidate_latin": mention.canonical_candidate_latin.strip(),
    }
    if product_result is not None:
        normalized["product_name_norm"] = product_result.value
        if product_result.numeric_variant_changed:
            normalized["product_variant_group_key"] = product_result.value
    abbreviation_candidate = ""
    if mention.entity_type == "diagnostic_method":
        abbreviation_candidate = diagnostic_abbreviation_candidate(primary_raw)
        if abbreviation_candidate:
            normalized["abbreviation_candidate"] = abbreviation_candidate
    if mention.entity_type == "disease":
        normalized["subtype_signature"] = subtype_signature(primary_raw)

    flags = normalization_flags_for_values(
        mention.surface,
        mention.canonical_candidate_ru,
        mention.canonical_candidate_latin,
    )
    if product_result is not None and product_result.changed:
        flags.append("product_name_cleanup")
    if product_result is not None and product_result.numeric_variant_changed:
        flags.append("trailing_numeric_product_variant")
    if mention.entity_type == "drug_class" and primary_norm != normalize_basic_text(primary_raw):
        flags.append("drug_class_cleanup")
    if abbreviation_candidate:
        flags.append("abbreviation_candidate")

    suspicious_flags = detect_suspicious_flags(
        surface=mention.surface,
        canonical_candidate_ru=mention.canonical_candidate_ru,
        primary_norm=primary_norm,
        entity_type=mention.entity_type,
        tag_role=mention.tag_role,
        confidence=mention.confidence,
        quote_validation_status=mention.quote_validation_status,
        quote_validation_details=mention.quote_validation_details,
        evidence_quotes=mention.evidence_quotes,
        document_name=mention.document_name,
        product_name_norm=str(normalized.get("product_name_norm", "")),
        product_too_short=bool(product_result and product_result.too_short),
        product_numeric_variant=bool(product_result and product_result.numeric_variant_changed),
    )
    risk_flags = risk_flags_from_flags(suspicious_flags)
    routing_flags = routing_flags_for_mention(
        tag_role=mention.tag_role,
        article_candidate=mention.article_candidate,
    )

    return NormalizedMention(
        mention_id=mention.mention_id,
        doc_id=mention.doc_id,
        document_name=mention.document_name,
        raw={
            "surface": mention.surface,
            "canonical_candidate_ru": mention.canonical_candidate_ru,
            "canonical_candidate_latin": mention.canonical_candidate_latin,
        },
        normalized=normalized,
        entity_type=mention.entity_type,
        tag_role=mention.tag_role,
        article_candidate=mention.article_candidate,
        is_primary=mention.is_primary,
        confidence=mention.confidence,
        evidence_quotes=mention.evidence_quotes,
        quote_validation_status=mention.quote_validation_status,
        quote_validation_details=mention.quote_validation_details,
        normalization_flags=sorted(set(flags)),
        risk_flags=risk_flags,
        routing_flags=routing_flags,
        suspicious_flags=risk_flags,
        source_file=mention.source_file,
    )


def _invalid_record(path: Path, line_number: int, reason: str, **extra: Any) -> dict[str, Any]:
    record = {
        "source_file": str(path),
        "line_number": line_number,
        "reason": reason,
    }
    record.update(extra)
    return record


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _as_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

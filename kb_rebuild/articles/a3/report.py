from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from kb_rebuild.articles.a3.models import STAGE, STAGE_VERSION, A3Config


FACT_GROUP_FIELDS = [
    "fact_group_id",
    "tag_id",
    "canonical_tag_ru",
    "canonical_tag_latin",
    "entity_type",
    "fact_type",
    "section_hint",
    "representative_claim",
    "representative_quote",
    "representative_quote_validation_status",
    "importance",
    "confidence",
    "evidence_item_ids",
    "source_task_ids",
    "source_doc_ids",
    "source_window_ids",
    "evidence_items_count",
    "source_documents_count",
    "valid_evidence_count",
    "review_evidence_count",
    "rejected_evidence_count",
    "quote_status_counts",
    "needs_review_before_publication",
    "review_reasons",
    "usable_for_a4",
    "a4_usage",
    "created_from_stage",
]

TAG_COVERAGE_FIELDS = [
    "tag_id",
    "canonical_tag_ru",
    "canonical_tag_latin",
    "entity_type",
    "article_status",
    "coverage_category",
    "evidence_items_total",
    "valid_evidence_items",
    "review_evidence_items",
    "rejected_evidence_items",
    "fact_groups_total",
    "core_fact_groups",
    "supporting_fact_groups",
    "review_only_fact_groups",
    "source_documents_count",
    "fact_types",
    "ready_for_a4",
    "a4_strategy",
    "needs_review_before_publication",
    "review_reasons",
]

SUMMARY_FIELDS = ["entity_type", "fact_type", "reason", "items_count", "tags_count", "documents_count"]
QUOTE_STATUS_ENTITY_FIELDS = ["entity_type", "quote_validation_status", "items_count", "tags_count", "documents_count"]
HIGH_VOLUME_FIELDS = ["tag_id", "canonical_tag_ru", "entity_type", "evidence_items_total", "fact_groups_total", "usable_fact_groups"]
MANUAL_QA_FIELDS = [
    "fact_group_id",
    "tag_id",
    "canonical_tag_ru",
    "entity_type",
    "fact_type",
    "representative_claim",
    "representative_quote",
    "quote_status",
    "source_documents_count",
    "evidence_items_count",
    "usable_for_a4",
    "a4_usage",
    "needs_review_before_publication",
    "review_reasons",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp_path.replace(path)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    count = 0
    with tmp_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})
            count += 1
    tmp_path.replace(path)
    return count


def build_report(
    *,
    created_at: str,
    config: A3Config,
    inputs: dict[str, Path],
    evidence_items_total: int,
    valid_evidence: list[dict[str, Any]],
    review_evidence: list[dict[str, Any]],
    rejected_evidence: list[dict[str, Any]],
    deduped_evidence: list[dict[str, Any]],
    duplicate_rows: list[dict[str, Any]],
    fact_groups: list[dict[str, Any]],
    tag_index: list[dict[str, Any]],
    coverage_counts: dict[str, int],
    warnings: list[str],
) -> dict[str, Any]:
    quote_counts = Counter(str(row.get("quote_validation_status") or "") for row in valid_evidence + review_evidence + rejected_evidence)
    by_entity_type: dict[str, Counter[str]] = defaultdict(Counter)
    by_fact_type: dict[str, Counter[str]] = defaultdict(Counter)
    for item in valid_evidence + review_evidence + rejected_evidence:
        layer = str(item.get("a3_layer") or "")
        by_entity_type[str(item.get("entity_type") or "")][layer] += 1
        by_fact_type[str(item.get("fact_type") or "")][layer] += 1

    usable_groups = [row for row in fact_groups if row.get("usable_for_a4")]
    review_only_groups = [row for row in fact_groups if row.get("a4_usage") == "review_only"]
    quality = _quality(
        evidence_items_total=evidence_items_total,
        valid_evidence=valid_evidence,
        review_evidence=review_evidence,
        rejected_evidence=rejected_evidence,
        fact_groups=fact_groups,
        tag_index=tag_index,
    )

    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "created_at": created_at,
        "input": {
            "a2_evidence_items": str(inputs["a2_evidence_items_jsonl"]),
            "a2_task_results": str(inputs["a2_task_results_jsonl"]),
            "a1_status_index": str(inputs["article_status_index_jsonl"]),
        },
        "counts": {
            "final_tags_total": coverage_counts.get("final_tags_total", 0),
            "a2_evidence_items_total": evidence_items_total,
            "valid_evidence_items": len(valid_evidence),
            "review_evidence_items": len(review_evidence),
            "rejected_evidence_items": len(rejected_evidence),
            "deduped_evidence_items": len(deduped_evidence),
            "exact_duplicate_items_removed": len(duplicate_rows),
            "fact_groups_total": len(fact_groups),
            "usable_fact_groups": len(usable_groups),
            "review_only_fact_groups": len(review_only_groups),
            "tags_with_a2_tasks": coverage_counts.get("tags_with_a2_tasks", 0),
            "tags_with_evidence_items": coverage_counts.get("tags_with_evidence_items", 0),
            "tags_with_valid_evidence": coverage_counts.get("tags_with_valid_evidence", 0),
            "tags_without_usable_evidence": coverage_counts.get("tags_without_usable_evidence", 0),
            "ready_for_a4_tags": coverage_counts.get("ready_for_a4_tags", 0),
            "compile_with_review_flag_tags": coverage_counts.get("compile_with_review_flag_tags", 0),
            "direct_copy_already_done_tags": coverage_counts.get("direct_copy_already_done_tags", 0),
            "stub_only_tags": coverage_counts.get("stub_only_tags", 0),
            "review_stub_tags": coverage_counts.get("review_stub_tags", 0),
        },
        "by_entity_type": {key: dict(value) for key, value in sorted(by_entity_type.items())},
        "by_fact_type": {key: dict(value) for key, value in sorted(by_fact_type.items())},
        "quote_validation": {
            "exact": quote_counts.get("exact", 0),
            "normalized_exact": quote_counts.get("normalized_exact", 0),
            "fuzzy": quote_counts.get("fuzzy", 0),
            "not_found": quote_counts.get("not_found", 0),
        },
        "quality": quality,
        "warnings": warnings,
        "config": {
            "min_confidence": config.min_confidence,
            "allow_fuzzy_for_review": config.allow_fuzzy_for_review,
            "max_quotes_per_fact_group": config.max_quotes_per_fact_group,
            "max_fact_groups_per_tag": config.max_fact_groups_per_tag,
        },
    }


def build_manifest(
    *,
    created_at: str,
    config: A3Config,
    inputs: dict[str, Path],
    outputs: dict[str, Path],
) -> dict[str, Any]:
    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "created_at": created_at,
        "inputs": {name: str(path) for name, path in inputs.items()},
        "outputs": {name: str(path) for name, path in outputs.items()},
        "config": {
            "data_dir": str(config.data_dir),
            "a2_dir": str(config.a2_dir),
            "a1_dir": str(config.a1_dir),
            "normalization_final_dir": str(config.normalization_final_dir),
            "out_dir": str(config.out_dir),
            "min_confidence": config.min_confidence,
            "allow_fuzzy_for_review": config.allow_fuzzy_for_review,
            "max_quotes_per_fact_group": config.max_quotes_per_fact_group,
            "max_fact_groups_per_tag": config.max_fact_groups_per_tag,
            "overwrite": config.overwrite,
        },
    }


def rejected_summary_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _summary_rows(items)


def review_summary_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _summary_rows(items)


def quote_status_by_entity_type_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        buckets[(str(item.get("entity_type") or ""), str(item.get("quote_validation_status") or ""))].append(item)
    rows: list[dict[str, Any]] = []
    for (entity_type, quote_status), bucket in sorted(buckets.items()):
        rows.append(
            {
                "entity_type": entity_type,
                "quote_validation_status": quote_status,
                "items_count": len(bucket),
                "tags_count": len({str(item.get("tag_id") or "") for item in bucket}),
                "documents_count": len({str(item.get("doc_id") or "") for item in bucket if item.get("doc_id")}),
            }
        )
    return rows


def high_volume_tag_rows(tag_index: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(tag_index, key=lambda row: (int(row.get("evidence_items_total") or 0), int(row.get("fact_groups_total") or 0)), reverse=True)
    return [
        {
            "tag_id": row.get("tag_id"),
            "canonical_tag_ru": row.get("canonical_tag_ru"),
            "entity_type": row.get("entity_type"),
            "evidence_items_total": row.get("evidence_items_total"),
            "fact_groups_total": row.get("fact_groups_total"),
            "usable_fact_groups": int(row.get("core_fact_groups") or 0) + int(row.get("supporting_fact_groups") or 0),
        }
        for row in rows[:200]
    ]


def manual_qa_rows(fact_groups: list[dict[str, Any]], tags_without_usable: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_manual_rows([row for row in fact_groups if row.get("usable_for_a4") and not row.get("needs_review_before_publication")], limit=20))
    rows.extend(_manual_rows([row for row in fact_groups if int(row.get("source_documents_count") or 0) > 1], limit=20))
    rows.extend(_manual_rows([row for row in fact_groups if row.get("a4_usage") == "review_only"], limit=20))
    for row in tags_without_usable[:20]:
        rows.append(
            {
                "fact_group_id": "",
                "tag_id": row.get("tag_id"),
                "canonical_tag_ru": row.get("canonical_tag_ru"),
                "entity_type": row.get("entity_type"),
                "fact_type": "",
                "representative_claim": "NO_USABLE_EVIDENCE",
                "representative_quote": "",
                "quote_status": "",
                "source_documents_count": 0,
                "evidence_items_count": row.get("evidence_items_total"),
                "usable_for_a4": False,
                "a4_usage": "insufficient_evidence_review",
                "needs_review_before_publication": True,
                "review_reasons": ["no_usable_fact_groups"],
            }
        )
    return rows


def _manual_rows(fact_groups: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in fact_groups[:limit]:
        rows.append(
            {
                "fact_group_id": group.get("fact_group_id"),
                "tag_id": group.get("tag_id"),
                "canonical_tag_ru": group.get("canonical_tag_ru"),
                "entity_type": group.get("entity_type"),
                "fact_type": group.get("fact_type"),
                "representative_claim": group.get("representative_claim"),
                "representative_quote": group.get("representative_quote"),
                "quote_status": group.get("representative_quote_validation_status"),
                "source_documents_count": group.get("source_documents_count"),
                "evidence_items_count": group.get("evidence_items_count"),
                "usable_for_a4": group.get("usable_for_a4"),
                "a4_usage": group.get("a4_usage"),
                "needs_review_before_publication": group.get("needs_review_before_publication"),
                "review_reasons": group.get("review_reasons"),
            }
        )
    return rows


def _summary_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        reasons = _list_value(item.get("a3_filter_reasons")) or _list_value(item.get("review_reasons")) or ["unspecified"]
        for reason in reasons:
            buckets[(str(item.get("entity_type") or ""), str(item.get("fact_type") or ""), reason)].append(item)
    rows: list[dict[str, Any]] = []
    for (entity_type, fact_type, reason), bucket in sorted(buckets.items()):
        rows.append(
            {
                "entity_type": entity_type,
                "fact_type": fact_type,
                "reason": reason,
                "items_count": len(bucket),
                "tags_count": len({str(item.get("tag_id") or "") for item in bucket}),
                "documents_count": len({str(item.get("doc_id") or "") for item in bucket if item.get("doc_id")}),
            }
        )
    return rows


def _quality(
    *,
    evidence_items_total: int,
    valid_evidence: list[dict[str, Any]],
    review_evidence: list[dict[str, Any]],
    rejected_evidence: list[dict[str, Any]],
    fact_groups: list[dict[str, Any]],
    tag_index: list[dict[str, Any]],
) -> dict[str, Any]:
    layer_ids = [
        str(item.get("evidence_item_id") or "")
        for item in valid_evidence + review_evidence + rejected_evidence
        if item.get("evidence_item_id")
    ]
    usable_groups = [group for group in fact_groups if group.get("usable_for_a4")]
    ready_rows = [row for row in tag_index if row.get("ready_for_a4")]
    quality = {
        "all_evidence_items_accounted_for": len(valid_evidence) + len(review_evidence) + len(rejected_evidence) == evidence_items_total,
        "no_duplicate_evidence_item_id_in_layer_outputs": len(layer_ids) == len(set(layer_ids)),
        "no_not_found_in_usable_fact_groups": all(
            int((group.get("quote_status_counts") or {}).get("not_found", 0) or 0) == 0 for group in usable_groups
        ),
        "no_fuzzy_only_fact_group_marked_usable": all(
            not (
                group.get("usable_for_a4")
                and int(group.get("valid_evidence_count") or 0) == 0
                and int((group.get("quote_status_counts") or {}).get("fuzzy", 0) or 0) > 0
            )
            for group in fact_groups
        ),
        "all_fact_groups_have_tag_id": all(group.get("tag_id") and group.get("canonical_tag_ru") and group.get("entity_type") for group in fact_groups),
        "all_a4_ready_tags_have_fact_groups": all(int(row.get("core_fact_groups") or 0) + int(row.get("supporting_fact_groups") or 0) > 0 for row in ready_rows),
        "tag_fact_group_index_complete": bool(tag_index),
    }
    quality["passed"] = all(bool(value) for value in quality.values())
    return quality


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value:
        return [str(value)]
    return []


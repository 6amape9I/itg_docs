from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from kb_rebuild.articles.a5.models import STAGE, STAGE_VERSION, A5Config


ARTICLE_EXPORT_INDEX_FIELDS = [
    "tag_id",
    "canonical_tag_ru",
    "canonical_tag_latin",
    "entity_type",
    "article_status",
    "source_stage",
    "source_article_status",
    "needs_review_before_publication",
    "review_reasons",
    "for_n8n_path",
    "for_docs_path",
    "for_docs_quotes_path",
    "content_blocks_count",
    "quotes_count",
    "questions_count",
    "source_documents_count",
    "used_fact_groups_count",
    "export_quality_status",
]

QUOTES_INDEX_FIELDS = [
    "tag_id",
    "canonical_tag_ru",
    "entity_type",
    "quotes_path",
    "questions_count",
    "quotes_count",
    "questions_generation_status",
    "quotes_source_status",
    "needs_review_before_publication",
]

MISSING_TAG_FIELDS = ["tag_id", "canonical_tag_ru", "entity_type", "reason"]
DUPLICATE_FILENAME_FIELDS = ["path", "export_area", "tag_ids"]
STATUS_DISTRIBUTION_FIELDS = ["article_status", "count"]
ENTITY_TYPE_DISTRIBUTION_FIELDS = ["entity_type", "article_status", "count"]
MANUAL_QA_FIELDS = [
    "tag_id",
    "canonical_tag_ru",
    "entity_type",
    "article_status",
    "needs_review_before_publication",
    "for_n8n_path",
    "for_docs_path",
    "quotes_path",
    "content_blocks_count",
    "questions_count",
    "quotes_count",
    "qa_excerpt",
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


def build_coverage_audit(
    *,
    counts: dict[str, Any],
    quality: dict[str, Any],
) -> dict[str, Any]:
    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "counts": counts,
        "quality": quality,
    }


def build_report(
    *,
    created_at: str,
    config: A5Config,
    inputs: dict[str, Path],
    outputs: dict[str, Path],
    counts: dict[str, Any],
    quality: dict[str, Any],
    export_rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    by_entity_type: dict[str, Counter[str]] = defaultdict(Counter)
    for row in export_rows:
        by_entity_type[str(row.get("entity_type") or "")][str(row.get("article_status") or "")] += 1
    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "created_at": created_at,
        "input": {
            "a1_status_index": str(inputs["article_status_index_jsonl"]),
            "a3_a4_compilation_input": str(inputs["a4_compilation_input_jsonl"]),
            "a3_fact_groups": str(inputs["fact_groups_jsonl"]),
            "a4_article_drafts": str(inputs["article_drafts_jsonl"]),
            "normalization_final": str(config.normalization_final_dir),
        },
        "outputs": {name: str(path) for name, path in outputs.items()},
        "counts": counts,
        "by_status": _status_counts(export_rows),
        "by_entity_type": {key: dict(value) for key, value in sorted(by_entity_type.items())},
        "quality": quality,
        "warnings": warnings,
        "export_quality_issue_samples": issues[:50],
    }


def build_manifest(
    *,
    created_at: str,
    config: A5Config,
    inputs: dict[str, Path],
    outputs: dict[str, Path],
) -> dict[str, Any]:
    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "created_at": created_at,
        "source_a1_manifest": str(inputs["a1_manifest_json"]),
        "source_a3_manifest": str(inputs["a3_manifest_json"]),
        "source_a4_manifest": str(inputs["a4_manifest_json"]),
        "source_normalization_manifest": str(inputs["final_normalization_manifest_json"]),
        "inputs": {name: str(path) for name, path in inputs.items()},
        "outputs": {name: str(path) for name, path in outputs.items()},
        "config": {
            "data_dir": str(config.data_dir),
            "a1_dir": str(config.a1_dir),
            "a3_dir": str(config.a3_dir),
            "a4_dir": str(config.a4_dir),
            "entities_dir": str(config.entities_dir),
            "normalization_final_dir": str(config.normalization_final_dir),
            "out_dir": str(config.out_dir),
            "overwrite": config.overwrite,
        },
    }


def status_distribution_rows(export_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(row.get("article_status") or "") for row in export_rows)
    return [{"article_status": status, "count": count} for status, count in sorted(counts.items())]


def entity_type_distribution_rows(export_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter((str(row.get("entity_type") or ""), str(row.get("article_status") or "")) for row in export_rows)
    return [
        {"entity_type": entity_type, "article_status": status, "count": count}
        for (entity_type, status), count in sorted(counts.items())
    ]


def manual_qa_rows(export_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = {
        "compiled_article": 20,
        "compiled_with_review_flag": 20,
        "direct_copy_article": 20,
        "stub_only": 20,
        "review_stub": 20,
    }
    rows: list[dict[str, Any]] = []
    for status, limit in targets.items():
        rows.extend([row for row in export_rows if row.get("article_status") == status][:limit])
    insufficient = [row for row in export_rows if row.get("article_status") == "insufficient_evidence_review"]
    rows.extend(insufficient if len(insufficient) <= 120 else insufficient[:20])
    return rows


def _status_counts(export_rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get("article_status") or "") for row in export_rows).items()))


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


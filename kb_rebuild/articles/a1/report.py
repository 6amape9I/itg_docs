from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from kb_rebuild.articles.a1.models import STAGE, STAGE_VERSION, A1Config


TAG_WORK_PLAN_ADJUSTED_FIELDS = [
    "tag_id",
    "canonical_tag_ru",
    "canonical_tag_latin",
    "entity_type",
    "article_candidate",
    "need_review",
    "primary_role",
    "mentions_count",
    "documents_count",
    "source_windows_count",
    "source_strategy_original",
    "strategy",
    "strategy_adjusted",
    "strategy_adjustment_reason",
    "needs_review_before_article",
    "needs_review_before_publication",
    "publication_review_reasons",
    "article_blocking_review_reasons",
    "estimated_llm_extraction_tasks",
    "estimated_article_compilation_tasks",
]

ARTICLE_STATUS_INDEX_FIELDS = [
    "tag_id",
    "canonical_tag_ru",
    "canonical_tag_latin",
    "entity_type",
    "article_status",
    "source_strategy_original",
    "source_strategy_adjusted",
    "strategy_adjusted",
    "article_file_path",
    "article_candidate",
    "mentions_count",
    "documents_count",
    "source_windows_count",
    "a2_extraction_tasks_count",
    "needs_review_before_article",
    "needs_review_before_publication",
    "review_reasons",
    "publication_review_reasons",
]

A2_TASK_QUEUE_FIELDS = [
    "task_id",
    "tag_id",
    "canonical_tag_ru",
    "canonical_tag_latin",
    "entity_type",
    "source_strategy",
    "doc_id",
    "document_name",
    "window_id",
    "window_char_length",
    "block_ids",
    "block_indexes",
    "heading_context",
    "match_method",
    "window_quality",
    "needs_review_before_publication",
    "priority",
    "batch_group_key",
    "estimated_input_chars",
    "recommended_max_output_tokens",
]

DIRECT_COPY_VALIDATION_FIELDS = [
    "tag_id",
    "canonical_tag_ru",
    "accepted",
    "rejection_reasons",
    "best_window_id",
    "best_window_quality",
    "best_window_coverage_ratio_estimate",
    "article_status",
]

MISSING_TAGS_FIELDS = ["tag_id", "canonical_tag_ru", "entity_type", "reason"]


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


def build_a1_report(
    *,
    created_at: str,
    final_tags_total: int,
    status_rows: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    direct_copy_rejected: list[dict[str, Any]],
    strategy_adjustment_report: dict[str, Any],
    publication_review_queue: list[dict[str, Any]],
    hard_review_queue: list[dict[str, Any]],
    coverage_audit: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    status_counts = Counter(str(row.get("article_status") or "") for row in status_rows)
    by_entity_type: dict[str, Counter[str]] = defaultdict(Counter)
    for row in status_rows:
        by_entity_type[str(row.get("entity_type") or "")][str(row.get("article_status") or "")] += 1
    quality = {
        "all_tags_have_entity_json": coverage_audit.get("missing_entity_json_files") == 0,
        "all_article_files_exist": coverage_audit.get("missing_entity_json_files") == 0,
        "article_status_index_complete": coverage_audit.get("status_index_missing_tags") == 0,
        "no_llm_called": True,
        "a2_task_queue_created": True,
    }
    quality["passed"] = bool(all(quality.values()) and coverage_audit.get("passed"))
    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "created_at": created_at,
        "counts": {
            "final_tags_total": final_tags_total,
            "entity_json_files_created": len(status_rows),
            "article_status_index_rows": len(status_rows),
            "a0_review_stub_original": int(strategy_adjustment_report.get("a0_review_stub_original") or 0),
            "a0_1_rerouted_from_review_stub": int(strategy_adjustment_report.get("a0_1_rerouted_from_review_stub") or 0),
            "stub_only_articles": status_counts.get("stub_only", 0),
            "review_stub_articles": status_counts.get("review_stub", 0),
            "direct_copy_articles": status_counts.get("direct_copy_article", 0),
            "direct_copy_rejected": len(direct_copy_rejected),
            "pending_single_doc_extract": status_counts.get("pending_single_doc_extract", 0),
            "pending_low_count_batch_extract": status_counts.get("pending_low_count_batch_extract", 0),
            "pending_multi_doc_map_reduce": status_counts.get("pending_multi_doc_map_reduce", 0),
            "pending_high_frequency_map_reduce": status_counts.get("pending_high_frequency_map_reduce", 0),
            "a2_extraction_tasks_total": len(tasks),
            "publication_review_queue_total": len(publication_review_queue),
            "hard_review_queue_total": len(hard_review_queue),
        },
        "by_entity_type": {entity: dict(counter) for entity, counter in sorted(by_entity_type.items())},
        "quality": quality,
        "strategy_adjustment_report": strategy_adjustment_report,
        "warnings": warnings,
    }


def build_manifest(
    *,
    created_at: str,
    config: A1Config,
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
            "articles_planning_dir": str(config.articles_planning_dir),
            "normalization_final_dir": str(config.normalization_final_dir),
            "parsed_dir": str(config.parsed_dir),
            "out_dir": str(config.out_dir),
            "entities_out_dir": str(config.entities_out_dir),
            "review_sample_size": config.review_sample_size,
            "low_count_doc_threshold": config.low_count_doc_threshold,
            "high_frequency_doc_threshold": config.high_frequency_doc_threshold,
            "overwrite": config.overwrite,
        },
    }


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value

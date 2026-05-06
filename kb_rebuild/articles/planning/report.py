from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from kb_rebuild.articles.planning.loaders import bool_value
from kb_rebuild.articles.planning.models import A0Config, STAGE, STAGE_VERSION


TAG_WORK_PLAN_CSV_FIELDS = [
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
    "high_quality_windows_count",
    "low_quality_windows_count",
    "strategy",
    "strategy_reasons",
    "estimated_llm_extraction_tasks",
    "estimated_article_compilation_tasks",
]

STRATEGY_SUMMARY_FIELDS = [
    "entity_type",
    "strategy",
    "tags_count",
    "mentions_count_total",
    "documents_count_total",
    "source_windows_count_total",
    "estimated_llm_extraction_tasks_total",
    "estimated_article_compilation_tasks_total",
]

HIGH_FREQUENCY_FIELDS = [
    "tag_id",
    "canonical_tag_ru",
    "entity_type",
    "documents_count",
    "mentions_count",
    "source_windows_count",
    "strategy",
]

SOURCE_WINDOW_QUALITY_FIELDS = [
    "match_method",
    "window_quality",
    "windows_count",
    "tags_count",
    "documents_count",
    "avg_window_chars",
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
    source_index: list[dict[str, Any]],
    work_plans: list[dict[str, Any]],
    windows: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    strategy_counts = Counter(str(plan.get("strategy") or "") for plan in work_plans)
    strategy_counts_by_entity_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for plan in work_plans:
        strategy_counts_by_entity_type[str(plan.get("entity_type") or "")][str(plan.get("strategy") or "")] += 1
    window_method_counts = Counter(str(window.get("match_method") or "") for window in windows)
    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "created_at": created_at,
        "counts": {
            "final_tags_total": len(source_index),
            "article_candidate_tags": sum(1 for row in source_index if bool_value(row.get("article_candidate"))),
            "context_only_tags": sum(1 for row in source_index if row.get("primary_role") == "context_only"),
            "folder_candidate_tags": sum(1 for row in source_index if row.get("primary_role") == "folder_candidate"),
            "need_review_tags": sum(1 for row in source_index if bool_value(row.get("need_review"))),
            "tags_with_mentions": sum(1 for row in source_index if int(row.get("mentions_count") or 0) > 0),
            "tags_without_mentions": sum(1 for row in source_index if int(row.get("mentions_count") or 0) == 0),
            "source_windows_total": len(windows),
            "high_quality_windows": sum(1 for window in windows if window.get("window_quality") == "high"),
            "medium_quality_windows": sum(1 for window in windows if window.get("window_quality") == "medium"),
            "low_quality_windows": sum(1 for window in windows if window.get("window_quality") == "low"),
            "direct_copy_candidates": strategy_counts.get("direct_copy_candidate", 0),
            "singleton_candidates": sum(1 for plan in work_plans if int(plan.get("documents_count") or 0) == 1),
            "stub_only_tags": strategy_counts.get("stub_only", 0),
            "review_stub_tags": strategy_counts.get("review_stub", 0) + strategy_counts.get("no_source_window_review", 0),
            "no_source_window_tags": sum(
                1
                for plan in work_plans
                if int(plan.get("mentions_count") or 0) > 0 and int(plan.get("source_windows_count") or 0) == 0
            ),
            "estimated_llm_extraction_tasks": sum(int(plan.get("estimated_llm_extraction_tasks") or 0) for plan in work_plans),
            "estimated_article_compilation_tasks": sum(int(plan.get("estimated_article_compilation_tasks") or 0) for plan in work_plans),
        },
        "strategy_counts": dict(sorted(strategy_counts.items())),
        "strategy_counts_by_entity_type": {
            entity_type: dict(sorted(counts.items()))
            for entity_type, counts in sorted(strategy_counts_by_entity_type.items())
        },
        "window_match_method_counts": dict(sorted(window_method_counts.items())),
        "warnings": warnings,
    }


def build_manifest(
    *,
    created_at: str,
    config: A0Config,
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
            "normalization_final_dir": str(config.normalization_final_dir),
            "parsed_dir": str(config.parsed_dir),
            "normalization_dir": str(config.normalization_dir),
            "out_dir": str(config.out_dir),
            "max_neighbor_blocks": config.max_neighbor_blocks,
            "max_window_chars": config.max_window_chars,
            "short_document_char_limit": config.short_document_char_limit,
            "high_frequency_doc_threshold": config.high_frequency_doc_threshold,
            "low_count_doc_threshold": config.low_count_doc_threshold,
            "review_sample_size": config.review_sample_size,
            "overwrite": config.overwrite,
        },
    }


def strategy_summary_rows(work_plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for plan in work_plans:
        key = (str(plan.get("entity_type") or ""), str(plan.get("strategy") or ""))
        row = grouped.setdefault(
            key,
            {
                "entity_type": key[0],
                "strategy": key[1],
                "tags_count": 0,
                "mentions_count_total": 0,
                "documents_count_total": 0,
                "source_windows_count_total": 0,
                "estimated_llm_extraction_tasks_total": 0,
                "estimated_article_compilation_tasks_total": 0,
            },
        )
        row["tags_count"] += 1
        row["mentions_count_total"] += int(plan.get("mentions_count") or 0)
        row["documents_count_total"] += int(plan.get("documents_count") or 0)
        row["source_windows_count_total"] += int(plan.get("source_windows_count") or 0)
        row["estimated_llm_extraction_tasks_total"] += int(plan.get("estimated_llm_extraction_tasks") or 0)
        row["estimated_article_compilation_tasks_total"] += int(plan.get("estimated_article_compilation_tasks") or 0)
    return [grouped[key] for key in sorted(grouped)]


def source_window_quality_rows(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    tags_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    docs_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    chars_by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for window in windows:
        key = (str(window.get("match_method") or ""), str(window.get("window_quality") or ""))
        row = grouped.setdefault(
            key,
            {
                "match_method": key[0],
                "window_quality": key[1],
                "windows_count": 0,
                "tags_count": 0,
                "documents_count": 0,
                "avg_window_chars": 0,
            },
        )
        row["windows_count"] += 1
        tags_by_key[key].add(str(window.get("tag_id") or ""))
        docs_by_key[key].add(str(window.get("doc_id") or ""))
        chars_by_key[key].append(int(window.get("window_char_length") or 0))
    rows = []
    for key in sorted(grouped):
        row = dict(grouped[key])
        row["tags_count"] = len(tags_by_key[key])
        row["documents_count"] = len(docs_by_key[key])
        chars = chars_by_key[key]
        row["avg_window_chars"] = round(sum(chars) / len(chars), 2) if chars else 0
        rows.append(row)
    return rows


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value

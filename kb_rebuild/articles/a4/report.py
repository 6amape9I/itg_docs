from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from kb_rebuild.articles.a4.models import PROMPT_VERSION, SCHEMA_VERSION, STAGE, STAGE_VERSION, A4Config
from kb_rebuild.articles.a4.validation import collect_editorjs_source_fact_group_ids


ARTICLE_DRAFT_FIELDS = [
    "task_id",
    "batch_id",
    "tag_id",
    "canonical_tag_ru",
    "canonical_tag_latin",
    "entity_type",
    "a4_strategy",
    "article_status",
    "needs_review_before_publication",
    "review_reasons",
    "title",
    "summary",
    "used_fact_groups_count",
    "unused_fact_groups_count",
    "source_documents_count",
    "content_blocks_count",
    "confidence",
    "reason",
    "article_file_path",
    "model",
    "provider",
    "created_at",
]

BATCH_REPORT_FIELDS = [
    "batch_id",
    "task_ids",
    "tag_ids",
    "entity_types",
    "a4_strategies",
    "tasks_count",
    "input_chars",
    "status",
    "attempts",
    "split_depth",
    "cache_hit",
    "latency_ms",
    "estimated_cost_usd",
    "error",
]

MANUAL_QA_FIELDS = [
    "tag_id",
    "canonical_tag_ru",
    "entity_type",
    "a4_strategy",
    "article_status",
    "needs_review_before_publication",
    "title",
    "summary",
    "blocks_count",
    "used_fact_groups_count",
    "source_documents_count",
    "article_file_path",
    "qa_excerpt",
    "quality_warnings",
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
    config: A4Config,
    inputs: dict[str, Path],
    tasks: list[dict[str, Any]],
    batches: list[dict[str, Any]],
    article_drafts: list[dict[str, Any]],
    failed_tasks: list[dict[str, Any]],
    batch_reports: list[dict[str, Any]],
    invalid_llm_responses: list[dict[str, Any]],
    article_quality_issues: list[dict[str, Any]],
    stats: dict[str, Any],
    stop_reason: str | None,
    warnings: list[str],
) -> dict[str, Any]:
    requested_task_ids = {str(task.get("task_id") or "") for task in tasks}
    processed_task_ids = {str(row.get("task_id") or "") for row in article_drafts} | {str(row.get("task_id") or "") for row in failed_tasks}
    status_counts = Counter(str(row.get("article_status") or "") for row in article_drafts)
    by_entity_type: dict[str, Counter[str]] = defaultdict(Counter)
    by_strategy: dict[str, Counter[str]] = defaultdict(Counter)
    for row in article_drafts:
        status = str(row.get("article_status") or "")
        by_entity_type[str(row.get("entity_type") or "")][status] += 1
        by_strategy[str(row.get("a4_strategy") or "")][status] += 1
    review_task_ids = {
        str(row.get("task_id") or "")
        for row in article_drafts
        if row.get("needs_review_before_publication") or row.get("article_status") != "compiled_article"
    }
    review_task_ids.update(str(row.get("task_id") or "") for row in failed_tasks)
    review_task_ids.discard("")

    quality = _quality(
        requested_task_ids=requested_task_ids,
        processed_task_ids=processed_task_ids,
        article_drafts=article_drafts,
        failed_tasks=failed_tasks,
        article_quality_issues=article_quality_issues,
        stats=stats,
    )

    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "created_at": created_at,
        "input": {
            "a3_a4_compilation_input": str(inputs["a4_compilation_input_jsonl"]),
            "a3_fact_groups": str(inputs["fact_groups_jsonl"]),
            "a3_manifest": str(inputs["a3_manifest_json"]),
            "a1_manifest": str(inputs["a1_manifest_json"]),
        },
        "counts": {
            "tasks_requested": len(requested_task_ids),
            "tasks_processed": len(processed_task_ids),
            "tasks_failed": len(failed_tasks),
            "failed_tasks": len(failed_tasks),
            "article_drafts_total": len(article_drafts),
            "compiled_article": status_counts.get("compiled_article", 0),
            "compiled_articles": status_counts.get("compiled_article", 0),
            "compiled_with_review_flag": status_counts.get("compiled_with_review_flag", 0),
            "insufficient_evidence_review": status_counts.get("insufficient_evidence_review", 0),
            "invalid_or_unclear": status_counts.get("invalid_or_unclear", 0),
            "needs_review_before_publication": sum(1 for row in article_drafts if row.get("needs_review_before_publication")),
            "review_tasks": len(review_task_ids),
            "batches_total": len(batches),
            "batches_success": sum(1 for row in batch_reports if row.get("status") == "success"),
            "batches_failed": sum(1 for row in batch_reports if row.get("status") == "failed"),
            "batch_splits": int(stats.get("batch_splits", 0) or 0),
            "article_quality_issues": len(article_quality_issues),
        },
        "by_entity_type": {key: dict(value) for key, value in sorted(by_entity_type.items())},
        "by_strategy": {key: dict(value) for key, value in sorted(by_strategy.items())},
        "by_a4_strategy": {key: dict(value) for key, value in sorted(by_strategy.items())},
        "llm": {
            "provider": config.provider,
            "model": config.model,
            "requests": int(stats.get("requests", 0) or 0),
            "cache_hits": int(stats.get("cache_hits", 0) or 0),
            "cache_misses": int(stats.get("cache_misses", 0) or 0),
            "invalid_json_count": int(stats.get("invalid_json_count", 0) or 0),
            "schema_validation_failures": int(stats.get("schema_validation_failures", 0) or 0),
            "http_status_counts": dict(stats.get("http_status_counts", {}) or {}),
            "estimated_cost_usd": round(float(stats.get("estimated_cost_usd", 0.0) or 0.0), 8),
            "avg_latency_ms": _avg_latency_ms(batch_reports),
        },
        "quality": quality,
        "stop_reason": stop_reason,
        "warnings": warnings,
        "invalid_llm_responses_total": len(invalid_llm_responses),
    }


def build_manifest(
    *,
    created_at: str,
    config: A4Config,
    inputs: dict[str, Path],
    outputs: dict[str, Path],
) -> dict[str, Any]:
    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "created_at": created_at,
        "source_a3_manifest": str(inputs["a3_manifest_json"]),
        "source_a1_manifest": str(inputs["a1_manifest_json"]),
        "inputs": {name: str(path) for name, path in inputs.items()},
        "outputs": {name: str(path) for name, path in outputs.items()},
        "provider": config.provider,
        "model": config.model,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "config": {
            "data_dir": str(config.data_dir),
            "a3_dir": str(config.a3_dir),
            "a1_dir": str(config.a1_dir),
            "entities_dir": str(config.entities_dir),
            "normalization_final_dir": str(config.normalization_final_dir),
            "out_dir": str(config.out_dir),
            "structured_output_mode": config.structured_output_mode,
            "limit": config.limit,
            "strategy_filter": list(config.strategy_filter),
            "entity_type_filter": list(config.entity_type_filter) if config.entity_type_filter else None,
            "priority_filter": list(config.priority_filter),
            "max_tags_per_batch": config.max_tags_per_batch,
            "max_fact_groups_per_tag": config.max_fact_groups_per_tag,
            "max_quotes_per_tag": config.max_quotes_per_tag,
            "batch_char_limit": config.batch_char_limit,
            "max_inflight": config.max_inflight,
            "max_retries": config.max_retries,
            "max_output_tokens": config.max_output_tokens,
            "repair_max_output_tokens": config.repair_max_output_tokens,
            "thinking_level": config.thinking_level,
            "max_cost_usd": config.max_cost_usd,
            "retry_failures": config.retry_failures,
            "resume": config.resume,
            "experiment_name": config.experiment_name,
        },
    }


def build_quality_diagnostics(report: dict[str, Any], article_quality_issues: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "quality": report.get("quality", {}),
        "counts": report.get("counts", {}),
        "article_quality_issue_samples": article_quality_issues[:50],
        "warnings": report.get("warnings", []),
    }


def build_cost_latency_report(report: dict[str, Any], batch_reports: list[dict[str, Any]]) -> dict[str, Any]:
    counts = report.get("counts", {})
    llm = report.get("llm", {})
    tasks_processed = int(counts.get("tasks_processed", 0) or 0)
    cost = float(llm.get("estimated_cost_usd", 0.0) or 0.0)
    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "requests": int(llm.get("requests", 0) or 0),
        "tasks_processed": tasks_processed,
        "tasks_per_request": round(tasks_processed / max(int(llm.get("requests", 0) or 0), 1), 4),
        "estimated_cost_usd": cost,
        "cost_per_task": round(cost / tasks_processed, 8) if tasks_processed else 0.0,
        "avg_latency_ms": llm.get("avg_latency_ms", 0),
        "batch_reports_count": len(batch_reports),
        "usage_source": "api_or_estimated",
    }


def manual_qa_rows(article_drafts: list[dict[str, Any]], failed_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if len(article_drafts) <= 200:
        rows.extend(_qa_rows(article_drafts, "smoke_all_articles", len(article_drafts)))
    else:
        rows.extend(_qa_rows([row for row in article_drafts if not row.get("needs_review_before_publication")], "compiled", 20))
        rows.extend(_qa_rows([row for row in article_drafts if row.get("needs_review_before_publication")], "review_flag", 20))
        rows.extend(_qa_rows(sorted(article_drafts, key=lambda row: int(row.get("used_fact_groups_count") or 0), reverse=True), "high_volume", 20))
    for row in failed_tasks[:20]:
        rows.append(
            {
                "tag_id": row.get("tag_id", ""),
                "canonical_tag_ru": row.get("canonical_tag_ru", ""),
                "entity_type": row.get("entity_type", ""),
                "a4_strategy": row.get("a4_strategy", ""),
                "article_status": "failed",
                "needs_review_before_publication": True,
                "title": "",
                "summary": "",
                "blocks_count": 0,
                "used_fact_groups_count": 0,
                "source_documents_count": 0,
                "article_file_path": "",
                "qa_excerpt": "",
                "quality_warnings": str(row.get("reason") or ""),
            }
        )
    return rows


def article_draft_csv_rows(article_drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "used_fact_groups_count": len(row.get("used_fact_group_ids", []) or []),
            "unused_fact_groups_count": len(row.get("unused_fact_group_ids", []) or []),
            "source_documents_count": len(row.get("source_doc_ids", []) or []),
            "content_blocks_count": len(row.get("content", {}).get("blocks", []) if isinstance(row.get("content"), dict) else []),
        }
        for row in article_drafts
    ]


def _quality(
    *,
    requested_task_ids: set[str],
    processed_task_ids: set[str],
    article_drafts: list[dict[str, Any]],
    failed_tasks: list[dict[str, Any]],
    article_quality_issues: list[dict[str, Any]],
    stats: dict[str, Any],
) -> dict[str, Any]:
    draft_file_paths = [Path(str(row.get("article_file_path") or "")) for row in article_drafts if row.get("article_file_path")]
    all_blocks_have_source_ids = True
    no_unknown_fact_group_ids = True
    review_flags_preserved = True
    for row in article_drafts:
        content = row.get("content") if isinstance(row.get("content"), dict) else {}
        cited = collect_editorjs_source_fact_group_ids(content)
        allowed = set(str(item) for item in row.get("fact_group_ids", []) or [])
        if cited - allowed:
            no_unknown_fact_group_ids = False
        for block in content.get("blocks", []) if isinstance(content, dict) else []:
            if not isinstance(block, dict) or block.get("type") == "header":
                continue
            metadata = block.get("metadata") if isinstance(block.get("metadata"), dict) else {}
            if not metadata.get("source_fact_group_ids"):
                all_blocks_have_source_ids = False
        task_review = bool(row.get("task_needs_review_before_publication"))
        if task_review and not bool(row.get("needs_review_before_publication")):
            review_flags_preserved = False

    quality = {
        "all_processed_tasks_have_result": requested_task_ids.issubset(processed_task_ids),
        "all_compiled_article_files_exist": all(path.exists() for path in draft_file_paths),
        "all_content_valid_editorjs": all(bool(row.get("content", {}).get("blocks")) for row in article_drafts),
        "all_content_blocks_have_source_ids": all_blocks_have_source_ids,
        "no_unknown_fact_group_ids": no_unknown_fact_group_ids and bool(stats.get("no_unknown_fact_group_ids", True)),
        "review_flags_preserved": review_flags_preserved,
        "failed_tasks_share": round(len(failed_tasks) / len(processed_task_ids), 6) if processed_task_ids else 0.0,
        "article_quality_issues": len(article_quality_issues),
    }
    quality["all_compiled_articles_have_editorjs"] = quality["all_content_valid_editorjs"]
    quality["all_content_blocks_have_source_fact_group_ids"] = quality["all_content_blocks_have_source_ids"]
    quality["no_unknown_fact_group_ids_used"] = quality["no_unknown_fact_group_ids"]
    quality["passed"] = bool(
        quality["all_processed_tasks_have_result"]
        and quality["all_compiled_article_files_exist"]
        and quality["all_content_valid_editorjs"]
        and quality["all_content_blocks_have_source_ids"]
        and quality["no_unknown_fact_group_ids"]
        and quality["review_flags_preserved"]
        and not failed_tasks
    )
    return quality


def _qa_rows(article_drafts: list[dict[str, Any]], reason: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in article_drafts[:limit]:
        rows.append(
            {
                "tag_id": row.get("tag_id", ""),
                "canonical_tag_ru": row.get("canonical_tag_ru", ""),
                "entity_type": row.get("entity_type", ""),
                "a4_strategy": row.get("a4_strategy", ""),
                "article_status": row.get("article_status", ""),
                "needs_review_before_publication": row.get("needs_review_before_publication", False),
                "title": row.get("title", ""),
                "summary": row.get("summary", ""),
                "blocks_count": len(row.get("content", {}).get("blocks", []) if isinstance(row.get("content"), dict) else []),
                "used_fact_groups_count": len(row.get("used_fact_group_ids", []) or []),
                "source_documents_count": len(row.get("source_doc_ids", []) or []),
                "article_file_path": row.get("article_file_path", ""),
                "qa_excerpt": _qa_excerpt(row),
                "quality_warnings": reason if row.get("needs_review_before_publication") else "",
            }
        )
    return rows


def _qa_excerpt(row: dict[str, Any]) -> str:
    content = row.get("content") if isinstance(row.get("content"), dict) else {}
    blocks = content.get("blocks", []) if isinstance(content, dict) else []
    excerpts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        data = block.get("data") if isinstance(block.get("data"), dict) else {}
        if block.get("type") in {"header", "paragraph"}:
            text = str(data.get("text") or "").strip()
            if text:
                excerpts.append(text)
        if len(" ".join(excerpts)) >= 500:
            break
    return " ".join(excerpts)[:700]


def _avg_latency_ms(batch_reports: list[dict[str, Any]]) -> int:
    values = [int(row.get("latency_ms") or 0) for row in batch_reports if int(row.get("latency_ms") or 0) > 0]
    return int(sum(values) / len(values)) if values else 0


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value

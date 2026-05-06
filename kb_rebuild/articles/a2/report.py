from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from kb_rebuild.articles.a2.models import PROMPT_VERSION, SCHEMA_VERSION, STAGE, STAGE_VERSION, A2Config


EVIDENCE_ITEM_FIELDS = [
    "evidence_item_id",
    "task_id",
    "batch_id",
    "tag_id",
    "canonical_tag_ru",
    "canonical_tag_latin",
    "entity_type",
    "doc_id",
    "document_name",
    "window_id",
    "block_ids",
    "block_indexes",
    "heading_context",
    "fact_type",
    "section_hint",
    "claim",
    "quote",
    "quote_validation_status",
    "importance",
    "confidence",
    "relevance",
    "source_strategy",
    "window_quality",
    "match_method",
    "needs_review_before_publication",
    "review_reasons",
    "model",
    "provider",
    "prompt_version",
    "schema_version",
    "created_at",
]

TASK_RESULT_FIELDS = [
    "task_id",
    "tag_id",
    "decision",
    "relevance",
    "evidence_items_count",
    "valid_quote_items_count",
    "invalid_quote_items_count",
    "confidence",
    "batch_id",
    "status",
    "reason",
]

BATCH_REPORT_FIELDS = [
    "batch_id",
    "task_ids",
    "entity_type",
    "source_strategy",
    "priority",
    "tasks_count",
    "input_chars",
    "batch_group_key",
    "status",
    "attempts",
    "split_depth",
    "cache_hit",
    "latency_ms",
    "estimated_cost_usd",
    "error",
]

MANUAL_QA_FIELDS = [
    "task_id",
    "tag_id",
    "canonical_tag_ru",
    "entity_type",
    "document_name",
    "window_text_excerpt",
    "decision",
    "fact_type",
    "claim",
    "quote",
    "quote_validation_status",
    "confidence",
    "review_flag",
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
    config: A2Config,
    inputs: dict[str, Path],
    task_results: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
    batches: list[dict[str, Any]],
    batch_reports: list[dict[str, Any]],
    invalid_llm_responses: list[dict[str, Any]],
    quote_validation_issues: list[dict[str, Any]],
    stats: dict[str, Any],
    stop_reason: str | None,
    warnings: list[str],
) -> dict[str, Any]:
    status_counts = Counter(str(row.get("status") or "") for row in task_results)
    quote_counts = Counter(str(item.get("quote_validation_status") or "") for item in evidence_items)
    by_entity_type: dict[str, Counter[str]] = defaultdict(Counter)
    by_source_strategy: dict[str, Counter[str]] = defaultdict(Counter)
    by_fact_type = Counter(str(item.get("fact_type") or "") for item in evidence_items)
    for result in task_results:
        task = result.get("_task")
        if isinstance(task, dict):
            by_entity_type[str(task.get("entity_type") or "")][str(result.get("status") or "")] += 1
            by_source_strategy[str(task.get("source_strategy") or "")][str(result.get("status") or "")] += 1

    processed_task_ids = {str(row.get("task_id") or "") for row in task_results}
    requested_task_ids = {
        str(task_id)
        for batch in batches
        for task_id in batch.get("task_ids", [])
    }
    quote_not_found_share = (
        quote_counts.get("not_found", 0) / len(evidence_items) if evidence_items else 0.0
    )
    failed_share = status_counts.get("failed", 0) / len(task_results) if task_results else 0.0
    quality = {
        "all_processed_tasks_have_result": requested_task_ids.issubset(processed_task_ids),
        "no_unknown_task_ids": bool(stats.get("no_unknown_task_ids", True)),
        "quote_not_found_share": round(quote_not_found_share, 6),
    }
    quality["passed"] = bool(
        quality["all_processed_tasks_have_result"]
        and quality["no_unknown_task_ids"]
        and failed_share <= 0.01
        and quote_not_found_share <= 0.05
    )

    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "created_at": created_at,
        "input": {
            "a2_task_queue": str(inputs["a2_task_queue_jsonl"]),
            "a1_manifest": str(inputs["a1_manifest_json"]),
        },
        "counts": {
            "tasks_requested": len(requested_task_ids),
            "tasks_processed": len(task_results),
            "tasks_success": status_counts.get("success", 0),
            "tasks_no_evidence": status_counts.get("no_evidence", 0),
            "tasks_review": status_counts.get("review", 0),
            "tasks_failed": status_counts.get("failed", 0),
            "batches_total": len(batches),
            "batches_success": sum(1 for row in batch_reports if row.get("status") == "success"),
            "batches_failed": sum(1 for row in batch_reports if row.get("status") == "failed"),
            "batch_splits": int(stats.get("batch_splits", 0) or 0),
            "evidence_items_total": len(evidence_items),
            "evidence_items_valid_quotes": sum(
                quote_counts.get(status, 0) for status in ("exact", "normalized_exact", "fuzzy")
            ),
            "evidence_items_quote_not_found": quote_counts.get("not_found", 0),
        },
        "by_entity_type": {key: dict(value) for key, value in sorted(by_entity_type.items())},
        "by_source_strategy": {key: dict(value) for key, value in sorted(by_source_strategy.items())},
        "by_fact_type": dict(sorted(by_fact_type.items())),
        "quote_validation": {
            "exact": quote_counts.get("exact", 0),
            "normalized_exact": quote_counts.get("normalized_exact", 0),
            "fuzzy": quote_counts.get("fuzzy", 0),
            "not_found": quote_counts.get("not_found", 0),
        },
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
        "quote_validation_issues_total": len(quote_validation_issues),
    }


def build_manifest(
    *,
    created_at: str,
    config: A2Config,
    inputs: dict[str, Path],
    outputs: dict[str, Path],
) -> dict[str, Any]:
    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "created_at": created_at,
        "source_a1_manifest": str(inputs["a1_manifest_json"]),
        "inputs": {name: str(path) for name, path in inputs.items()},
        "outputs": {name: str(path) for name, path in outputs.items()},
        "provider": config.provider,
        "model": config.model,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "config": {
            "data_dir": str(config.data_dir),
            "a1_dir": str(config.a1_dir),
            "planning_dir": str(config.planning_dir),
            "normalization_final_dir": str(config.normalization_final_dir),
            "out_dir": str(config.out_dir),
            "structured_output_mode": config.structured_output_mode,
            "limit": config.limit,
            "task_filter": config.task_filter,
            "strategy_filter": list(config.strategy_filter),
            "priority_filter": list(config.priority_filter),
            "max_tasks_per_batch": config.max_tasks_per_batch,
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


def build_quality_diagnostics(report: dict[str, Any], quote_validation_issues: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "quality": report.get("quality", {}),
        "quote_validation": report.get("quote_validation", {}),
        "counts": report.get("counts", {}),
        "quote_validation_issue_samples": quote_validation_issues[:20],
        "warnings": report.get("warnings", []),
    }


def build_cost_latency_report(report: dict[str, Any], batch_reports: list[dict[str, Any]]) -> dict[str, Any]:
    counts = report.get("counts", {})
    llm = report.get("llm", {})
    tasks_processed = int(counts.get("tasks_processed", 0) or 0)
    evidence_items_total = int(counts.get("evidence_items_total", 0) or 0)
    cost = float(llm.get("estimated_cost_usd", 0.0) or 0.0)
    return {
        "stage": STAGE,
        "stage_version": STAGE_VERSION,
        "requests": int(llm.get("requests", 0) or 0),
        "tasks_processed": tasks_processed,
        "tasks_per_request": round(tasks_processed / max(int(llm.get("requests", 0) or 0), 1), 4),
        "estimated_cost_usd": cost,
        "cost_per_task": round(cost / tasks_processed, 8) if tasks_processed else 0.0,
        "cost_per_evidence_item": round(cost / evidence_items_total, 8) if evidence_items_total else 0.0,
        "avg_latency_ms": llm.get("avg_latency_ms", 0),
        "batch_reports_count": len(batch_reports),
        "usage_source": "api_or_estimated",
    }


def manual_qa_rows(
    *,
    task_results: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
    quote_validation_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    items_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in evidence_items:
        items_by_task[str(item.get("task_id") or "")].append(item)
    success_items = [item for item in evidence_items if item.get("quote_validation_status") in {"exact", "normalized_exact"}]
    for item in success_items[:10]:
        rows.append(_qa_row_from_item(item, ""))
    no_evidence = [row for row in task_results if row.get("status") == "no_evidence"]
    for result in no_evidence[:5]:
        rows.append(_qa_row_from_result(result))
    review = [row for row in task_results if row.get("status") == "review"]
    for result in review[:5]:
        task_items = items_by_task.get(str(result.get("task_id") or ""), [])
        if task_items:
            rows.append(_qa_row_from_item(task_items[0], str(result.get("reason") or "")))
        else:
            rows.append(_qa_row_from_result(result))
    if len(quote_validation_issues) <= 20:
        for issue in quote_validation_issues:
            rows.append(_qa_row_from_issue(issue))
    return rows


def scrub_internal_task(task_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in row.items() if key != "_task"} for row in task_results]


def _qa_row_from_item(item: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "task_id": item.get("task_id", ""),
        "tag_id": item.get("tag_id", ""),
        "canonical_tag_ru": item.get("canonical_tag_ru", ""),
        "entity_type": item.get("entity_type", ""),
        "document_name": item.get("document_name", ""),
        "window_text_excerpt": "",
        "decision": "evidence_extracted",
        "fact_type": item.get("fact_type", ""),
        "claim": item.get("claim", ""),
        "quote": item.get("quote", ""),
        "quote_validation_status": item.get("quote_validation_status", ""),
        "confidence": item.get("confidence", ""),
        "review_flag": bool(item.get("needs_review_before_publication")) or bool(reason),
    }


def _qa_row_from_result(result: dict[str, Any]) -> dict[str, Any]:
    task = result.get("_task") if isinstance(result.get("_task"), dict) else {}
    return {
        "task_id": result.get("task_id", ""),
        "tag_id": result.get("tag_id", ""),
        "canonical_tag_ru": task.get("canonical_tag_ru", ""),
        "entity_type": task.get("entity_type", ""),
        "document_name": task.get("document_name", ""),
        "window_text_excerpt": str(task.get("window_text") or "")[:500],
        "decision": result.get("decision", ""),
        "fact_type": "",
        "claim": "",
        "quote": "",
        "quote_validation_status": "",
        "confidence": result.get("confidence", ""),
        "review_flag": result.get("status") == "review",
    }


def _qa_row_from_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": issue.get("task_id", ""),
        "tag_id": issue.get("tag_id", ""),
        "canonical_tag_ru": issue.get("canonical_tag_ru", ""),
        "entity_type": issue.get("entity_type", ""),
        "document_name": issue.get("document_name", ""),
        "window_text_excerpt": "",
        "decision": "quote_validation_issue",
        "fact_type": issue.get("fact_type", ""),
        "claim": issue.get("claim", ""),
        "quote": issue.get("quote", ""),
        "quote_validation_status": issue.get("quote_validation_status", ""),
        "confidence": issue.get("confidence", ""),
        "review_flag": True,
    }


def _avg_latency_ms(batch_reports: list[dict[str, Any]]) -> int:
    values = [int(row.get("latency_ms") or 0) for row in batch_reports if int(row.get("latency_ms") or 0) > 0]
    return int(sum(values) / len(values)) if values else 0


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


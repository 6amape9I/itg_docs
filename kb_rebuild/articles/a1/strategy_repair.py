from __future__ import annotations

from collections import Counter
from typing import Any

from kb_rebuild.articles.a1.models import ARTICLE_BLOCKING_REVIEW_MARKERS, A1Config, EXTRACTION_STRATEGIES
from kb_rebuild.articles.planning.loaders import bool_value, list_value


def split_review_reasons(review_reasons: list[Any]) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    publication: list[str] = []
    for reason_value in review_reasons:
        reason = str(reason_value)
        reason_lower = reason.lower()
        if any(marker in reason_lower for marker in ARTICLE_BLOCKING_REVIEW_MARKERS):
            blocking.append(reason)
        elif reason:
            publication.append(reason)
    return _dedupe(blocking), _dedupe(publication)


def repair_work_plan(
    rows: list[dict[str, Any]],
    windows_by_id: dict[str, dict[str, Any]],
    config: A1Config,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    adjusted_rows: list[dict[str, Any]] = []
    adjustments: list[dict[str, Any]] = []
    original_strategy_counts = Counter(str(row.get("strategy") or "") for row in rows)
    adjusted_strategy_counts: Counter[str] = Counter()

    for row in rows:
        adjusted = repair_plan_row(row, windows_by_id, config)
        adjusted_rows.append(adjusted)
        adjusted_strategy_counts[str(adjusted.get("strategy") or "")] += 1
        if adjusted.get("strategy_adjusted"):
            adjustments.append(
                {
                    "tag_id": adjusted.get("tag_id"),
                    "canonical_tag_ru": adjusted.get("canonical_tag_ru"),
                    "entity_type": adjusted.get("entity_type"),
                    "original_strategy": row.get("strategy"),
                    "adjusted_strategy": adjusted.get("strategy"),
                    "strategy_adjustment_reason": adjusted.get("strategy_adjustment_reason"),
                    "publication_review_reasons": adjusted.get("publication_review_reasons", []),
                    "article_blocking_review_reasons": adjusted.get("article_blocking_review_reasons", []),
                    "documents_count": adjusted.get("documents_count"),
                    "source_windows_count": adjusted.get("source_windows_count"),
                }
            )

    report = {
        "original_strategy_counts": dict(sorted(original_strategy_counts.items())),
        "adjusted_strategy_counts": dict(sorted(adjusted_strategy_counts.items())),
        "a0_review_stub_original": original_strategy_counts.get("review_stub", 0),
        "a0_1_rerouted_from_review_stub": sum(1 for item in adjustments if item.get("original_strategy") == "review_stub"),
        "adjustments_total": len(adjustments),
    }
    return adjusted_rows, adjustments, report


def repair_plan_row(
    row: dict[str, Any],
    windows_by_id: dict[str, dict[str, Any]],
    config: A1Config,
) -> dict[str, Any]:
    original_strategy = str(row.get("strategy") or "")
    adjusted = dict(row)
    review_reasons = [str(item) for item in list_value(row.get("review_reasons"))]
    blocking_reasons, publication_reasons = split_review_reasons(review_reasons)
    article_candidate = bool_value(row.get("article_candidate"))
    documents_count = int(row.get("documents_count") or 0)
    source_windows_count = int(row.get("source_windows_count") or 0)

    adjusted["source_strategy_original"] = original_strategy
    adjusted["strategy_adjusted"] = False
    adjusted["strategy_adjustment_reason"] = ""
    adjusted["article_blocking_review_reasons"] = blocking_reasons
    adjusted["publication_review_reasons"] = publication_reasons
    adjusted["needs_review_before_publication"] = bool(blocking_reasons or publication_reasons)

    if blocking_reasons:
        if original_strategy != "review_stub":
            adjusted["strategy"] = "review_stub"
            adjusted["strategy_adjusted"] = True
            adjusted["strategy_adjustment_reason"] = "article_blocking_review_reason"
        adjusted["needs_review_before_article"] = True
        adjusted["needs_review_before_publication"] = True
        _set_estimates(adjusted, 0, 0)
        adjusted["can_direct_copy"] = False
        adjusted["can_create_stub_without_llm"] = True
        return adjusted

    if not article_candidate:
        if original_strategy not in {"stub_only", "review_stub"}:
            adjusted["strategy"] = "stub_only"
            adjusted["strategy_adjusted"] = True
            adjusted["strategy_adjustment_reason"] = "non_article_candidate_not_rerouted"
        return adjusted

    if source_windows_count == 0:
        if original_strategy not in {"no_source_window_review", "review_stub"}:
            adjusted["strategy"] = "no_source_window_review"
            adjusted["strategy_adjusted"] = True
            adjusted["strategy_adjustment_reason"] = "source_windows_count_zero"
        adjusted["needs_review_before_article"] = True
        adjusted["needs_review_before_publication"] = True
        _set_estimates(adjusted, 0, 0)
        return adjusted

    if original_strategy == "review_stub":
        new_strategy = _rerouted_article_strategy(row, windows_by_id, config)
        adjusted["strategy"] = new_strategy
        adjusted["strategy_adjusted"] = True
        adjusted["strategy_adjustment_reason"] = "publication_review_not_article_blocking"
        adjusted["needs_review_before_article"] = False
        adjusted["needs_review_before_publication"] = True
        adjusted["publication_review_reasons"] = publication_reasons or review_reasons
        if new_strategy == "direct_copy_candidate":
            _set_estimates(adjusted, 0, 0)
            adjusted["can_direct_copy"] = True
            adjusted["can_create_stub_without_llm"] = False
        else:
            _set_estimates(adjusted, source_windows_count, 1)
            adjusted["can_direct_copy"] = False
            adjusted["can_create_stub_without_llm"] = False
        return adjusted

    if original_strategy in EXTRACTION_STRATEGIES:
        _set_estimates(adjusted, source_windows_count, 1)
    if original_strategy == "direct_copy_candidate":
        _set_estimates(adjusted, 0, 0)
    return adjusted


def _rerouted_article_strategy(
    row: dict[str, Any],
    windows_by_id: dict[str, dict[str, Any]],
    config: A1Config,
) -> str:
    documents_count = int(row.get("documents_count") or 0)
    if documents_count == 1:
        return "direct_copy_candidate" if _can_direct_copy_from_plan(row, windows_by_id) else "single_doc_extract"
    if 2 <= documents_count <= config.low_count_doc_threshold:
        return "low_count_batch_extract"
    if documents_count > config.high_frequency_doc_threshold:
        return "high_frequency_map_reduce"
    return "multi_doc_map_reduce"


def _can_direct_copy_from_plan(row: dict[str, Any], windows_by_id: dict[str, dict[str, Any]]) -> bool:
    if int(row.get("documents_count") or 0) != 1:
        return False
    if int(row.get("source_windows_count") or 0) < 1:
        return False
    if int(row.get("competing_article_candidate_tags_in_doc") or 0) != 0:
        return False
    windows = [windows_by_id[item] for item in list_value(row.get("source_window_ids")) if str(item) in windows_by_id]
    if not windows:
        return False
    best_window = max(windows, key=lambda item: float(item.get("coverage_ratio_estimate") or 0.0))
    quality = str(best_window.get("window_quality") or "")
    if quality not in {"high", "medium"}:
        return False
    if str(best_window.get("match_method") or "") == "short_doc_fallback":
        return True
    return float(best_window.get("coverage_ratio_estimate") or 0.0) >= 0.8


def _set_estimates(row: dict[str, Any], extraction_tasks: int, compilation_tasks: int) -> None:
    row["estimated_llm_extraction_tasks"] = extraction_tasks
    row["estimated_article_compilation_tasks"] = compilation_tasks


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result

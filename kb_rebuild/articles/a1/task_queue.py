from __future__ import annotations

from typing import Any

from kb_rebuild.articles.a1.models import EXTRACTION_STRATEGIES
from kb_rebuild.articles.planning.loaders import bool_value, list_value


def build_tasks_for_plan(
    *,
    plan: dict[str, Any],
    source_strategy: str,
    article_status: str,
    windows_by_id: dict[str, dict[str, Any]],
    next_task_number: int,
) -> tuple[list[dict[str, Any]], int]:
    if source_strategy not in EXTRACTION_STRATEGIES or article_status == "direct_copy_article":
        return [], next_task_number
    tasks: list[dict[str, Any]] = []
    for window_id_value in list_value(plan.get("source_window_ids")):
        window_id = str(window_id_value)
        window = windows_by_id.get(window_id)
        if window is None:
            continue
        task = build_task(plan=plan, source_strategy=source_strategy, window=window, task_number=next_task_number)
        tasks.append(task)
        next_task_number += 1
    return tasks, next_task_number


def build_task(
    *,
    plan: dict[str, Any],
    source_strategy: str,
    window: dict[str, Any],
    task_number: int,
) -> dict[str, Any]:
    window_quality = str(window.get("window_quality") or "")
    review_reasons = [str(item) for item in list_value(plan.get("review_reasons"))]
    publication_review_reasons = [str(item) for item in list_value(plan.get("publication_review_reasons"))]
    needs_review_before_publication = bool_value(plan.get("needs_review_before_publication"))
    if window_quality == "low":
        needs_review_before_publication = True
        if "low_quality_source_window" not in review_reasons:
            review_reasons.append("low_quality_source_window")
        if "low_quality_source_window" not in publication_review_reasons:
            publication_review_reasons.append("low_quality_source_window")
    priority = task_priority(plan=plan, source_strategy=source_strategy, window=window, needs_review_before_publication=needs_review_before_publication)
    chars = int(window.get("window_char_length") or len(str(window.get("window_text") or "")))
    return {
        "task_id": f"a2task_{task_number:09d}",
        "tag_id": str(plan.get("tag_id") or ""),
        "canonical_tag_ru": str(plan.get("canonical_tag_ru") or ""),
        "canonical_tag_latin": _nullable_string(plan.get("canonical_tag_latin")),
        "entity_type": str(plan.get("entity_type") or ""),
        "source_strategy": source_strategy,
        "doc_id": str(window.get("doc_id") or ""),
        "document_name": str(window.get("document_name") or ""),
        "window_id": str(window.get("window_id") or ""),
        "window_text": str(window.get("window_text") or ""),
        "window_char_length": chars,
        "block_ids": [str(item) for item in list_value(window.get("block_ids"))],
        "block_indexes": [int(item) for item in list_value(window.get("block_indexes"))],
        "heading_context": [str(item) for item in list_value(window.get("heading_context"))],
        "match_method": str(window.get("match_method") or ""),
        "window_quality": window_quality,
        "needs_review_before_publication": needs_review_before_publication,
        "review_reasons": review_reasons,
        "publication_review_reasons": publication_review_reasons,
        "priority": priority,
        "batch_group_key": f"{plan.get('entity_type')}:{source_strategy}",
        "estimated_input_chars": chars,
        "recommended_max_output_tokens": recommended_max_output_tokens(chars),
    }


def task_priority(
    *,
    plan: dict[str, Any],
    source_strategy: str,
    window: dict[str, Any],
    needs_review_before_publication: bool,
) -> str:
    window_quality = str(window.get("window_quality") or "")
    if window_quality == "low":
        return "low"
    if source_strategy == "high_frequency_map_reduce":
        return "low"
    if (
        bool_value(plan.get("article_candidate"))
        and not bool_value(plan.get("needs_review_before_article"))
        and window_quality == "high"
        and source_strategy in {"single_doc_extract", "low_count_batch_extract"}
        and not needs_review_before_publication
    ):
        return "high"
    return "medium"


def recommended_max_output_tokens(input_chars: int) -> int:
    if input_chars <= 2500:
        return 2000
    if input_chars <= 8000:
        return 3000
    return 4500


def _nullable_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None

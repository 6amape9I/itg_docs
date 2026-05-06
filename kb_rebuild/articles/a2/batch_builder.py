from __future__ import annotations

from collections import OrderedDict
from typing import Any


PROMPT_OVERHEAD_CHARS = 4000


def filter_tasks(
    tasks: list[dict[str, Any]],
    *,
    task_filter: str = "all",
    strategy_filter: tuple[str, ...] | list[str] | set[str] | None = None,
    priority_filter: tuple[str, ...] | list[str] | set[str] | None = None,
    limit: int | None = None,
    completed_task_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    strategies = {str(item) for item in strategy_filter} if strategy_filter else None
    priorities = {str(item) for item in priority_filter} if priority_filter else None
    completed = completed_task_ids or set()
    selected: list[dict[str, Any]] = []
    for task in tasks:
        task_id = str(task.get("task_id") or "")
        if not task_id:
            continue
        if task_filter == "pending_review" and not bool(task.get("needs_review_before_publication")):
            continue
        if strategies is not None and str(task.get("source_strategy") or "") not in strategies:
            continue
        if priorities is not None and str(task.get("priority") or "") not in priorities:
            continue
        if task_id in completed:
            continue
        selected.append(task)
        if limit is not None and len(selected) >= limit:
            break
    return selected


def build_batches(
    tasks: list[dict[str, Any]],
    *,
    max_tasks_per_batch: int = 8,
    batch_char_limit: int = 60000,
    start_index: int = 1,
) -> list[dict[str, Any]]:
    if max_tasks_per_batch < 1:
        raise ValueError("max_tasks_per_batch must be >= 1")
    if batch_char_limit < 1:
        raise ValueError("batch_char_limit must be >= 1")

    grouped: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    for task in tasks:
        key = batch_group_key(task)
        grouped.setdefault(key, []).append(task)

    batches: list[dict[str, Any]] = []
    next_index = start_index
    for key, group_tasks in grouped.items():
        current: list[dict[str, Any]] = []
        current_chars = PROMPT_OVERHEAD_CHARS
        for task in group_tasks:
            task_chars = task_input_chars(task)
            if current and (
                len(current) >= max_tasks_per_batch
                or current_chars + task_chars > batch_char_limit
            ):
                batches.append(_batch_record(next_index, key, current, current_chars))
                next_index += 1
                current = []
                current_chars = PROMPT_OVERHEAD_CHARS
            current.append(task)
            current_chars += task_chars
        if current:
            batches.append(_batch_record(next_index, key, current, current_chars))
            next_index += 1
    return batches


def batch_group_key(task: dict[str, Any]) -> str:
    entity_type = str(task.get("entity_type") or "unknown")
    source_strategy = str(task.get("source_strategy") or "unknown")
    priority = str(task.get("priority") or "medium")
    return f"{entity_type}:{source_strategy}:{priority}"


def task_input_chars(task: dict[str, Any]) -> int:
    estimated = task.get("estimated_input_chars")
    try:
        parsed = int(estimated)
    except (TypeError, ValueError):
        parsed = 0
    return max(parsed, len(str(task.get("window_text") or "")))


def batch_prompt_payload(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        "batch_id": batch["batch_id"],
        "tasks": [_task_prompt_payload(task) for task in batch.get("tasks", [])],
    }


def _batch_record(index: int, key: str, tasks: list[dict[str, Any]], input_chars: int) -> dict[str, Any]:
    first = tasks[0]
    return {
        "batch_id": f"a2batch_{index:06d}",
        "task_ids": [str(task.get("task_id") or "") for task in tasks],
        "entity_type": str(first.get("entity_type") or ""),
        "source_strategy": str(first.get("source_strategy") or ""),
        "priority": str(first.get("priority") or ""),
        "tasks_count": len(tasks),
        "input_chars": input_chars,
        "batch_group_key": key,
        "tasks": tasks,
    }


def _task_prompt_payload(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": str(task.get("task_id") or ""),
        "tag_id": str(task.get("tag_id") or ""),
        "canonical_tag_ru": str(task.get("canonical_tag_ru") or ""),
        "canonical_tag_latin": _nullable_string(task.get("canonical_tag_latin")),
        "entity_type": str(task.get("entity_type") or ""),
        "source_strategy": str(task.get("source_strategy") or ""),
        "doc_id": str(task.get("doc_id") or ""),
        "document_name": str(task.get("document_name") or ""),
        "window_id": str(task.get("window_id") or ""),
        "heading_context": list(task.get("heading_context") or []),
        "window_text": str(task.get("window_text") or ""),
        "window_quality": str(task.get("window_quality") or ""),
        "match_method": str(task.get("match_method") or ""),
    }


def _nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


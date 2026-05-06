from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from kb_rebuild.articles.a4.models import ARTICLE_SECTIONS, COMPILABLE_STRATEGIES, GENERIC_SECTIONS


FACT_TYPE_SOFT_CAPS = {
    "definition": 8,
    "description": 8,
    "classification": 8,
    "mechanism": 8,
    "symptom": 12,
    "diagnostics": 12,
    "treatment": 12,
    "usage_or_dosage": 12,
    "indication": 12,
    "contraindication": 8,
    "side_effect": 8,
    "procedure_step": 15,
    "composition": 10,
    "other": 10,
}
FACT_TYPE_PRIORITY = {
    "definition": 0,
    "description": 1,
    "classification": 2,
    "mechanism": 3,
    "symptom": 4,
    "diagnostics": 5,
    "treatment": 6,
    "usage_or_dosage": 7,
    "indication": 8,
    "contraindication": 9,
    "side_effect": 10,
    "procedure_step": 11,
    "composition": 12,
}
ENTITY_TYPE_ORDER = [
    "disease",
    "drug_trade_name",
    "diagnostic_method",
    "procedure",
    "microorganism",
    "supplement",
    "biological_substance",
    "medical_concept",
    "symptom",
    "medical_device",
]


def build_compilation_tasks(
    *,
    a4_inputs: list[dict[str, Any]],
    fact_groups: list[dict[str, Any]],
    limit: int | None,
    strategy_filter: tuple[str, ...],
    entity_type_filter: tuple[str, ...] | None,
    priority_filter: tuple[str, ...],
    max_fact_groups_per_tag: int,
    max_quotes_per_tag: int,
    completed_task_tag_ids: set[str] | None = None,
    retry_failures: bool = False,
) -> list[dict[str, Any]]:
    fact_groups_by_id = {str(row.get("fact_group_id") or ""): row for row in fact_groups}
    completed = completed_task_tag_ids or set()
    candidates: list[dict[str, Any]] = []
    for row in a4_inputs:
        if not row.get("ready_for_a4"):
            continue
        strategy = str(row.get("a4_strategy") or "")
        if strategy not in COMPILABLE_STRATEGIES or strategy not in strategy_filter:
            continue
        entity_type = str(row.get("entity_type") or "")
        if entity_type_filter is not None and entity_type not in entity_type_filter:
            continue
        tag_id = str(row.get("tag_id") or "")
        if completed and tag_id in completed and not retry_failures:
            continue
        selected_groups, excluded_ids = select_fact_groups(
            row,
            fact_groups_by_id=fact_groups_by_id,
            max_fact_groups=max_fact_groups_per_tag,
            max_quotes=max_quotes_per_tag,
        )
        if not selected_groups:
            continue
        priority = _priority(row, selected_groups)
        if priority not in priority_filter:
            continue
        task = {
            "task_id": "",
            "tag_id": tag_id,
            "canonical_tag_ru": row.get("canonical_tag_ru"),
            "canonical_tag_latin": row.get("canonical_tag_latin"),
            "entity_type": entity_type,
            "a4_strategy": strategy,
            "article_status_from_a1": row.get("article_status_from_a1"),
            "needs_review_before_publication": bool(row.get("needs_review_before_publication")),
            "review_reasons": _list_value(row.get("review_reasons")),
            "fact_group_ids": [group["fact_group_id"] for group in selected_groups],
            "core_fact_group_ids": [group["fact_group_id"] for group in selected_groups if group.get("a4_usage") == "core_fact"],
            "supporting_fact_group_ids": [group["fact_group_id"] for group in selected_groups if group.get("a4_usage") == "supporting_fact"],
            "review_only_fact_group_ids": [],
            "excluded_fact_group_ids": excluded_ids,
            "fact_groups": [_prompt_fact_group(group) for group in selected_groups],
            "source_documents_count": row.get("source_documents_count"),
            "usable_fact_groups_count": len(selected_groups),
            "priority": priority,
            "recommended_sections": ARTICLE_SECTIONS.get(entity_type, GENERIC_SECTIONS),
            "recommended_max_output_tokens": 16000,
        }
        task["estimated_input_chars"] = len(json.dumps(task, ensure_ascii=False, sort_keys=True))
        candidates.append(task)

    selected = _select_smoke_tasks(candidates, limit=limit)
    for index, task in enumerate(selected, start=1):
        task["task_id"] = f"a4task_{index:09d}"
    return selected


def select_fact_groups(
    a4_row: dict[str, Any],
    *,
    fact_groups_by_id: dict[str, dict[str, Any]],
    max_fact_groups: int,
    max_quotes: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    requested_ids = [str(item) for item in _list_value(a4_row.get("fact_group_ids"))]
    groups = [
        fact_groups_by_id[group_id]
        for group_id in requested_ids
        if group_id in fact_groups_by_id
        and fact_groups_by_id[group_id].get("usable_for_a4")
        and fact_groups_by_id[group_id].get("a4_usage") in {"core_fact", "supporting_fact"}
    ]
    ranked = sorted(groups, key=_fact_group_rank)
    selected: list[dict[str, Any]] = []
    excluded: list[str] = []
    fact_type_counts: dict[str, int] = defaultdict(int)
    for group in ranked:
        group_id = str(group.get("fact_group_id") or "")
        fact_type = str(group.get("fact_type") or "other")
        soft_cap = FACT_TYPE_SOFT_CAPS.get(fact_type, FACT_TYPE_SOFT_CAPS["other"])
        if len(selected) >= max_fact_groups or len(selected) >= max_quotes:
            excluded.append(group_id)
            continue
        if fact_type_counts[fact_type] >= soft_cap and len(selected) >= max(5, max_fact_groups // 2):
            excluded.append(group_id)
            continue
        selected.append(group)
        fact_type_counts[fact_type] += 1
    return selected, excluded


def build_batches(
    tasks: list[dict[str, Any]],
    *,
    max_tags_per_batch: int,
    batch_char_limit: int,
) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for task in tasks:
        task_chars = int(task.get("estimated_input_chars") or 0)
        force_single = task_chars > batch_char_limit // 2
        should_flush = bool(
            current
            and (
                force_single
                or len(current) >= max_tags_per_batch
                or current_chars + task_chars > batch_char_limit
            )
        )
        if should_flush:
            batches.append(_batch(len(batches) + 1, current))
            current = []
            current_chars = 0
        current.append(task)
        current_chars += task_chars
        if force_single:
            batches.append(_batch(len(batches) + 1, current))
            current = []
            current_chars = 0
    if current:
        batches.append(_batch(len(batches) + 1, current))
    return batches


def status_updates_for_all_inputs(a4_inputs: list[dict[str, Any]], selected_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected_by_tag = {str(task.get("tag_id") or ""): task for task in selected_tasks}
    rows: list[dict[str, Any]] = []
    for row in a4_inputs:
        tag_id = str(row.get("tag_id") or "")
        task = selected_by_tag.get(tag_id)
        if task:
            status = "selected_for_compilation"
            task_id = task.get("task_id")
        else:
            strategy = str(row.get("a4_strategy") or "")
            if strategy in COMPILABLE_STRATEGIES and row.get("ready_for_a4"):
                status = "not_selected_in_smoke_limit"
            else:
                status = f"skipped_{strategy or 'unknown'}"
            task_id = ""
        rows.append(
            {
                "tag_id": tag_id,
                "task_id": task_id,
                "canonical_tag_ru": row.get("canonical_tag_ru"),
                "entity_type": row.get("entity_type"),
                "a4_strategy": row.get("a4_strategy"),
                "ready_for_a4": row.get("ready_for_a4"),
                "status_update": status,
                "needs_review_before_publication": row.get("needs_review_before_publication"),
                "review_reasons": row.get("review_reasons", []),
            }
        )
    return rows


def _select_smoke_tasks(tasks: list[dict[str, Any]], *, limit: int | None) -> list[dict[str, Any]]:
    ordered = sorted(tasks, key=_candidate_sort_key)
    if limit is None or len(ordered) <= limit:
        return ordered
    selected: dict[str, dict[str, Any]] = {}

    high_volume_count = min(10 if limit >= 200 else 5, limit)
    for task in sorted(ordered, key=lambda row: int(row.get("usable_fact_groups_count") or 0), reverse=True)[:high_volume_count]:
        selected[str(task["tag_id"])] = task

    target_per_strategy = max(1, limit // 2)
    for strategy in ("compile_from_fact_groups", "compile_with_review_flag"):
        for task in _round_robin_by_entity([row for row in ordered if row.get("a4_strategy") == strategy]):
            if len(selected) >= limit:
                break
            current_strategy_count = sum(1 for row in selected.values() if row.get("a4_strategy") == strategy)
            if current_strategy_count >= target_per_strategy and len(selected) < limit - 5:
                continue
            selected.setdefault(str(task["tag_id"]), task)

    for task in _round_robin_by_entity(ordered):
        if len(selected) >= limit:
            break
        selected.setdefault(str(task["tag_id"]), task)
    return list(selected.values())[:limit]


def _round_robin_by_entity(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in sorted(tasks, key=_candidate_sort_key):
        buckets[str(task.get("entity_type") or "")].append(task)
    entity_order = sorted(buckets, key=lambda value: ENTITY_TYPE_ORDER.index(value) if value in ENTITY_TYPE_ORDER else len(ENTITY_TYPE_ORDER))
    result: list[dict[str, Any]] = []
    while any(buckets.values()):
        for entity_type in entity_order:
            if buckets[entity_type]:
                result.append(buckets[entity_type].pop(0))
    return result


def _batch(index: int, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "batch_id": f"a4batch_{index:06d}",
        "task_ids": [str(task.get("task_id") or "") for task in tasks],
        "tag_ids": [str(task.get("tag_id") or "") for task in tasks],
        "entity_types": sorted({str(task.get("entity_type") or "") for task in tasks}),
        "a4_strategies": sorted({str(task.get("a4_strategy") or "") for task in tasks}),
        "tasks_count": len(tasks),
        "input_chars": sum(int(task.get("estimated_input_chars") or 0) for task in tasks),
        "tasks": tasks,
    }


def _prompt_fact_group(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "fact_group_id": group.get("fact_group_id"),
        "fact_type": group.get("fact_type"),
        "section_hint": group.get("section_hint"),
        "representative_claim": group.get("representative_claim"),
        "representative_quote": group.get("representative_quote"),
        "representative_quote_validation_status": group.get("representative_quote_validation_status"),
        "source_doc_ids": group.get("source_doc_ids", []),
        "source_documents_count": group.get("source_documents_count", 0),
        "confidence": group.get("confidence", 0.0),
        "importance": group.get("importance"),
        "a4_usage": group.get("a4_usage"),
    }


def _fact_group_rank(group: dict[str, Any]) -> tuple[int, int, int, int, float, int, int, str]:
    usage_rank = {"core_fact": 0, "supporting_fact": 1}.get(str(group.get("a4_usage") or ""), 2)
    importance_rank = {"high": 0, "medium": 1, "low": 2}.get(str(group.get("importance") or ""), 3)
    fact_rank = FACT_TYPE_PRIORITY.get(str(group.get("fact_type") or ""), 99)
    quote_rank = {"exact": 0, "normalized_exact": 1}.get(str(group.get("representative_quote_validation_status") or ""), 2)
    try:
        confidence = float(group.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    source_count = int(group.get("source_documents_count") or 0)
    text_len = len(str(group.get("representative_claim") or "")) + len(str(group.get("representative_quote") or ""))
    return (usage_rank, importance_rank, fact_rank, quote_rank, -confidence, -source_count, text_len, str(group.get("fact_group_id") or ""))


def _candidate_sort_key(task: dict[str, Any]) -> tuple[int, int, int, str]:
    strategy_rank = {"compile_from_fact_groups": 0, "compile_with_review_flag": 1}.get(str(task.get("a4_strategy") or ""), 2)
    entity_type = str(task.get("entity_type") or "")
    entity_rank = ENTITY_TYPE_ORDER.index(entity_type) if entity_type in ENTITY_TYPE_ORDER else len(ENTITY_TYPE_ORDER)
    return (strategy_rank, entity_rank, -int(task.get("usable_fact_groups_count") or 0), str(task.get("tag_id") or ""))


def _priority(row: dict[str, Any], selected_groups: list[dict[str, Any]]) -> str:
    if row.get("needs_review_before_publication") or len(selected_groups) >= 20:
        return "high"
    if len(selected_groups) >= 5:
        return "medium"
    return "low"


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value:
        return [str(value)]
    return []


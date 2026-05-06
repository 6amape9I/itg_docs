from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def build_tag_outputs(
    *,
    status_rows: list[dict[str, Any]],
    task_results: list[dict[str, Any]],
    valid_evidence: list[dict[str, Any]],
    review_evidence: list[dict[str, Any]],
    rejected_evidence: list[dict[str, Any]],
    fact_groups: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    task_tag_ids = {str(row.get("tag_id") or "") for row in task_results if row.get("tag_id")}
    valid_by_tag = _items_by_tag(valid_evidence)
    review_by_tag = _items_by_tag(review_evidence)
    rejected_by_tag = _items_by_tag(rejected_evidence)
    groups_by_tag = _items_by_tag(fact_groups)

    tag_index: list[dict[str, Any]] = []
    a4_input: list[dict[str, Any]] = []
    tags_without_usable: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []

    for status in status_rows:
        tag_id = str(status.get("tag_id") or "")
        tag_groups = sorted(groups_by_tag.get(tag_id, []), key=lambda row: str(row.get("fact_group_id") or ""))
        usable_groups = [row for row in tag_groups if row.get("usable_for_a4")]
        core_groups = [row for row in tag_groups if row.get("a4_usage") == "core_fact"]
        supporting_groups = [row for row in tag_groups if row.get("a4_usage") == "supporting_fact"]
        review_only_groups = [row for row in tag_groups if row.get("a4_usage") == "review_only"]
        source_docs = sorted({doc_id for group in tag_groups for doc_id in _list_value(group.get("source_doc_ids"))})
        needs_review = bool(status.get("needs_review_before_publication")) or any(
            bool(group.get("needs_review_before_publication")) for group in usable_groups
        )
        review_reasons = sorted(
            set(
                _list_value(status.get("review_reasons"))
                + _list_value(status.get("publication_review_reasons"))
                + [
                    reason
                    for group in usable_groups
                    for reason in _list_value(group.get("review_reasons"))
                ]
            )
        )
        strategy, ready = _a4_strategy(status, usable_groups=usable_groups, needs_review=needs_review)
        fact_types = sorted({str(group.get("fact_type") or "") for group in tag_groups if group.get("fact_type")})
        row = {
            "tag_id": tag_id,
            "canonical_tag_ru": status.get("canonical_tag_ru"),
            "canonical_tag_latin": status.get("canonical_tag_latin"),
            "entity_type": status.get("entity_type"),
            "article_status": status.get("article_status"),
            "article_candidate": bool(status.get("article_candidate")),
            "evidence_items_total": len(valid_by_tag.get(tag_id, [])) + len(review_by_tag.get(tag_id, [])) + len(rejected_by_tag.get(tag_id, [])),
            "valid_evidence_items": len(valid_by_tag.get(tag_id, [])),
            "review_evidence_items": len(review_by_tag.get(tag_id, [])),
            "rejected_evidence_items": len(rejected_by_tag.get(tag_id, [])),
            "fact_groups_total": len(tag_groups),
            "core_fact_groups": len(core_groups),
            "supporting_fact_groups": len(supporting_groups),
            "review_only_fact_groups": len(review_only_groups),
            "source_documents_count": len(source_docs),
            "fact_types": fact_types,
            "ready_for_a4": ready,
            "a4_strategy": strategy,
            "needs_review_before_publication": bool(needs_review and usable_groups),
            "review_reasons": review_reasons if usable_groups else _list_value(status.get("review_reasons")),
        }
        tag_index.append(row)

        a4_row = {
            "tag_id": tag_id,
            "canonical_tag_ru": status.get("canonical_tag_ru"),
            "entity_type": status.get("entity_type"),
            "article_status_from_a1": status.get("article_status"),
            "a4_strategy": strategy,
            "ready_for_a4": ready,
            "fact_group_ids": [group["fact_group_id"] for group in usable_groups],
            "core_fact_group_ids": [group["fact_group_id"] for group in core_groups if group.get("usable_for_a4")],
            "supporting_fact_group_ids": [group["fact_group_id"] for group in supporting_groups if group.get("usable_for_a4")],
            "review_only_fact_group_ids": [group["fact_group_id"] for group in review_only_groups],
            "source_documents_count": len(source_docs),
            "usable_fact_groups_count": len(usable_groups),
            "needs_review_before_publication": bool(needs_review and usable_groups),
            "review_reasons": review_reasons if usable_groups else _list_value(status.get("review_reasons")),
        }
        a4_input.append(a4_row)

        has_a2_tasks = tag_id in task_tag_ids or int(status.get("a2_extraction_tasks_count") or 0) > 0
        if has_a2_tasks and not usable_groups and strategy == "insufficient_evidence_review":
            tags_without_usable.append(
                {
                    "tag_id": tag_id,
                    "canonical_tag_ru": status.get("canonical_tag_ru"),
                    "canonical_tag_latin": status.get("canonical_tag_latin"),
                    "entity_type": status.get("entity_type"),
                    "article_status": status.get("article_status"),
                    "a2_tasks_present": has_a2_tasks,
                    "evidence_items_total": row["evidence_items_total"],
                    "review_evidence_items": row["review_evidence_items"],
                    "rejected_evidence_items": row["rejected_evidence_items"],
                    "fact_groups_total": row["fact_groups_total"],
                    "reason": "no_usable_fact_groups",
                }
            )

        coverage = dict(row)
        coverage["coverage_category"] = _coverage_category(status, usable_groups=usable_groups)
        coverage_rows.append(coverage)

    return tag_index, a4_input, tags_without_usable, coverage_rows


def coverage_counts(tag_index: list[dict[str, Any]], task_results: list[dict[str, Any]]) -> dict[str, int]:
    task_tag_ids = {str(row.get("tag_id") or "") for row in task_results if row.get("tag_id")}
    return {
        "final_tags_total": len(tag_index),
        "tags_with_a2_tasks": len(task_tag_ids),
        "tags_with_evidence_items": sum(1 for row in tag_index if int(row.get("evidence_items_total") or 0) > 0),
        "tags_with_valid_evidence": sum(1 for row in tag_index if int(row.get("valid_evidence_items") or 0) > 0),
        "tags_without_usable_evidence": sum(1 for row in tag_index if row.get("a4_strategy") == "insufficient_evidence_review"),
        "ready_for_a4_tags": sum(1 for row in tag_index if row.get("ready_for_a4")),
        "compile_with_review_flag_tags": sum(1 for row in tag_index if row.get("a4_strategy") == "compile_with_review_flag"),
        "direct_copy_already_done_tags": sum(1 for row in tag_index if row.get("a4_strategy") == "direct_copy_already_done"),
        "stub_only_tags": sum(1 for row in tag_index if row.get("a4_strategy") == "stub_only"),
        "review_stub_tags": sum(1 for row in tag_index if row.get("a4_strategy") == "review_stub"),
    }


def _a4_strategy(status: dict[str, Any], *, usable_groups: list[dict[str, Any]], needs_review: bool) -> tuple[str, bool]:
    article_status = str(status.get("article_status") or "")
    if article_status == "direct_copy_article":
        return "direct_copy_already_done", False
    if article_status == "stub_only":
        return "stub_only", False
    if article_status == "review_stub":
        return "review_stub", False
    if usable_groups:
        if needs_review:
            return "compile_with_review_flag", True
        return "compile_from_fact_groups", True
    return "insufficient_evidence_review", False


def _coverage_category(status: dict[str, Any], *, usable_groups: list[dict[str, Any]]) -> str:
    article_status = str(status.get("article_status") or "")
    if article_status == "direct_copy_article":
        return "direct_copy_article"
    if article_status == "stub_only":
        return "stub_only"
    if article_status == "review_stub":
        return "review_stub"
    if usable_groups:
        return "pending_with_usable_evidence"
    return "pending_without_usable_evidence"


def _items_by_tag(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_tag: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_tag[str(item.get("tag_id") or "")].append(item)
    return dict(by_tag)


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value:
        return [str(value)]
    return []


from __future__ import annotations

import hashlib
import json
from typing import Any


REVIEW_FIELDS = ["canonical_tag_ru", "canonical_tag_latin", "aliases", "need_review"]


def specialist_review_rows(canonical_rows: list[dict[str, Any]], aliases_by_tag_id: dict[str, list[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in canonical_rows:
        tag_id = str(row.get("tag_id") or "")
        rows.append(
            {
                "canonical_tag_ru": str(row.get("canonical_tag_ru") or ""),
                "canonical_tag_latin": str(row.get("canonical_tag_latin") or "") or "null",
                "aliases": json.dumps(sorted(set(aliases_by_tag_id.get(tag_id, []))), ensure_ascii=False),
                "need_review": "true" if bool(row.get("need_review")) else "false",
            }
        )
    return rows


def specialist_review_sample(
    canonical_rows: list[dict[str, Any]],
    aliases_by_tag_id: dict[str, list[str]],
    *,
    sample_size: int,
) -> list[dict[str, Any]]:
    if sample_size <= 0:
        return []
    if len(canonical_rows) <= sample_size:
        return specialist_review_rows(canonical_rows, aliases_by_tag_id)

    selected: dict[str, dict[str, Any]] = {}
    need_review = [row for row in canonical_rows if bool(row.get("need_review"))]
    for row in sorted(need_review, key=_review_priority)[:sample_size]:
        selected[str(row["tag_id"])] = row
    if len(selected) >= sample_size:
        return specialist_review_rows(list(selected.values()), aliases_by_tag_id)

    for row in _top_by_entity_type(canonical_rows):
        selected.setdefault(str(row["tag_id"]), row)
        if len(selected) >= sample_size:
            break

    for row in sorted(canonical_rows, key=_stable_sample_key):
        selected.setdefault(str(row["tag_id"]), row)
        if len(selected) >= sample_size:
            break

    return specialist_review_rows(
        sorted(selected.values(), key=lambda row: (str(row.get("entity_type") or ""), str(row.get("canonical_tag_ru") or ""), str(row.get("tag_id") or ""))),
        aliases_by_tag_id,
    )


def _review_priority(row: dict[str, Any]) -> tuple[int, int, int, str]:
    reasons = row.get("review_reasons")
    reason_text = " ".join(str(reason) for reason in reasons) if isinstance(reasons, list) else str(reasons or "")
    priority = 10
    if "drug_trade_name_active_substance_conflict" in reason_text:
        priority = 0
    elif "alias_conflict" in reason_text:
        priority = 1
    elif "merge_conflict" in reason_text or "rejected_constraint_conflict" in reason_text:
        priority = 2
    return (
        priority,
        -int(row.get("mentions_count") or 0),
        -int(row.get("documents_count") or 0),
        str(row.get("tag_id") or ""),
    )


def _top_by_entity_type(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        entity_type = str(row.get("entity_type") or "")
        current = best.get(entity_type)
        if current is None or (int(row.get("mentions_count") or 0), str(row.get("tag_id") or "")) > (
            int(current.get("mentions_count") or 0),
            str(current.get("tag_id") or ""),
        ):
            best[entity_type] = row
    return [best[key] for key in sorted(best)]


def _stable_sample_key(row: dict[str, Any]) -> str:
    value = f"{row.get('entity_type', '')}\n{row.get('tag_id', '')}\n{row.get('canonical_tag_ru', '')}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

from __future__ import annotations

import hashlib
from collections import Counter
from difflib import SequenceMatcher
from typing import Any

from kb_rebuild.articles.a3.dedupe import normalize_text, numeric_tokens, token_set
from kb_rebuild.articles.a3.models import CORE_FACT_TYPES, REVIEW_LAYER, SUPPORTING_FACT_TYPES, VALID_LAYER


CLAIM_SEQUENCE_THRESHOLD = 0.88
TOKEN_JACCARD_THRESHOLD = 0.82


def build_fact_groups(
    evidence_items: list[dict[str, Any]],
    *,
    max_quotes_per_fact_group: int = 8,
    max_fact_groups_per_tag: int = 200,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in evidence_items:
        buckets.setdefault((str(item.get("tag_id") or ""), str(item.get("fact_type") or "")), []).append(item)

    fact_groups: list[dict[str, Any]] = []
    tag_group_counts: Counter[str] = Counter()
    for (tag_id, fact_type), bucket in sorted(buckets.items()):
        candidates: list[list[dict[str, Any]]] = []
        for item in sorted(bucket, key=_item_sort_key):
            placed = False
            for group_items in candidates:
                if _can_group(item, group_items):
                    group_items.append(item)
                    placed = True
                    break
            if not placed:
                candidates.append([item])

        for group_items in candidates:
            if tag_group_counts[tag_id] >= max_fact_groups_per_tag:
                overflow = dict(group_items[0])
                overflow["a3_layer"] = REVIEW_LAYER
                overflow["a3_filter_reasons"] = sorted(set(_list_value(overflow.get("a3_filter_reasons")) + ["max_fact_groups_per_tag_overflow"]))
                group_items = [overflow]
            fact_group = _build_fact_group(group_items, max_quotes_per_fact_group=max_quotes_per_fact_group)
            fact_groups.append(fact_group)
            tag_group_counts[tag_id] += 1

    return sorted(fact_groups, key=lambda row: (str(row.get("tag_id") or ""), str(row.get("fact_type") or ""), str(row.get("fact_group_id") or "")))


def _can_group(item: dict[str, Any], group_items: list[dict[str, Any]]) -> bool:
    for existing in group_items:
        if _same_claim_or_quote(item, existing):
            return True
    representative = group_items[0]
    return _high_claim_similarity(item, representative)


def _same_claim_or_quote(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_claim = normalize_text(str(left.get("claim") or ""))
    right_claim = normalize_text(str(right.get("claim") or ""))
    left_quote = normalize_text(str(left.get("quote") or ""))
    right_quote = normalize_text(str(right.get("quote") or ""))
    return bool((left_claim and left_claim == right_claim) or (left_quote and left_quote == right_quote))


def _high_claim_similarity(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_claim = normalize_text(str(left.get("claim") or ""))
    right_claim = normalize_text(str(right.get("claim") or ""))
    if not left_claim or not right_claim:
        return False
    if _numeric_conflict(left_claim, right_claim):
        return False
    sequence_similarity = SequenceMatcher(None, left_claim, right_claim).ratio()
    if sequence_similarity >= CLAIM_SEQUENCE_THRESHOLD:
        return True
    left_tokens = token_set(left_claim)
    right_tokens = token_set(right_claim)
    if not left_tokens or not right_tokens:
        return False
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return jaccard >= TOKEN_JACCARD_THRESHOLD


def _numeric_conflict(left_claim: str, right_claim: str) -> bool:
    left_numbers = numeric_tokens(left_claim)
    right_numbers = numeric_tokens(right_claim)
    return bool(left_numbers and right_numbers and left_numbers != right_numbers)


def _build_fact_group(group_items: list[dict[str, Any]], *, max_quotes_per_fact_group: int) -> dict[str, Any]:
    items = sorted(group_items, key=_representative_claim_rank)
    representative = items[0]
    quote_representative = sorted(items, key=_representative_quote_rank)[0]
    all_evidence_ids = sorted({evidence_id for item in items for evidence_id in _provenance_ids(item)})
    visible_evidence_ids = all_evidence_ids[:max_quotes_per_fact_group]
    quote_counts = Counter(str(item.get("quote_validation_status") or "") for item in items)
    valid_count = sum(1 for item in items if item.get("a3_layer") == VALID_LAYER)
    review_count = sum(1 for item in items if item.get("a3_layer") == REVIEW_LAYER)
    review_reasons = _group_review_reasons(items, valid_count=valid_count, review_count=review_count)
    needs_review = bool(review_reasons)
    a4_usage, usable = _a4_usage(representative, valid_count=valid_count, review_count=review_count)
    if review_count and usable:
        review_reasons = sorted(set(review_reasons + ["review_evidence_present"]))
        needs_review = True
    if quote_counts.get("fuzzy", 0) and usable:
        review_reasons = sorted(set(review_reasons + ["fuzzy_quote_evidence_present"]))
        needs_review = True

    group_id = _fact_group_id(
        tag_id=str(representative.get("tag_id") or ""),
        fact_type=str(representative.get("fact_type") or ""),
        primary_claim_norm=normalize_text(str(representative.get("claim") or "")),
        representative_quote_norm=normalize_text(str(quote_representative.get("quote") or "")),
        evidence_item_ids=all_evidence_ids,
    )
    row = {
        "fact_group_id": group_id,
        "tag_id": representative.get("tag_id"),
        "canonical_tag_ru": representative.get("canonical_tag_ru"),
        "canonical_tag_latin": representative.get("canonical_tag_latin"),
        "entity_type": representative.get("entity_type"),
        "fact_type": representative.get("fact_type"),
        "section_hint": representative.get("section_hint"),
        "representative_claim": representative.get("claim"),
        "representative_quote": quote_representative.get("quote"),
        "representative_quote_validation_status": quote_representative.get("quote_validation_status"),
        "importance": representative.get("importance"),
        "confidence": representative.get("confidence"),
        "evidence_item_ids": visible_evidence_ids,
        "source_task_ids": sorted({str(item.get("task_id") or "") for item in items if item.get("task_id")}),
        "source_doc_ids": sorted({str(item.get("doc_id") or "") for item in items if item.get("doc_id")}),
        "source_window_ids": sorted({str(item.get("window_id") or "") for item in items if item.get("window_id")}),
        "evidence_items_count": len(all_evidence_ids),
        "source_documents_count": len({str(item.get("doc_id") or "") for item in items if item.get("doc_id")}),
        "valid_evidence_count": valid_count,
        "review_evidence_count": review_count,
        "rejected_evidence_count": 0,
        "quote_status_counts": {
            "exact": quote_counts.get("exact", 0),
            "normalized_exact": quote_counts.get("normalized_exact", 0),
            "fuzzy": quote_counts.get("fuzzy", 0),
            "not_found": quote_counts.get("not_found", 0),
        },
        "needs_review_before_publication": needs_review,
        "review_reasons": review_reasons,
        "usable_for_a4": usable,
        "a4_usage": a4_usage,
        "created_from_stage": "a3.0",
    }
    if len(visible_evidence_ids) < len(all_evidence_ids):
        row["all_evidence_item_ids"] = all_evidence_ids
    return row


def _a4_usage(representative: dict[str, Any], *, valid_count: int, review_count: int) -> tuple[str, bool]:
    fact_type = str(representative.get("fact_type") or "")
    relevance = str(representative.get("relevance") or "")
    importance = str(representative.get("importance") or "")
    if fact_type == "related_entity" or relevance == "related":
        return "related_only", False
    if valid_count < 1:
        return "review_only" if review_count else "not_usable", False
    if fact_type in CORE_FACT_TYPES and importance in {"high", "medium"}:
        return "core_fact", True
    if importance == "low" or fact_type in SUPPORTING_FACT_TYPES:
        return "supporting_fact", True
    return "supporting_fact", True


def _group_review_reasons(items: list[dict[str, Any]], *, valid_count: int, review_count: int) -> list[str]:
    reasons: list[str] = []
    for item in items:
        reasons.extend(_list_value(item.get("review_reasons")))
        reasons.extend(_list_value(item.get("a3_filter_reasons")))
        if item.get("needs_review_before_publication"):
            reasons.append("publication_review_required")
    if valid_count < 1 and review_count:
        reasons.append("only_review_evidence")
    return sorted(set(reason for reason in reasons if reason))


def _representative_claim_rank(item: dict[str, Any]) -> tuple[int, float, int, int, str]:
    importance_rank = {"high": 0, "medium": 1, "low": 2}.get(str(item.get("importance") or ""), 3)
    quote_rank = {"exact": 0, "normalized_exact": 1, "fuzzy": 2, "not_found": 3}.get(str(item.get("quote_validation_status") or ""), 4)
    try:
        confidence = float(item.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    claim_length = len(str(item.get("claim") or ""))
    return (importance_rank, -confidence, quote_rank, claim_length, str(item.get("evidence_item_id") or ""))


def _representative_quote_rank(item: dict[str, Any]) -> tuple[int, int, float, int, str]:
    quote_rank = {"exact": 0, "normalized_exact": 1, "fuzzy": 2, "not_found": 3}.get(str(item.get("quote_validation_status") or ""), 4)
    importance_rank = {"high": 0, "medium": 1, "low": 2}.get(str(item.get("importance") or ""), 3)
    try:
        confidence = float(item.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    quote_length = len(str(item.get("quote") or ""))
    return (quote_rank, importance_rank, -confidence, quote_length, str(item.get("evidence_item_id") or ""))


def _item_sort_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        normalize_text(str(item.get("claim") or "")),
        normalize_text(str(item.get("quote") or "")),
        str(item.get("doc_id") or ""),
        str(item.get("evidence_item_id") or ""),
    )


def _fact_group_id(
    *,
    tag_id: str,
    fact_type: str,
    primary_claim_norm: str,
    representative_quote_norm: str,
    evidence_item_ids: list[str],
) -> str:
    payload = "\n".join([tag_id, fact_type, primary_claim_norm, representative_quote_norm, "|".join(sorted(evidence_item_ids))])
    return f"fg_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}"


def _provenance_ids(item: dict[str, Any]) -> list[str]:
    ids = _list_value(item.get("original_evidence_item_ids"))
    evidence_id = str(item.get("evidence_item_id") or "")
    if evidence_id:
        ids.append(evidence_id)
    return sorted(set(ids))


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value:
        return [str(value)]
    return []

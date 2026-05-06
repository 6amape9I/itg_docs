from __future__ import annotations

from typing import Any

from kb_rebuild.articles.a3.models import (
    REJECTED_LAYER,
    REJECTED_QUOTE_STATUSES,
    REVIEW_LAYER,
    REVIEW_QUOTE_STATUSES,
    USABLE_QUOTE_STATUSES,
    VALID_LAYER,
)


def classify_evidence_item(item: dict[str, Any], *, min_confidence: float = 0.5) -> dict[str, Any]:
    """Return a copy of an A2 evidence item annotated with its A3 layer."""
    row = dict(item)
    reasons: list[str] = []
    reasons.extend(_list_value(row.get("a3_pre_filter_reasons")))
    quote_status = str(row.get("quote_validation_status") or "")
    relevance = str(row.get("relevance") or "")
    fact_type = str(row.get("fact_type") or "")
    quote = str(row.get("quote") or "")
    claim = str(row.get("claim") or "")
    confidence = _float_value(row.get("confidence"))

    if quote_status in REJECTED_QUOTE_STATUSES:
        reasons.append("quote_not_found")
    if quote_status and quote_status not in USABLE_QUOTE_STATUSES | REVIEW_QUOTE_STATUSES | REJECTED_QUOTE_STATUSES:
        reasons.append("unknown_quote_status")
    if not quote.strip():
        reasons.append("empty_quote")
    if not claim.strip():
        reasons.append("empty_claim")
    if _has_ellipsis_or_stitched_quote(quote):
        reasons.append("ellipsis_or_stitched_quote")
    if relevance == "not_relevant":
        reasons.append("not_relevant")

    if reasons:
        return _with_layer(row, REJECTED_LAYER, reasons)

    review_reasons: list[str] = []
    if quote_status in REVIEW_QUOTE_STATUSES:
        review_reasons.append("fuzzy_quote")
    if relevance in {"related", "unclear"}:
        review_reasons.append(f"relevance:{relevance}")
    if fact_type == "related_entity":
        review_reasons.append("related_entity_fact_type")
    if confidence < min_confidence:
        review_reasons.append("confidence_below_min")
    if str(row.get("window_quality") or "") == "low":
        review_reasons.append("low_quality_window")

    if review_reasons:
        return _with_layer(row, REVIEW_LAYER, review_reasons)

    if quote_status in USABLE_QUOTE_STATUSES and relevance == "direct" and fact_type != "related_entity":
        publication_reasons = _list_value(row.get("review_reasons"))
        if row.get("needs_review_before_publication"):
            publication_reasons.append("publication_review_required")
        return _with_layer(row, VALID_LAYER, sorted(set(publication_reasons)))

    return _with_layer(row, REVIEW_LAYER, ["not_valid_direct_evidence"])


def split_evidence_layers(
    evidence_items: list[dict[str, Any]],
    *,
    min_confidence: float = 0.5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    valid: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in evidence_items:
        classified = classify_evidence_item(item, min_confidence=min_confidence)
        layer = classified["a3_layer"]
        if layer == VALID_LAYER:
            valid.append(classified)
        elif layer == REVIEW_LAYER:
            review.append(classified)
        else:
            rejected.append(classified)
    return valid, review, rejected


def _with_layer(row: dict[str, Any], layer: str, reasons: list[str]) -> dict[str, Any]:
    merged_reasons = sorted(set(str(reason) for reason in reasons if str(reason)))
    row["a3_layer"] = layer
    row["a3_filter_reasons"] = merged_reasons
    row["usable_for_a4_candidate"] = layer == VALID_LAYER
    return row


def _has_ellipsis_or_stitched_quote(quote: str) -> bool:
    return "..." in quote or "…" in quote


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value:
        return [str(value)]
    return []

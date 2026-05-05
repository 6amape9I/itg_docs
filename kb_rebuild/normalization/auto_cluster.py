from __future__ import annotations

from collections import Counter, defaultdict

from kb_rebuild.normalization.models import AutoCluster, NormalizedMention
from kb_rebuild.normalization.text import (
    contains_dosage,
    contains_packaging,
    normalize_basic_text,
    normalize_product_name,
)


BLOCKING_FLAGS = {
    "very_short_alias",
    "possible_abbreviation",
    "quote_not_found",
    "low_confidence",
    "possible_genus_level_entity",
    "product_norm_too_short",
    "has_type_subtype_marker",
    "possible_parent_child_term",
    "possible_numeric_dosage_variant",
}
REVIEW_FLAGS = BLOCKING_FLAGS | {
    "contains_specificity_modifier",
    "has_specificity_modifier",
    "mixed_cyrillic_latin",
    "latin_only",
    "contains_dosage",
    "contains_packaging",
    "possible_trade_name_with_dosage",
    "possible_name_only_entity",
}


def build_auto_cluster_key(mention: NormalizedMention) -> str:
    entity_type = mention.entity_type
    if not entity_type:
        return ""
    key_value = mention.primary_norm
    if entity_type in {"drug_trade_name", "supplement"}:
        product_name_norm = str(mention.normalized.get("product_name_norm", "")).strip()
        if product_name_norm and "product_norm_too_short" not in mention.suspicious_flags:
            key_value = product_name_norm
    if entity_type == "disease":
        subtype = str(mention.normalized.get("subtype_signature", "none"))
        if subtype and subtype != "none":
            key_value = f"{key_value}::{subtype}"
    if not key_value:
        return ""
    return f"{entity_type}::{key_value}"


def build_auto_clusters(mentions: list[NormalizedMention]) -> list[AutoCluster]:
    grouped: dict[str, list[NormalizedMention]] = defaultdict(list)
    base_keys: dict[str, str] = {}
    for mention in mentions:
        base_key = build_auto_cluster_key(mention)
        if not base_key:
            continue
        grouped[base_key].append(mention)
        base_keys[base_key] = base_key

    clusters: list[AutoCluster] = []
    for index, group_key in enumerate(sorted(grouped), start=1):
        group_mentions = sorted(grouped[group_key], key=lambda item: item.mention_id)
        clusters.append(_cluster_from_mentions(index, base_keys[group_key], group_mentions))
    return clusters


def _cluster_from_mentions(index: int, auto_cluster_key: str, mentions: list[NormalizedMention]) -> AutoCluster:
    confidences = [mention.confidence for mention in mentions]
    roles = Counter(mention.tag_role for mention in mentions)
    quote_statuses = Counter(mention.quote_validation_status for mention in mentions)
    risk_flags = _combined_flags(mention.risk_flags for mention in mentions)
    routing_flags = _combined_flags(mention.routing_flags for mention in mentions)
    blocking_flags = sorted(flag for flag in risk_flags if flag in BLOCKING_FLAGS)
    review_reasons = _review_reasons(mentions, risk_flags=risk_flags, blocking_flags=blocking_flags)
    cluster_status = _cluster_status(mentions, blocking_flags)
    merge_allowed = cluster_status == "auto_merged"
    aliases = _unique_sorted(
        value
        for mention in mentions
        for value in (
            str(mention.raw.get("surface", "")).strip(),
            str(mention.raw.get("canonical_candidate_ru", "")).strip(),
        )
        if value
    )
    normalized_aliases = _unique_sorted(
        value
        for mention in mentions
        for value in (
            str(mention.normalized.get("surface_norm", "")).strip(),
            str(mention.normalized.get("candidate_ru_norm", "")).strip(),
            str(mention.normalized.get("primary_norm", "")).strip(),
            str(mention.normalized.get("product_name_norm", "")).strip(),
        )
        if value
    )

    return AutoCluster(
        auto_cluster_id=f"ac_{index:06d}",
        entity_type=mentions[0].entity_type,
        auto_cluster_key=auto_cluster_key,
        canonical_display_candidate=_choose_canonical_display(mentions),
        canonical_latin_candidate=_choose_display(
            [str(mention.raw.get("canonical_candidate_latin", "")).strip() for mention in mentions]
        ),
        aliases=aliases,
        normalized_aliases=normalized_aliases,
        mention_ids=[mention.mention_id for mention in mentions],
        documents_count=len({mention.doc_id for mention in mentions}),
        mentions_count=len(mentions),
        roles_count=dict(sorted(roles.items())),
        article_candidate_count=sum(1 for mention in mentions if mention.article_candidate),
        context_only_count=sum(1 for mention in mentions if mention.tag_role == "context_only"),
        folder_candidate_count=sum(1 for mention in mentions if mention.tag_role == "folder_candidate"),
        quote_not_found_count=sum(1 for mention in mentions if "quote_not_found" in mention.suspicious_flags),
        confidence_stats={
            "min": round(min(confidences), 6) if confidences else 0.0,
            "avg": round(sum(confidences) / len(confidences), 6) if confidences else 0.0,
            "max": round(max(confidences), 6) if confidences else 0.0,
        },
        quote_status_count=dict(sorted(quote_statuses.items())),
        normalization_method="deterministic_exact_norm",
        cluster_status=cluster_status,
        merge_allowed=merge_allowed,
        blocking_flags=blocking_flags,
        risk_flags=risk_flags,
        routing_flags=routing_flags,
        review_required=bool(review_reasons),
        review_reasons=review_reasons,
    )


def _review_reasons(
    mentions: list[NormalizedMention],
    *,
    risk_flags: list[str],
    blocking_flags: list[str],
) -> list[str]:
    reasons: set[str] = set(blocking_flags)
    for flag in set(risk_flags) & REVIEW_FLAGS:
        reasons.add(flag)
    if len({mention.tag_role for mention in mentions}) > 1:
        reasons.add("mixed_tag_roles")
    if len({mention.article_candidate for mention in mentions}) > 1:
        reasons.add("mixed_article_candidate")
    if blocking_flags:
        reasons.add("merge_blocked_by_risk_flags")
    return sorted(reasons)


def _cluster_status(mentions: list[NormalizedMention], blocking_flags: list[str]) -> str:
    if len(mentions) == 1:
        return "isolated_mention"
    if blocking_flags:
        return "review_group"
    return "auto_merged"


def _choose_canonical_display(mentions: list[NormalizedMention]) -> str:
    entity_type = mentions[0].entity_type
    if entity_type in {"drug_trade_name", "supplement"}:
        product_norms = [
            str(mention.normalized.get("product_name_norm", "")).strip()
            for mention in mentions
            if str(mention.normalized.get("product_name_norm", "")).strip()
        ]
        if product_norms:
            return _choose_product_display(mentions, product_norms[0], entity_type)
    return _choose_display(
        [
            str(mention.raw.get("canonical_candidate_ru", "")).strip()
            or str(mention.raw.get("surface", "")).strip()
            for mention in mentions
        ]
    )


def _choose_product_display(mentions: list[NormalizedMention], product_norm: str, entity_type: str) -> str:
    aliases = [
        value
        for mention in mentions
        for value in (
            str(mention.raw.get("canonical_candidate_ru", "")).strip(),
            str(mention.raw.get("surface", "")).strip(),
        )
        if value
    ]
    if not aliases:
        return _display_from_norm(product_norm)
    counts = Counter(aliases)

    def is_clean(alias: str) -> bool:
        return (
            normalize_basic_text(alias) == product_norm
            and not contains_dosage(alias)
            and not contains_packaging(alias)
        )

    clean_aliases = [alias for alias in aliases if is_clean(alias)]
    if clean_aliases:
        return _choose_short_display(clean_aliases)

    restored = _display_from_norm(product_norm)
    if restored:
        return restored
    product_aliases = [
        alias
        for alias in aliases
        if normalize_product_name(alias, entity_type).value == product_norm
    ]
    if product_aliases:
        return _choose_short_display(product_aliases, prefer_short=True)
    return _choose_display(aliases)


def _choose_short_display(values: list[str], *, prefer_short: bool = False) -> str:
    counts = Counter(value.strip() for value in values if value.strip())
    if not counts:
        return ""

    def sort_key(value: str) -> tuple[int, int, int, str]:
        all_lower = int(value == value.lower() and value != value.upper())
        length = len(value) if prefer_short else -len(value)
        return (-counts[value], all_lower, length, value)

    return sorted(counts, key=sort_key)[0]


def _choose_display(values: list[str]) -> str:
    non_empty = [value.strip() for value in values if value and value.strip()]
    if not non_empty:
        return ""
    counts = Counter(non_empty)

    def sort_key(value: str) -> tuple[int, int, int, str]:
        all_lower = int(value == value.lower() and value != value.upper())
        return (-counts[value], all_lower, -len(value), value)

    return sorted(counts, key=sort_key)[0]


def _display_from_norm(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    return stripped[:1].upper() + stripped[1:]


def _combined_flags(flag_lists: object) -> list[str]:
    result: set[str] = set()
    for flags in flag_lists:
        result.update(str(flag) for flag in flags if str(flag).strip())
    return sorted(result)


def _unique_sorted(values: object) -> list[str]:
    return sorted(set(str(value) for value in values if str(value).strip()))

from __future__ import annotations

from collections import Counter, defaultdict

from kb_rebuild.normalization.models import AutoCluster, NormalizedMention


NO_AUTO_MERGE_FLAGS = {
    "very_short_alias",
    "possible_abbreviation",
    "quote_not_found",
    "low_confidence",
    "possible_genus_level_entity",
    "product_norm_too_short",
}
REVIEW_FLAGS = NO_AUTO_MERGE_FLAGS | {
    "context_only",
    "folder_candidate",
    "contains_specificity_modifier",
    "has_specificity_modifier",
    "possible_parent_child_term",
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
        group_key = _group_key(mention, base_key)
        grouped[group_key].append(mention)
        base_keys[group_key] = base_key

    clusters: list[AutoCluster] = []
    for index, group_key in enumerate(sorted(grouped), start=1):
        group_mentions = sorted(grouped[group_key], key=lambda item: item.mention_id)
        clusters.append(_cluster_from_mentions(index, base_keys[group_key], group_mentions))
    return clusters


def _group_key(mention: NormalizedMention, base_key: str) -> str:
    if set(mention.suspicious_flags) & NO_AUTO_MERGE_FLAGS:
        return f"{base_key}::no_auto_merge::{mention.mention_id}"
    return base_key


def _cluster_from_mentions(index: int, auto_cluster_key: str, mentions: list[NormalizedMention]) -> AutoCluster:
    confidences = [mention.confidence for mention in mentions]
    roles = Counter(mention.tag_role for mention in mentions)
    quote_statuses = Counter(mention.quote_validation_status for mention in mentions)
    review_reasons = _review_reasons(mentions)
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
        canonical_display_candidate=_choose_display(
            [
                str(mention.raw.get("canonical_candidate_ru", "")).strip()
                or str(mention.raw.get("surface", "")).strip()
                for mention in mentions
            ]
        ),
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
        review_required=bool(review_reasons),
        review_reasons=review_reasons,
    )


def _review_reasons(mentions: list[NormalizedMention]) -> list[str]:
    reasons: set[str] = set()
    all_flags: set[str] = set()
    for mention in mentions:
        all_flags.update(mention.suspicious_flags)
    for flag in all_flags & REVIEW_FLAGS:
        reasons.add(flag)
    if len({mention.tag_role for mention in mentions}) > 1:
        reasons.add("mixed_tag_roles")
    if len({mention.article_candidate for mention in mentions}) > 1:
        reasons.add("mixed_article_candidate")
    if any(set(mention.suspicious_flags) & NO_AUTO_MERGE_FLAGS for mention in mentions):
        reasons.add("no_auto_merge_suspicious_flag")
    return sorted(reasons)


def _choose_display(values: list[str]) -> str:
    non_empty = [value.strip() for value in values if value and value.strip()]
    if not non_empty:
        return ""
    counts = Counter(non_empty)

    def sort_key(value: str) -> tuple[int, int, int, str]:
        all_lower = int(value == value.lower() and value != value.upper())
        return (-counts[value], all_lower, -len(value), value)

    return sorted(counts, key=sort_key)[0]


def _unique_sorted(values: object) -> list[str]:
    return sorted(set(str(value) for value in values if str(value).strip()))

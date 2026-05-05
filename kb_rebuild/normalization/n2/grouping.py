from __future__ import annotations

from collections import Counter
from dataclasses import replace

from kb_rebuild.normalization.n2.features import has_clean_reason, has_strong_reason
from kb_rebuild.normalization.n2.models import CandidateGroup, CandidateNode, CandidatePair
from kb_rebuild.normalization.n2.scope_conflict import (
    cellular_conflict,
    extract_cellular_markers,
    extract_complex_markers,
    extract_disease_heads,
    extract_location_markers,
    extract_subtype_markers,
)


MAX_GROUP_SIZE = 12
MAX_BLOCKED_REVIEW_GROUPS = 5000
HUB_N3_GROUP_LIMIT = 5
N3_SCORE_THRESHOLD = 0.72
HARD_ALIAS_REASONS = {
    "primary_label_exact_match",
    "explicit_parenthetical_alias_match",
    "explicit_alias_exact_match",
    "product_variant_match",
    "canonical_alias_exact_match",
}
QUALITY_RISK_HARD_ALIAS_REASONS = {
    "primary_label_exact_match",
    "explicit_parenthetical_alias_match",
    "explicit_alias_exact_match",
    "canonical_alias_exact_match",
}
QUALITY_RISK_FLAGS = {"quote_issue", "low_confidence", "contains_short_alias", "very_short_alias", "possible_abbreviation"}
SUBTYPE_BLOCKING_REASONS = {"disease_subtype_conflict"}
LOCATION_SCOPE_BLOCKING_REASONS = {
    "diagnostic_method_parent_child_scope",
    "diagnostic_method_scope_conflict",
    "disease_location_conflict",
    "disease_parent_child_scope",
    "drug_class_parent_child_scope",
    "parent_child_blocked",
    "procedure_object_scope_conflict",
}


def build_candidate_groups(
    nodes: list[CandidateNode],
    candidate_pairs: list[CandidatePair],
    blocked_pairs: list[CandidatePair],
    *,
    high_priority_score: float,
) -> list[CandidateGroup]:
    nodes_by_id = {node.node_id: node for node in nodes}
    edge_pairs = {
        frozenset((pair.left_node_id, pair.right_node_id)): pair
        for pair in candidate_pairs
        if pair.pair_status in {"candidate", "high_priority_candidate", "low_confidence_candidate"}
    }
    groups: list[set[str]] = []

    for pair in sorted(candidate_pairs, key=lambda item: (-item.score, item.pair_id)):
        pair_nodes = {pair.left_node_id, pair.right_node_id}
        placed = False
        for group in groups:
            if not group & pair_nodes:
                continue
            proposed = group | pair_nodes
            if len(proposed) > MAX_GROUP_SIZE:
                continue
            if _pairwise_compatible(proposed, edge_pairs):
                group.update(pair_nodes)
                placed = True
                break
        if not placed:
            groups.append(set(pair_nodes))

    candidate_groups: list[CandidateGroup] = []
    seen_node_sets: set[frozenset[str]] = set()
    for node_ids in groups:
        frozen = frozenset(node_ids)
        if len(frozen) < 2 or frozen in seen_node_sets:
            continue
        seen_node_sets.add(frozen)
        group_pairs = [
            pair
            for key, pair in edge_pairs.items()
            if key <= frozen
        ]
        candidate_groups.append(
            _group_from_nodes_and_pairs(
                group_index=len(candidate_groups) + 1,
                node_ids=sorted(frozen),
                pairs=group_pairs,
                nodes_by_id=nodes_by_id,
                high_priority_score=high_priority_score,
                blocked=False,
            )
        )

    blocked_added = 0
    for pair in sorted(blocked_pairs, key=lambda item: (-item.score, item.pair_id)):
        if blocked_added >= MAX_BLOCKED_REVIEW_GROUPS:
            break
        node_ids = frozenset((pair.left_node_id, pair.right_node_id))
        if node_ids in seen_node_sets:
            continue
        seen_node_sets.add(node_ids)
        candidate_groups.append(
            _group_from_nodes_and_pairs(
                group_index=len(candidate_groups) + 1,
                node_ids=sorted(node_ids),
                pairs=[pair],
                nodes_by_id=nodes_by_id,
                high_priority_score=high_priority_score,
                blocked=True,
            )
        )
        blocked_added += 1

    return _apply_hub_protection(candidate_groups)


def _pairwise_compatible(node_ids: set[str], edge_pairs: dict[frozenset[str], CandidatePair]) -> bool:
    ids = sorted(node_ids)
    for left_index, left in enumerate(ids):
        for right in ids[left_index + 1 :]:
            if frozenset((left, right)) not in edge_pairs:
                return False
    return True


def _group_from_nodes_and_pairs(
    *,
    group_index: int,
    node_ids: list[str],
    pairs: list[CandidatePair],
    nodes_by_id: dict[str, CandidateNode],
    high_priority_score: float,
    blocked: bool,
) -> CandidateGroup:
    group_nodes = [nodes_by_id[node_id] for node_id in node_ids]
    entity_types = {node.entity_type for node in group_nodes}
    if len(entity_types) != 1:
        raise ValueError(f"group contains mixed entity types: {sorted(entity_types)}")
    reasons = sorted({reason for pair in pairs for reason in pair.candidate_reasons})
    clean_reasons = sorted({reason for pair in pairs for reason in pair.clean_candidate_reasons})
    weak_reasons = sorted({reason for pair in pairs for reason in pair.weak_candidate_reasons})
    scope_conflicts = sorted({reason for pair in pairs for reason in pair.scope_conflict_reasons})
    ambiguous_abbreviations = sorted(
        {
            abbreviation
            for pair in pairs
            for abbreviation in pair.metrics.get("abbreviations_matched", [])
            if "ambiguous_abbreviation" in pair.risk_reasons
        }
    )
    generic_aliases = sorted(
        {
            alias
            for pair in pairs
            for alias in pair.metrics.get("generic_aliases_matched", [])
        }
    )
    risks = sorted(
        {risk for pair in pairs for risk in pair.risk_reasons}
        | {reason for pair in pairs for reason in pair.blocking_reasons}
        | {flag for node in group_nodes for flag in node.risk_flags if flag in {"very_short_alias", "possible_abbreviation"}}
    )
    if any("very_short_alias" in node.risk_flags for node in group_nodes):
        risks.append("contains_short_alias")
    risks = sorted(set(risks))
    scores = [pair.score for pair in pairs]
    group_score = round(sum(scores) / len(scores), 6) if scores else 0.0
    mentions_count = _unique_mentions_count(group_nodes)
    article_candidate_count = _bounded_count(
        sum(node.article_candidate_count for node in group_nodes),
        mentions_count,
    )
    context_only_count = _bounded_count(
        sum(node.context_only_count for node in group_nodes),
        mentions_count,
    )
    if "both_context_only" in risks and context_only_count < mentions_count:
        risks = sorted((set(risks) - {"both_context_only"}) | {"partial_context_only_pair"})
    group_labels = sorted({node.label for node in group_nodes if node.label})
    marker_profile = _marker_profile(group_nodes)
    hard_alias_reason = bool(set(clean_reasons) & HARD_ALIAS_REASONS)
    quality_flags = _quality_gate_flags(
        entity_type=group_nodes[0].entity_type,
        group_labels=group_labels,
        group_score=group_score,
        clean_reasons=clean_reasons,
        risks=risks,
        scope_conflicts=scope_conflicts,
        marker_profile=marker_profile,
        hard_alias_reason=hard_alias_reason,
    )
    score_gate_passed = "score_below_n3_threshold_without_hard_alias_reason" not in quality_flags
    priority = _group_priority(
        pairs=pairs,
        group_score=group_score,
        article_candidate_count=article_candidate_count,
        risks=risks,
        clean_reasons=clean_reasons,
        high_priority_score=high_priority_score,
        blocked=blocked,
    )
    status, exclusions = _group_status_and_exclusions(
        blocked=blocked,
        priority=priority,
        pairs=pairs,
        clean_reasons=clean_reasons,
        risks=risks,
        scope_conflicts=scope_conflicts,
        generic_aliases=generic_aliases,
        ambiguous_abbreviations=ambiguous_abbreviations,
        quality_flags=quality_flags,
    )
    recommended = _recommended_for_n3(
        status=status,
        priority=priority,
        clean_reasons=clean_reasons,
        exclusions=exclusions,
        score_gate_passed=score_gate_passed,
        quality_flags=quality_flags,
    )
    documents = _sample_documents(group_nodes)
    return CandidateGroup(
        candidate_group_id=f"cg_{group_index:06d}",
        entity_type=group_nodes[0].entity_type,
        group_labels=group_labels,
        node_ids=node_ids,
        pair_ids=[pair.pair_id for pair in pairs],
        group_score=group_score,
        group_priority=priority,
        candidate_group_status=status,
        n3_ready=recommended,
        hard_alias_reason=hard_alias_reason,
        score_gate_passed=score_gate_passed,
        candidate_reasons=reasons,
        clean_candidate_reasons=clean_reasons,
        weak_candidate_reasons=weak_reasons,
        group_risk_flags=risks,
        exclusion_reasons=exclusions,
        subtype_markers=marker_profile["subtype_markers"],
        location_markers=marker_profile["location_markers"],
        cellular_markers=marker_profile["cellular_markers"],
        complex_markers=marker_profile["complex_markers"],
        quality_gate_flags=quality_flags,
        hub_node_ids=[],
        generic_aliases_matched=generic_aliases,
        ambiguous_abbreviations=ambiguous_abbreviations,
        scope_conflict_reasons=scope_conflicts,
        requires_llm_validation=status != "blocked_review",
        recommended_for_n3=recommended,
        mentions_count=mentions_count,
        documents_count=len({doc["doc_id"] for node in group_nodes for doc in node.documents}),
        article_candidate_count=article_candidate_count,
        context_only_count=context_only_count,
        sample_documents=documents,
    )


def _group_priority(
    *,
    pairs: list[CandidatePair],
    group_score: float,
    article_candidate_count: int,
    risks: list[str],
    clean_reasons: list[str],
    high_priority_score: float,
    blocked: bool,
) -> str:
    if blocked:
        return "blocked_review"
    if not has_clean_reason(clean_reasons):
        return "low"
    if (
        group_score >= high_priority_score
        or any(pair.pair_status == "high_priority_candidate" for pair in pairs)
        or any(has_strong_reason(pair.clean_candidate_reasons) for pair in pairs)
    ) and article_candidate_count:
        return "high"
    if group_score >= 0.72:
        return "medium"
    return "low"


def _group_status_and_exclusions(
    *,
    blocked: bool,
    priority: str,
    pairs: list[CandidatePair],
    clean_reasons: list[str],
    risks: list[str],
    scope_conflicts: list[str],
    generic_aliases: list[str],
    ambiguous_abbreviations: list[str],
    quality_flags: list[str],
) -> tuple[str, list[str]]:
    exclusions: set[str] = set()
    blocking = {reason for pair in pairs for reason in pair.blocking_reasons}
    exclusions.update(quality_flags)
    if blocking & SUBTYPE_BLOCKING_REASONS:
        exclusions.update(blocking & SUBTYPE_BLOCKING_REASONS)
        return "subtype_conflict", sorted(exclusions)
    if _has_subtype_conflict(quality_flags):
        return "subtype_conflict", sorted(exclusions)
    if blocking & LOCATION_SCOPE_BLOCKING_REASONS:
        exclusions.update(blocking & LOCATION_SCOPE_BLOCKING_REASONS)
        return "location_scope_conflict", sorted(exclusions)
    if _has_location_scope_conflict(quality_flags) or scope_conflicts:
        exclusions.update(scope_conflicts)
        return "location_scope_conflict", sorted(exclusions)
    if blocked or blocking:
        exclusions.update(blocking or {"blocked_pair"})
        if scope_conflicts or "parent_child_suspect" in blocking or "parent_child_blocked" in blocking:
            return "location_scope_conflict", sorted(exclusions)
        return "blocked_review", sorted(exclusions)
    if "parent_child_suspect" in risks:
        exclusions.add("parent_child_suspect")
        return "location_scope_conflict", sorted(exclusions)
    if ambiguous_abbreviations or "ambiguous_abbreviation" in risks:
        exclusions.add("ambiguous_abbreviation")
        return "ambiguous_abbreviation", sorted(exclusions)
    if generic_aliases or "generic_alias_conflict" in risks:
        exclusions.add("generic_alias_conflict")
        return "generic_alias_conflict", sorted(exclusions)
    if "both_context_only" in risks:
        exclusions.add("both_context_only")
    if not has_clean_reason(clean_reasons):
        exclusions.add("no_clean_candidate_reason")
    if priority not in {"high", "medium"}:
        exclusions.add("low_priority")
    if set(exclusions) & {
        "score_below_n3_threshold_without_hard_alias_reason",
        "quality_risk_without_hard_alias_reason",
        "disease_modifier_mismatch",
    }:
        return "quality_score_rejected", sorted(exclusions)
    if exclusions:
        return "low_confidence_candidate", sorted(exclusions)
    return "n3_candidate", []


def _recommended_for_n3(
    *,
    status: str,
    priority: str,
    clean_reasons: list[str],
    exclusions: list[str],
    score_gate_passed: bool,
    quality_flags: list[str],
) -> bool:
    return (
        status == "n3_candidate"
        and priority in {"high", "medium"}
        and has_clean_reason(clean_reasons)
        and score_gate_passed
        and not quality_flags
        and not exclusions
    )


def _marker_profile(group_nodes: list[CandidateNode]) -> dict[str, list[str]]:
    if not group_nodes or group_nodes[0].entity_type != "disease":
        return {
            "subtype_markers": [],
            "location_markers": [],
            "cellular_markers": [],
            "complex_markers": [],
            "disease_heads": [],
            "labels_with_subtype_count": 0,
            "labels_without_subtype_count": 0,
            "labels_with_location_count": 0,
            "labels_without_location_count": 0,
        }
    subtype_sets = [extract_subtype_markers(node.label) for node in group_nodes]
    location_sets = [extract_location_markers(node.label) for node in group_nodes]
    cellular_sets = [extract_cellular_markers(node.label) for node in group_nodes]
    complex_sets = [extract_complex_markers(node.label) for node in group_nodes]
    head_sets = [extract_disease_heads(node.label) for node in group_nodes]
    subtype_markers = sorted({marker for markers in subtype_sets for marker in markers if not marker.startswith("complex_")})
    location_markers = sorted({marker for markers in location_sets for marker in markers})
    cellular_markers = sorted({marker for markers in cellular_sets for marker in markers})
    complex_markers = sorted({marker for markers in complex_sets for marker in markers})
    disease_heads = sorted({marker for markers in head_sets for marker in markers})
    return {
        "subtype_markers": subtype_markers,
        "location_markers": location_markers,
        "cellular_markers": cellular_markers,
        "complex_markers": complex_markers,
        "disease_heads": disease_heads,
        "labels_with_subtype_count": sum(1 for markers in subtype_sets if markers),
        "labels_without_subtype_count": sum(1 for markers in subtype_sets if not markers),
        "labels_with_location_count": sum(1 for markers in location_sets if markers),
        "labels_without_location_count": sum(1 for markers in location_sets if not markers),
    }


def _quality_gate_flags(
    *,
    entity_type: str,
    group_labels: list[str],
    group_score: float,
    clean_reasons: list[str],
    risks: list[str],
    scope_conflicts: list[str],
    marker_profile: dict[str, list[str] | int],
    hard_alias_reason: bool,
) -> list[str]:
    flags: set[str] = set()
    hard_conflicts: set[str] = set(scope_conflicts)
    if entity_type == "disease":
        subtype_markers = set(marker_profile["subtype_markers"])  # type: ignore[arg-type]
        location_markers = set(marker_profile["location_markers"])  # type: ignore[arg-type]
        cellular_markers = set(marker_profile["cellular_markers"])  # type: ignore[arg-type]
        complex_markers = set(marker_profile["complex_markers"])  # type: ignore[arg-type]
        disease_heads = set(marker_profile["disease_heads"])  # type: ignore[arg-type]
        if len(subtype_markers) > 1:
            flags.add("different_subtype_values_inside_group")
        if marker_profile["labels_with_subtype_count"] and marker_profile["labels_without_subtype_count"]:  # type: ignore[index]
            flags.add("base_vs_subtype_conflict")
        if cellular_conflict(cellular_markers):
            flags.add("cellular_subtype_conflict")
        if len(complex_markers) > 1:
            flags.add("complex_subtype_conflict")
        if disease_heads and len(location_markers) > 1:
            flags.add("disease_location_conflict")
        if disease_heads and marker_profile["labels_with_location_count"] and marker_profile["labels_without_location_count"]:  # type: ignore[index]
            flags.add("disease_parent_child_scope")
    hard_conflicts.update(
        flag
        for flag in flags
        if flag
        in {
            "different_subtype_values_inside_group",
            "base_vs_subtype_conflict",
            "cellular_subtype_conflict",
            "complex_subtype_conflict",
            "disease_location_conflict",
            "disease_parent_child_scope",
        }
    )
    if group_score < N3_SCORE_THRESHOLD and (not hard_alias_reason or hard_conflicts):
        flags.add("score_below_n3_threshold_without_hard_alias_reason")
    quality_risks = QUALITY_RISK_FLAGS & set(risks)
    has_quality_risk_alias_reason = bool(set(clean_reasons) & QUALITY_RISK_HARD_ALIAS_REASONS)
    if quality_risks and not has_quality_risk_alias_reason:
        flags.add("quality_risk_without_hard_alias_reason")
    if "disease_modifier_mismatch" in risks and (not hard_alias_reason or hard_conflicts):
        flags.add("disease_modifier_mismatch")
    return sorted(flags)


def _has_subtype_conflict(flags: list[str]) -> bool:
    return bool(
        set(flags)
        & {
            "different_subtype_values_inside_group",
            "base_vs_subtype_conflict",
            "cellular_subtype_conflict",
            "complex_subtype_conflict",
        }
    )


def _has_location_scope_conflict(flags: list[str]) -> bool:
    return bool(set(flags) & {"disease_location_conflict", "disease_parent_child_scope"})


def _apply_hub_protection(groups: list[CandidateGroup]) -> list[CandidateGroup]:
    n3_counts: Counter[str] = Counter()
    for group in groups:
        if group.n3_ready:
            n3_counts.update(group.node_ids)
    hub_node_ids = {node_id for node_id, count in n3_counts.items() if count > HUB_N3_GROUP_LIMIT}
    if not hub_node_ids:
        return groups

    protected: list[CandidateGroup] = []
    for group in groups:
        group_hubs = sorted(hub_node_ids & set(group.node_ids))
        if group.n3_ready and group_hubs and not _hub_safe_exception(group):
            exclusions = sorted(set(group.exclusion_reasons) | {"hub_parent_child_suspect"})
            protected.append(
                replace(
                    group,
                    candidate_group_status="hub_parent_child_suspect",
                    n3_ready=False,
                    recommended_for_n3=False,
                    hub_node_ids=group_hubs,
                    quality_gate_flags=sorted(set(group.quality_gate_flags) | {"hub_parent_child_suspect"}),
                    exclusion_reasons=exclusions,
                )
            )
        else:
            protected.append(group)
    return protected


def _hub_safe_exception(group: CandidateGroup) -> bool:
    return len(group.node_ids) <= MAX_GROUP_SIZE and "product_variant_match" in group.clean_candidate_reasons


def _sample_documents(nodes: list[CandidateNode]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for node in nodes:
        for doc in node.documents:
            doc_id = str(doc.get("doc_id", ""))
            if not doc_id or doc_id in seen:
                continue
            seen.add(doc_id)
            result.append({"doc_id": doc_id, "document_name": str(doc.get("document_name", ""))})
            if len(result) >= 10:
                return result
    return result


def _unique_mentions_count(nodes: list[CandidateNode]) -> int:
    mention_ids = {mention_id for node in nodes for mention_id in node.mention_ids}
    return len(mention_ids) or sum(node.mentions_count for node in nodes)


def _bounded_count(value: int, upper_bound: int) -> int:
    if not upper_bound:
        return value
    return min(value, upper_bound)


def group_priority_counts(groups: list[CandidateGroup]) -> Counter[str]:
    return Counter(group.group_priority for group in groups)

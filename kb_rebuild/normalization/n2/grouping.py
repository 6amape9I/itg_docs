from __future__ import annotations

from collections import Counter
from dataclasses import replace

from kb_rebuild.normalization.n2.features import has_clean_reason, has_strong_reason
from kb_rebuild.normalization.n2.models import CandidateGroup, CandidateNode, CandidatePair


MAX_GROUP_SIZE = 12
MAX_BLOCKED_REVIEW_GROUPS = 5000
HUB_N3_GROUP_LIMIT = 5


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
    )
    recommended = _recommended_for_n3(
        status=status,
        priority=priority,
        clean_reasons=clean_reasons,
        exclusions=exclusions,
    )
    documents = _sample_documents(group_nodes)
    return CandidateGroup(
        candidate_group_id=f"cg_{group_index:06d}",
        entity_type=group_nodes[0].entity_type,
        group_labels=sorted({node.label for node in group_nodes if node.label}),
        node_ids=node_ids,
        pair_ids=[pair.pair_id for pair in pairs],
        group_score=group_score,
        group_priority=priority,
        candidate_group_status=status,
        n3_ready=recommended,
        candidate_reasons=reasons,
        clean_candidate_reasons=clean_reasons,
        weak_candidate_reasons=weak_reasons,
        group_risk_flags=risks,
        exclusion_reasons=exclusions,
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
) -> tuple[str, list[str]]:
    exclusions: set[str] = set()
    blocking = {reason for pair in pairs for reason in pair.blocking_reasons}
    if blocked or blocking:
        exclusions.update(blocking or {"blocked_pair"})
        if scope_conflicts or "parent_child_suspect" in blocking or "parent_child_blocked" in blocking:
            return "hub_parent_child_suspect", sorted(exclusions)
        return "blocked_review", sorted(exclusions)
    if scope_conflicts or "parent_child_suspect" in risks:
        exclusions.update(scope_conflicts or {"parent_child_suspect"})
        return "hub_parent_child_suspect", sorted(exclusions)
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
    if exclusions:
        return "low_confidence_candidate", sorted(exclusions)
    return "n3_candidate", []


def _recommended_for_n3(
    *,
    status: str,
    priority: str,
    clean_reasons: list[str],
    exclusions: list[str],
) -> bool:
    return status == "n3_candidate" and priority in {"high", "medium"} and has_clean_reason(clean_reasons) and not exclusions


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

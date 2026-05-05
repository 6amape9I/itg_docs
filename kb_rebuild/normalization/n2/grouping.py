from __future__ import annotations

from collections import Counter

from kb_rebuild.normalization.n2.features import has_strong_reason
from kb_rebuild.normalization.n2.models import CandidateGroup, CandidateNode, CandidatePair


MAX_GROUP_SIZE = 12
MAX_BLOCKED_REVIEW_GROUPS = 5000


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
        if pair.pair_status in {"candidate", "high_priority_candidate"}
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

    return candidate_groups


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
    priority = _group_priority(
        pairs=pairs,
        group_score=group_score,
        article_candidate_count=article_candidate_count,
        risks=risks,
        high_priority_score=high_priority_score,
        blocked=blocked,
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
        candidate_reasons=reasons,
        group_risk_flags=risks,
        requires_llm_validation=priority != "blocked_review",
        recommended_for_n3=priority in {"high", "medium"},
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
    high_priority_score: float,
    blocked: bool,
) -> str:
    if blocked:
        return "blocked_review"
    if (
        group_score >= high_priority_score
        or any(pair.pair_status == "high_priority_candidate" for pair in pairs)
        or any(has_strong_reason(pair.candidate_reasons) for pair in pairs)
    ) and article_candidate_count:
        return "high"
    if group_score >= 0.72:
        return "medium"
    return "low"


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

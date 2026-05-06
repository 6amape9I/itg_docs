from __future__ import annotations

import itertools
from collections import defaultdict
from typing import Any

from kb_rebuild.normalization.n4.models import FinalComponent, GraphBuildResult, MergeEdge
from kb_rebuild.normalization.text import normalize_basic_text


ACTIVE_SUBSTANCE_MARKERS = {
    "ацетат",
    "бензоат",
    "бромид",
    "гидробромид",
    "гидрохлорид",
    "дигидрохлорид",
    "калия",
    "кальция",
    "магния",
    "натрия",
    "сульфат",
    "фосфат",
    "хлорид",
}

ACTIVE_SUBSTANCE_EXAMPLES = {
    "азоксимера бромид",
    "амикацин",
    "амикацина сульфат",
    "аминоглутетимид",
    "амлодипин",
    "атомоксетин",
    "бетагистина дигидрохлорид",
    "бусерелин",
    "бусерелина ацетат",
}

DRUG_POLICY_REASON_MARKERS = {
    "active substance",
    "inn",
    "действующее вещество",
    "действующим веществом",
    "мнн",
    "соль",
}


class DisjointSet:
    def __init__(self, values: list[str]) -> None:
        self.parent = {value: value for value in values}
        self.rank = {value: 0 for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1


def build_node_to_auto_cluster(candidate_nodes: list[dict[str, Any]]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    mapping: dict[str, str] = {}
    conflicts: list[dict[str, Any]] = []
    for node in candidate_nodes:
        node_id = str(node.get("node_id") or "")
        auto_cluster_id = str(node.get("auto_cluster_id") or "")
        if not node_id or not auto_cluster_id:
            conflicts.append(
                {
                    "conflict_type": "invalid_candidate_node",
                    "node_id": node_id,
                    "auto_cluster_id": auto_cluster_id,
                    "reason": "candidate node misses node_id or auto_cluster_id",
                    "critical": True,
                }
            )
            continue
        if node_id in mapping and mapping[node_id] != auto_cluster_id:
            conflicts.append(
                {
                    "conflict_type": "duplicate_candidate_node_mapping",
                    "node_id": node_id,
                    "auto_cluster_id": auto_cluster_id,
                    "previous_auto_cluster_id": mapping[node_id],
                    "reason": "same node_id maps to multiple auto_cluster_id values",
                    "critical": True,
                }
            )
            continue
        mapping[node_id] = auto_cluster_id
    return mapping, conflicts


def build_graph_components(
    *,
    auto_clusters: list[dict[str, Any]],
    candidate_nodes: list[dict[str, Any]],
    accepted_clusters: list[dict[str, Any]],
    rejected_groups: list[dict[str, Any]] | None = None,
    review_groups: list[dict[str, Any]] | None = None,
) -> GraphBuildResult:
    rejected_groups = rejected_groups or []
    review_groups = review_groups or []
    auto_by_id = {str(cluster.get("auto_cluster_id")): cluster for cluster in auto_clusters}
    auto_ids = sorted(auto_by_id)
    dsu = DisjointSet(auto_ids)
    node_to_auto, node_conflicts = build_node_to_auto_cluster(candidate_nodes)
    merge_conflicts = list(node_conflicts)
    edges: list[MergeEdge] = []
    drug_policy_review: list[dict[str, Any]] = []
    rejected_constraints = _rejected_constraints(rejected_groups, node_to_auto)

    for cluster in accepted_clusters:
        edge, conflicts, drug_rows = _edge_from_accepted_cluster(cluster, node_to_auto, auto_by_id)
        merge_conflicts.extend(conflicts)
        drug_policy_review.extend(drug_rows)
        if edge is None:
            continue
        weak_rejected = _direct_weak_rejected_conflict(edge, rejected_constraints)
        if weak_rejected:
            merge_conflicts.append(
                {
                    "conflict_type": "direct_weak_rejected_constraint_conflict",
                    "n3_cluster_id": edge.n3_cluster_id,
                    "source_candidate_group_id": edge.source_candidate_group_id,
                    "node_ids": list(edge.node_ids),
                    "auto_cluster_ids": list(edge.auto_cluster_ids),
                    "confidence": edge.confidence,
                    "reason": "weak accepted edge conflicts with an explicit N3 rejected constraint",
                    "critical": True,
                }
            )
            continue
        auto_cluster_ids = list(edge.auto_cluster_ids)
        for left, right in zip(auto_cluster_ids, auto_cluster_ids[1:]):
            dsu.union(left, right)
        edges.append(edge)

    component_auto_ids: dict[str, list[str]] = defaultdict(list)
    for auto_id in auto_ids:
        component_auto_ids[dsu.find(auto_id)].append(auto_id)

    edge_by_root: dict[str, list[MergeEdge]] = defaultdict(list)
    for edge in edges:
        root = dsu.find(edge.auto_cluster_ids[0])
        edge_by_root[root].append(edge)

    components: list[FinalComponent] = []
    auto_cluster_to_component_id: dict[str, str] = {}
    for index, root in enumerate(sorted(component_auto_ids, key=lambda value: min(component_auto_ids[value])), start=1):
        cluster_ids = sorted(component_auto_ids[root])
        entity_types = sorted({str(auto_by_id[cluster_id].get("entity_type") or "") for cluster_id in cluster_ids})
        component_id = f"fc_{index:06d}"
        component = FinalComponent(
            component_id=component_id,
            auto_cluster_ids=cluster_ids,
            entity_type=entity_types[0] if entity_types else "",
            edges=sorted(edge_by_root.get(root, []), key=lambda edge: edge.n3_cluster_id),
        )
        if len(entity_types) != 1:
            component.review_reasons.add("entity_type_conflict")
        for cluster_id in cluster_ids:
            auto_cluster_to_component_id[cluster_id] = component_id
        components.append(component)

    components_by_id = {component.component_id: component for component in components}
    _mark_rejected_constraint_reviews(components_by_id, auto_cluster_to_component_id, rejected_groups, node_to_auto)

    unresolved_review_groups = [
        _review_group_record(group, node_to_auto)
        for group in review_groups
    ]

    return GraphBuildResult(
        components=components,
        auto_cluster_to_component_id=auto_cluster_to_component_id,
        merge_conflicts=merge_conflicts,
        drug_policy_review=drug_policy_review,
        unresolved_review_groups=unresolved_review_groups,
    )


def drug_trade_name_active_substance_conflict(labels: list[str], reason: str = "") -> bool:
    norms = [normalize_basic_text(label) for label in labels if normalize_basic_text(label)]
    if len(set(norms)) < 2:
        return False
    reason_norm = normalize_basic_text(reason)
    if any(marker in reason_norm for marker in DRUG_POLICY_REASON_MARKERS):
        return True
    active_like = [norm for norm in norms if _looks_like_active_substance(norm)]
    if not active_like:
        return False
    return any(norm not in set(active_like) for norm in norms)


def _looks_like_active_substance(norm: str) -> bool:
    if norm in ACTIVE_SUBSTANCE_EXAMPLES:
        return True
    tokens = norm.split()
    if any(token in ACTIVE_SUBSTANCE_MARKERS for token in tokens):
        return True
    return False


def _edge_from_accepted_cluster(
    cluster: dict[str, Any],
    node_to_auto: dict[str, str],
    auto_by_id: dict[str, dict[str, Any]],
) -> tuple[MergeEdge | None, list[dict[str, Any]], list[dict[str, Any]]]:
    node_ids = [str(node_id) for node_id in cluster.get("node_ids", []) if str(node_id)]
    labels = [str(label) for label in cluster.get("labels", []) if str(label)]
    n3_cluster_id = str(cluster.get("n3_cluster_id") or "")
    source_candidate_group_id = str(cluster.get("source_candidate_group_id") or "")
    entity_type = str(cluster.get("entity_type") or "")
    conflicts: list[dict[str, Any]] = []
    drug_rows: list[dict[str, Any]] = []
    unknown_node_ids = [node_id for node_id in node_ids if node_id not in node_to_auto]
    if unknown_node_ids:
        conflicts.append(
            {
                "conflict_type": "unknown_node_id",
                "n3_cluster_id": n3_cluster_id,
                "source_candidate_group_id": source_candidate_group_id,
                "node_ids": node_ids,
                "unknown_node_ids": unknown_node_ids,
                "reason": "N3 accepted cluster references node_id missing from N2 candidate_nodes",
                "critical": True,
            }
        )
        return None, conflicts, drug_rows

    auto_cluster_ids = sorted({node_to_auto[node_id] for node_id in node_ids})
    missing_auto_ids = [auto_id for auto_id in auto_cluster_ids if auto_id not in auto_by_id]
    if missing_auto_ids:
        conflicts.append(
            {
                "conflict_type": "unknown_auto_cluster_id",
                "n3_cluster_id": n3_cluster_id,
                "source_candidate_group_id": source_candidate_group_id,
                "node_ids": node_ids,
                "auto_cluster_ids": auto_cluster_ids,
                "missing_auto_cluster_ids": missing_auto_ids,
                "reason": "N2 node maps to auto_cluster_id missing from N1 auto_clusters",
                "critical": True,
            }
        )
        return None, conflicts, drug_rows

    if len(auto_cluster_ids) < 2:
        return None, conflicts, drug_rows

    entity_types = sorted({str(auto_by_id[auto_id].get("entity_type") or "") for auto_id in auto_cluster_ids})
    if len(entity_types) != 1 or (entity_type and entity_types and entity_type != entity_types[0]):
        conflicts.append(
            {
                "conflict_type": "entity_type_conflict",
                "n3_cluster_id": n3_cluster_id,
                "source_candidate_group_id": source_candidate_group_id,
                "node_ids": node_ids,
                "auto_cluster_ids": auto_cluster_ids,
                "entity_type": entity_type,
                "auto_cluster_entity_types": entity_types,
                "reason": "accepted cluster crosses entity_type boundaries",
                "critical": True,
            }
        )
        return None, conflicts, drug_rows

    reason = str(cluster.get("reason") or "")
    if entity_type == "drug_trade_name" and drug_trade_name_active_substance_conflict(labels, reason):
        drug_row = {
            "n3_cluster_id": n3_cluster_id,
            "source_candidate_group_id": source_candidate_group_id,
            "entity_type": entity_type,
            "node_ids": node_ids,
            "auto_cluster_ids": auto_cluster_ids,
            "labels": labels,
            "reason": reason,
            "action": "merge_blocked",
            "alias_status": "blocked_active_substance_candidate",
            "review_reason": "drug_trade_name_active_substance_conflict",
        }
        drug_rows.append(drug_row)
        conflicts.append(
            {
                "conflict_type": "drug_trade_name_active_substance_conflict",
                "n3_cluster_id": n3_cluster_id,
                "source_candidate_group_id": source_candidate_group_id,
                "node_ids": node_ids,
                "auto_cluster_ids": auto_cluster_ids,
                "labels": labels,
                "reason": "drug trade name cannot be automatically merged with active substance or salt",
                "critical": True,
            }
        )
        return None, conflicts, drug_rows

    return (
        MergeEdge(
            n3_cluster_id=n3_cluster_id,
            source_candidate_group_id=source_candidate_group_id,
            entity_type=entity_type or entity_types[0],
            node_ids=tuple(node_ids),
            auto_cluster_ids=tuple(auto_cluster_ids),
            confidence=float(cluster.get("confidence") or 0.0),
            labels=tuple(labels),
            canonical_tag_ru=str(cluster.get("canonical_tag_ru") or ""),
            canonical_tag_latin=str(cluster.get("canonical_tag_latin") or ""),
            from_split=bool(cluster.get("from_split", False)),
            reason=reason,
        ),
        conflicts,
        drug_rows,
    )


def _rejected_constraints(rejected_groups: list[dict[str, Any]], node_to_auto: dict[str, str]) -> list[set[str]]:
    constraints: list[set[str]] = []
    for group in rejected_groups:
        node_ids = [str(node_id) for node_id in group.get("input_node_ids") or group.get("node_ids") or []]
        auto_ids = {node_to_auto[node_id] for node_id in node_ids if node_id in node_to_auto}
        if len(auto_ids) >= 2:
            constraints.append(auto_ids)
    return constraints


def _direct_weak_rejected_conflict(edge: MergeEdge, rejected_constraints: list[set[str]]) -> bool:
    if edge.confidence >= 0.9:
        return False
    edge_ids = set(edge.auto_cluster_ids)
    return any(constraint.issubset(edge_ids) for constraint in rejected_constraints)


def _mark_rejected_constraint_reviews(
    components_by_id: dict[str, FinalComponent],
    auto_cluster_to_component_id: dict[str, str],
    rejected_groups: list[dict[str, Any]],
    node_to_auto: dict[str, str],
) -> None:
    for group in rejected_groups:
        node_ids = [str(node_id) for node_id in group.get("input_node_ids") or group.get("node_ids") or []]
        auto_ids = [node_to_auto[node_id] for node_id in node_ids if node_id in node_to_auto]
        for left, right in itertools.combinations(sorted(set(auto_ids)), 2):
            left_component = auto_cluster_to_component_id.get(left)
            if left_component and left_component == auto_cluster_to_component_id.get(right):
                components_by_id[left_component].review_reasons.add("rejected_constraint_conflict")


def _review_group_record(group: dict[str, Any], node_to_auto: dict[str, str]) -> dict[str, Any]:
    node_ids = [str(node_id) for node_id in group.get("input_node_ids") or group.get("node_ids") or []]
    return {
        "candidate_group_id": str(group.get("candidate_group_id") or group.get("source_candidate_group_id") or ""),
        "entity_type": str(group.get("entity_type") or ""),
        "decision": str(group.get("decision") or ""),
        "node_ids": node_ids,
        "auto_cluster_ids": sorted({node_to_auto[node_id] for node_id in node_ids if node_id in node_to_auto}),
        "labels": list(group.get("input_group_labels") or group.get("labels") or []),
        "reason": str(group.get("reason") or ""),
        "requires_human_review": True,
    }

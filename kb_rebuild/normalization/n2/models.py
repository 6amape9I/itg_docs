from __future__ import annotations

from dataclasses import dataclass
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class CandidateNode:
    node_id: str
    auto_cluster_id: str
    entity_type: str
    label: str
    normalized_label: str
    latin_label: str
    aliases: list[str]
    normalized_aliases: list[str]
    mention_ids: list[str]
    documents: list[JsonDict]
    mentions_count: int
    documents_count: int
    article_candidate_count: int
    context_only_count: int
    folder_candidate_count: int
    risk_flags: list[str]
    routing_flags: list[str]
    cluster_status: str
    merge_allowed: bool
    subtype_signature: str
    product_key: str

    def to_dict(self) -> JsonDict:
        return {
            "node_id": self.node_id,
            "auto_cluster_id": self.auto_cluster_id,
            "entity_type": self.entity_type,
            "label": self.label,
            "normalized_label": self.normalized_label,
            "latin_label": self.latin_label,
            "aliases": self.aliases,
            "normalized_aliases": self.normalized_aliases,
            "mention_ids": self.mention_ids,
            "documents": self.documents,
            "mentions_count": self.mentions_count,
            "documents_count": self.documents_count,
            "article_candidate_count": self.article_candidate_count,
            "context_only_count": self.context_only_count,
            "folder_candidate_count": self.folder_candidate_count,
            "risk_flags": self.risk_flags,
            "routing_flags": self.routing_flags,
            "cluster_status": self.cluster_status,
            "merge_allowed": self.merge_allowed,
            "subtype_signature": self.subtype_signature,
            "product_key": self.product_key,
        }


@dataclass(frozen=True)
class PairFeatures:
    score: float
    candidate_reasons: list[str]
    risk_reasons: list[str]
    blocking_reasons: list[str]
    metrics: JsonDict


@dataclass(frozen=True)
class CandidatePair:
    pair_id: str
    left_node_id: str
    right_node_id: str
    entity_type: str
    left_label: str
    right_label: str
    score: float
    pair_status: str
    candidate_reasons: list[str]
    risk_reasons: list[str]
    blocking_reasons: list[str]
    metrics: JsonDict

    def to_dict(self) -> JsonDict:
        return {
            "pair_id": self.pair_id,
            "left_node_id": self.left_node_id,
            "right_node_id": self.right_node_id,
            "entity_type": self.entity_type,
            "left_label": self.left_label,
            "right_label": self.right_label,
            "score": self.score,
            "pair_status": self.pair_status,
            "candidate_reasons": self.candidate_reasons,
            "risk_reasons": self.risk_reasons,
            "blocking_reasons": self.blocking_reasons,
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class CandidateGroup:
    candidate_group_id: str
    entity_type: str
    group_labels: list[str]
    node_ids: list[str]
    pair_ids: list[str]
    group_score: float
    group_priority: str
    candidate_reasons: list[str]
    group_risk_flags: list[str]
    requires_llm_validation: bool
    recommended_for_n3: bool
    mentions_count: int
    documents_count: int
    article_candidate_count: int
    context_only_count: int
    sample_documents: list[JsonDict]

    def to_dict(self) -> JsonDict:
        return {
            "candidate_group_id": self.candidate_group_id,
            "entity_type": self.entity_type,
            "group_labels": self.group_labels,
            "node_ids": self.node_ids,
            "pair_ids": self.pair_ids,
            "group_score": self.group_score,
            "group_priority": self.group_priority,
            "candidate_reasons": self.candidate_reasons,
            "group_risk_flags": self.group_risk_flags,
            "requires_llm_validation": self.requires_llm_validation,
            "recommended_for_n3": self.recommended_for_n3,
            "mentions_count": self.mentions_count,
            "documents_count": self.documents_count,
            "article_candidate_count": self.article_candidate_count,
            "context_only_count": self.context_only_count,
            "sample_documents": self.sample_documents,
        }

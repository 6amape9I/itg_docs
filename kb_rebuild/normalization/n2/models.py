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
    clean_candidate_reasons: list[str]
    weak_candidate_reasons: list[str]
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
    clean_candidate_reasons: list[str]
    weak_candidate_reasons: list[str]
    risk_reasons: list[str]
    blocking_reasons: list[str]
    candidate_quality: str
    scope_conflict_reasons: list[str]
    abbreviation_source: list[str]
    generic_alias_match: bool
    n3_pair_ready: bool
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
            "clean_candidate_reasons": self.clean_candidate_reasons,
            "weak_candidate_reasons": self.weak_candidate_reasons,
            "risk_reasons": self.risk_reasons,
            "blocking_reasons": self.blocking_reasons,
            "candidate_quality": self.candidate_quality,
            "scope_conflict_reasons": self.scope_conflict_reasons,
            "abbreviation_source": self.abbreviation_source,
            "generic_alias_match": self.generic_alias_match,
            "n3_pair_ready": self.n3_pair_ready,
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
    candidate_group_status: str
    n3_ready: bool
    hard_alias_reason: bool
    score_gate_passed: bool
    candidate_reasons: list[str]
    clean_candidate_reasons: list[str]
    weak_candidate_reasons: list[str]
    group_risk_flags: list[str]
    exclusion_reasons: list[str]
    subtype_markers: list[str]
    location_markers: list[str]
    cellular_markers: list[str]
    complex_markers: list[str]
    quality_gate_flags: list[str]
    hub_node_ids: list[str]
    generic_aliases_matched: list[str]
    ambiguous_abbreviations: list[str]
    scope_conflict_reasons: list[str]
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
            "candidate_group_status": self.candidate_group_status,
            "n3_ready": self.n3_ready,
            "hard_alias_reason": self.hard_alias_reason,
            "score_gate_passed": self.score_gate_passed,
            "candidate_reasons": self.candidate_reasons,
            "clean_candidate_reasons": self.clean_candidate_reasons,
            "weak_candidate_reasons": self.weak_candidate_reasons,
            "group_risk_flags": self.group_risk_flags,
            "exclusion_reasons": self.exclusion_reasons,
            "subtype_markers": self.subtype_markers,
            "location_markers": self.location_markers,
            "cellular_markers": self.cellular_markers,
            "complex_markers": self.complex_markers,
            "quality_gate_flags": self.quality_gate_flags,
            "hub_node_ids": self.hub_node_ids,
            "generic_aliases_matched": self.generic_aliases_matched,
            "ambiguous_abbreviations": self.ambiguous_abbreviations,
            "scope_conflict_reasons": self.scope_conflict_reasons,
            "requires_llm_validation": self.requires_llm_validation,
            "recommended_for_n3": self.recommended_for_n3,
            "mentions_count": self.mentions_count,
            "documents_count": self.documents_count,
            "article_candidate_count": self.article_candidate_count,
            "context_only_count": self.context_only_count,
            "sample_documents": self.sample_documents,
        }

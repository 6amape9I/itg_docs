from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


STAGE_VERSION = "n3.0"
PROMPT_VERSION = "n3_validate_group_v1"
SCHEMA_VERSION = "n3_group_decision_v1"

GROUP_DECISIONS = {
    "accept_same_entity",
    "reject_distinct_entities",
    "split_into_subclusters",
    "needs_web_or_human_review",
}
SUBCLUSTER_DECISIONS = {"same_entity", "singleton", "reject"}


@dataclass(frozen=True)
class N3InputGroup:
    candidate_group_id: str
    entity_type: str
    group_labels: list[str]
    node_ids: list[str]
    group_score: float
    candidate_reasons: list[str]
    clean_candidate_reasons: list[str]
    weak_candidate_reasons: list[str]
    group_risk_flags: list[str]
    mentions_count: int
    documents_count: int
    article_candidate_count: int
    context_only_count: int
    sample_documents: list[dict[str, Any]]
    nodes: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_n2_group(cls, group: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]) -> "N3InputGroup":
        node_ids = [str(node_id) for node_id in group.get("node_ids", [])]
        return cls(
            candidate_group_id=str(group.get("candidate_group_id", "")),
            entity_type=str(group.get("entity_type", "")),
            group_labels=[str(label) for label in group.get("group_labels", [])],
            node_ids=node_ids,
            group_score=float(group.get("group_score", 0.0) or 0.0),
            candidate_reasons=[str(reason) for reason in group.get("candidate_reasons", [])],
            clean_candidate_reasons=[str(reason) for reason in group.get("clean_candidate_reasons", [])],
            weak_candidate_reasons=[str(reason) for reason in group.get("weak_candidate_reasons", [])],
            group_risk_flags=[str(flag) for flag in group.get("group_risk_flags", [])],
            mentions_count=int(group.get("mentions_count", 0) or 0),
            documents_count=int(group.get("documents_count", 0) or 0),
            article_candidate_count=int(group.get("article_candidate_count", 0) or 0),
            context_only_count=int(group.get("context_only_count", 0) or 0),
            sample_documents=[
                item for item in group.get("sample_documents", []) if isinstance(item, dict)
            ],
            nodes=[_node_for_prompt(nodes_by_id[node_id]) for node_id in node_ids if node_id in nodes_by_id],
        )

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "candidate_group_id": self.candidate_group_id,
            "entity_type": self.entity_type,
            "group_labels": self.group_labels,
            "node_ids": self.node_ids,
            "group_score": self.group_score,
            "candidate_reasons": self.candidate_reasons,
            "clean_candidate_reasons": self.clean_candidate_reasons,
            "weak_candidate_reasons": self.weak_candidate_reasons,
            "group_risk_flags": self.group_risk_flags,
            "mentions_count": self.mentions_count,
            "documents_count": self.documents_count,
            "article_candidate_count": self.article_candidate_count,
            "context_only_count": self.context_only_count,
            "sample_documents": self.sample_documents,
            "nodes": self.nodes,
        }


@dataclass(frozen=True)
class N3Subcluster:
    subcluster_id: str
    decision: str
    canonical_tag_ru: str
    canonical_tag_latin: str
    labels: list[str]
    node_ids: list[str]
    confidence: float
    reason: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "N3Subcluster":
        return cls(
            subcluster_id=str(value.get("subcluster_id", "")),
            decision=str(value.get("decision", "")),
            canonical_tag_ru=str(value.get("canonical_tag_ru", "")),
            canonical_tag_latin=str(value.get("canonical_tag_latin", "")),
            labels=[str(label) for label in value.get("labels", []) if isinstance(label, str)],
            node_ids=[str(node_id) for node_id in value.get("node_ids", [])],
            confidence=float(value.get("confidence", 0.0) or 0.0),
            reason=str(value.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "subcluster_id": self.subcluster_id,
            "decision": self.decision,
            "canonical_tag_ru": self.canonical_tag_ru,
            "canonical_tag_latin": self.canonical_tag_latin,
            "labels": self.labels,
            "node_ids": self.node_ids,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class N3RejectedLabel:
    label: str
    node_id: str
    reason: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "N3RejectedLabel":
        return cls(
            label=str(value.get("label", "")),
            node_id=str(value.get("node_id", "")),
            reason=str(value.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "node_id": self.node_id, "reason": self.reason}


@dataclass(frozen=True)
class N3Decision:
    candidate_group_id: str
    entity_type: str
    input_group_labels: list[str]
    input_node_ids: list[str]
    decision: str
    confidence: float
    canonical_tag_ru: str
    canonical_tag_latin: str
    subclusters: list[N3Subcluster]
    rejected_labels: list[N3RejectedLabel]
    reason: str
    risk_flags: list[str]
    requires_human_review: bool
    model: str
    provider: str
    prompt_version: str
    schema_version: str
    usage: dict[str, int]
    estimated_cost_usd: float
    latency_ms: int
    cache_key: str
    from_cache: bool
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_group_id": self.candidate_group_id,
            "entity_type": self.entity_type,
            "input_group_labels": self.input_group_labels,
            "input_node_ids": self.input_node_ids,
            "decision": self.decision,
            "confidence": self.confidence,
            "canonical_tag_ru": self.canonical_tag_ru,
            "canonical_tag_latin": self.canonical_tag_latin,
            "subclusters": [subcluster.to_dict() for subcluster in self.subclusters],
            "rejected_labels": [label.to_dict() for label in self.rejected_labels],
            "reason": self.reason,
            "risk_flags": self.risk_flags,
            "requires_human_review": self.requires_human_review,
            "model": self.model,
            "provider": self.provider,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "usage": self.usage,
            "estimated_cost_usd": self.estimated_cost_usd,
            "latency_ms": self.latency_ms,
            "cache_key": self.cache_key,
            "from_cache": self.from_cache,
            "created_at": self.created_at,
        }


def _node_for_prompt(node: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "node_id",
        "label",
        "normalized_label",
        "aliases",
        "normalized_aliases",
        "latin_label",
        "mentions_count",
        "documents_count",
        "risk_flags",
        "routing_flags",
    ]
    return {key: node.get(key) for key in keys}


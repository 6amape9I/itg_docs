from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


STAGE_VERSION = "n4.0"


@dataclass(frozen=True)
class MergeEdge:
    n3_cluster_id: str
    source_candidate_group_id: str
    entity_type: str
    node_ids: tuple[str, ...]
    auto_cluster_ids: tuple[str, ...]
    confidence: float
    labels: tuple[str, ...]
    canonical_tag_ru: str
    canonical_tag_latin: str
    from_split: bool
    reason: str


@dataclass
class FinalComponent:
    component_id: str
    auto_cluster_ids: list[str]
    entity_type: str
    edges: list[MergeEdge] = field(default_factory=list)
    review_reasons: set[str] = field(default_factory=set)

    @property
    def n3_cluster_ids(self) -> list[str]:
        return sorted({edge.n3_cluster_id for edge in self.edges if edge.n3_cluster_id})

    @property
    def source_candidate_group_ids(self) -> list[str]:
        return sorted({edge.source_candidate_group_id for edge in self.edges if edge.source_candidate_group_id})

    @property
    def from_n3_split(self) -> bool:
        return any(edge.from_split for edge in self.edges)

    @property
    def merged_by_n3(self) -> bool:
        return len(self.auto_cluster_ids) > 1 and bool(self.edges)


@dataclass
class GraphBuildResult:
    components: list[FinalComponent]
    auto_cluster_to_component_id: dict[str, str]
    merge_conflicts: list[dict[str, Any]]
    drug_policy_review: list[dict[str, Any]]
    unresolved_review_groups: list[dict[str, Any]]

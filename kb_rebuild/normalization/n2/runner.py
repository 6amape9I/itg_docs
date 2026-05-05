from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kb_rebuild.io.jsonl import read_jsonl, write_jsonl
from kb_rebuild.llm.tagging import utc_now
from kb_rebuild.normalization.n2.grouping import build_candidate_groups
from kb_rebuild.normalization.n2.pair_generation import build_candidate_nodes, generate_candidate_pairs
from kb_rebuild.normalization.n2.report import (
    build_candidate_groups_csv_rows,
    build_report,
    build_singleton_fast_path_rows,
    write_csv,
    write_json,
)


@dataclass(frozen=True)
class N2Config:
    data_dir: Path = Path("data")
    normalization_dir: Path = Path("data/normalization")
    out_dir: Path = Path("data/normalization/n2")
    min_score: float = 0.72
    high_priority_score: float = 0.88
    max_pairs_per_type: int = 50_000

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Path,
        *,
        normalization_dir: Path | None = None,
        out_dir: Path | None = None,
        min_score: float = 0.72,
        high_priority_score: float = 0.88,
        max_pairs_per_type: int = 50_000,
    ) -> "N2Config":
        norm_dir = normalization_dir or data_dir / "normalization"
        return cls(
            data_dir=data_dir,
            normalization_dir=norm_dir,
            out_dir=out_dir or norm_dir / "n2",
            min_score=min_score,
            high_priority_score=high_priority_score,
            max_pairs_per_type=max_pairs_per_type,
        )


OUTPUT_FILENAMES = {
    "candidate_nodes": "candidate_nodes.jsonl",
    "candidate_pairs": "candidate_pairs.jsonl",
    "blocked_pairs": "blocked_pairs.jsonl",
    "rejected_pairs": "rejected_pairs.jsonl",
    "candidate_groups": "candidate_groups.jsonl",
    "candidate_groups_csv": "candidate_groups.csv",
    "high_priority_candidate_groups_csv": "high_priority_candidate_groups.csv",
    "singleton_fast_path_candidates_csv": "singleton_fast_path_candidates.csv",
    "candidate_generation_report": "candidate_generation_report.json",
    "candidate_generation_manifest": "candidate_generation_manifest.json",
}


def run_normalization_n2(config: N2Config) -> dict[str, Any]:
    return NormalizationN2Runner(config).run()


class NormalizationN2Runner:
    def __init__(self, config: N2Config) -> None:
        self.config = config
        self.paths = {name: config.out_dir / filename for name, filename in OUTPUT_FILENAMES.items()}
        self.inputs = {
            "auto_clusters": config.normalization_dir / "auto_clusters.jsonl",
            "tag_mentions_normalized": config.normalization_dir / "tag_mentions_normalized.jsonl",
            "singleton_entity_candidates": config.normalization_dir / "singleton_entity_candidates.jsonl",
            "normalization_manifest": config.normalization_dir / "normalization_n1_manifest.json",
            "cluster_duplicate_diagnostics": config.normalization_dir / "cluster_duplicate_diagnostics.csv",
        }

    def run(self) -> dict[str, Any]:
        warnings: list[str] = []
        created_at = utc_now()
        self._validate_inputs()

        clusters = read_jsonl(self.inputs["auto_clusters"])
        mentions = read_jsonl(self.inputs["tag_mentions_normalized"])
        singletons = read_jsonl(self.inputs["singleton_entity_candidates"])
        nodes = build_candidate_nodes(clusters, mentions)
        self._validate_nodes(nodes)

        candidate_pairs, blocked_pairs, rejected_pairs = generate_candidate_pairs(
            nodes,
            min_score=self.config.min_score,
            high_priority_score=self.config.high_priority_score,
            max_pairs_per_type=self.config.max_pairs_per_type,
            warnings=warnings,
        )
        self._validate_pairs(candidate_pairs, blocked_pairs, rejected_pairs)

        groups = build_candidate_groups(
            nodes,
            candidate_pairs,
            blocked_pairs,
            high_priority_score=self.config.high_priority_score,
        )
        self._validate_groups(groups, candidate_pairs, blocked_pairs)

        singleton_rows = build_singleton_fast_path_rows(singletons)
        self.config.out_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(self.paths["candidate_nodes"], (node.to_dict() for node in nodes))
        write_jsonl(self.paths["candidate_pairs"], (pair.to_dict() for pair in candidate_pairs))
        write_jsonl(self.paths["blocked_pairs"], (pair.to_dict() for pair in blocked_pairs))
        write_jsonl(self.paths["rejected_pairs"], (pair.to_dict() for pair in rejected_pairs))
        write_jsonl(self.paths["candidate_groups"], (group.to_dict() for group in groups))

        group_rows = build_candidate_groups_csv_rows(groups)
        group_fields = [
            "candidate_group_id",
            "entity_type",
            "group_priority",
            "group_score",
            "group_labels",
            "node_ids",
            "mentions_count",
            "documents_count",
            "article_candidate_count",
            "context_only_count",
            "candidate_reasons",
            "group_risk_flags",
            "requires_llm_validation",
            "recommended_for_n3",
            "sample_documents",
        ]
        write_csv(self.paths["candidate_groups_csv"], group_fields, group_rows)
        write_csv(
            self.paths["high_priority_candidate_groups_csv"],
            group_fields,
            [row for row in group_rows if row.get("group_priority") == "high"],
        )
        singleton_fields = [
            "candidate_id",
            "doc_id",
            "document_name",
            "entity_type",
            "canonical_display_candidate",
            "canonical_latin_candidate",
            "surface",
            "confidence",
            "quote_validation_status",
            "mentions_count",
            "documents_count",
            "document_article_candidate_count",
            "has_competing_article_candidates",
            "competing_article_candidates",
            "recommended_fast_path",
            "review_required",
            "review_reasons",
            "fast_path_reason",
            "expected_downstream_action",
        ]
        write_csv(self.paths["singleton_fast_path_candidates_csv"], singleton_fields, singleton_rows)

        report = build_report(
            created_at=created_at,
            source_manifest_path=self.inputs["normalization_manifest"],
            nodes=nodes,
            candidate_pairs=candidate_pairs,
            blocked_pairs=blocked_pairs,
            rejected_pairs=rejected_pairs,
            groups=groups,
            singleton_fast_path_rows=singleton_rows,
            warnings=warnings,
        )
        write_json(self.paths["candidate_generation_report"], report)
        write_json(self.paths["candidate_generation_manifest"], self._build_manifest(created_at))
        return report

    def _validate_inputs(self) -> None:
        for name, path in self.inputs.items():
            if not path.exists():
                raise FileNotFoundError(f"missing N2 input {name}: {path}")
        with self.inputs["normalization_manifest"].open("r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        if manifest.get("stage_version") != "n1.1":
            raise ValueError("N2 requires normalization_n1_manifest.json stage_version=n1.1")
        if _csv_has_data_rows(self.inputs["cluster_duplicate_diagnostics"]):
            raise ValueError("N2 refuses to run while cluster_duplicate_diagnostics.csv has duplicate rows")

    def _validate_nodes(self, nodes: list[Any]) -> None:
        node_ids = [node.node_id for node in nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("node_ids are not unique")

    def _validate_pairs(self, *pair_lists: list[Any]) -> None:
        pair_ids: list[str] = []
        for pairs in pair_lists:
            for pair in pairs:
                pair_ids.append(pair.pair_id)
                if not pair.entity_type:
                    raise ValueError(f"{pair.pair_id}: missing entity_type")
        if len(pair_ids) != len(set(pair_ids)):
            raise ValueError("pair_ids are not unique")

    def _validate_groups(self, groups: list[Any], candidate_pairs: list[Any], blocked_pairs: list[Any]) -> None:
        group_ids = [group.candidate_group_id for group in groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("candidate_group_ids are not unique")
        candidate_pair_ids = {pair.pair_id for pair in candidate_pairs}
        blocked_pair_ids = {pair.pair_id for pair in blocked_pairs}
        for group in groups:
            if len(group.node_ids) < 2:
                raise ValueError(f"{group.candidate_group_id}: candidate group has fewer than 2 nodes")
            if group.group_priority != "blocked_review" and any(pair_id in blocked_pair_ids for pair_id in group.pair_ids):
                raise ValueError(f"{group.candidate_group_id}: blocked pair entered a normal candidate group")
            if group.group_priority != "blocked_review" and any(pair_id not in candidate_pair_ids for pair_id in group.pair_ids):
                raise ValueError(f"{group.candidate_group_id}: normal group references non-candidate pair")

    def _build_manifest(self, created_at: str) -> dict[str, Any]:
        return {
            "stage": "normalization_n2_candidate_generation",
            "created_at": created_at,
            "source_normalization_manifest": str(self.inputs["normalization_manifest"]),
            "source_stage_version": "n1.1",
            "inputs": {name: str(path) for name, path in self.inputs.items()},
            "outputs": {name: str(path) for name, path in self.paths.items()},
        }


def _csv_has_data_rows(path: Path) -> bool:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)
        return any(any(cell.strip() for cell in row) for row in reader)

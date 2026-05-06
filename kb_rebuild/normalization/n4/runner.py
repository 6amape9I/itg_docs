from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from kb_rebuild.io.jsonl import read_jsonl, write_jsonl
from kb_rebuild.llm.tagging import utc_now
from kb_rebuild.normalization.n4.aliases import (
    build_alias_records,
    build_component_alias_candidates,
    find_alias_conflicts,
    mark_alias_conflicts,
)
from kb_rebuild.normalization.n4.canonical import canonical_tag_id, choose_canonical, component_stats
from kb_rebuild.normalization.n4.graph import build_graph_components
from kb_rebuild.normalization.n4.links import audit_coverage, build_document_links, build_document_tags_by_doc
from kb_rebuild.normalization.n4.models import STAGE_VERSION, FinalComponent
from kb_rebuild.normalization.n4.review import REVIEW_FIELDS, specialist_review_rows, specialist_review_sample
from kb_rebuild.normalization.text import normalize_basic_text


@dataclass(frozen=True)
class N4Config:
    data_dir: Path = Path("data")
    normalization_dir: Path = Path("data/normalization")
    n2_dir: Path = Path("data/normalization/n2")
    n3_dir: Path = Path("data/normalization/n3")
    out_dir: Path = Path("data/normalization/final")
    review_sample_size: int = 500

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Path,
        *,
        normalization_dir: Path | None = None,
        n2_dir: Path | None = None,
        n3_dir: Path | None = None,
        out_dir: Path | None = None,
        review_sample_size: int = 500,
    ) -> "N4Config":
        norm_dir = normalization_dir or data_dir / "normalization"
        return cls(
            data_dir=data_dir,
            normalization_dir=norm_dir,
            n2_dir=n2_dir or norm_dir / "n2",
            n3_dir=n3_dir or norm_dir / "n3",
            out_dir=out_dir or norm_dir / "final",
            review_sample_size=review_sample_size,
        )


OUTPUT_FILENAMES = {
    "tags_canonical_csv": "tags_canonical.csv",
    "tag_aliases_csv": "tag_aliases.csv",
    "document_tag_links_normalized_jsonl": "document_tag_links_normalized.jsonl",
    "document_tag_links_normalized_csv": "document_tag_links_normalized.csv",
    "document_tags_normalized_by_doc_jsonl": "document_tags_normalized_by_doc.jsonl",
    "final_canonical_tag_names_csv": "final_canonical_tag_names.csv",
    "specialist_review_full_csv": "specialist_review_full.csv",
    "specialist_review_sample_csv": "specialist_review_sample.csv",
    "canonical_review_detailed_csv": "canonical_review_detailed.csv",
    "coverage_audit_json": "coverage_audit.json",
    "coverage_audit_missing_mentions_csv": "coverage_audit_missing_mentions.csv",
    "coverage_audit_missing_aliases_csv": "coverage_audit_missing_aliases.csv",
    "alias_conflicts_csv": "alias_conflicts.csv",
    "merge_conflicts_jsonl": "merge_conflicts.jsonl",
    "drug_policy_review_csv": "drug_policy_review.csv",
    "unresolved_review_groups_jsonl": "unresolved_review_groups.jsonl",
    "final_report": "final_normalization_report.json",
    "final_manifest": "final_normalization_manifest.json",
}


def run_normalization_n4(config: N4Config) -> dict[str, Any]:
    return NormalizationN4Runner(config).run()


class NormalizationN4Runner:
    def __init__(self, config: N4Config) -> None:
        self.config = config
        self.paths = {name: config.out_dir / filename for name, filename in OUTPUT_FILENAMES.items()}
        self.inputs = {
            "auto_clusters": config.normalization_dir / "auto_clusters.jsonl",
            "tag_mentions_normalized": config.normalization_dir / "tag_mentions_normalized.jsonl",
            "tag_mentions_raw": config.normalization_dir / "tag_mentions_raw.jsonl",
            "normalization_n1_manifest": config.normalization_dir / "normalization_n1_manifest.json",
            "normalization_n1_report": config.normalization_dir / "normalization_n1_report.json",
            "candidate_nodes": config.n2_dir / "candidate_nodes.jsonl",
            "candidate_generation_manifest": config.n2_dir / "candidate_generation_manifest.json",
            "candidate_generation_report": config.n2_dir / "candidate_generation_report.json",
            "accepted_clusters": config.n3_dir / "accepted_clusters.jsonl",
            "rejected_groups": config.n3_dir / "rejected_groups.jsonl",
            "split_groups": config.n3_dir / "split_groups.jsonl",
            "web_or_human_review_groups": config.n3_dir / "web_or_human_review_groups.jsonl",
            "llm_group_decisions": config.n3_dir / "llm_group_decisions.jsonl",
            "n3_report": config.n3_dir / "n3_report.json",
            "n3_manifest": config.n3_dir / "n3_manifest.json",
            "n3_quality_diagnostics": config.n3_dir / "n3_quality_diagnostics.json",
        }

    def run(self) -> dict[str, Any]:
        created_at = utc_now()
        self._validate_config()
        self._validate_inputs()

        auto_clusters = read_jsonl(self.inputs["auto_clusters"])
        mentions = read_jsonl(self.inputs["tag_mentions_normalized"])
        raw_mentions_count = _count_jsonl(self.inputs["tag_mentions_raw"])
        candidate_nodes = read_jsonl(self.inputs["candidate_nodes"])
        accepted_clusters = read_jsonl(self.inputs["accepted_clusters"])
        rejected_groups = read_jsonl(self.inputs["rejected_groups"])
        review_groups = read_jsonl(self.inputs["web_or_human_review_groups"])
        n1_report = _read_json(self.inputs["normalization_n1_report"])
        n3_report = _read_json(self.inputs["n3_report"])

        clusters_by_id = {str(cluster.get("auto_cluster_id") or ""): cluster for cluster in auto_clusters}
        mention_by_id = {str(mention.get("mention_id") or ""): mention for mention in mentions}
        mention_to_auto_cluster, mentions_by_auto_cluster, duplicate_mentions = _mention_cluster_maps(auto_clusters, mention_by_id)

        graph = build_graph_components(
            auto_clusters=auto_clusters,
            candidate_nodes=candidate_nodes,
            accepted_clusters=accepted_clusters,
            rejected_groups=rejected_groups,
            review_groups=review_groups,
        )

        canonical_rows, alias_rows = self._build_tags_and_aliases(
            components=graph.components,
            clusters_by_id=clusters_by_id,
            mentions_by_auto_cluster=mentions_by_auto_cluster,
        )

        alias_conflicts = find_alias_conflicts(alias_rows, canonical_rows)
        if alias_conflicts:
            mark_alias_conflicts(alias_rows, alias_conflicts)
            _mark_conflicted_tags(canonical_rows, alias_conflicts)

        tags_by_id = {str(row.get("tag_id") or ""): row for row in canonical_rows}
        auto_cluster_to_tag_id = {
            auto_cluster_id: tags_by_id_by_component[component_id]
            for auto_cluster_id, component_id in graph.auto_cluster_to_component_id.items()
            for tags_by_id_by_component in [{row["component_id"]: row["tag_id"] for row in canonical_rows}]
        }
        document_links, missing_mentions = build_document_links(
            mentions=mentions,
            mention_to_auto_cluster=mention_to_auto_cluster,
            auto_cluster_to_tag_id=auto_cluster_to_tag_id,
            tags_by_id=tags_by_id,
        )
        document_tags_by_doc = build_document_tags_by_doc(document_links)
        coverage_audit, missing_aliases = audit_coverage(
            mentions=mentions,
            links=document_links,
            canonical_rows=canonical_rows,
            alias_rows=alias_rows,
            missing_mentions=missing_mentions,
        )

        if duplicate_mentions:
            for item in duplicate_mentions:
                item["reason"] = "mention_id appears in multiple auto_clusters"
            missing_mentions.extend(duplicate_mentions)
            coverage_audit["mentions_without_tag_id"] = len(missing_mentions)
            coverage_audit["all_mentions_have_tag_id"] = len(missing_mentions) == 0
            coverage_audit["passed"] = bool(coverage_audit["passed"] and not duplicate_mentions)
            coverage_audit["quality"]["all_mentions_have_tag_id"] = coverage_audit["all_mentions_have_tag_id"]
            coverage_audit["quality"]["passed"] = coverage_audit["passed"]

        aliases_by_tag_id = _aliases_by_tag_id(alias_rows)
        report = self._build_report(
            created_at=created_at,
            n1_report=n1_report,
            n3_report=n3_report,
            auto_clusters=auto_clusters,
            accepted_clusters=accepted_clusters,
            canonical_rows=canonical_rows,
            alias_rows=alias_rows,
            document_links=document_links,
            document_tags_by_doc=document_tags_by_doc,
            coverage_audit=coverage_audit,
            alias_conflicts=alias_conflicts,
            merge_conflicts=graph.merge_conflicts,
            drug_policy_review=graph.drug_policy_review,
            unresolved_review_groups=graph.unresolved_review_groups,
            raw_mentions_count=raw_mentions_count,
        )

        self.config.out_dir.mkdir(parents=True, exist_ok=True)
        write_csv(self.paths["tags_canonical_csv"], TAGS_CANONICAL_FIELDS, canonical_rows)
        write_csv(self.paths["tag_aliases_csv"], TAG_ALIASES_FIELDS, alias_rows)
        write_jsonl(self.paths["document_tag_links_normalized_jsonl"], document_links)
        write_csv(self.paths["document_tag_links_normalized_csv"], DOCUMENT_LINK_FIELDS, document_links)
        write_jsonl(self.paths["document_tags_normalized_by_doc_jsonl"], document_tags_by_doc)
        write_csv(self.paths["final_canonical_tag_names_csv"], FINAL_NAMES_FIELDS, _final_name_rows(canonical_rows))
        write_csv(self.paths["specialist_review_full_csv"], REVIEW_FIELDS, specialist_review_rows(canonical_rows, aliases_by_tag_id))
        write_csv(
            self.paths["specialist_review_sample_csv"],
            REVIEW_FIELDS,
            specialist_review_sample(canonical_rows, aliases_by_tag_id, sample_size=self.config.review_sample_size),
        )
        write_csv(self.paths["canonical_review_detailed_csv"], CANONICAL_REVIEW_FIELDS, _canonical_review_rows(canonical_rows, aliases_by_tag_id))
        write_json(self.paths["coverage_audit_json"], coverage_audit)
        write_csv(self.paths["coverage_audit_missing_mentions_csv"], MISSING_MENTIONS_FIELDS, missing_mentions)
        write_csv(self.paths["coverage_audit_missing_aliases_csv"], MISSING_ALIASES_FIELDS, missing_aliases)
        write_csv(self.paths["alias_conflicts_csv"], ALIAS_CONFLICT_FIELDS, alias_conflicts)
        write_jsonl(self.paths["merge_conflicts_jsonl"], graph.merge_conflicts)
        write_csv(self.paths["drug_policy_review_csv"], DRUG_POLICY_FIELDS, graph.drug_policy_review)
        write_jsonl(self.paths["unresolved_review_groups_jsonl"], graph.unresolved_review_groups)
        write_json(self.paths["final_report"], report)
        write_json(self.paths["final_manifest"], self._build_manifest(created_at))
        return report

    def _validate_config(self) -> None:
        if self.config.review_sample_size < 0:
            raise ValueError("review_sample_size must be >= 0")

    def _validate_inputs(self) -> None:
        for name, path in self.inputs.items():
            if not path.exists():
                raise FileNotFoundError(f"missing N4 input {name}: {path}")
        n1_report = _read_json(self.inputs["normalization_n1_report"])
        n1_manifest = _read_json(self.inputs["normalization_n1_manifest"])
        n2_manifest = _read_json(self.inputs["candidate_generation_manifest"])
        n2_report = _read_json(self.inputs["candidate_generation_report"])
        n3_manifest = _read_json(self.inputs["n3_manifest"])
        n3_report = _read_json(self.inputs["n3_report"])
        if n1_manifest.get("stage_version") != "n1.1":
            raise ValueError("N4 requires normalization_n1_manifest.json stage_version=n1.1")
        if int(n1_report.get("counts", {}).get("mentions_total") or 0) <= 0:
            raise ValueError("N4 requires N1 mentions_total > 0")
        if int(n1_report.get("counts", {}).get("auto_clusters_total") or 0) <= 0:
            raise ValueError("N4 requires N1 auto_clusters_total > 0")
        if n2_manifest.get("stage_version") != "n2.2":
            raise ValueError("N4 requires N2 manifest stage_version=n2.2")
        if n2_report.get("stage_version") != "n2.2":
            raise ValueError("N4 requires N2 report stage_version=n2.2")
        if n3_manifest.get("stage_version") != "n3.0":
            raise ValueError("N4 requires N3 manifest stage_version=n3.0")
        if n3_report.get("stage_version") != "n3.0":
            raise ValueError("N4 requires N3 report stage_version=n3.0")
        if not bool(n3_report.get("quality", {}).get("passed")):
            raise ValueError("N4 refuses to run unless N3 quality.passed=true")

    def _build_tags_and_aliases(
        self,
        *,
        components: list[FinalComponent],
        clusters_by_id: dict[str, dict[str, Any]],
        mentions_by_auto_cluster: dict[str, list[dict[str, Any]]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        canonical_rows: list[dict[str, Any]] = []
        alias_rows: list[dict[str, Any]] = []
        used_tag_ids: set[str] = set()
        for component in components:
            component_mentions = [
                mention
                for auto_cluster_id in component.auto_cluster_ids
                for mention in mentions_by_auto_cluster.get(auto_cluster_id, [])
            ]
            canonical_ru, canonical_latin, canonical_review_reasons = choose_canonical(component, clusters_by_id, component_mentions)
            review_reasons = sorted(
                set(canonical_review_reasons)
                | set(component.review_reasons)
                | set(_cluster_review_reasons(component, clusters_by_id))
            )
            stats = component_stats(component, clusters_by_id, component_mentions)
            alias_candidates = build_component_alias_candidates(component, clusters_by_id, component_mentions, canonical_ru, canonical_latin)
            alias_norms = [normalize_basic_text(str(candidate.get("alias") or "")) for candidate in alias_candidates]
            tag_id = canonical_tag_id(component.entity_type, canonical_ru, canonical_latin, alias_norms)
            if tag_id in used_tag_ids:
                review_reasons.append("duplicate_tag_id_disambiguated")
                tag_id = canonical_tag_id(component.entity_type, canonical_ru, canonical_latin, [*alias_norms, component.component_id])
            used_tag_ids.add(tag_id)
            need_review = bool(review_reasons)
            normalization_source = "n1_auto_cluster"
            if component.edges:
                normalization_source = "n3_split_accepted" if component.from_n3_split else "n3_accepted"
            merge_method = "single_auto_cluster"
            if component.edges:
                merge_method = "llm_split_validated" if component.from_n3_split else "llm_validated"
            row = {
                "component_id": component.component_id,
                "tag_id": tag_id,
                "canonical_tag_ru": canonical_ru,
                "canonical_tag_latin": canonical_latin,
                "entity_type": component.entity_type,
                "primary_role": stats["primary_role"],
                "article_candidate": stats["article_candidate"],
                "status": "active",
                "need_review": need_review,
                "review_reasons": sorted(set(review_reasons)),
                "aliases_count": len(alias_candidates),
                "mentions_count": stats["mentions_count"],
                "documents_count": stats["documents_count"],
                "confidence": stats["confidence"],
                "normalization_source": normalization_source,
                "merge_method": merge_method,
                "auto_cluster_ids": component.auto_cluster_ids,
                "n3_cluster_ids": component.n3_cluster_ids,
                "source_candidate_group_ids": component.source_candidate_group_ids,
                "created_from_stage": STAGE_VERSION,
                "active": True,
                "needs_review": need_review,
                "context_only": stats["context_only"],
                "folder_candidate": stats["folder_candidate"],
                "n1_auto_cluster": True,
                "n3_accepted": bool(component.edges),
                "n3_split_accepted": component.from_n3_split,
                "n4_drug_policy_review": False,
                "n4_conflict_review": any(reason.endswith("_conflict") for reason in review_reasons),
                "single_auto_cluster": len(component.auto_cluster_ids) == 1,
                "deterministic": True,
                "llm_validated": bool(component.edges and not component.from_n3_split),
                "llm_split_validated": component.from_n3_split,
                "review_required": need_review,
                "article_candidate_count": stats["article_candidate_count"],
                "context_only_count": stats["context_only_count"],
                "folder_candidate_count": stats["folder_candidate_count"],
            }
            canonical_rows.append(row)
            mention_norm_counts = _mention_norm_counts(component_mentions)
            alias_rows.extend(
                build_alias_records(
                    tag_id=tag_id,
                    entity_type=component.entity_type,
                    candidates=alias_candidates,
                    mention_norm_counts=mention_norm_counts,
                    need_review=need_review,
                    review_reasons=review_reasons,
                )
            )
        return canonical_rows, alias_rows

    def _build_report(
        self,
        *,
        created_at: str,
        n1_report: dict[str, Any],
        n3_report: dict[str, Any],
        auto_clusters: list[dict[str, Any]],
        accepted_clusters: list[dict[str, Any]],
        canonical_rows: list[dict[str, Any]],
        alias_rows: list[dict[str, Any]],
        document_links: list[dict[str, Any]],
        document_tags_by_doc: list[dict[str, Any]],
        coverage_audit: dict[str, Any],
        alias_conflicts: list[dict[str, Any]],
        merge_conflicts: list[dict[str, Any]],
        drug_policy_review: list[dict[str, Any]],
        unresolved_review_groups: list[dict[str, Any]],
        raw_mentions_count: int,
    ) -> dict[str, Any]:
        n1_counts = n1_report.get("counts", {})
        tag_ids = [str(row.get("tag_id") or "") for row in canonical_rows]
        alias_tag_ids_missing = [row for row in alias_rows if str(row.get("tag_id") or "") not in set(tag_ids)]
        auto_cluster_ids_in_output = {
            auto_cluster_id
            for row in canonical_rows
            for auto_cluster_id in _list(row.get("auto_cluster_ids"))
        }
        all_auto_clusters_covered = len(auto_cluster_ids_in_output) == len(auto_clusters)
        no_duplicate_tag_ids = len(tag_ids) == len(set(tag_ids))
        no_empty_canonical = all(str(row.get("canonical_tag_ru") or "").strip() for row in canonical_rows)
        no_missing_tag_ids_in_links = coverage_audit.get("links_to_missing_tag_id") == 0
        quality_passed = bool(
            coverage_audit.get("passed")
            and all_auto_clusters_covered
            and no_empty_canonical
            and no_missing_tag_ids_in_links
            and not alias_tag_ids_missing
            and no_duplicate_tag_ids
        )
        counts = {
            "mentions_total": len(document_links),
            "tag_mentions_raw_total": raw_mentions_count,
            "document_tag_links_total": len(document_links),
            "documents_with_tags": int(n1_counts.get("documents_with_tags") or coverage_audit.get("documents_with_mentions") or 0),
            "documents_with_normalized_tags": len(document_tags_by_doc),
            "auto_clusters_total": len(auto_clusters),
            "n3_accepted_clusters_total": len(accepted_clusters),
            "final_canonical_tags_total": len(canonical_rows),
            "standalone_auto_cluster_tags": sum(1 for row in canonical_rows if row.get("single_auto_cluster") and not row.get("n3_accepted")),
            "merged_n3_tags": sum(1 for row in canonical_rows if row.get("n3_accepted") and not row.get("single_auto_cluster")),
            "aliases_total": len(alias_rows),
            "need_review_tags": sum(1 for row in canonical_rows if row.get("need_review")),
            "alias_conflicts": len(alias_conflicts),
            "merge_conflicts": len(merge_conflicts),
            "drug_policy_review_items": len(drug_policy_review),
            "unresolved_review_groups": len(unresolved_review_groups),
        }
        return {
            "stage": "normalization_n4_final_canonical_layer",
            "stage_version": STAGE_VERSION,
            "created_at": created_at,
            "source_n1_stage_version": "n1.1",
            "source_n3_stage_version": n3_report.get("stage_version"),
            "counts": counts,
            "coverage_audit": coverage_audit,
            "quality": {
                "all_auto_clusters_covered": all_auto_clusters_covered,
                "all_mentions_have_tag_id": bool(coverage_audit.get("all_mentions_have_tag_id")),
                "all_original_tag_names_recognized": bool(coverage_audit.get("all_original_tag_names_recognized")),
                "no_empty_canonical_tag_ru": no_empty_canonical,
                "no_missing_tag_ids_in_links": no_missing_tag_ids_in_links,
                "no_alias_without_tag_id": not alias_tag_ids_missing,
                "no_duplicate_tag_ids": no_duplicate_tag_ids,
                "final_canonical_tag_names_created": True,
                "specialist_review_full_created": True,
                "specialist_review_sample_created": True,
                "passed": quality_passed,
            },
        }

    def _build_manifest(self, created_at: str) -> dict[str, Any]:
        return {
            "stage": "normalization_n4_final_canonical_layer",
            "stage_version": STAGE_VERSION,
            "created_at": created_at,
            "inputs": {name: str(path) for name, path in self.inputs.items()},
            "outputs": {name: str(path) for name, path in self.paths.items()},
            "review_sample_size": self.config.review_sample_size,
        }


TAGS_CANONICAL_FIELDS = [
    "component_id",
    "tag_id",
    "canonical_tag_ru",
    "canonical_tag_latin",
    "entity_type",
    "primary_role",
    "article_candidate",
    "status",
    "need_review",
    "review_reasons",
    "aliases_count",
    "mentions_count",
    "documents_count",
    "confidence",
    "normalization_source",
    "merge_method",
    "auto_cluster_ids",
    "n3_cluster_ids",
    "source_candidate_group_ids",
    "created_from_stage",
    "active",
    "needs_review",
    "context_only",
    "folder_candidate",
    "n1_auto_cluster",
    "n3_accepted",
    "n3_split_accepted",
    "n4_drug_policy_review",
    "n4_conflict_review",
    "single_auto_cluster",
    "deterministic",
    "llm_validated",
    "llm_split_validated",
    "review_required",
    "article_candidate_count",
    "context_only_count",
    "folder_candidate_count",
]

TAG_ALIASES_FIELDS = [
    "alias_id",
    "tag_id",
    "alias",
    "alias_norm",
    "alias_latin",
    "entity_type",
    "alias_source",
    "alias_status",
    "mention_count",
    "document_count",
    "confidence",
    "need_review",
    "review_reasons",
    "n1_surface",
    "n1_canonical_candidate_ru",
    "n1_canonical_candidate_latin",
    "n1_auto_cluster_alias",
    "n3_label",
    "n3_canonical",
    "n4_generated",
    "active",
    "needs_review",
    "blocked_active_substance_candidate",
    "conflict_alias",
]

DOCUMENT_LINK_FIELDS = [
    "doc_id",
    "document_name",
    "mention_id",
    "entity_type",
    "raw_surface",
    "raw_canonical_candidate_ru",
    "raw_canonical_candidate_latin",
    "tag_id",
    "canonical_tag_ru",
    "canonical_tag_latin",
    "tag_role",
    "article_candidate",
    "confidence",
    "normalization_source",
    "need_review",
    "review_reasons",
]

FINAL_NAMES_FIELDS = ["tag_id", "canonical_tag_ru", "canonical_tag_latin", "entity_type", "need_review"]

CANONICAL_REVIEW_FIELDS = [
    "tag_id",
    "canonical_tag_ru",
    "canonical_tag_latin",
    "entity_type",
    "aliases",
    "need_review",
    "review_reasons",
    "mentions_count",
    "documents_count",
    "auto_cluster_ids",
    "n3_cluster_ids",
]

MISSING_MENTIONS_FIELDS = ["mention_id", "doc_id", "document_name", "entity_type", "reason"]

MISSING_ALIASES_FIELDS = [
    "mention_id",
    "doc_id",
    "document_name",
    "entity_type",
    "missing_value",
    "missing_value_norm",
    "source_field",
    "raw_surface",
    "raw_canonical_candidate_ru",
    "raw_canonical_candidate_latin",
    "expected_tag_id",
    "reason",
]

ALIAS_CONFLICT_FIELDS = ["entity_type", "alias_norm", "tag_ids", "conflict_type", "need_review"]

DRUG_POLICY_FIELDS = [
    "n3_cluster_id",
    "source_candidate_group_id",
    "entity_type",
    "node_ids",
    "auto_cluster_ids",
    "labels",
    "reason",
    "action",
    "alias_status",
    "review_reason",
]


def _mention_cluster_maps(
    auto_clusters: list[dict[str, Any]],
    mention_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    mention_to_auto_cluster: dict[str, str] = {}
    mentions_by_auto_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    duplicates: list[dict[str, Any]] = []
    for cluster in auto_clusters:
        auto_cluster_id = str(cluster.get("auto_cluster_id") or "")
        for mention_id in _list(cluster.get("mention_ids")):
            mention_id = str(mention_id)
            mention = mention_by_id.get(mention_id)
            if not mention:
                continue
            if mention_id in mention_to_auto_cluster and mention_to_auto_cluster[mention_id] != auto_cluster_id:
                duplicates.append(
                    {
                        "mention_id": mention_id,
                        "doc_id": str(mention.get("doc_id") or ""),
                        "document_name": str(mention.get("document_name") or ""),
                        "entity_type": str(mention.get("entity_type") or ""),
                    }
                )
                continue
            mention_to_auto_cluster[mention_id] = auto_cluster_id
            mentions_by_auto_cluster[auto_cluster_id].append(mention)
    return mention_to_auto_cluster, mentions_by_auto_cluster, duplicates


def _cluster_review_reasons(component: FinalComponent, clusters_by_id: dict[str, dict[str, Any]]) -> list[str]:
    reasons: set[str] = set()
    for auto_cluster_id in component.auto_cluster_ids:
        cluster = clusters_by_id[auto_cluster_id]
        if bool(cluster.get("review_required")):
            reasons.add("n1_review_required")
        for reason in _list(cluster.get("review_reasons")):
            if str(reason):
                reasons.add(str(reason))
        for flag in _list(cluster.get("risk_flags")):
            if str(flag):
                reasons.add(f"risk:{flag}")
    return sorted(reasons)


def _mention_norm_counts(mentions: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    docs_by_norm: dict[str, set[str]] = defaultdict(set)
    counts: dict[str, int] = defaultdict(int)
    for mention in mentions:
        doc_id = str(mention.get("doc_id") or "")
        for value in _mention_values(mention):
            norm = normalize_basic_text(value)
            if not norm:
                continue
            counts[norm] += 1
            if doc_id:
                docs_by_norm[norm].add(doc_id)
    return {
        norm: {"mention_count": counts[norm], "document_count": len(docs_by_norm[norm])}
        for norm in counts
    }


def _mention_values(mention: dict[str, Any]) -> list[str]:
    raw = mention.get("raw") if isinstance(mention.get("raw"), dict) else {}
    normalized = mention.get("normalized") if isinstance(mention.get("normalized"), dict) else {}
    values = [
        str(raw.get("surface") or ""),
        str(raw.get("canonical_candidate_ru") or ""),
        str(raw.get("canonical_candidate_latin") or ""),
    ]
    for key in ("display_candidate_ru", "display_candidate_latin", "surface_norm", "candidate_ru_norm", "candidate_latin_norm", "primary_norm"):
        values.append(str(normalized.get(key) or ""))
    return values


def _mark_conflicted_tags(canonical_rows: list[dict[str, Any]], alias_conflicts: list[dict[str, Any]]) -> None:
    conflicted_tag_ids = {
        str(tag_id)
        for conflict in alias_conflicts
        for tag_id in _list(conflict.get("tag_ids"))
    }
    for row in canonical_rows:
        if str(row.get("tag_id") or "") not in conflicted_tag_ids:
            continue
        row["need_review"] = True
        row["needs_review"] = True
        row["review_required"] = True
        row["n4_conflict_review"] = True
        reasons = row.get("review_reasons")
        if not isinstance(reasons, list):
            reasons = []
        if "alias_conflict" not in reasons:
            reasons.append("alias_conflict")
        row["review_reasons"] = sorted(set(str(reason) for reason in reasons))


def _aliases_by_tag_id(alias_rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for row in alias_rows:
        if row.get("alias_status") == "blocked_active_substance_candidate":
            continue
        alias = str(row.get("alias") or "")
        if alias:
            result[str(row.get("tag_id") or "")].append(alias)
    return result


def _final_name_rows(canonical_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "tag_id": row["tag_id"],
            "canonical_tag_ru": row["canonical_tag_ru"],
            "canonical_tag_latin": row["canonical_tag_latin"],
            "entity_type": row["entity_type"],
            "need_review": row["need_review"],
        }
        for row in canonical_rows
    ]


def _canonical_review_rows(canonical_rows: list[dict[str, Any]], aliases_by_tag_id: dict[str, list[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in canonical_rows:
        tag_id = str(row.get("tag_id") or "")
        rows.append(
            {
                "tag_id": tag_id,
                "canonical_tag_ru": row.get("canonical_tag_ru"),
                "canonical_tag_latin": row.get("canonical_tag_latin"),
                "entity_type": row.get("entity_type"),
                "aliases": sorted(set(aliases_by_tag_id.get(tag_id, []))),
                "need_review": row.get("need_review"),
                "review_reasons": row.get("review_reasons"),
                "mentions_count": row.get("mentions_count"),
                "documents_count": row.get("documents_count"),
                "auto_cluster_ids": row.get("auto_cluster_ids"),
                "n3_cluster_ids": row.get("n3_cluster_ids"),
            }
        )
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def _count_jsonl(path: Path) -> int:
    with path.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp_path.replace(path)


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    count = 0
    with tmp_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fields})
            count += 1
    tmp_path.replace(path)
    return count


def _csv_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (list, dict, set, tuple)):
        return json.dumps(list(value) if isinstance(value, set) else value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

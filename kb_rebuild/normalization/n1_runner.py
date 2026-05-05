from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kb_rebuild.io.jsonl import write_jsonl
from kb_rebuild.llm.tagging import utc_now
from kb_rebuild.normalization.auto_cluster import build_auto_clusters
from kb_rebuild.normalization.mentions import flatten_mentions, load_tagging_records, normalize_mention
from kb_rebuild.normalization.models import AutoCluster, NormalizedMention
from kb_rebuild.normalization.report import (
    build_auto_cluster_csv_rows,
    build_cluster_duplicate_diagnostics_rows,
    build_report,
    build_singleton_entity_candidate_rows,
    build_tags_raw_rows,
    build_top_aliases_by_type_rows,
    build_top_canonical_candidates_rows,
    build_type_role_stats_rows,
    write_csv,
    write_json,
)
from kb_rebuild.normalization.text import quote_issue_type


@dataclass(frozen=True)
class N1Config:
    data_dir: Path = Path("data")
    tagging_active_path: Path = Path("data/tagging/document_tags_raw_active.jsonl")
    failures_path: Path = Path("data/tagging/document_tagging_failures_active.jsonl")
    empty_candidates_path: Path = Path("data/tagging/empty_documents_name_candidates.jsonl")
    out_dir: Path = Path("data/normalization")
    min_mentions_for_report: int = 1
    overwrite: bool = True

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Path,
        *,
        tagging_active_path: Path | None = None,
        failures_path: Path | None = None,
        empty_candidates_path: Path | None = None,
        out_dir: Path | None = None,
        min_mentions_for_report: int = 1,
        overwrite: bool = True,
    ) -> "N1Config":
        return cls(
            data_dir=data_dir,
            tagging_active_path=tagging_active_path or data_dir / "tagging" / "document_tags_raw_active.jsonl",
            failures_path=failures_path or data_dir / "tagging" / "document_tagging_failures_active.jsonl",
            empty_candidates_path=empty_candidates_path or data_dir / "tagging" / "empty_documents_name_candidates.jsonl",
            out_dir=out_dir or data_dir / "normalization",
            min_mentions_for_report=min_mentions_for_report,
            overwrite=overwrite,
        )


OUTPUT_FILENAMES = {
    "tag_mentions_raw": "tag_mentions_raw.jsonl",
    "tag_mentions_normalized": "tag_mentions_normalized.jsonl",
    "tags_raw_csv": "tags_raw.csv",
    "auto_clusters_jsonl": "auto_clusters.jsonl",
    "auto_clusters_csv": "auto_clusters.csv",
    "normalization_n1_report": "normalization_n1_report.json",
    "normalization_n1_manifest": "normalization_n1_manifest.json",
    "type_role_stats": "type_role_stats.csv",
    "suspicious_mentions": "suspicious_mentions.jsonl",
    "failed_documents_snapshot": "failed_documents_snapshot.jsonl",
    "top_aliases_by_type": "top_aliases_by_type.csv",
    "top_canonical_candidates": "top_canonical_candidates.csv",
    "quote_issue_mentions": "quote_issue_mentions.jsonl",
    "article_candidate_mentions": "article_candidate_mentions.jsonl",
    "context_only_mentions": "context_only_mentions.jsonl",
    "invalid_tagging_records": "invalid_tagging_records.jsonl",
    "risk_mentions": "risk_mentions.jsonl",
    "routing_mentions": "routing_mentions.jsonl",
    "singleton_entity_candidates_csv": "singleton_entity_candidates.csv",
    "singleton_entity_candidates_jsonl": "singleton_entity_candidates.jsonl",
    "cluster_duplicate_diagnostics": "cluster_duplicate_diagnostics.csv",
}


def run_normalization_n1(config: N1Config) -> dict[str, Any]:
    return NormalizationN1Runner(config).run()


class NormalizationN1Runner:
    def __init__(self, config: N1Config) -> None:
        self.config = config
        self.paths = {name: config.out_dir / filename for name, filename in OUTPUT_FILENAMES.items()}

    def run(self) -> dict[str, Any]:
        if not self.config.tagging_active_path.exists():
            raise FileNotFoundError(f"missing tagging active file: {self.config.tagging_active_path}")
        if self.config.min_mentions_for_report < 1:
            raise ValueError("min_mentions_for_report must be >= 1")
        self._check_overwrite()

        created_at = utc_now()
        warnings: list[str] = []
        input_sha_before = _sha256_file(self.config.tagging_active_path)
        source_manifest = self._load_source_manifest(warnings)

        records, invalid_records, load_warnings = load_tagging_records(self.config.tagging_active_path)
        warnings.extend(load_warnings)
        raw_mentions, flatten_invalids, flatten_warnings = flatten_mentions(
            records,
            source_file=self.config.tagging_active_path,
        )
        invalid_records.extend(flatten_invalids)
        warnings.extend(flatten_warnings)

        normalized_mentions = [normalize_mention(mention) for mention in raw_mentions]
        self._validate_mentions(normalized_mentions)
        clusters = build_auto_clusters(normalized_mentions)
        self._validate_clusters(clusters, normalized_mentions)
        singleton_rows = build_singleton_entity_candidate_rows(normalized_mentions, clusters)
        duplicate_diagnostics_rows = build_cluster_duplicate_diagnostics_rows(clusters)

        failed_records, failed_invalids, failed_warnings = self._read_optional_jsonl(
            self.config.failures_path,
            missing_warning=f"{self.config.failures_path}: failures file is missing; failed snapshot will be empty",
        )
        invalid_records.extend(failed_invalids)
        warnings.extend(failed_warnings)
        empty_candidates, empty_invalids, empty_warnings = self._read_optional_jsonl(
            self.config.empty_candidates_path,
            missing_warning=f"{self.config.empty_candidates_path}: empty candidates file is missing",
        )
        invalid_records.extend(empty_invalids)
        warnings.extend(empty_warnings)

        failed_snapshot = _failed_documents_snapshot(failed_records)
        quote_issue_mentions = _quote_issue_records(normalized_mentions)

        self.config.out_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(self.paths["tag_mentions_raw"], (mention.to_dict() for mention in raw_mentions))
        write_jsonl(self.paths["tag_mentions_normalized"], (mention.to_dict() for mention in normalized_mentions))
        write_jsonl(self.paths["auto_clusters_jsonl"], (cluster.to_dict() for cluster in clusters))
        write_jsonl(
            self.paths["suspicious_mentions"],
            (mention.to_dict() for mention in normalized_mentions if mention.suspicious_flags),
        )
        write_jsonl(
            self.paths["risk_mentions"],
            (mention.to_dict() for mention in normalized_mentions if mention.risk_flags),
        )
        write_jsonl(
            self.paths["routing_mentions"],
            (mention.to_dict() for mention in normalized_mentions if mention.routing_flags),
        )
        write_jsonl(self.paths["failed_documents_snapshot"], failed_snapshot)
        write_jsonl(self.paths["quote_issue_mentions"], quote_issue_mentions)
        write_jsonl(
            self.paths["article_candidate_mentions"],
            (mention.to_dict() for mention in normalized_mentions if mention.article_candidate),
        )
        write_jsonl(
            self.paths["context_only_mentions"],
            (mention.to_dict() for mention in normalized_mentions if mention.tag_role == "context_only"),
        )
        write_jsonl(self.paths["invalid_tagging_records"], invalid_records)
        write_jsonl(self.paths["singleton_entity_candidates_jsonl"], singleton_rows)

        write_csv(
            self.paths["tags_raw_csv"],
            [
                "raw_value",
                "normalized_value",
                "entity_type",
                "tag_role",
                "article_candidate",
                "mentions_count",
                "documents_count",
                "avg_confidence",
                "quote_not_found_count",
                "examples",
            ],
            build_tags_raw_rows(normalized_mentions, self.config.min_mentions_for_report),
        )
        write_csv(
            self.paths["auto_clusters_csv"],
            [
                "auto_cluster_id",
                "entity_type",
                "canonical_display_candidate",
                "canonical_latin_candidate",
                "aliases",
                "normalized_aliases",
                "mentions_count",
                "documents_count",
                "article_candidate_count",
                "folder_candidate_count",
                "context_only_count",
                "avg_confidence",
                "quote_not_found_count",
                "cluster_status",
                "merge_allowed",
                "blocking_flags",
                "risk_flags",
                "routing_flags",
                "review_required",
                "review_reasons",
            ],
            build_auto_cluster_csv_rows(clusters),
        )
        write_csv(
            self.paths["type_role_stats"],
            [
                "entity_type",
                "tag_role",
                "article_candidate",
                "mentions_count",
                "documents_count",
                "unique_normalized_count",
            ],
            build_type_role_stats_rows(normalized_mentions),
        )
        write_csv(
            self.paths["top_aliases_by_type"],
            ["entity_type", "raw_value", "normalized_value", "mentions_count", "documents_count"],
            build_top_aliases_by_type_rows(normalized_mentions),
        )
        write_csv(
            self.paths["top_canonical_candidates"],
            ["entity_type", "canonical_candidate_ru", "normalized_value", "mentions_count", "documents_count"],
            build_top_canonical_candidates_rows(normalized_mentions),
        )
        write_csv(
            self.paths["singleton_entity_candidates_csv"],
            [
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
            ],
            singleton_rows,
        )
        write_csv(
            self.paths["cluster_duplicate_diagnostics"],
            [
                "duplicate_key",
                "duplicate_type",
                "rows_count",
                "entity_type",
                "canonical_display_candidates",
                "auto_cluster_ids",
                "reason",
            ],
            duplicate_diagnostics_rows,
        )

        input_sha_after = _sha256_file(self.config.tagging_active_path)
        if input_sha_after != input_sha_before:
            warnings.append(f"{self.config.tagging_active_path}: input SHA changed during normalization")

        report = build_report(
            created_at=created_at,
            input_paths={
                "tagging_active_path": str(self.config.tagging_active_path),
                "failures_path": str(self.config.failures_path),
                "empty_candidates_path": str(self.config.empty_candidates_path),
            },
            mentions=normalized_mentions,
            clusters=clusters,
            failed_documents_count=len(failed_records),
            invalid_records_count=len(invalid_records),
            singleton_rows=singleton_rows,
            duplicate_diagnostics_rows=duplicate_diagnostics_rows,
            warnings=warnings,
            min_mentions_for_report=self.config.min_mentions_for_report,
        )
        write_json(self.paths["normalization_n1_report"], report)
        manifest = self._build_manifest(
            created_at=created_at,
            source_manifest=source_manifest,
            input_sha256=input_sha_after,
            report=report,
            empty_candidates_count=len(empty_candidates),
        )
        write_json(self.paths["normalization_n1_manifest"], manifest)
        return report

    def _check_overwrite(self) -> None:
        if self.config.overwrite:
            return
        existing = [str(path) for path in self.paths.values() if path.exists()]
        if existing:
            raise FileExistsError("--no-overwrite set and output files already exist: " + ", ".join(existing))

    def _load_source_manifest(self, warnings: list[str]) -> dict[str, Any]:
        manifest_path = self.config.data_dir / "tagging" / "tagging_active_manifest.json"
        if not manifest_path.exists():
            warnings.append(f"{manifest_path}: source tagging manifest is missing")
            return {}
        try:
            with manifest_path.open("r", encoding="utf-8") as fh:
                value = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"{manifest_path}: could not read source tagging manifest: {exc}")
            return {}
        return value if isinstance(value, dict) else {}

    def _read_optional_jsonl(
        self,
        path: Path,
        *,
        missing_warning: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        if not path.exists():
            return [], [], [missing_warning]
        records: list[dict[str, Any]] = []
        invalid_records: list[dict[str, Any]] = []
        warnings: list[str] = []
        with path.open("r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    value = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    invalid_records.append(
                        {
                            "source_file": str(path),
                            "line_number": line_number,
                            "reason": "invalid_json",
                            "raw_line": stripped,
                            "error": str(exc),
                        }
                    )
                    continue
                if not isinstance(value, dict):
                    invalid_records.append(
                        {
                            "source_file": str(path),
                            "line_number": line_number,
                            "reason": "record_not_object",
                            "raw_value": value,
                        }
                    )
                    continue
                records.append(value)
        if invalid_records:
            warnings.append(f"{path}: invalid records skipped: {len(invalid_records)}")
        return records, invalid_records, warnings

    def _validate_mentions(self, mentions: list[NormalizedMention]) -> None:
        mention_ids = [mention.mention_id for mention in mentions]
        if len(mention_ids) != len(set(mention_ids)):
            raise ValueError("mention_id values are not unique")

    def _validate_clusters(self, clusters: list[AutoCluster], mentions: list[NormalizedMention]) -> None:
        cluster_ids = [cluster.auto_cluster_id for cluster in clusters]
        if len(cluster_ids) != len(set(cluster_ids)):
            raise ValueError("auto_cluster_id values are not unique")
        mention_ids = {mention.mention_id for mention in mentions}
        for cluster in clusters:
            missing = [mention_id for mention_id in cluster.mention_ids if mention_id not in mention_ids]
            if missing:
                raise ValueError(f"{cluster.auto_cluster_id}: cluster references missing mention ids: {missing}")

    def _build_manifest(
        self,
        *,
        created_at: str,
        source_manifest: dict[str, Any],
        input_sha256: str,
        report: dict[str, Any],
        empty_candidates_count: int,
    ) -> dict[str, Any]:
        outputs = {name: str(path) for name, path in self.paths.items()}
        return {
            "stage": "normalization_n1",
            "stage_version": "n1.1",
            "created_at": created_at,
            "source_tagging_run_id": source_manifest.get("run_id", ""),
            "source_provider": source_manifest.get("provider", ""),
            "source_model": source_manifest.get("model", ""),
            "source_prompt_version": source_manifest.get("prompt_version", ""),
            "source_schema_version": source_manifest.get("schema_version") or source_manifest.get("raw_schema_version", ""),
            "source_tagging_input_sha256": input_sha256,
            "source_documents_tagged": source_manifest.get("documents_tagged"),
            "source_documents_failed": source_manifest.get("documents_failed"),
            "empty_candidates_count": empty_candidates_count,
            "counts": report.get("counts", {}),
            "outputs": outputs,
        }


def _failed_documents_snapshot(failed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for record in failed_records:
        item = dict(record)
        failure_reason = str(item.get("failure_reason") or item.get("reason") or "")
        if failure_reason == "empty_clean_text":
            item["suggested_followup"] = "name_only_recovery_after_normalization"
        snapshot.append(item)
    return snapshot


def _quote_issue_records(mentions: list[NormalizedMention]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for mention in mentions:
        if "quote_not_found" not in mention.suspicious_flags:
            continue
        records.append(
            {
                "mention_id": mention.mention_id,
                "doc_id": mention.doc_id,
                "document_name": mention.document_name,
                "entity_type": mention.entity_type,
                "canonical_candidate_ru": str(mention.raw.get("canonical_candidate_ru", "")),
                "quote_validation_status": mention.quote_validation_status,
                "evidence_quotes": mention.evidence_quotes,
                "issue_type": quote_issue_type(
                    mention.quote_validation_status,
                    mention.quote_validation_details,
                    mention.evidence_quotes,
                ),
            }
        )
    return records


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

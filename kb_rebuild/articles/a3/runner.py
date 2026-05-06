from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from kb_rebuild.articles.a3.coverage import build_tag_outputs, coverage_counts
from kb_rebuild.articles.a3.dedupe import dedupe_evidence
from kb_rebuild.articles.a3.filtering import split_evidence_layers
from kb_rebuild.articles.a3.grouping import build_fact_groups
from kb_rebuild.articles.a3.models import STAGE, STAGE_VERSION, A3Config
from kb_rebuild.articles.a3.report import (
    FACT_GROUP_FIELDS,
    HIGH_VOLUME_FIELDS,
    MANUAL_QA_FIELDS,
    QUOTE_STATUS_ENTITY_FIELDS,
    SUMMARY_FIELDS,
    TAG_COVERAGE_FIELDS,
    build_manifest,
    build_report,
    high_volume_tag_rows,
    manual_qa_rows,
    quote_status_by_entity_type_rows,
    rejected_summary_rows,
    review_summary_rows,
    utc_now,
    write_csv,
    write_json,
)
from kb_rebuild.io.jsonl import read_jsonl, write_jsonl


OUTPUT_FILENAMES = {
    "evidence_items_valid_jsonl": "evidence_items_valid.jsonl",
    "evidence_items_review_jsonl": "evidence_items_review.jsonl",
    "evidence_items_rejected_jsonl": "evidence_items_rejected.jsonl",
    "evidence_deduped_jsonl": "evidence_deduped.jsonl",
    "fact_groups_jsonl": "fact_groups.jsonl",
    "tag_fact_group_index_jsonl": "tag_fact_group_index.jsonl",
    "a4_compilation_input_jsonl": "a4_compilation_input.jsonl",
    "tags_without_usable_evidence_jsonl": "tags_without_usable_evidence.jsonl",
    "tag_evidence_coverage_jsonl": "tag_evidence_coverage.jsonl",
    "fact_groups_csv": "fact_groups.csv",
    "tag_evidence_coverage_csv": "tag_evidence_coverage.csv",
    "rejected_evidence_summary_csv": "rejected_evidence_summary.csv",
    "review_evidence_summary_csv": "review_evidence_summary.csv",
    "a3_report_json": "a3_report.json",
    "a3_manifest_json": "a3_manifest.json",
    "manual_qa_fact_groups_sample_csv": "manual_qa_fact_groups_sample.csv",
    "high_volume_tags_csv": "high_volume_tags.csv",
    "duplicate_evidence_diagnostics_csv": "duplicate_evidence_diagnostics.csv",
    "quote_status_by_entity_type_csv": "quote_status_by_entity_type.csv",
}


def run_article_a3_grouping(config: A3Config) -> dict[str, Any]:
    return ArticleA3Runner(config).run()


class ArticleA3Runner:
    def __init__(self, config: A3Config) -> None:
        self.config = config
        self.inputs = {
            "a2_evidence_items_jsonl": config.a2_dir / "evidence_items.jsonl",
            "a2_task_results_jsonl": config.a2_dir / "evidence_task_results.jsonl",
            "a2_quote_validation_issues_jsonl": config.a2_dir / "quote_validation_issues.jsonl",
            "a2_report_json": config.a2_dir / "a2_report.json",
            "a2_manifest_json": config.a2_dir / "a2_manifest.json",
            "article_status_index_jsonl": config.a1_dir / "article_status_index.jsonl",
            "tag_work_plan_adjusted_jsonl": config.a1_dir / "tag_work_plan_adjusted.jsonl",
            "a1_report_json": config.a1_dir / "a1_report.json",
            "a1_manifest_json": config.a1_dir / "a1_manifest.json",
            "tags_canonical_csv": config.normalization_final_dir / "tags_canonical.csv",
            "tag_aliases_csv": config.normalization_final_dir / "tag_aliases.csv",
        }
        self.outputs = {name: config.out_dir / filename for name, filename in OUTPUT_FILENAMES.items()}

    def run(self) -> dict[str, Any]:
        created_at = utc_now()
        warnings: list[str] = []
        self._validate_inputs()
        self._validate_output_policy()

        a2_report = _read_json(self.inputs["a2_report_json"])
        a1_report = _read_json(self.inputs["a1_report_json"])
        self._validate_reports(a2_report=a2_report, a1_report=a1_report)

        evidence_items = read_jsonl(self.inputs["a2_evidence_items_jsonl"])
        task_results = read_jsonl(self.inputs["a2_task_results_jsonl"])
        status_rows = read_jsonl(self.inputs["article_status_index_jsonl"])
        evidence_items = self._annotate_task_tag_mismatches(evidence_items, task_results)

        valid_evidence, review_evidence, rejected_evidence = split_evidence_layers(
            evidence_items,
            min_confidence=self.config.min_confidence,
        )
        deduped_evidence, duplicate_rows = dedupe_evidence(valid_evidence + review_evidence)
        fact_groups = build_fact_groups(
            deduped_evidence,
            max_quotes_per_fact_group=self.config.max_quotes_per_fact_group,
            max_fact_groups_per_tag=self.config.max_fact_groups_per_tag,
        )
        tag_index, a4_input, tags_without_usable, coverage_rows = build_tag_outputs(
            status_rows=status_rows,
            task_results=task_results,
            valid_evidence=valid_evidence,
            review_evidence=review_evidence,
            rejected_evidence=rejected_evidence,
            fact_groups=fact_groups,
        )
        coverage_summary = coverage_counts(tag_index, task_results)
        report = build_report(
            created_at=created_at,
            config=self.config,
            inputs=self.inputs,
            evidence_items_total=len(evidence_items),
            valid_evidence=valid_evidence,
            review_evidence=review_evidence,
            rejected_evidence=rejected_evidence,
            deduped_evidence=deduped_evidence,
            duplicate_rows=duplicate_rows,
            fact_groups=fact_groups,
            tag_index=tag_index,
            coverage_counts=coverage_summary,
            warnings=warnings,
        )
        manifest = build_manifest(created_at=created_at, config=self.config, inputs=self.inputs, outputs=self.outputs)
        self._write_outputs(
            valid_evidence=valid_evidence,
            review_evidence=review_evidence,
            rejected_evidence=rejected_evidence,
            deduped_evidence=deduped_evidence,
            duplicate_rows=duplicate_rows,
            fact_groups=fact_groups,
            tag_index=tag_index,
            a4_input=a4_input,
            tags_without_usable=tags_without_usable,
            coverage_rows=coverage_rows,
            report=report,
            manifest=manifest,
        )
        if not report.get("quality", {}).get("passed"):
            raise ValueError("A3 quality gate failed; see a3_report.json")
        return report

    def _validate_inputs(self) -> None:
        missing = [str(path) for path in self.inputs.values() if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Missing A3 inputs: {missing}")

    def _validate_output_policy(self) -> None:
        if self.config.overwrite:
            return
        existing = [str(path) for path in self.outputs.values() if path.exists()]
        if existing:
            raise FileExistsError(f"A3 outputs already exist and --no-overwrite was set: {existing[:10]}")

    def _validate_reports(self, *, a2_report: dict[str, Any], a1_report: dict[str, Any]) -> None:
        if a2_report.get("stage") != "article_a2_evidence_extraction":
            raise ValueError("A2 report stage != article_a2_evidence_extraction")
        if not a2_report.get("quality", {}).get("passed"):
            raise ValueError("A2 quality.passed != true")
        counts = a2_report.get("counts", {})
        if int(counts.get("tasks_failed") or 0) > 0:
            raise ValueError("A2 tasks_failed > 0")
        if int(counts.get("evidence_items_total") or 0) <= 0:
            raise ValueError("A2 evidence_items_total = 0")
        quote_not_found_share = float(a2_report.get("quality", {}).get("quote_not_found_share") or 0.0)
        if quote_not_found_share > 0.05:
            raise ValueError("A2 quote_not_found_share > 0.05")
        if not a1_report.get("quality", {}).get("passed"):
            raise ValueError("A1 quality.passed != true")

    def _annotate_task_tag_mismatches(
        self,
        evidence_items: list[dict[str, Any]],
        task_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        task_to_tag = {str(row.get("task_id") or ""): str(row.get("tag_id") or "") for row in task_results if row.get("task_id")}
        annotated: list[dict[str, Any]] = []
        for item in evidence_items:
            row = dict(item)
            expected_tag = task_to_tag.get(str(row.get("task_id") or ""))
            if expected_tag and expected_tag != str(row.get("tag_id") or ""):
                row["a3_pre_filter_reasons"] = ["task_id_tag_id_mismatch"]
            annotated.append(row)
        return annotated

    def _write_outputs(
        self,
        *,
        valid_evidence: list[dict[str, Any]],
        review_evidence: list[dict[str, Any]],
        rejected_evidence: list[dict[str, Any]],
        deduped_evidence: list[dict[str, Any]],
        duplicate_rows: list[dict[str, Any]],
        fact_groups: list[dict[str, Any]],
        tag_index: list[dict[str, Any]],
        a4_input: list[dict[str, Any]],
        tags_without_usable: list[dict[str, Any]],
        coverage_rows: list[dict[str, Any]],
        report: dict[str, Any],
        manifest: dict[str, Any],
    ) -> None:
        self.config.out_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(self.outputs["evidence_items_valid_jsonl"], valid_evidence)
        write_jsonl(self.outputs["evidence_items_review_jsonl"], review_evidence)
        write_jsonl(self.outputs["evidence_items_rejected_jsonl"], rejected_evidence)
        write_jsonl(self.outputs["evidence_deduped_jsonl"], deduped_evidence)
        write_jsonl(self.outputs["fact_groups_jsonl"], fact_groups)
        write_jsonl(self.outputs["tag_fact_group_index_jsonl"], tag_index)
        write_jsonl(self.outputs["a4_compilation_input_jsonl"], a4_input)
        write_jsonl(self.outputs["tags_without_usable_evidence_jsonl"], tags_without_usable)
        write_jsonl(self.outputs["tag_evidence_coverage_jsonl"], coverage_rows)
        write_csv(self.outputs["fact_groups_csv"], FACT_GROUP_FIELDS, fact_groups)
        write_csv(self.outputs["tag_evidence_coverage_csv"], TAG_COVERAGE_FIELDS, coverage_rows)
        write_csv(self.outputs["rejected_evidence_summary_csv"], SUMMARY_FIELDS, rejected_summary_rows(rejected_evidence))
        write_csv(self.outputs["review_evidence_summary_csv"], SUMMARY_FIELDS, review_summary_rows(review_evidence))
        write_csv(self.outputs["duplicate_evidence_diagnostics_csv"], list(_duplicate_fields()), duplicate_rows)
        write_csv(
            self.outputs["quote_status_by_entity_type_csv"],
            QUOTE_STATUS_ENTITY_FIELDS,
            quote_status_by_entity_type_rows(valid_evidence + review_evidence + rejected_evidence),
        )
        write_csv(self.outputs["high_volume_tags_csv"], HIGH_VOLUME_FIELDS, high_volume_tag_rows(tag_index))
        write_csv(self.outputs["manual_qa_fact_groups_sample_csv"], MANUAL_QA_FIELDS, manual_qa_rows(fact_groups, tags_without_usable))
        write_json(self.outputs["a3_report_json"], report)
        write_json(self.outputs["a3_manifest_json"], manifest)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _duplicate_fields() -> tuple[str, ...]:
    return (
        "duplicate_evidence_item_id",
        "kept_evidence_item_id",
        "tag_id",
        "fact_type",
        "doc_id",
        "window_id",
        "normalized_claim",
        "normalized_quote",
    )


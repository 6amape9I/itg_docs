from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from kb_rebuild.articles.a1.direct_copy import validate_direct_copy
from kb_rebuild.articles.a1.entity_json import (
    article_status_for_strategy,
    build_entity_json,
    direct_copy_entity_json,
    entity_file_path,
    write_entity_json,
)
from kb_rebuild.articles.a1.models import A1Config, ARTICLE_STATUSES
from kb_rebuild.articles.a1.report import (
    A2_TASK_QUEUE_FIELDS,
    ARTICLE_STATUS_INDEX_FIELDS,
    DIRECT_COPY_VALIDATION_FIELDS,
    MISSING_TAGS_FIELDS,
    TAG_WORK_PLAN_ADJUSTED_FIELDS,
    build_a1_report,
    build_manifest,
    utc_now,
    write_csv,
    write_json,
)
from kb_rebuild.articles.a1.strategy_repair import repair_work_plan
from kb_rebuild.articles.a1.task_queue import build_tasks_for_plan
from kb_rebuild.articles.planning.loaders import bool_value, list_value, read_csv_dicts
from kb_rebuild.io.jsonl import read_jsonl, write_jsonl


OUTPUT_FILENAMES = {
    "tag_work_plan_adjusted_jsonl": "tag_work_plan_adjusted.jsonl",
    "tag_work_plan_adjusted_csv": "tag_work_plan_adjusted.csv",
    "a0_1_strategy_adjustments_jsonl": "a0_1_strategy_adjustments.jsonl",
    "a0_1_strategy_adjustment_report_json": "a0_1_strategy_adjustment_report.json",
    "article_status_index_jsonl": "article_status_index.jsonl",
    "article_status_index_csv": "article_status_index.csv",
    "direct_copy_articles_jsonl": "direct_copy_articles.jsonl",
    "stub_articles_jsonl": "stub_articles.jsonl",
    "review_stub_articles_jsonl": "review_stub_articles.jsonl",
    "pending_extraction_articles_jsonl": "pending_extraction_articles.jsonl",
    "a2_extraction_task_queue_jsonl": "a2_extraction_task_queue.jsonl",
    "a2_extraction_task_queue_csv": "a2_extraction_task_queue.csv",
    "a1_report_json": "a1_report.json",
    "a1_manifest_json": "a1_manifest.json",
    "direct_copy_rejected_jsonl": "direct_copy_rejected.jsonl",
    "direct_copy_validation_report_csv": "direct_copy_validation_report.csv",
    "publication_review_queue_jsonl": "publication_review_queue.jsonl",
    "hard_review_queue_jsonl": "hard_review_queue.jsonl",
    "article_file_coverage_audit_json": "article_file_coverage_audit.json",
    "article_file_coverage_missing_tags_csv": "article_file_coverage_missing_tags.csv",
}


def run_article_a1_bootstrap(config: A1Config) -> dict[str, Any]:
    return ArticleA1Runner(config).run()


class ArticleA1Runner:
    def __init__(self, config: A1Config) -> None:
        self.config = config
        self.outputs = {name: config.out_dir / filename for name, filename in OUTPUT_FILENAMES.items()}
        self.inputs = {
            "tag_source_index_jsonl": config.articles_planning_dir / "tag_source_index.jsonl",
            "tag_work_plan_jsonl": config.articles_planning_dir / "tag_work_plan.jsonl",
            "source_block_windows_jsonl": config.articles_planning_dir / "source_block_windows.jsonl",
            "direct_copy_candidates_jsonl": config.articles_planning_dir / "direct_copy_candidates.jsonl",
            "singleton_candidates_jsonl": config.articles_planning_dir / "singleton_candidates.jsonl",
            "article_planning_report_json": config.articles_planning_dir / "article_planning_report.json",
            "article_planning_manifest_json": config.articles_planning_dir / "article_planning_manifest.json",
            "tags_canonical_csv": config.normalization_final_dir / "tags_canonical.csv",
            "tag_aliases_csv": config.normalization_final_dir / "tag_aliases.csv",
            "document_tag_links_normalized_jsonl": config.normalization_final_dir / "document_tag_links_normalized.jsonl",
            "document_tags_normalized_by_doc_jsonl": config.normalization_final_dir / "document_tags_normalized_by_doc.jsonl",
            "final_normalization_report_json": config.normalization_final_dir / "final_normalization_report.json",
            "final_normalization_manifest_json": config.normalization_final_dir / "final_normalization_manifest.json",
            "parsed_documents_jsonl": config.parsed_dir / "parsed_documents.jsonl",
            "document_blocks_jsonl": config.parsed_dir / "document_blocks.jsonl",
        }

    def run(self) -> dict[str, Any]:
        created_at = utc_now()
        self._validate_config()
        self._validate_outputs()
        self._validate_inputs()

        final_tags = read_csv_dicts(self.inputs["tags_canonical_csv"])
        final_tag_ids = {str(row.get("tag_id") or "") for row in final_tags}
        work_plan = read_jsonl(self.inputs["tag_work_plan_jsonl"])
        windows = read_jsonl(self.inputs["source_block_windows_jsonl"])
        docs = read_jsonl(self.inputs["parsed_documents_jsonl"])
        blocks = read_jsonl(self.inputs["document_blocks_jsonl"])

        windows_by_id = {str(window.get("window_id") or ""): window for window in windows}
        docs_by_id = {str(doc.get("doc_id") or ""): doc for doc in docs}
        blocks_by_doc = _blocks_by_doc(blocks)

        adjusted_plan, adjustments, strategy_report = repair_work_plan(work_plan, windows_by_id, self.config)

        status_rows: list[dict[str, Any]] = []
        direct_copy_articles: list[dict[str, Any]] = []
        direct_copy_rejected: list[dict[str, Any]] = []
        direct_copy_validation_rows: list[dict[str, Any]] = []
        stub_articles: list[dict[str, Any]] = []
        review_stub_articles: list[dict[str, Any]] = []
        pending_extraction_articles: list[dict[str, Any]] = []
        publication_review_queue: list[dict[str, Any]] = []
        hard_review_queue: list[dict[str, Any]] = []
        tasks: list[dict[str, Any]] = []
        next_task_number = 1

        for plan in adjusted_plan:
            entity_path = entity_file_path(self.config.entities_out_dir, plan)
            direct_copy_accepted = False
            direct_copy_rejection = False
            validation = None
            if str(plan.get("strategy") or "") == "direct_copy_candidate":
                validation = validate_direct_copy(plan, windows_by_id=windows_by_id, docs_by_id=docs_by_id, blocks_by_doc=blocks_by_doc)
                direct_copy_accepted = validation.accepted
                direct_copy_rejection = not validation.accepted

            article_status, source_strategy = article_status_for_strategy(
                plan,
                direct_copy_accepted=direct_copy_accepted,
                direct_copy_rejected=direct_copy_rejection,
            )
            if article_status not in ARTICLE_STATUSES:
                article_status = "failed_or_blocked"

            if validation is not None:
                validation_row = _direct_copy_validation_row(plan, validation, article_status)
                direct_copy_validation_rows.append(validation_row)
                if validation.accepted:
                    entity = direct_copy_entity_json(plan=plan, entity_path=entity_path, source_blocks=validation.source_blocks)
                else:
                    reject_row = _direct_copy_rejected_row(plan, validation, article_status, entity_path)
                    direct_copy_rejected.append(reject_row)
                    entity = build_entity_json(plan=plan, article_status=article_status, source_strategy=source_strategy, entity_path=entity_path)
            else:
                entity = build_entity_json(plan=plan, article_status=article_status, source_strategy=source_strategy, entity_path=entity_path)

            plan_tasks, next_task_number = build_tasks_for_plan(
                plan=plan,
                source_strategy=source_strategy,
                article_status=article_status,
                windows_by_id=windows_by_id,
                next_task_number=next_task_number,
            )
            tasks.extend(plan_tasks)
            write_entity_json(entity_path, entity)
            status_row = _status_row(plan, article_status, source_strategy, entity_path, len(plan_tasks))
            status_rows.append(status_row)

            if article_status == "direct_copy_article":
                direct_copy_articles.append(status_row)
            elif article_status == "stub_only":
                stub_articles.append(status_row)
            elif article_status == "review_stub":
                review_stub_articles.append(status_row)
            elif article_status.startswith("pending_"):
                pending_extraction_articles.append(status_row)
            if bool_value(plan.get("needs_review_before_publication")) and not list_value(plan.get("article_blocking_review_reasons")):
                publication_review_queue.append(status_row)
            if list_value(plan.get("article_blocking_review_reasons")) or (
                article_status == "review_stub" and bool_value(plan.get("needs_review_before_article"))
            ):
                hard_review_queue.append(status_row)

        coverage_audit, missing_tags = _coverage_audit(final_tags, final_tag_ids, status_rows)
        report = build_a1_report(
            created_at=created_at,
            final_tags_total=len(final_tags),
            status_rows=status_rows,
            tasks=tasks,
            direct_copy_rejected=direct_copy_rejected,
            strategy_adjustment_report=strategy_report,
            publication_review_queue=publication_review_queue,
            hard_review_queue=hard_review_queue,
            coverage_audit=coverage_audit,
            warnings=[],
        )
        manifest = build_manifest(created_at=created_at, config=self.config, inputs=self.inputs, outputs=self.outputs)
        self._write_outputs(
            adjusted_plan=adjusted_plan,
            adjustments=adjustments,
            strategy_report=strategy_report,
            status_rows=status_rows,
            direct_copy_articles=direct_copy_articles,
            stub_articles=stub_articles,
            review_stub_articles=review_stub_articles,
            pending_extraction_articles=pending_extraction_articles,
            tasks=tasks,
            direct_copy_rejected=direct_copy_rejected,
            direct_copy_validation_rows=direct_copy_validation_rows,
            publication_review_queue=publication_review_queue,
            hard_review_queue=hard_review_queue,
            coverage_audit=coverage_audit,
            missing_tags=missing_tags,
            report=report,
            manifest=manifest,
        )
        if not bool(report.get("quality", {}).get("passed")):
            raise ValueError("A1 quality gates failed")
        return report

    def _validate_config(self) -> None:
        if self.config.review_sample_size < 0:
            raise ValueError("review_sample_size must be >= 0")
        if self.config.low_count_doc_threshold < 1:
            raise ValueError("low_count_doc_threshold must be >= 1")
        if self.config.high_frequency_doc_threshold <= self.config.low_count_doc_threshold:
            raise ValueError("high_frequency_doc_threshold must be > low_count_doc_threshold")

    def _validate_outputs(self) -> None:
        if self.config.overwrite:
            return
        existing = [path for path in self.outputs.values() if path.exists()]
        if existing:
            raise FileExistsError(f"A1 output exists and --no-overwrite was set: {existing[0]}")
        if self.config.entities_out_dir.exists() and any(self.config.entities_out_dir.rglob("*.json")):
            raise FileExistsError(f"A1 entity output exists and --no-overwrite was set: {self.config.entities_out_dir}")

    def _validate_inputs(self) -> None:
        required = (
            "tag_source_index_jsonl",
            "tag_work_plan_jsonl",
            "source_block_windows_jsonl",
            "direct_copy_candidates_jsonl",
            "singleton_candidates_jsonl",
            "article_planning_report_json",
            "article_planning_manifest_json",
            "tags_canonical_csv",
            "tag_aliases_csv",
            "document_tag_links_normalized_jsonl",
            "document_tags_normalized_by_doc_jsonl",
            "final_normalization_report_json",
            "final_normalization_manifest_json",
            "parsed_documents_jsonl",
            "document_blocks_jsonl",
        )
        for name in required:
            path = self.inputs[name]
            if not path.exists():
                raise FileNotFoundError(f"missing A1 input {name}: {path}")
        final_report = _read_json(self.inputs["final_normalization_report_json"])
        if not bool(final_report.get("quality", {}).get("passed")):
            raise ValueError("A1 refuses to run unless final_normalization_report.quality.passed=true")
        a0_report = _read_json(self.inputs["article_planning_report_json"])
        if a0_report.get("stage") != "article_planning_a0":
            raise ValueError("A1 requires article_planning_report.json stage=article_planning_a0")

    def _write_outputs(
        self,
        *,
        adjusted_plan: list[dict[str, Any]],
        adjustments: list[dict[str, Any]],
        strategy_report: dict[str, Any],
        status_rows: list[dict[str, Any]],
        direct_copy_articles: list[dict[str, Any]],
        stub_articles: list[dict[str, Any]],
        review_stub_articles: list[dict[str, Any]],
        pending_extraction_articles: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        direct_copy_rejected: list[dict[str, Any]],
        direct_copy_validation_rows: list[dict[str, Any]],
        publication_review_queue: list[dict[str, Any]],
        hard_review_queue: list[dict[str, Any]],
        coverage_audit: dict[str, Any],
        missing_tags: list[dict[str, Any]],
        report: dict[str, Any],
        manifest: dict[str, Any],
    ) -> None:
        write_jsonl(self.outputs["tag_work_plan_adjusted_jsonl"], adjusted_plan)
        write_csv(self.outputs["tag_work_plan_adjusted_csv"], TAG_WORK_PLAN_ADJUSTED_FIELDS, adjusted_plan)
        write_jsonl(self.outputs["a0_1_strategy_adjustments_jsonl"], adjustments)
        write_json(self.outputs["a0_1_strategy_adjustment_report_json"], strategy_report)
        write_jsonl(self.outputs["article_status_index_jsonl"], status_rows)
        write_csv(self.outputs["article_status_index_csv"], ARTICLE_STATUS_INDEX_FIELDS, status_rows)
        write_jsonl(self.outputs["direct_copy_articles_jsonl"], direct_copy_articles)
        write_jsonl(self.outputs["stub_articles_jsonl"], stub_articles)
        write_jsonl(self.outputs["review_stub_articles_jsonl"], review_stub_articles)
        write_jsonl(self.outputs["pending_extraction_articles_jsonl"], pending_extraction_articles)
        write_jsonl(self.outputs["a2_extraction_task_queue_jsonl"], tasks)
        write_csv(self.outputs["a2_extraction_task_queue_csv"], A2_TASK_QUEUE_FIELDS, tasks)
        write_json(self.outputs["a1_report_json"], report)
        write_json(self.outputs["a1_manifest_json"], manifest)
        write_jsonl(self.outputs["direct_copy_rejected_jsonl"], direct_copy_rejected)
        write_csv(self.outputs["direct_copy_validation_report_csv"], DIRECT_COPY_VALIDATION_FIELDS, direct_copy_validation_rows)
        write_jsonl(self.outputs["publication_review_queue_jsonl"], publication_review_queue)
        write_jsonl(self.outputs["hard_review_queue_jsonl"], hard_review_queue)
        write_json(self.outputs["article_file_coverage_audit_json"], coverage_audit)
        write_csv(self.outputs["article_file_coverage_missing_tags_csv"], MISSING_TAGS_FIELDS, missing_tags)


def _blocks_by_doc(blocks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for block in blocks:
        grouped[str(block.get("doc_id") or "")].append(block)
    return {doc_id: sorted(items, key=lambda item: int(item.get("block_index") or 0)) for doc_id, items in grouped.items()}


def _status_row(
    plan: dict[str, Any],
    article_status: str,
    source_strategy: str,
    entity_path: Path,
    tasks_count: int,
) -> dict[str, Any]:
    return {
        "tag_id": str(plan.get("tag_id") or ""),
        "canonical_tag_ru": str(plan.get("canonical_tag_ru") or ""),
        "canonical_tag_latin": _nullable_string(plan.get("canonical_tag_latin")),
        "entity_type": str(plan.get("entity_type") or ""),
        "article_status": article_status,
        "source_strategy_original": str(plan.get("source_strategy_original") or plan.get("strategy") or ""),
        "source_strategy_adjusted": source_strategy,
        "strategy_adjusted": bool_value(plan.get("strategy_adjusted")),
        "article_file_path": str(entity_path),
        "article_candidate": bool_value(plan.get("article_candidate")),
        "mentions_count": int(plan.get("mentions_count") or 0),
        "documents_count": int(plan.get("documents_count") or 0),
        "source_windows_count": int(plan.get("source_windows_count") or 0),
        "a2_extraction_tasks_count": tasks_count,
        "needs_review_before_article": bool_value(plan.get("needs_review_before_article")),
        "needs_review_before_publication": bool_value(plan.get("needs_review_before_publication")),
        "review_reasons": [str(item) for item in list_value(plan.get("review_reasons"))],
        "publication_review_reasons": [str(item) for item in list_value(plan.get("publication_review_reasons"))],
        "article_blocking_review_reasons": [str(item) for item in list_value(plan.get("article_blocking_review_reasons"))],
    }


def _direct_copy_validation_row(plan: dict[str, Any], validation: Any, article_status: str) -> dict[str, Any]:
    best = validation.best_window or {}
    return {
        "tag_id": str(plan.get("tag_id") or ""),
        "canonical_tag_ru": str(plan.get("canonical_tag_ru") or ""),
        "accepted": validation.accepted,
        "rejection_reasons": validation.rejection_reasons,
        "best_window_id": str(best.get("window_id") or ""),
        "best_window_quality": str(best.get("window_quality") or ""),
        "best_window_coverage_ratio_estimate": best.get("coverage_ratio_estimate", ""),
        "article_status": article_status,
    }


def _direct_copy_rejected_row(plan: dict[str, Any], validation: Any, article_status: str, entity_path: Path) -> dict[str, Any]:
    row = _direct_copy_validation_row(plan, validation, article_status)
    row["article_file_path"] = str(entity_path)
    row["fallback_source_strategy"] = "single_doc_extract"
    return row


def _coverage_audit(
    final_tags: list[dict[str, Any]],
    final_tag_ids: set[str],
    status_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    status_by_tag = {str(row.get("tag_id") or ""): row for row in status_rows}
    missing: list[dict[str, Any]] = []
    for tag in final_tags:
        tag_id = str(tag.get("tag_id") or "")
        row = status_by_tag.get(tag_id)
        if row is None:
            missing.append(
                {
                    "tag_id": tag_id,
                    "canonical_tag_ru": str(tag.get("canonical_tag_ru") or ""),
                    "entity_type": str(tag.get("entity_type") or ""),
                    "reason": "missing_status_index_row",
                }
            )
            continue
        path = Path(str(row.get("article_file_path") or ""))
        if not path.exists():
            missing.append(
                {
                    "tag_id": tag_id,
                    "canonical_tag_ru": str(tag.get("canonical_tag_ru") or ""),
                    "entity_type": str(tag.get("entity_type") or ""),
                    "reason": "missing_entity_json_file",
                }
            )
    status_index_missing = len(final_tag_ids - set(status_by_tag))
    missing_files = sum(1 for row in missing if row.get("reason") == "missing_entity_json_file")
    audit = {
        "final_tags_total": len(final_tags),
        "entity_json_files_created": len(status_rows) - missing_files,
        "missing_entity_json_files": missing_files,
        "article_status_index_rows": len(status_rows),
        "status_index_missing_tags": status_index_missing,
        "passed": bool(missing_files == 0 and status_index_missing == 0 and len(status_rows) == len(final_tags)),
    }
    return audit, missing


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _nullable_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None

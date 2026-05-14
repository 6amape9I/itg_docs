from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from kb_rebuild.articles.a5.editorjs import content_blocks_count, content_excerpt, safe_review_stub_content, validate_editorjs_content
from kb_rebuild.articles.a5.exporter import json_file_is_valid, prepare_output_dir, unique_export_filename_base, write_article_exports
from kb_rebuild.articles.a5.loaders import (
    assert_report_passed,
    load_canonical_rows,
    load_jsonl_by_key,
    read_json,
    read_optional_json,
    require_paths,
)
from kb_rebuild.articles.a5.models import STAGE, STAGE_VERSION, A5Config
from kb_rebuild.articles.a5.quotes import build_companion_quotes
from kb_rebuild.articles.a5.report import (
    ARTICLE_EXPORT_INDEX_FIELDS,
    DUPLICATE_FILENAME_FIELDS,
    ENTITY_TYPE_DISTRIBUTION_FIELDS,
    MANUAL_QA_FIELDS,
    MISSING_TAG_FIELDS,
    QUOTES_INDEX_FIELDS,
    STATUS_DISTRIBUTION_FIELDS,
    build_coverage_audit,
    build_manifest,
    build_report,
    entity_type_distribution_rows,
    manual_qa_rows,
    status_distribution_rows,
    utc_now,
    write_csv,
    write_json,
)
from kb_rebuild.articles.a5.source_selection import select_article_source
from kb_rebuild.io.jsonl import read_jsonl, write_jsonl


OUTPUT_FILENAMES = {
    "for_n8n_dir": "for_n8n",
    "for_docs_dir": "for_docs",
    "article_export_index_jsonl": "article_export_index.jsonl",
    "article_export_index_csv": "article_export_index.csv",
    "export_coverage_audit_json": "export_coverage_audit.json",
    "export_missing_tags_csv": "export_missing_tags.csv",
    "export_duplicate_filenames_csv": "export_duplicate_filenames.csv",
    "export_quality_issues_jsonl": "export_quality_issues.jsonl",
    "quotes_index_jsonl": "quotes_index.jsonl",
    "quotes_index_csv": "quotes_index.csv",
    "a5_report_json": "a5_report.json",
    "a5_manifest_json": "a5_manifest.json",
    "manual_qa_export_sample_csv": "manual_qa_export_sample.csv",
    "status_distribution_csv": "status_distribution.csv",
    "entity_type_distribution_csv": "entity_type_distribution.csv",
}


def run_article_a5_export(config: A5Config) -> dict[str, Any]:
    return ArticleA5Runner(config).run()


class ArticleA5Runner:
    def __init__(self, config: A5Config) -> None:
        self.config = config
        self.outputs = {name: config.out_dir / filename for name, filename in OUTPUT_FILENAMES.items()}
        self.inputs = {
            "article_status_index_jsonl": config.a1_dir / "article_status_index.jsonl",
            "a1_report_json": config.a1_dir / "a1_report.json",
            "a1_manifest_json": config.a1_dir / "a1_manifest.json",
            "a4_compilation_input_jsonl": config.a3_dir / "a4_compilation_input.jsonl",
            "fact_groups_jsonl": config.a3_dir / "fact_groups.jsonl",
            "tag_fact_group_index_jsonl": config.a3_dir / "tag_fact_group_index.jsonl",
            "a3_report_json": config.a3_dir / "a3_report.json",
            "a3_manifest_json": config.a3_dir / "a3_manifest.json",
            "article_drafts_jsonl": config.a4_dir / "article_drafts.jsonl",
            "a4_report_json": config.a4_dir / "a4_report.json",
            "a4_manifest_json": config.a4_dir / "a4_manifest.json",
            "article_quality_diagnostics_json": config.a4_dir / "article_quality_diagnostics.json",
            "tags_canonical_csv": config.normalization_final_dir / "tags_canonical.csv",
            "tag_aliases_csv": config.normalization_final_dir / "tag_aliases.csv",
            "final_normalization_report_json": config.normalization_final_dir / "final_normalization_report.json",
            "final_normalization_manifest_json": config.normalization_final_dir / "final_normalization_manifest.json",
            "entities_dir": config.entities_dir,
        }

    def run(self) -> dict[str, Any]:
        created_at = utc_now()
        warnings: list[str] = []
        self._validate_inputs()
        status_rows = read_jsonl(self.inputs["article_status_index_jsonl"])
        a3_inputs_by_tag = load_jsonl_by_key(self.inputs["a4_compilation_input_jsonl"], "tag_id")
        a4_drafts_by_tag = load_jsonl_by_key(self.inputs["article_drafts_jsonl"], "tag_id")
        fact_groups_by_id = load_jsonl_by_key(self.inputs["fact_groups_jsonl"], "fact_group_id")
        canonical_rows = load_canonical_rows(self.inputs["tags_canonical_csv"])
        self._validate_consistency(status_rows=status_rows, a4_drafts_by_tag=a4_drafts_by_tag, canonical_rows=canonical_rows)

        known_output_files = [path for name, path in self.outputs.items() if name not in {"for_n8n_dir", "for_docs_dir"}]
        prepare_output_dir(self.config.out_dir, overwrite=self.config.overwrite, known_files=known_output_files)

        export_rows: list[dict[str, Any]] = []
        quotes_rows: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        missing_rows: list[dict[str, Any]] = []
        duplicate_rows: list[dict[str, Any]] = []
        seen_paths: dict[str, list[str]] = {}
        used_filename_bases: set[str] = set()

        for status_row in status_rows:
            entity_path = self._entity_path(status_row)
            entity_article = read_optional_json(entity_path) if entity_path and entity_path.exists() else None
            selected = select_article_source(
                status_row,
                a4_draft=a4_drafts_by_tag.get(str(status_row.get("tag_id") or "")),
                a3_input=a3_inputs_by_tag.get(str(status_row.get("tag_id") or "")),
                entity_article=entity_article,
                entity_path=entity_path,
            )
            article, article_issues = self._build_article(selected=selected, created_at=created_at)
            issues.extend(article_issues)
            entity_type = str(article.get("entity_type") or "unknown")
            tag_id = str(article.get("tag_id") or "")
            filename_base = unique_export_filename_base(article, used_filename_bases)
            n8n_path = self.outputs["for_n8n_dir"] / f"{filename_base}.json"
            docs_path = self.outputs["for_docs_dir"] / entity_type / f"{filename_base}.json"
            quotes_path = self.outputs["for_docs_dir"] / entity_type / f"{filename_base}_quotes.json"
            self._track_duplicate_path(seen_paths, duplicate_rows, n8n_path, tag_id, "for_n8n")
            self._track_duplicate_path(seen_paths, duplicate_rows, docs_path, tag_id, "for_docs")
            self._track_duplicate_path(seen_paths, duplicate_rows, quotes_path, tag_id, "for_docs_quotes")
            article["export"] = {
                "stage": STAGE,
                "exported_at": created_at,
                "for_n8n_path": str(n8n_path),
                "for_docs_path": str(docs_path),
                "for_docs_quotes_path": str(quotes_path),
            }
            companion = build_companion_quotes(
                article,
                fact_groups_by_id=fact_groups_by_id,
                source_fact_groups_path=str(self.inputs["fact_groups_jsonl"]),
                source_article_path=str(docs_path),
            )
            write_article_exports(article, companion, n8n_path=n8n_path, docs_path=docs_path, quotes_path=quotes_path)
            if article["article_status"] == "missing_article_source":
                missing_rows.append(
                    {
                        "tag_id": tag_id,
                        "canonical_tag_ru": article.get("canonical_tag_ru") or "",
                        "entity_type": entity_type,
                        "reason": "missing_article_source",
                    }
                )
            export_rows.append(self._export_index_row(article, companion))
            quotes_rows.append(self._quotes_index_row(article, companion, quotes_path))

        counts, quality = self._coverage(status_rows=status_rows, export_rows=export_rows, quotes_rows=quotes_rows, issues=issues, missing_rows=missing_rows, duplicate_rows=duplicate_rows)
        coverage_audit = build_coverage_audit(counts=counts, quality=quality)
        report = build_report(
            created_at=created_at,
            config=self.config,
            inputs=self.inputs,
            outputs=self.outputs,
            counts=counts,
            quality=quality,
            export_rows=export_rows,
            issues=issues,
            warnings=warnings,
        )
        manifest = build_manifest(created_at=created_at, config=self.config, inputs=self.inputs, outputs=self.outputs)
        self._write_indexes_and_reports(
            export_rows=export_rows,
            quotes_rows=quotes_rows,
            missing_rows=missing_rows,
            duplicate_rows=duplicate_rows,
            issues=issues,
            coverage_audit=coverage_audit,
            report=report,
            manifest=manifest,
        )
        return report

    def _validate_inputs(self) -> None:
        require_paths(self.inputs)
        a1_report = read_json(self.inputs["a1_report_json"])
        a3_report = read_json(self.inputs["a3_report_json"])
        a4_report = read_json(self.inputs["a4_report_json"])
        final_report = read_json(self.inputs["final_normalization_report_json"])
        assert_report_passed(a1_report, name="A1")
        assert_report_passed(a3_report, name="A3")
        assert_report_passed(a4_report, name="A4")
        assert_report_passed(final_report, name="normalization final")
        a4_counts = a4_report.get("counts") if isinstance(a4_report.get("counts"), dict) else {}
        if int(a4_counts.get("tasks_failed", 0) or 0) > 0:
            raise ValueError("A4 has failed tasks; A5 export refused")
        if int(a4_counts.get("article_quality_issues", 0) or 0) > 0:
            raise ValueError("A4 has article quality issues; A5 export refused")
        if not self.config.entities_dir.exists() or not self.config.entities_dir.is_dir():
            raise ValueError(f"A1 entities dir missing: {self.config.entities_dir}")

    def _validate_consistency(
        self,
        *,
        status_rows: list[dict[str, Any]],
        a4_drafts_by_tag: dict[str, dict[str, Any]],
        canonical_rows: list[dict[str, Any]],
    ) -> None:
        a1_report = read_json(self.inputs["a1_report_json"])
        a4_report = read_json(self.inputs["a4_report_json"])
        final_tags_total = int((a1_report.get("counts") or {}).get("final_tags_total", 0) or 0)
        if final_tags_total != len(status_rows):
            raise ValueError(f"A1 final_tags_total={final_tags_total} does not match article_status_index rows={len(status_rows)}")
        article_drafts_total = int((a4_report.get("counts") or {}).get("article_drafts_total", 0) or 0)
        if article_drafts_total != len(a4_drafts_by_tag):
            raise ValueError(f"A4 article_drafts_total={article_drafts_total} does not match unique article_drafts rows={len(a4_drafts_by_tag)}")
        canonical_tag_ids = {str(row.get("tag_id") or "").strip() for row in canonical_rows if str(row.get("tag_id") or "").strip()}
        status_tag_ids = {str(row.get("tag_id") or "").strip() for row in status_rows if str(row.get("tag_id") or "").strip()}
        if len(status_tag_ids) != len(status_rows):
            raise ValueError("A1 article_status_index contains missing or duplicate tag_id")
        if canonical_tag_ids and canonical_tag_ids != status_tag_ids:
            raise ValueError("N4 tags_canonical.csv tag_id set does not match A1 article_status_index")

    def _build_article(self, *, selected: dict[str, Any], created_at: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        issues: list[dict[str, Any]] = []
        tag_id = str(selected.get("tag_id") or "")
        canonical = str(selected.get("canonical_tag_ru") or selected.get("canonical_tag_latin") or tag_id)
        status = str(selected.get("article_status") or "missing_article_source")
        needs_review = bool(selected.get("needs_review_before_publication"))
        review_reasons = _unique_strings(_string_list(selected.get("review_reasons")))

        if selected.get("selection_issue") == "missing_article_source":
            content = safe_review_stub_content(canonical)
            issues.append(_issue(selected, "missing_article_source", "error", "No A4 draft or A1 entity article source found"))
        else:
            content, errors = validate_editorjs_content(selected.get("content"))
            if errors:
                status = "export_repair_stub"
                needs_review = True
                review_reasons = _unique_strings(review_reasons + ["malformed_source_editorjs"])
                content = safe_review_stub_content(canonical)
                issues.append(_issue(selected, "malformed_source_editorjs", "error", "; ".join(errors[:10])))

        source_doc_ids = _unique_strings(_string_list(selected.get("source_doc_ids")))
        source_documents_count = int(selected.get("source_documents_count") or len(source_doc_ids))
        fact_group_ids = _unique_strings(_string_list(selected.get("fact_group_ids")))
        used_fact_group_ids = _unique_strings(_string_list(selected.get("used_fact_group_ids")))
        article = {
            "tag_id": tag_id,
            "canonical_tag_ru": canonical,
            "canonical_tag_latin": selected.get("canonical_tag_latin"),
            "entity_type": str(selected.get("entity_type") or "unknown"),
            "article_status": status,
            "source_article_status": str(selected.get("source_article_status") or ""),
            "source_stage": str(selected.get("source_stage") or ""),
            "needs_review_before_publication": needs_review,
            "review_reasons": review_reasons,
            "content_format": "editorjs",
            "content": content,
            "sources": {
                "source_doc_ids": source_doc_ids,
                "source_documents_count": source_documents_count,
                "fact_group_ids": fact_group_ids,
                "used_fact_group_ids": used_fact_group_ids,
            },
            "export": {
                "stage": STAGE,
                "exported_at": created_at,
                "for_n8n_path": "",
                "for_docs_path": "",
                "for_docs_quotes_path": "",
            },
            "provenance": {
                "a1_entity_json_path": str(selected.get("a1_entity_json_path") or ""),
                "a3_fact_groups_path": str(self.inputs["fact_groups_jsonl"]),
                "a4_draft_path": str(selected.get("a4_draft_path") or ""),
            },
        }
        return article, issues

    def _entity_path(self, status_row: dict[str, Any]) -> Path | None:
        value = str(status_row.get("article_file_path") or "").strip()
        if value:
            return Path(value)
        tag_id = str(status_row.get("tag_id") or "").strip()
        entity_type = str(status_row.get("entity_type") or "").strip()
        if tag_id and entity_type:
            return self.config.entities_dir / entity_type / f"{tag_id}.json"
        return None

    def _export_index_row(self, article: dict[str, Any], companion: dict[str, Any]) -> dict[str, Any]:
        sources = article.get("sources") if isinstance(article.get("sources"), dict) else {}
        export = article.get("export") if isinstance(article.get("export"), dict) else {}
        return {
            "tag_id": article.get("tag_id") or "",
            "canonical_tag_ru": article.get("canonical_tag_ru") or "",
            "canonical_tag_latin": article.get("canonical_tag_latin"),
            "entity_type": article.get("entity_type") or "",
            "article_status": article.get("article_status") or "",
            "source_stage": article.get("source_stage") or "",
            "source_article_status": article.get("source_article_status") or "",
            "needs_review_before_publication": bool(article.get("needs_review_before_publication")),
            "review_reasons": _string_list(article.get("review_reasons")),
            "for_n8n_path": export.get("for_n8n_path") or "",
            "for_docs_path": export.get("for_docs_path") or "",
            "for_docs_quotes_path": export.get("for_docs_quotes_path") or "",
            "content_blocks_count": content_blocks_count(article.get("content") if isinstance(article.get("content"), dict) else {}),
            "quotes_count": len(companion.get("quotes") if isinstance(companion.get("quotes"), list) else []),
            "questions_count": len(companion.get("questions") if isinstance(companion.get("questions"), list) else []),
            "source_documents_count": int(sources.get("source_documents_count") or 0),
            "used_fact_groups_count": len(_string_list(sources.get("used_fact_group_ids"))),
            "export_quality_status": "ok" if article.get("article_status") not in {"missing_article_source", "export_repair_stub"} else "issue",
            "qa_excerpt": content_excerpt(article.get("content") if isinstance(article.get("content"), dict) else {}),
        }

    def _quotes_index_row(self, article: dict[str, Any], companion: dict[str, Any], quotes_path: Path) -> dict[str, Any]:
        return {
            "tag_id": article.get("tag_id") or "",
            "canonical_tag_ru": article.get("canonical_tag_ru") or "",
            "entity_type": article.get("entity_type") or "",
            "quotes_path": str(quotes_path),
            "questions_count": len(companion.get("questions") if isinstance(companion.get("questions"), list) else []),
            "quotes_count": len(companion.get("quotes") if isinstance(companion.get("quotes"), list) else []),
            "questions_generation_status": companion.get("questions_generation_status") or "",
            "quotes_source_status": companion.get("quotes_source_status") or "",
            "needs_review_before_publication": bool(article.get("needs_review_before_publication")),
        }

    def _track_duplicate_path(
        self,
        seen_paths: dict[str, list[str]],
        duplicate_rows: list[dict[str, Any]],
        path: Path,
        tag_id: str,
        export_area: str,
    ) -> None:
        key = str(path)
        seen_paths.setdefault(key, []).append(tag_id)
        if len(seen_paths[key]) == 2:
            duplicate_rows.append({"path": key, "export_area": export_area, "tag_ids": list(seen_paths[key])})
        elif len(seen_paths[key]) > 2:
            duplicate_rows[-1]["tag_ids"] = list(seen_paths[key])

    def _coverage(
        self,
        *,
        status_rows: list[dict[str, Any]],
        export_rows: list[dict[str, Any]],
        quotes_rows: list[dict[str, Any]],
        issues: list[dict[str, Any]],
        missing_rows: list[dict[str, Any]],
        duplicate_rows: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        final_tags_total = len(status_rows)
        status_counts = Counter(str(row.get("article_status") or "") for row in export_rows)
        for_n8n_files = list(self.outputs["for_n8n_dir"].glob("*.json"))
        for_n8n_subdirs = [path for path in self.outputs["for_n8n_dir"].iterdir() if path.is_dir()]
        docs_article_files = [path for path in self.outputs["for_docs_dir"].glob("*/*.json") if not path.name.endswith("_quotes.json")]
        docs_quotes_files = list(self.outputs["for_docs_dir"].glob("*/*_quotes.json"))
        all_article_json_valid, all_articles_valid_editorjs = self._validate_written_articles(for_n8n_files + docs_article_files)
        all_quotes_json_valid = all(json_file_is_valid(path) for path in docs_quotes_files)
        quality = {
            "all_tags_exported_to_for_n8n": len(for_n8n_files) == final_tags_total,
            "for_n8n_flat": not for_n8n_subdirs,
            "all_tags_exported_to_for_docs": len(docs_article_files) == final_tags_total,
            "all_for_docs_have_quotes_file": len(docs_quotes_files) == final_tags_total,
            "no_duplicate_filenames": not duplicate_rows,
            "no_missing_tag_id": all(str(row.get("tag_id") or "").strip() for row in export_rows),
            "all_exported_article_json_valid": all_article_json_valid,
            "all_articles_valid_editorjs": all_articles_valid_editorjs,
            "all_content_format_editorjs": self._all_content_format_editorjs(for_n8n_files + docs_article_files),
            "article_export_index_complete": len(export_rows) == final_tags_total,
            "quotes_index_complete": len(quotes_rows) == final_tags_total,
            "all_for_docs_quotes_files_valid_json": all_quotes_json_valid,
            "no_export_quality_errors": not any(str(issue.get("severity") or "") == "error" for issue in issues),
        }
        quality["passed"] = all(bool(value) for value in quality.values())
        counts = {
            "final_tags_total": final_tags_total,
            "for_n8n_article_files": len(for_n8n_files),
            "for_docs_article_files": len(docs_article_files),
            "for_docs_quotes_files": len(docs_quotes_files),
            "compiled_article": status_counts.get("compiled_article", 0),
            "compiled_with_review_flag": status_counts.get("compiled_with_review_flag", 0),
            "direct_copy_article": status_counts.get("direct_copy_article", 0),
            "stub_only": status_counts.get("stub_only", 0),
            "review_stub": status_counts.get("review_stub", 0),
            "insufficient_evidence_review": status_counts.get("insufficient_evidence_review", 0),
            "missing_article_source": status_counts.get("missing_article_source", 0),
            "export_repair_stub": status_counts.get("export_repair_stub", 0),
            "malformed_editorjs_repaired": sum(1 for issue in issues if issue.get("issue_type") == "malformed_source_editorjs"),
            "export_quality_issues": len(issues),
            "missing_tags": len(missing_rows),
            "duplicate_filenames": len(duplicate_rows),
            "questions_total": sum(int(row.get("questions_count") or 0) for row in quotes_rows),
            "quotes_total": sum(int(row.get("quotes_count") or 0) for row in quotes_rows),
            "needs_review_before_publication": sum(1 for row in export_rows if row.get("needs_review_before_publication")),
        }
        return counts, quality

    def _validate_written_articles(self, paths: list[Path]) -> tuple[bool, bool]:
        all_json_valid = True
        all_editorjs_valid = True
        for path in paths:
            try:
                article = read_json(path)
            except Exception:
                all_json_valid = False
                all_editorjs_valid = False
                continue
            content, errors = validate_editorjs_content(article.get("content"))
            if errors or content is None:
                all_editorjs_valid = False
        return all_json_valid, all_editorjs_valid

    def _all_content_format_editorjs(self, paths: list[Path]) -> bool:
        for path in paths:
            try:
                article = read_json(path)
            except Exception:
                return False
            if article.get("content_format") != "editorjs":
                return False
        return True

    def _write_indexes_and_reports(
        self,
        *,
        export_rows: list[dict[str, Any]],
        quotes_rows: list[dict[str, Any]],
        missing_rows: list[dict[str, Any]],
        duplicate_rows: list[dict[str, Any]],
        issues: list[dict[str, Any]],
        coverage_audit: dict[str, Any],
        report: dict[str, Any],
        manifest: dict[str, Any],
    ) -> None:
        write_jsonl(self.outputs["article_export_index_jsonl"], export_rows)
        write_csv(self.outputs["article_export_index_csv"], ARTICLE_EXPORT_INDEX_FIELDS, export_rows)
        write_jsonl(self.outputs["quotes_index_jsonl"], quotes_rows)
        write_csv(self.outputs["quotes_index_csv"], QUOTES_INDEX_FIELDS, quotes_rows)
        write_csv(self.outputs["export_missing_tags_csv"], MISSING_TAG_FIELDS, missing_rows)
        write_csv(self.outputs["export_duplicate_filenames_csv"], DUPLICATE_FILENAME_FIELDS, duplicate_rows)
        write_jsonl(self.outputs["export_quality_issues_jsonl"], issues)
        write_csv(self.outputs["manual_qa_export_sample_csv"], MANUAL_QA_FIELDS, manual_qa_rows(export_rows))
        write_csv(self.outputs["status_distribution_csv"], STATUS_DISTRIBUTION_FIELDS, status_distribution_rows(export_rows))
        write_csv(self.outputs["entity_type_distribution_csv"], ENTITY_TYPE_DISTRIBUTION_FIELDS, entity_type_distribution_rows(export_rows))
        write_json(self.outputs["export_coverage_audit_json"], coverage_audit)
        write_json(self.outputs["a5_report_json"], report)
        write_json(self.outputs["a5_manifest_json"], manifest)


def _issue(selected: dict[str, Any], issue_type: str, severity: str, reason: str) -> dict[str, Any]:
    return {
        "tag_id": selected.get("tag_id") or "",
        "canonical_tag_ru": selected.get("canonical_tag_ru") or "",
        "entity_type": selected.get("entity_type") or "",
        "issue_type": issue_type,
        "severity": severity,
        "reason": reason,
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    stripped = str(value).strip()
    return [stripped] if stripped else []


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

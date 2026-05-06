from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kb_rebuild.articles.a4.models import A4Config
from kb_rebuild.articles.a4.report import build_manifest, build_report, manual_qa_rows, write_json


class ArticleA4ReportTests(unittest.TestCase):
    def test_report_counts_and_manifest_are_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = _config(root)
            draft = _draft(root)
            write_json(Path(draft["article_file_path"]), {"tag_id": "tag_1"})

            report = build_report(
                created_at="2026-05-06T00:00:00Z",
                config=config,
                inputs=_inputs(root),
                tasks=[{"task_id": "a4task_000000001"}],
                batches=[{"batch_id": "a4batch_000001"}],
                article_drafts=[draft],
                failed_tasks=[],
                batch_reports=[{"status": "success", "latency_ms": 10}],
                invalid_llm_responses=[],
                article_quality_issues=[],
                stats={"no_unknown_fact_group_ids": True},
                stop_reason=None,
                warnings=[],
            )
            manifest = build_manifest(
                created_at="2026-05-06T00:00:00Z",
                config=config,
                inputs=_inputs(root),
                outputs={"a4_report_json": config.out_dir / "a4_report.json"},
            )

            self.assertEqual(report["counts"]["compiled_articles"], 1)
            self.assertTrue(report["quality"]["passed"])
            self.assertEqual(manifest["stage_version"], "a4.0")

    def test_quality_fails_on_missing_article_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = build_report(
                created_at="2026-05-06T00:00:00Z",
                config=_config(root),
                inputs=_inputs(root),
                tasks=[{"task_id": "a4task_000000001"}],
                batches=[],
                article_drafts=[_draft(root)],
                failed_tasks=[],
                batch_reports=[],
                invalid_llm_responses=[],
                article_quality_issues=[],
                stats={"no_unknown_fact_group_ids": True},
                stop_reason=None,
                warnings=[],
            )

            self.assertFalse(report["quality"]["all_compiled_article_files_exist"])
            self.assertFalse(report["quality"]["passed"])

    def test_manual_qa_sample_is_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rows = manual_qa_rows([_draft(Path(tmp))], [])

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["tag_id"], "tag_1")
            self.assertIn("qa_excerpt", rows[0])


def _config(root: Path) -> A4Config:
    return A4Config.from_data_dir(
        root,
        a3_dir=root / "articles" / "a3",
        a1_dir=root / "articles" / "a1",
        entities_dir=root / "articles" / "entities",
        normalization_final_dir=root / "normalization" / "final",
        out_dir=root / "articles" / "a4" / "experiments" / "smoke_test",
        limit=1,
    )


def _inputs(root: Path) -> dict[str, Path]:
    return {
        "a4_compilation_input_jsonl": root / "articles" / "a3" / "a4_compilation_input.jsonl",
        "fact_groups_jsonl": root / "articles" / "a3" / "fact_groups.jsonl",
        "a3_manifest_json": root / "articles" / "a3" / "a3_manifest.json",
        "a1_manifest_json": root / "articles" / "a1" / "a1_manifest.json",
    }


def _draft(root: Path) -> dict[str, object]:
    return {
        "task_id": "a4task_000000001",
        "batch_id": "a4batch_000001",
        "tag_id": "tag_1",
        "canonical_tag_ru": "Тестовый тег",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "a4_strategy": "compile_from_fact_groups",
        "article_status": "compiled_article",
        "title": "Тестовый тег",
        "summary": "Краткое описание.",
        "content": {
            "blocks": [
                {"type": "header", "data": {"text": "Что это"}, "metadata": {"source_fact_group_ids": []}},
                {"type": "paragraph", "data": {"text": "Текст."}, "metadata": {"source_fact_group_ids": ["fg_1"]}},
            ]
        },
        "used_fact_group_ids": ["fg_1"],
        "unused_fact_group_ids": [],
        "fact_group_ids": ["fg_1"],
        "source_doc_ids": ["doc_1"],
        "source_documents_count": 1,
        "task_needs_review_before_publication": False,
        "needs_review_before_publication": False,
        "review_reasons": [],
        "confidence": 0.9,
        "reason": "",
        "article_file_path": str(root / "article.json"),
    }


if __name__ == "__main__":
    unittest.main()

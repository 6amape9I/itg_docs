from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from kb_rebuild.articles.a3.models import A3Config
from kb_rebuild.articles.a3.runner import run_article_a3_grouping
from kb_rebuild.io.jsonl import read_jsonl, write_jsonl


class ArticleA3RunnerTests(unittest.TestCase):
    def test_runner_creates_required_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root)
            config = _config(root)

            report = run_article_a3_grouping(config)

            self.assertTrue(report["quality"]["passed"])
            self.assertTrue((config.out_dir / "fact_groups.jsonl").exists())
            self.assertTrue((config.out_dir / "a4_compilation_input.jsonl").exists())
            self.assertEqual(len(read_jsonl(config.out_dir / "tag_fact_group_index.jsonl")), 2)

    def test_runner_refuses_bad_a2_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root, a2_quality_passed=False)
            config = _config(root)

            with self.assertRaises(ValueError):
                run_article_a3_grouping(config)

    def test_runner_refuses_quote_not_found_share_above_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root, quote_not_found_share=0.051)
            config = _config(root)

            with self.assertRaises(ValueError):
                run_article_a3_grouping(config)


def _config(root: Path) -> A3Config:
    return A3Config.from_data_dir(
        root,
        a2_dir=root / "articles" / "a2" / "production_v1",
        a1_dir=root / "articles" / "a1",
        normalization_final_dir=root / "normalization" / "final",
        out_dir=root / "articles" / "a3",
    )


def _write_inputs(root: Path, *, a2_quality_passed: bool = True, quote_not_found_share: float = 0.0) -> None:
    a2_dir = root / "articles" / "a2" / "production_v1"
    a1_dir = root / "articles" / "a1"
    final_dir = root / "normalization" / "final"
    a2_dir.mkdir(parents=True, exist_ok=True)
    a1_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(a2_dir / "evidence_items.jsonl", [_evidence_item("ev_1", "tag_1")])
    write_jsonl(a2_dir / "evidence_task_results.jsonl", [{"task_id": "task_1", "tag_id": "tag_1", "status": "success"}])
    write_jsonl(a2_dir / "quote_validation_issues.jsonl", [])
    _write_json(
        a2_dir / "a2_report.json",
        {
            "stage": "article_a2_evidence_extraction",
            "counts": {"tasks_failed": 0, "evidence_items_total": 1},
            "quality": {"passed": a2_quality_passed, "quote_not_found_share": quote_not_found_share},
        },
    )
    _write_json(a2_dir / "a2_manifest.json", {"stage_version": "a2.0"})
    write_jsonl(a1_dir / "article_status_index.jsonl", [_status("tag_1", a2_extraction_tasks_count=1), _status("tag_2", article_status="stub_only")])
    write_jsonl(a1_dir / "tag_work_plan_adjusted.jsonl", [])
    _write_json(a1_dir / "a1_report.json", {"stage": "article_a1_entity_json_bootstrap", "quality": {"passed": True}})
    _write_json(a1_dir / "a1_manifest.json", {"stage_version": "a1.0"})
    (final_dir / "tags_canonical.csv").write_text("tag_id,canonical_tag_ru\n", encoding="utf-8")
    (final_dir / "tag_aliases.csv").write_text("tag_id,alias\n", encoding="utf-8")


def _evidence_item(evidence_id: str, tag_id: str) -> dict[str, Any]:
    return {
        "evidence_item_id": evidence_id,
        "task_id": "task_1",
        "batch_id": "batch_1",
        "tag_id": tag_id,
        "canonical_tag_ru": "Тег",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "doc_id": "doc_1",
        "document_name": "Документ",
        "window_id": "win_1",
        "fact_type": "definition",
        "section_hint": "Что это",
        "claim": "Тег является тестовым.",
        "quote": "Тег является тестовым.",
        "quote_validation_status": "exact",
        "importance": "high",
        "confidence": 0.9,
        "relevance": "direct",
        "source_strategy": "single_doc_extract",
        "window_quality": "high",
        "needs_review_before_publication": False,
        "review_reasons": [],
    }


def _status(tag_id: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "tag_id": tag_id,
        "canonical_tag_ru": "Тег",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "article_status": "pending_single_doc_extract",
        "article_candidate": True,
        "a2_extraction_tasks_count": 0,
        "needs_review_before_publication": False,
        "review_reasons": [],
        "publication_review_reasons": [],
    }
    row.update(overrides)
    return row


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()


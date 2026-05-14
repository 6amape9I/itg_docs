from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from kb_rebuild.articles.a5.models import A5Config
from kb_rebuild.articles.a5.runner import run_article_a5_export
from kb_rebuild.io.jsonl import read_jsonl, write_jsonl


class ArticleA5RunnerTests(unittest.TestCase):
    def test_runner_creates_complete_export_for_small_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_fixture(root)
            config = _config(root)

            report = run_article_a5_export(config)

            self.assertTrue(report["quality"]["passed"])
            self.assertEqual(report["counts"]["final_tags_total"], 4)
            self.assertEqual(report["counts"]["for_n8n_article_files"], 4)
            self.assertEqual(report["counts"]["for_docs_quotes_files"], 4)
            self.assertEqual(len(read_jsonl(config.out_dir / "article_export_index.jsonl")), 4)
            self.assertTrue((config.out_dir / "for_docs" / "disease" / "disease_Тег compiled_quotes.json").exists())
            self.assertTrue((config.out_dir / "for_n8n" / "disease_Тег compiled.json").exists())

    def test_runner_refuses_failed_a4_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_fixture(root, a4_quality_passed=False)
            config = _config(root)

            with self.assertRaises(ValueError):
                run_article_a5_export(config)


def _config(root: Path) -> A5Config:
    return A5Config.from_data_dir(
        root,
        a1_dir=root / "articles" / "a1",
        a3_dir=root / "articles" / "a3",
        a4_dir=root / "articles" / "a4" / "production_v1",
        entities_dir=root / "articles" / "entities",
        normalization_final_dir=root / "normalization" / "final",
        out_dir=root / "articles" / "final_exports",
        overwrite=True,
    )


def _write_fixture(root: Path, *, a4_quality_passed: bool = True) -> None:
    a1_dir = root / "articles" / "a1"
    a3_dir = root / "articles" / "a3"
    a4_dir = root / "articles" / "a4" / "production_v1"
    entities_dir = root / "articles" / "entities" / "disease"
    final_dir = root / "normalization" / "final"
    for path in (a1_dir, a3_dir, a4_dir, entities_dir, final_dir):
        path.mkdir(parents=True, exist_ok=True)

    statuses = [
        _status("tag_compiled", "pending_single_doc_extract"),
        _status("tag_direct", "direct_copy_article"),
        _status("tag_stub", "stub_only"),
        _status("tag_insufficient", "pending_single_doc_extract"),
    ]
    for status in statuses:
        status["article_file_path"] = str(entities_dir / f"{status['tag_id']}.json")
    write_jsonl(a1_dir / "article_status_index.jsonl", statuses)
    _write_json(a1_dir / "a1_report.json", {"quality": {"passed": True}, "counts": {"final_tags_total": 4}})
    _write_json(a1_dir / "a1_manifest.json", {"stage_version": "a1.0"})

    for status in statuses:
        _write_json(entities_dir / f"{status['tag_id']}.json", _entity(str(status["tag_id"]), str(status["article_status"])))

    write_jsonl(
        a3_dir / "a4_compilation_input.jsonl",
        [
            {"tag_id": "tag_compiled", "a4_strategy": "compile_from_fact_groups"},
            {"tag_id": "tag_direct", "a4_strategy": "direct_copy_already_done"},
            {"tag_id": "tag_stub", "a4_strategy": "stub_only"},
            {"tag_id": "tag_insufficient", "a4_strategy": "insufficient_evidence_review", "article_status_from_a1": "pending_single_doc_extract"},
        ],
    )
    write_jsonl(a3_dir / "fact_groups.jsonl", [_fact_group("fg_1", "tag_compiled")])
    write_jsonl(a3_dir / "tag_fact_group_index.jsonl", [])
    _write_json(a3_dir / "a3_report.json", {"quality": {"passed": True}, "counts": {"final_tags_total": 4}})
    _write_json(a3_dir / "a3_manifest.json", {"stage_version": "a3.0"})

    write_jsonl(a4_dir / "article_drafts.jsonl", [_a4_draft()])
    _write_json(
        a4_dir / "a4_report.json",
        {"quality": {"passed": a4_quality_passed}, "counts": {"article_drafts_total": 1, "tasks_failed": 0, "article_quality_issues": 0}},
    )
    _write_json(a4_dir / "a4_manifest.json", {"stage_version": "a4.0"})
    _write_json(a4_dir / "article_quality_diagnostics.json", {"quality": {"passed": a4_quality_passed}})

    (final_dir / "tags_canonical.csv").write_text(
        "tag_id,canonical_tag_ru,canonical_tag_latin,entity_type\n"
        "tag_compiled,Тег compiled,,disease\n"
        "tag_direct,Тег direct,,disease\n"
        "tag_stub,Тег stub,,disease\n"
        "tag_insufficient,Тег insufficient,,disease\n",
        encoding="utf-8",
    )
    (final_dir / "tag_aliases.csv").write_text("tag_id,alias\n", encoding="utf-8")
    _write_json(final_dir / "final_normalization_report.json", {"quality": {"passed": True}})
    _write_json(final_dir / "final_normalization_manifest.json", {"stage_version": "n4.0"})


def _status(tag_id: str, article_status: str) -> dict[str, object]:
    return {
        "tag_id": tag_id,
        "canonical_tag_ru": f"Тег {tag_id}",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "article_status": article_status,
        "article_file_path": "",
        "documents_count": 1,
        "needs_review_before_publication": False,
        "review_reasons": [],
        "publication_review_reasons": [],
    }


def _entity(tag_id: str, article_status: str) -> dict[str, Any]:
    return {
        "tag_id": tag_id,
        "canonical_tag_ru": f"Тег {tag_id}",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "article_status": article_status,
        "content_format": "editorjs",
        "content": _content(f"Тег {tag_id}"),
        "sources": {"source_doc_ids": ["doc_1"]},
        "documents_count": 1,
        "needs_review_before_publication": False,
        "review_reasons": [],
    }


def _a4_draft() -> dict[str, Any]:
    return {
        "tag_id": "tag_compiled",
        "canonical_tag_ru": "Тег compiled",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "article_status": "compiled_article",
        "content_format": "editorjs",
        "content": _content("Тег compiled"),
        "source_doc_ids": ["doc_1"],
        "source_documents_count": 1,
        "fact_group_ids": ["fg_1"],
        "used_fact_group_ids": ["fg_1"],
        "needs_review_before_publication": False,
        "review_reasons": [],
    }


def _fact_group(fact_group_id: str, tag_id: str) -> dict[str, Any]:
    return {
        "fact_group_id": fact_group_id,
        "tag_id": tag_id,
        "fact_type": "definition",
        "representative_claim": "Тег является тестовым.",
        "representative_quote": "Тег является тестовым.",
        "representative_quote_validation_status": "exact",
        "source_doc_ids": ["doc_1"],
        "source_window_ids": ["win_1"],
        "usable_for_a4": True,
    }


def _content(title: str) -> dict[str, Any]:
    return {
        "time": 0,
        "version": "2.28.0",
        "blocks": [
            {"type": "header", "data": {"text": title, "level": 2}},
            {"type": "paragraph", "data": {"text": "Тестовый текст."}},
        ],
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

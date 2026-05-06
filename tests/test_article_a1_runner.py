from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from kb_rebuild.articles.a1.models import A1Config
from kb_rebuild.articles.a1.runner import run_article_a1_bootstrap
from kb_rebuild.io.jsonl import read_jsonl, write_jsonl


class ArticleA1RunnerTests(unittest.TestCase):
    def test_runner_creates_outputs_and_coverage_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_fixture(Path(tmp))
            report = run_article_a1_bootstrap(A1Config.from_data_dir(data_dir))
            out_dir = data_dir / "articles" / "a1"

            for filename in (
                "tag_work_plan_adjusted.jsonl",
                "article_status_index.jsonl",
                "a2_extraction_task_queue.jsonl",
                "a1_report.json",
                "a1_manifest.json",
                "article_file_coverage_audit.json",
            ):
                self.assertTrue((out_dir / filename).exists(), filename)
            self.assertTrue(report["quality"]["passed"])
            self.assertEqual(report["counts"]["final_tags_total"], 3)
            self.assertEqual(report["counts"]["entity_json_files_created"], 3)
            self.assertEqual(report["counts"]["a0_1_rerouted_from_review_stub"], 1)
            self.assertGreaterEqual(report["counts"]["a2_extraction_tasks_total"], 1)
            status = read_jsonl(out_dir / "article_status_index.jsonl")
            self.assertEqual(len(status), 3)

    def test_runner_refuses_missing_a0_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_fixture(Path(tmp))
            (data_dir / "articles" / "planning" / "article_planning_manifest.json").unlink()

            with self.assertRaisesRegex(FileNotFoundError, "article_planning_manifest"):
                run_article_a1_bootstrap(A1Config.from_data_dir(data_dir))

    def test_runner_refuses_missing_final_normalization_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_fixture(Path(tmp))
            (data_dir / "normalization" / "final" / "final_normalization_report.json").unlink()

            with self.assertRaisesRegex(FileNotFoundError, "final_normalization_report"):
                run_article_a1_bootstrap(A1Config.from_data_dir(data_dir))


def _write_fixture(root: Path) -> Path:
    data_dir = root / "data"
    planning_dir = data_dir / "articles" / "planning"
    final_dir = data_dir / "normalization" / "final"
    parsed_dir = data_dir / "parsed"
    planning_dir.mkdir(parents=True)
    final_dir.mkdir(parents=True)
    parsed_dir.mkdir(parents=True)

    tags = [
        ["disease_direct", "Астма", "Asthma", "disease"],
        ["disease_review", "МРТ", "MRI", "diagnostic_method"],
        ["context_stub", "Педиатрия", "Pediatrics", "specialty"],
    ]
    _write_csv(final_dir / "tags_canonical.csv", ["tag_id", "canonical_tag_ru", "canonical_tag_latin", "entity_type"], tags)
    _write_csv(final_dir / "tag_aliases.csv", ["tag_id", "alias"], [[row[0], row[1]] for row in tags])
    write_jsonl(final_dir / "document_tag_links_normalized.jsonl", [])
    write_jsonl(final_dir / "document_tags_normalized_by_doc.jsonl", [])
    _write_json(final_dir / "final_normalization_report.json", {"quality": {"passed": True}})
    _write_json(final_dir / "final_normalization_manifest.json", {"stage": "normalization_n4_final_canonical_layer"})

    work_plan = [
        _plan("disease_direct", "Астма", "disease", "direct_copy_candidate", ["win1"], ["doc1"], documents=1, windows=1),
        _plan(
            "disease_review",
            "МРТ",
            "diagnostic_method",
            "review_stub",
            ["win2"],
            ["doc2", "doc3"],
            documents=2,
            windows=1,
            review_reasons=["alias_conflict"],
        ),
        _plan("context_stub", "Педиатрия", "specialty", "stub_only", ["win3"], ["doc4"], article_candidate=False, documents=1, windows=1),
    ]
    write_jsonl(planning_dir / "tag_work_plan.jsonl", work_plan)
    write_jsonl(planning_dir / "tag_source_index.jsonl", [])
    write_jsonl(
        planning_dir / "source_block_windows.jsonl",
        [
            _window("win1", "disease_direct", "doc1", coverage=1.0),
            _window("win2", "disease_review", "doc2", coverage=0.5),
            _window("win3", "context_stub", "doc4", coverage=0.5),
        ],
    )
    write_jsonl(planning_dir / "direct_copy_candidates.jsonl", [])
    write_jsonl(planning_dir / "singleton_candidates.jsonl", [])
    _write_json(planning_dir / "article_planning_report.json", {"stage": "article_planning_a0"})
    _write_json(planning_dir / "article_planning_manifest.json", {"stage": "article_planning_a0"})

    write_jsonl(
        parsed_dir / "parsed_documents.jsonl",
        [
            {"doc_id": "doc1", "name": "Астма", "text_length_chars": 20},
            {"doc_id": "doc2", "name": "МРТ", "text_length_chars": 20},
            {"doc_id": "doc4", "name": "Педиатрия", "text_length_chars": 20},
        ],
    )
    write_jsonl(
        parsed_dir / "document_blocks.jsonl",
        [
            {"doc_id": "doc1", "block_id": "b1", "block_index": 0, "block_type": "paragraph", "text": "Астма текст"},
            {"doc_id": "doc2", "block_id": "b1", "block_index": 0, "block_type": "paragraph", "text": "МРТ текст"},
            {"doc_id": "doc4", "block_id": "b1", "block_index": 0, "block_type": "paragraph", "text": "Педиатрия текст"},
        ],
    )
    return data_dir


def _plan(
    tag_id: str,
    name: str,
    entity_type: str,
    strategy: str,
    window_ids: list[str],
    doc_ids: list[str],
    *,
    article_candidate: bool = True,
    documents: int,
    windows: int,
    review_reasons: list[str] | None = None,
) -> dict[str, object]:
    return {
        "tag_id": tag_id,
        "canonical_tag_ru": name,
        "canonical_tag_latin": "",
        "entity_type": entity_type,
        "strategy": strategy,
        "article_candidate": article_candidate,
        "need_review": bool(review_reasons),
        "needs_review_before_article": strategy == "review_stub",
        "primary_role": "article_candidate" if article_candidate else "context_only",
        "mentions_count": documents,
        "documents_count": documents,
        "source_windows_count": windows,
        "source_window_ids": window_ids,
        "source_doc_ids": doc_ids,
        "competing_article_candidate_tags_in_doc": 0,
        "review_reasons": review_reasons or [],
    }


def _window(window_id: str, tag_id: str, doc_id: str, *, coverage: float) -> dict[str, object]:
    return {
        "window_id": window_id,
        "tag_id": tag_id,
        "canonical_tag_ru": "",
        "entity_type": "",
        "doc_id": doc_id,
        "document_name": "Doc",
        "window_text": "source window text",
        "window_char_length": 18,
        "block_ids": ["b1"],
        "block_indexes": [0],
        "heading_context": [],
        "match_method": "quote_match",
        "window_quality": "high",
        "coverage_ratio_estimate": coverage,
    }


def _write_csv(path: Path, fieldnames: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(fieldnames)
        writer.writerows(rows)


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from kb_rebuild.articles.planning.models import A0Config
from kb_rebuild.articles.planning.runner import run_article_planning_a0
from kb_rebuild.io.jsonl import read_jsonl, write_jsonl


class ArticlePlanningRunnerTests(unittest.TestCase):
    def test_runner_creates_required_outputs_and_work_plan_for_every_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_runner_fixture(Path(tmp))
            config = A0Config.from_data_dir(data_dir)

            report = run_article_planning_a0(config)

            for filename in (
                "tag_source_index.jsonl",
                "tag_work_plan.jsonl",
                "source_block_windows.jsonl",
                "direct_copy_candidates.jsonl",
                "singleton_candidates.jsonl",
                "stub_only_tags.jsonl",
                "review_stub_tags.jsonl",
                "no_source_window_tags.jsonl",
                "article_planning_report.json",
                "article_planning_manifest.json",
                "tag_work_plan.csv",
                "strategy_summary_by_entity_type.csv",
                "high_frequency_tags.csv",
                "source_window_quality_report.csv",
            ):
                self.assertTrue((config.out_dir / filename).exists(), filename)

            work_plan = read_jsonl(config.out_dir / "tag_work_plan.jsonl")
            self.assertEqual(len(work_plan), 2)
            self.assertEqual(report["counts"]["final_tags_total"], 2)
            self.assertEqual(report["counts"]["source_windows_total"], 2)
            strategies = {row["tag_id"]: row["strategy"] for row in work_plan}
            self.assertEqual(strategies["disease_a"], "direct_copy_candidate")
            self.assertEqual(strategies["context_a"], "stub_only")


def _write_runner_fixture(root: Path) -> Path:
    data_dir = root / "data"
    final_dir = data_dir / "normalization" / "final"
    norm_dir = data_dir / "normalization"
    parsed_dir = data_dir / "parsed"
    final_dir.mkdir(parents=True)
    parsed_dir.mkdir(parents=True)

    _write_csv(
        final_dir / "tags_canonical.csv",
        ["tag_id", "canonical_tag_ru", "canonical_tag_latin", "entity_type", "primary_role", "article_candidate", "need_review", "review_reasons"],
        [
            ["disease_a", "Астма", "Asthma", "disease", "article_candidate", "true", "false", "[]"],
            ["context_a", "Педиатрия", "Pediatrics", "specialty", "context_only", "false", "false", "[]"],
        ],
    )
    _write_csv(
        final_dir / "tag_aliases.csv",
        ["tag_id", "alias", "alias_latin"],
        [["disease_a", "Астма", "Asthma"], ["context_a", "Педиатрия", "Pediatrics"]],
    )
    write_jsonl(
        final_dir / "document_tag_links_normalized.jsonl",
        [
            {
                "tag_id": "disease_a",
                "canonical_tag_ru": "Астма",
                "doc_id": "doc1",
                "mention_id": "m1",
                "document_name": "Астма",
                "raw_surface": "Астма",
                "tag_role": "article_candidate",
                "article_candidate": True,
                "confidence": 1.0,
            },
            {
                "tag_id": "context_a",
                "canonical_tag_ru": "Педиатрия",
                "doc_id": "doc2",
                "mention_id": "m2",
                "document_name": "Педиатрия",
                "raw_surface": "Педиатрия",
                "tag_role": "context_only",
                "article_candidate": False,
                "confidence": 1.0,
            },
        ],
    )
    write_jsonl(
        final_dir / "document_tags_normalized_by_doc.jsonl",
        [{"doc_id": "doc1", "tags": [{"tag_id": "disease_a"}]}, {"doc_id": "doc2", "tags": [{"tag_id": "context_a"}]}],
    )
    _write_json(final_dir / "final_normalization_report.json", {"quality": {"passed": True}, "counts": {"document_tag_links_total": 2}})
    _write_json(final_dir / "final_normalization_manifest.json", {"stage": "normalization_n4_final_canonical_layer"})
    write_jsonl(
        parsed_dir / "parsed_documents.jsonl",
        [
            {"doc_id": "doc1", "name": "Астма", "clean_text": "Астма\n\nАстма - хроническое заболевание", "text_length_chars": 38},
            {"doc_id": "doc2", "name": "Педиатрия", "clean_text": "Педиатрия изучает здоровье детей", "text_length_chars": 32},
        ],
    )
    write_jsonl(
        parsed_dir / "document_blocks.jsonl",
        [
            {"doc_id": "doc1", "block_id": "b1", "block_index": 0, "block_type": "header", "text": "Астма"},
            {"doc_id": "doc1", "block_id": "b2", "block_index": 1, "block_type": "paragraph", "text": "Астма - хроническое заболевание"},
            {"doc_id": "doc2", "block_id": "b1", "block_index": 0, "block_type": "paragraph", "text": "Педиатрия изучает здоровье детей"},
        ],
    )
    write_jsonl(norm_dir / "tag_mentions_normalized.jsonl", [{"mention_id": "m1", "evidence_quotes": ["Астма - хроническое заболевание"]}])
    write_jsonl(norm_dir / "tag_mentions_raw.jsonl", [{"mention_id": "m1"}, {"mention_id": "m2"}])
    return data_dir


def _write_csv(path: Path, fieldnames: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(fieldnames)
        writer.writerows(rows)


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

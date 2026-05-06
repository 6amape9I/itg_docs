from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from kb_rebuild.articles.planning.loaders import load_planning_inputs
from kb_rebuild.articles.planning.models import A0Config
from kb_rebuild.io.jsonl import write_jsonl


class ArticlePlanningLoadersTests(unittest.TestCase):
    def test_loads_required_inputs_and_optional_mentions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_loader_fixture(Path(tmp))

            loaded = load_planning_inputs(A0Config.from_data_dir(data_dir))

            self.assertEqual(len(loaded.canonical_tags), 1)
            self.assertEqual(len(loaded.aliases), 1)
            self.assertEqual(len(loaded.document_links), 1)
            self.assertEqual(len(loaded.documents), 1)
            self.assertEqual(len(loaded.blocks), 1)
            self.assertEqual(len(loaded.tag_mentions_normalized), 1)
            self.assertEqual(loaded.warnings, [])

    def test_fails_on_missing_required_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_loader_fixture(Path(tmp))
            (data_dir / "normalization" / "final" / "tag_aliases.csv").unlink()

            with self.assertRaisesRegex(FileNotFoundError, "tag_aliases"):
                load_planning_inputs(A0Config.from_data_dir(data_dir))

    def test_fails_when_report_link_count_differs_from_jsonl_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_loader_fixture(Path(tmp), expected_links=2)

            with self.assertRaisesRegex(ValueError, "document_tag_links_total"):
                load_planning_inputs(A0Config.from_data_dir(data_dir))


def _write_loader_fixture(root: Path, *, expected_links: int = 1) -> Path:
    data_dir = root / "data"
    final_dir = data_dir / "normalization" / "final"
    norm_dir = data_dir / "normalization"
    parsed_dir = data_dir / "parsed"
    final_dir.mkdir(parents=True)
    parsed_dir.mkdir(parents=True)

    _write_csv(
        final_dir / "tags_canonical.csv",
        ["tag_id", "canonical_tag_ru", "canonical_tag_latin", "entity_type", "primary_role", "article_candidate", "need_review", "review_reasons"],
        [["disease_a", "Астма", "Asthma", "disease", "article_candidate", "true", "false", "[]"]],
    )
    _write_csv(final_dir / "tag_aliases.csv", ["tag_id", "alias", "alias_latin"], [["disease_a", "Астма", "Asthma"]])
    write_jsonl(
        final_dir / "document_tag_links_normalized.jsonl",
        [
            {
                "tag_id": "disease_a",
                "doc_id": "doc1",
                "mention_id": "m1",
                "document_name": "Астма",
                "raw_surface": "астма",
                "article_candidate": True,
            }
        ],
    )
    write_jsonl(final_dir / "document_tags_normalized_by_doc.jsonl", [{"doc_id": "doc1", "tags": [{"tag_id": "disease_a"}]}])
    _write_json(final_dir / "final_normalization_report.json", {"quality": {"passed": True}, "counts": {"document_tag_links_total": expected_links}})
    _write_json(final_dir / "final_normalization_manifest.json", {"stage": "normalization_n4_final_canonical_layer"})
    write_jsonl(parsed_dir / "parsed_documents.jsonl", [{"doc_id": "doc1", "name": "Астма", "clean_text": "Астма", "text_length_chars": 5}])
    write_jsonl(parsed_dir / "document_blocks.jsonl", [{"doc_id": "doc1", "block_id": "b1", "block_index": 0, "block_type": "paragraph", "text": "Астма"}])
    write_jsonl(norm_dir / "tag_mentions_normalized.jsonl", [{"mention_id": "m1", "evidence_quotes": ["Астма"]}])
    write_jsonl(norm_dir / "tag_mentions_raw.jsonl", [{"mention_id": "m1"}])
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

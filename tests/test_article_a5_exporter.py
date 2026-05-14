from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kb_rebuild.articles.a5.exporter import export_filename_base, prepare_output_dir, unique_export_filename_base, write_article_exports


class ArticleA5ExporterTests(unittest.TestCase):
    def test_write_article_exports_creates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_output_dir(root, overwrite=False, known_files=[])
            article = {"tag_id": "tag_1", "content_format": "editorjs", "content": {"blocks": []}}
            companion = {"tag_id": "tag_1", "questions": [], "quotes": []}

            write_article_exports(
                article,
                companion,
                n8n_path=root / "for_n8n" / "tag_1.json",
                docs_path=root / "for_docs" / "disease" / "tag_1.json",
                quotes_path=root / "for_docs" / "disease" / "tag_1_quotes.json",
            )

            self.assertTrue((root / "for_n8n" / "tag_1.json").exists())
            self.assertTrue((root / "for_docs" / "disease" / "tag_1.json").exists())
            self.assertTrue((root / "for_docs" / "disease" / "tag_1_quotes.json").exists())
            self.assertEqual(json.loads((root / "for_n8n" / "tag_1.json").read_text(encoding="utf-8"))["tag_id"], "tag_1")

    def test_prepare_output_dir_refuses_existing_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "for_n8n").mkdir(parents=True)

            with self.assertRaises(ValueError):
                prepare_output_dir(root, overwrite=False, known_files=[])

    def test_export_filename_uses_entity_type_and_ru_canonical(self) -> None:
        filename = export_filename_base(
            {
                "tag_id": "disease_1",
                "entity_type": "disease",
                "canonical_tag_ru": "Астма/бронхиальная",
                "canonical_tag_latin": "Asthma",
            }
        )

        self.assertEqual(filename, "disease_Астма_бронхиальная")

    def test_export_filename_falls_back_to_latin(self) -> None:
        filename = export_filename_base(
            {
                "tag_id": "disease_1",
                "entity_type": "disease",
                "canonical_tag_ru": "",
                "canonical_tag_latin": "Asthma",
            }
        )

        self.assertEqual(filename, "disease_Asthma")

    def test_duplicate_filename_gets_tag_id_suffix(self) -> None:
        used: set[str] = set()
        first = unique_export_filename_base(
            {"tag_id": "disease_a", "entity_type": "disease", "canonical_tag_ru": "Астма", "canonical_tag_latin": None},
            used,
        )
        second = unique_export_filename_base(
            {"tag_id": "disease_b", "entity_type": "disease", "canonical_tag_ru": "Астма", "canonical_tag_latin": None},
            used,
        )

        self.assertEqual(first, "disease_Астма")
        self.assertEqual(second, "disease_Астма_disease_b")


if __name__ == "__main__":
    unittest.main()

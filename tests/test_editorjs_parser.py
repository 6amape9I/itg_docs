from __future__ import annotations

import json
import tempfile
import unittest
import csv
from pathlib import Path

from kb_rebuild.cli import main
from kb_rebuild.io.jsonl import read_jsonl
from kb_rebuild.parsing.documents import parse_csv_documents
from kb_rebuild.parsing.editorjs import parse_editorjs_content


FIXTURES = Path(__file__).parent / "fixtures"


class EditorJSParserTests(unittest.TestCase):
    def test_simple_header_and_paragraph(self) -> None:
        raw = (FIXTURES / "editorjs_simple.json").read_text(encoding="utf-8")
        result = parse_editorjs_content(raw, doc_id="doc_test")

        self.assertEqual(result.parse_status, "ok")
        self.assertEqual(len(result.blocks), 2)
        self.assertIn("Гастрит", result.clean_text)
        self.assertIn("воспаление слизистой оболочки желудка", result.clean_text)
        self.assertEqual(result.blocks[0].metadata["level"], 2)
        self.assertEqual(result.blocks[0].metadata["source_block_id"], "source_header")

    def test_list_parsing(self) -> None:
        raw = (FIXTURES / "editorjs_mixed_blocks.json").read_text(encoding="utf-8")
        result = parse_editorjs_content(raw, doc_id="doc_test")

        self.assertEqual(result.parse_status, "ok")
        self.assertEqual(len(result.blocks), 4)
        self.assertIn("- Первый пункт", result.clean_text)
        self.assertIn("  - Вложенный пункт", result.clean_text)

    def test_table_parsing(self) -> None:
        raw = (FIXTURES / "editorjs_mixed_blocks.json").read_text(encoding="utf-8")
        result = parse_editorjs_content(raw, doc_id="doc_test")

        self.assertEqual(result.parse_status, "ok")
        self.assertIn("Препарат\tДозировка", result.clean_text)

    def test_unknown_block_with_nested_text(self) -> None:
        raw = (FIXTURES / "editorjs_mixed_blocks.json").read_text(encoding="utf-8")
        result = parse_editorjs_content(raw, doc_id="doc_test")

        self.assertEqual(result.parse_status, "ok")
        self.assertIn("Скрытый заголовок", result.clean_text)
        self.assertIn("customMedicalBlock", result.block_types)

    def test_broken_json_does_not_raise(self) -> None:
        result = parse_editorjs_content("{bad json", doc_id="doc_test")

        self.assertEqual(result.parse_status, "failed")
        self.assertEqual(result.clean_text, "")
        self.assertTrue(result.parse_errors)

    def test_document_blocks_have_source_doc_id_from_cli_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exit_code = main(
                [
                    "parse",
                    "--input",
                    str(FIXTURES / "documents_sample.csv"),
                    "--out",
                    tmp,
                    "--limit",
                    "4",
                ]
            )
            self.assertEqual(exit_code, 0)

            documents = read_jsonl(Path(tmp) / "parsed" / "parsed_documents.jsonl")
            blocks = read_jsonl(Path(tmp) / "parsed" / "document_blocks.jsonl")
            doc_ids = {document["doc_id"] for document in documents}

            self.assertEqual(len(documents), 4)
            self.assertTrue(blocks)
            for block in blocks:
                self.assertIn(block["doc_id"], doc_ids)

            validate_code = main(["validate-parsed", "--data", tmp, "--expected-docs", "4"])
            self.assertEqual(validate_code, 0)

    def test_large_csv_content_field_is_supported(self) -> None:
        large_text = "A" * 150_000
        content = json.dumps(
            {
                "time": 0,
                "blocks": [{"type": "paragraph", "data": {"text": large_text}}],
                "version": "2.28.0",
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "documents.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=["name", "description", "content"])
                writer.writeheader()
                writer.writerow({"name": "Large", "description": "", "content": content})

            documents, blocks, duplicate_doc_ids, errors = parse_csv_documents(csv_path)

        self.assertEqual(len(documents), 1)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(documents[0].parse_status, "ok")
        self.assertEqual(blocks[0].text_length_chars, len(large_text))
        self.assertEqual(duplicate_doc_ids, 0)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

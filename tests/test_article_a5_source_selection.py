from __future__ import annotations

import unittest
from pathlib import Path

from kb_rebuild.articles.a5.source_selection import select_article_source


class ArticleA5SourceSelectionTests(unittest.TestCase):
    def test_a4_compiled_wins_over_a1_status(self) -> None:
        selected = select_article_source(
            _status("tag_1", article_status="direct_copy_article"),
            a4_draft=_a4_draft("tag_1", "compiled_article"),
            a3_input=None,
            entity_article=_entity("tag_1", "direct_copy_article"),
            entity_path=Path("entities/disease/tag_1.json"),
        )

        self.assertEqual(selected["article_status"], "compiled_article")
        self.assertEqual(selected["source_stage"], "A4")
        self.assertEqual(selected["used_fact_group_ids"], ["fg_1"])

    def test_direct_copy_uses_a1_entity(self) -> None:
        selected = select_article_source(
            _status("tag_1", article_status="direct_copy_article"),
            a4_draft=None,
            a3_input=None,
            entity_article=_entity("tag_1", "direct_copy_article"),
            entity_path=Path("entities/disease/tag_1.json"),
        )

        self.assertEqual(selected["article_status"], "direct_copy_article")
        self.assertEqual(selected["source_stage"], "A1")
        self.assertEqual(selected["source_doc_ids"], ["doc_1"])

    def test_insufficient_evidence_uses_a1_entity_with_review_status(self) -> None:
        selected = select_article_source(
            _status("tag_1", article_status="pending_single_doc_extract"),
            a4_draft=None,
            a3_input={"tag_id": "tag_1", "a4_strategy": "insufficient_evidence_review", "article_status_from_a1": "pending_single_doc_extract"},
            entity_article=_entity("tag_1", "pending_single_doc_extract"),
            entity_path=Path("entities/disease/tag_1.json"),
        )

        self.assertEqual(selected["article_status"], "insufficient_evidence_review")
        self.assertEqual(selected["source_stage"], "A3")
        self.assertTrue(selected["needs_review_before_publication"])
        self.assertIn("insufficient_evidence_review", selected["review_reasons"])

    def test_missing_source_marks_review_issue(self) -> None:
        selected = select_article_source(
            _status("tag_1", article_status="pending_single_doc_extract"),
            a4_draft=None,
            a3_input=None,
            entity_article=None,
            entity_path=Path("entities/disease/tag_1.json"),
        )

        self.assertEqual(selected["article_status"], "missing_article_source")
        self.assertTrue(selected["needs_review_before_publication"])
        self.assertEqual(selected["selection_issue"], "missing_article_source")


def _status(tag_id: str, *, article_status: str) -> dict[str, object]:
    return {
        "tag_id": tag_id,
        "canonical_tag_ru": "Тег",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "article_status": article_status,
        "documents_count": 1,
        "review_reasons": [],
        "publication_review_reasons": [],
    }


def _entity(tag_id: str, article_status: str) -> dict[str, object]:
    return {
        "tag_id": tag_id,
        "canonical_tag_ru": "Тег",
        "entity_type": "disease",
        "article_status": article_status,
        "content_format": "editorjs",
        "content": {"time": 0, "version": "2.28.0", "blocks": [{"type": "header", "data": {"text": "Тег", "level": 2}}]},
        "sources": {"source_doc_ids": ["doc_1"]},
        "documents_count": 1,
    }


def _a4_draft(tag_id: str, article_status: str) -> dict[str, object]:
    return {
        "tag_id": tag_id,
        "canonical_tag_ru": "Тег",
        "entity_type": "disease",
        "article_status": article_status,
        "content_format": "editorjs",
        "content": {"time": 0, "version": "2.28.0", "blocks": [{"type": "header", "data": {"text": "Тег", "level": 2}}]},
        "source_doc_ids": ["doc_1"],
        "source_documents_count": 1,
        "fact_group_ids": ["fg_1"],
        "used_fact_group_ids": ["fg_1"],
    }


if __name__ == "__main__":
    unittest.main()


from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kb_rebuild.articles.a1.entity_json import build_entity_json, entity_file_path


class ArticleA1EntityJsonTests(unittest.TestCase):
    def test_entity_json_has_required_fields_and_stub_editorjs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = _plan(strategy="stub_only", article_candidate=False)
            path = entity_file_path(Path(tmp), plan)
            entity = build_entity_json(plan=plan, article_status="stub_only", source_strategy="stub_only", entity_path=path)

            self.assertEqual(entity["tag_id"], "disease_a")
            self.assertEqual(entity["content_format"], "editorjs")
            self.assertEqual(entity["content"]["version"], "2.28.0")
            self.assertEqual(entity["content"]["blocks"][0]["type"], "header")
            self.assertIn("служебная карточка", entity["content"]["blocks"][1]["data"]["text"])

    def test_review_stub_content_has_no_review_reason_as_medical_fact(self) -> None:
        entity = build_entity_json(
            plan=_plan(strategy="review_stub", review_reasons=["alias_conflict"]),
            article_status="review_stub",
            source_strategy="review_stub",
            entity_path=Path("entity.json"),
        )

        text = "\n".join(block["data"].get("text", "") for block in entity["content"]["blocks"])
        self.assertNotIn("alias_conflict", text)
        self.assertEqual(entity["review_reasons"], ["alias_conflict"])

    def test_pending_extraction_content_is_valid_editorjs(self) -> None:
        entity = build_entity_json(
            plan=_plan(strategy="single_doc_extract"),
            article_status="pending_single_doc_extract",
            source_strategy="single_doc_extract",
            entity_path=Path("entity.json"),
        )

        self.assertEqual(entity["content"]["blocks"][0]["type"], "header")
        self.assertTrue(entity["content"]["blocks"][1]["data"]["text"])


def _plan(*, strategy: str, article_candidate: bool = True, review_reasons: list[str] | None = None) -> dict[str, object]:
    return {
        "tag_id": "disease_a",
        "canonical_tag_ru": "Астма",
        "canonical_tag_latin": "",
        "entity_type": "disease",
        "strategy": strategy,
        "article_candidate": article_candidate,
        "primary_role": "article_candidate" if article_candidate else "context_only",
        "mentions_count": 1,
        "documents_count": 1,
        "source_doc_ids": ["doc1"],
        "source_window_ids": ["win1"],
        "source_windows_count": 1,
        "review_reasons": review_reasons or [],
    }


if __name__ == "__main__":
    unittest.main()

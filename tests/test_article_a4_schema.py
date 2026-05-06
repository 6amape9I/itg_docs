from __future__ import annotations

import json
import unittest

from kb_rebuild.articles.a4.schema import parse_response_json, validate_batch_response
from kb_rebuild.articles.a4.schema import A4_RESPONSE_SCHEMA
from kb_rebuild.llm.gemini_schema import schema_for_gemini


class ArticleA4SchemaTests(unittest.TestCase):
    def test_valid_compiled_article_response_passes(self) -> None:
        normalized, errors = validate_batch_response(_response(), _batch())

        self.assertFalse(errors)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["articles"][0]["article_status"], "compiled_article")

    def test_unknown_task_id_fails(self) -> None:
        parsed = _response()
        parsed["articles"][0]["task_id"] = "unknown"

        normalized, errors = validate_batch_response(parsed, _batch())

        self.assertIsNone(normalized)
        self.assertTrue(any("unknown task_id" in error for error in errors))

    def test_unknown_fact_group_id_fails(self) -> None:
        parsed = _response()
        parsed["articles"][0]["used_fact_group_ids"] = ["fg_unknown"]

        normalized, errors = validate_batch_response(parsed, _batch())

        self.assertIsNone(normalized)
        self.assertTrue(any("unknown" in error for error in errors))

    def test_missing_editorjs_blocks_fails(self) -> None:
        parsed = _response()
        parsed["articles"][0]["content"]["blocks"] = []

        normalized, errors = validate_batch_response(parsed, _batch())

        self.assertIsNone(normalized)
        self.assertTrue(any("blocks must be a non-empty list" in error for error in errors))

    def test_content_block_without_source_fact_group_ids_fails(self) -> None:
        parsed = _response()
        parsed["articles"][0]["content"]["blocks"][1]["metadata"]["source_fact_group_ids"] = []
        parsed["articles"][0]["used_fact_group_ids"] = []

        normalized, errors = validate_batch_response(parsed, _batch())

        self.assertIsNone(normalized)
        self.assertTrue(any("must cite source_fact_group_ids" in error for error in errors))

    def test_review_flag_lost_fails(self) -> None:
        parsed = _response(status="compiled_with_review_flag", review=True)
        parsed["articles"][0]["needs_review_before_publication"] = False

        normalized, errors = validate_batch_response(parsed, _batch(review=True, strategy="compile_with_review_flag"))

        self.assertIsNone(normalized)
        self.assertTrue(any("preserve true input flag" in error for error in errors))

    def test_parse_response_json_strips_code_fence(self) -> None:
        parsed, errors = parse_response_json("```json\n" + json.dumps({"batch_id": "b", "articles": []}) + "\n```")

        self.assertFalse(errors)
        self.assertEqual(parsed["batch_id"], "b")

    def test_gemini_schema_keeps_title_property_name(self) -> None:
        schema = schema_for_gemini(A4_RESPONSE_SCHEMA)
        article_properties = schema["properties"]["articles"]["items"]["properties"]

        self.assertIn("title", article_properties)
        self.assertIn("summary", article_properties)


def _batch(*, review: bool = False, strategy: str = "compile_from_fact_groups") -> dict[str, object]:
    return {
        "batch_id": "a4batch_000001",
        "tasks": [
            {
                "task_id": "a4task_000000001",
                "tag_id": "tag_1",
                "canonical_tag_ru": "Тестовый тег",
                "a4_strategy": strategy,
                "fact_group_ids": ["fg_1"],
                "core_fact_group_ids": ["fg_1"],
                "needs_review_before_publication": review,
                "review_reasons": ["publication_review_required"] if review else [],
            }
        ],
    }


def _response(*, status: str = "compiled_article", review: bool = False) -> dict[str, object]:
    return {
        "batch_id": "a4batch_000001",
        "articles": [
            {
                "task_id": "a4task_000000001",
                "tag_id": "tag_1",
                "article_status": status,
                "title": "Тестовый тег",
                "summary": "Краткое описание.",
                "content": {
                    "time": 0,
                    "version": "2.28.0",
                    "blocks": [
                        {
                            "id": "block_001",
                            "type": "header",
                            "data": {"text": "Что это", "level": 2},
                            "metadata": {"source_fact_group_ids": []},
                        },
                        {
                            "id": "block_002",
                            "type": "paragraph",
                            "data": {"text": "Тестовый тег является примером."},
                            "metadata": {"source_fact_group_ids": ["fg_1"]},
                        },
                    ],
                },
                "used_fact_group_ids": ["fg_1"],
                "unused_fact_group_ids": [],
                "needs_review_before_publication": review,
                "review_reasons": ["publication_review_required"] if review else [],
                "confidence": 0.9,
                "reason": "",
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()

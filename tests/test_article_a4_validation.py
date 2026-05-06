from __future__ import annotations

import unittest

from kb_rebuild.articles.a4.validation import validate_article_response, validate_editorjs_content


class ArticleA4ValidationTests(unittest.TestCase):
    def test_valid_editorjs_article_passes(self) -> None:
        normalized, errors = validate_article_response(_article(), _task())

        self.assertFalse(errors)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["used_fact_group_ids"], ["fg_1"])

    def test_paragraph_without_sources_fails(self) -> None:
        content = _content()
        content["blocks"][1]["metadata"]["source_fact_group_ids"] = []

        normalized, errors = validate_editorjs_content(content, allowed_fact_ids={"fg_1"})

        self.assertIsNone(normalized)
        self.assertTrue(any("must cite source_fact_group_ids" in error for error in errors))

    def test_header_without_sources_allowed(self) -> None:
        content = _content()
        content["blocks"][0]["metadata"]["source_fact_group_ids"] = []

        normalized, errors = validate_editorjs_content(content, allowed_fact_ids={"fg_1"})

        self.assertFalse(errors)
        self.assertIsNotNone(normalized)

    def test_unsupported_fact_group_id_fails(self) -> None:
        article = _article()
        article["content"]["blocks"][1]["metadata"]["source_fact_group_ids"] = ["fg_unknown"]
        article["used_fact_group_ids"] = ["fg_unknown"]

        normalized, errors = validate_article_response(article, _task())

        self.assertIsNone(normalized)
        self.assertTrue(any("unknown" in error for error in errors))

    def test_empty_title_and_header_fail(self) -> None:
        article = _article()
        article["title"] = ""
        article["content"]["blocks"][0]["data"]["text"] = ""

        normalized, errors = validate_article_response(article, _task())

        self.assertIsNone(normalized)
        self.assertTrue(any("title must be non-empty" in error for error in errors))
        self.assertTrue(any("header.text must be non-empty" in error for error in errors))


def _task() -> dict[str, object]:
    return {
        "task_id": "a4task_000000001",
        "tag_id": "tag_1",
        "canonical_tag_ru": "Тестовый тег",
        "a4_strategy": "compile_from_fact_groups",
        "fact_group_ids": ["fg_1"],
        "core_fact_group_ids": ["fg_1"],
        "needs_review_before_publication": False,
        "review_reasons": [],
    }


def _article() -> dict[str, object]:
    return {
        "task_id": "a4task_000000001",
        "tag_id": "tag_1",
        "article_status": "compiled_article",
        "title": "Тестовый тег",
        "summary": "Краткое описание.",
        "content": _content(),
        "used_fact_group_ids": ["fg_1"],
        "unused_fact_group_ids": [],
        "needs_review_before_publication": False,
        "review_reasons": [],
        "confidence": 0.9,
        "reason": "",
    }


def _content() -> dict[str, object]:
    return {
        "time": 0,
        "version": "2.28.0",
        "blocks": [
            {"id": "block_001", "type": "header", "data": {"text": "Что это", "level": 2}, "metadata": {"source_fact_group_ids": []}},
            {
                "id": "block_002",
                "type": "paragraph",
                "data": {"text": "Тестовый тег является примером."},
                "metadata": {"source_fact_group_ids": ["fg_1"]},
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()

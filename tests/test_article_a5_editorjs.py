from __future__ import annotations

import unittest

from kb_rebuild.articles.a5.editorjs import DEFAULT_EDITORJS_VERSION, safe_review_stub_content, validate_editorjs_content


class ArticleA5EditorJSTests(unittest.TestCase):
    def test_valid_compiled_editorjs_passes(self) -> None:
        content, errors = validate_editorjs_content(
            {
                "time": 0,
                "blocks": [
                    {"type": "header", "data": {"text": "Что это", "level": 2}},
                    {"type": "paragraph", "data": {"text": "Тестовый текст."}},
                    {"type": "list", "data": {"items": ["Первый"]}},
                    {"type": "table", "data": {"content": [["А", "Б"]]}},
                ],
            }
        )

        self.assertFalse(errors)
        self.assertIsNotNone(content)
        self.assertEqual(content["version"], DEFAULT_EDITORJS_VERSION)

    def test_valid_stub_editorjs_passes(self) -> None:
        content, errors = validate_editorjs_content(safe_review_stub_content("Тег"))

        self.assertFalse(errors)
        self.assertIsNotNone(content)

    def test_empty_paragraph_fails(self) -> None:
        content, errors = validate_editorjs_content({"blocks": [{"type": "paragraph", "data": {"text": " "}}]})

        self.assertIsNone(content)
        self.assertTrue(any("paragraph.text" in error for error in errors))

    def test_list_requires_non_empty_items(self) -> None:
        content, errors = validate_editorjs_content({"blocks": [{"type": "list", "data": {"items": []}}]})

        self.assertIsNone(content)
        self.assertTrue(any("list.items" in error for error in errors))


if __name__ == "__main__":
    unittest.main()


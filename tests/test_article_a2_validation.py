from __future__ import annotations

import unittest

from kb_rebuild.articles.a2.validation import validate_quote


class ArticleA2QuoteValidationTests(unittest.TestCase):
    def test_exact_quote_passes(self) -> None:
        result = validate_quote("точная цитата", "До этого точная цитата после этого")

        self.assertEqual(result.status, "exact")

    def test_normalized_quote_passes(self) -> None:
        result = validate_quote("точная   цитата", "До этого точная\nцитата после этого")

        self.assertEqual(result.status, "normalized_exact")

    def test_stitched_quote_fails(self) -> None:
        text = "Первая часть содержит симптом. Между ними другой факт. Вторая часть содержит лечение."
        result = validate_quote("Первая часть содержит симптом Вторая часть содержит лечение", text)

        self.assertEqual(result.status, "not_found")

    def test_ellipsis_quote_fails(self) -> None:
        result = validate_quote("Первая часть ... Вторая часть", "Первая часть и Вторая часть")

        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.reason, "ellipsis_or_stitched_quote")

    def test_quote_from_different_window_fails(self) -> None:
        result = validate_quote("цитата из другого окна", "В этом окне другой текст")

        self.assertEqual(result.status, "not_found")


if __name__ == "__main__":
    unittest.main()


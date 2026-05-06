from __future__ import annotations

import unittest

from kb_rebuild.articles.a3.filtering import classify_evidence_item


class ArticleA3FilteringTests(unittest.TestCase):
    def test_exact_quote_direct_relevance_is_valid(self) -> None:
        item = _item(quote_validation_status="exact", relevance="direct")
        result = classify_evidence_item(item)

        self.assertEqual(result["a3_layer"], "valid")

    def test_normalized_exact_quote_is_valid(self) -> None:
        item = _item(quote_validation_status="normalized_exact", relevance="direct")
        result = classify_evidence_item(item)

        self.assertEqual(result["a3_layer"], "valid")

    def test_fuzzy_quote_goes_review(self) -> None:
        item = _item(quote_validation_status="fuzzy", relevance="direct")
        result = classify_evidence_item(item)

        self.assertEqual(result["a3_layer"], "review")
        self.assertIn("fuzzy_quote", result["a3_filter_reasons"])

    def test_not_found_quote_goes_rejected(self) -> None:
        item = _item(quote_validation_status="not_found", relevance="direct")
        result = classify_evidence_item(item)

        self.assertEqual(result["a3_layer"], "rejected")

    def test_related_entity_goes_review(self) -> None:
        item = _item(quote_validation_status="exact", relevance="direct", fact_type="related_entity")
        result = classify_evidence_item(item)

        self.assertEqual(result["a3_layer"], "review")

    def test_publication_review_with_exact_quote_remains_valid(self) -> None:
        item = _item(
            quote_validation_status="exact",
            relevance="direct",
            needs_review_before_publication=True,
            review_reasons=["publication_review"],
        )
        result = classify_evidence_item(item)

        self.assertEqual(result["a3_layer"], "valid")
        self.assertIn("publication_review_required", result["a3_filter_reasons"])


def _item(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "evidence_item_id": "ev_1",
        "task_id": "task_1",
        "tag_id": "tag_1",
        "canonical_tag_ru": "Тег",
        "entity_type": "disease",
        "fact_type": "definition",
        "claim": "Тестовый факт.",
        "quote": "Тестовая цитата.",
        "quote_validation_status": "exact",
        "relevance": "direct",
        "importance": "high",
        "confidence": 0.9,
        "window_quality": "high",
        "needs_review_before_publication": False,
        "review_reasons": [],
    }
    row.update(overrides)
    return row


if __name__ == "__main__":
    unittest.main()


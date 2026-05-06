from __future__ import annotations

import unittest

from kb_rebuild.articles.a3.dedupe import dedupe_evidence, normalize_text
from kb_rebuild.articles.a3.grouping import build_fact_groups


class ArticleA3DedupeTests(unittest.TestCase):
    def test_exact_duplicate_evidence_removed(self) -> None:
        first = _item("ev_1", claim="Ёж — факт.", quote=" Цитата — один. ")
        second = _item("ev_2", claim="еж - факт", quote="Цитата - один")

        deduped, duplicates = dedupe_evidence([first, second])

        self.assertEqual(len(deduped), 1)
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(deduped[0]["original_evidence_item_ids"], ["ev_1", "ev_2"])

    def test_same_quote_different_claim_grouped(self) -> None:
        items = [_item("ev_1", claim="Первый claim", quote="Одна цитата"), _item("ev_2", claim="Другой claim", quote="Одна цитата")]

        groups = build_fact_groups(items)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["evidence_items_count"], 2)

    def test_same_claim_different_quotes_grouped_as_multi_source(self) -> None:
        items = [
            _item("ev_1", claim="Одинаковый claim", quote="Цитата один", doc_id="doc_1"),
            _item("ev_2", claim="Одинаковый claim", quote="Цитата два", doc_id="doc_2"),
        ]

        groups = build_fact_groups(items)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["source_documents_count"], 2)

    def test_different_numeric_values_are_not_merged(self) -> None:
        items = [
            _item("ev_1", claim="Доза составляет 5 мг.", quote="Доза составляет 5 мг."),
            _item("ev_2", claim="Доза составляет 10 мг.", quote="Доза составляет 10 мг."),
        ]

        groups = build_fact_groups(items)

        self.assertEqual(len(groups), 2)

    def test_normalize_keeps_medical_numbers(self) -> None:
        self.assertIn("25", normalize_text(" 25 мг — Доза "))


def _item(evidence_id: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "evidence_item_id": evidence_id,
        "task_id": f"task_{evidence_id}",
        "tag_id": "tag_1",
        "canonical_tag_ru": "Тег",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "fact_type": "definition",
        "section_hint": "Что это",
        "claim": "Claim",
        "quote": "Quote",
        "quote_validation_status": "exact",
        "importance": "high",
        "confidence": 0.9,
        "relevance": "direct",
        "doc_id": "doc_1",
        "window_id": "win_1",
        "a3_layer": "valid",
        "a3_filter_reasons": [],
        "needs_review_before_publication": False,
        "review_reasons": [],
    }
    row.update(overrides)
    return row


if __name__ == "__main__":
    unittest.main()


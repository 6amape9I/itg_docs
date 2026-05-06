from __future__ import annotations

import unittest

from kb_rebuild.articles.a3.grouping import build_fact_groups


class ArticleA3GroupingTests(unittest.TestCase):
    def test_groups_only_inside_same_tag_and_fact_type(self) -> None:
        groups = build_fact_groups(
            [
                _item("ev_1", tag_id="tag_1", fact_type="definition"),
                _item("ev_2", tag_id="tag_2", fact_type="definition"),
                _item("ev_3", tag_id="tag_1", fact_type="treatment"),
            ]
        )

        self.assertEqual(len(groups), 3)

    def test_representative_claim_selected_from_existing_claim(self) -> None:
        groups = build_fact_groups([_item("ev_1", claim="Первый claim"), _item("ev_2", claim="Первый claim")])

        self.assertIn(groups[0]["representative_claim"], {"Первый claim"})

    def test_representative_quote_never_uses_fuzzy_when_exact_exists(self) -> None:
        groups = build_fact_groups(
            [
                _item("ev_1", quote="Fuzzy quote", quote_validation_status="fuzzy", a3_layer="review"),
                _item("ev_2", quote="Exact quote", quote_validation_status="exact", a3_layer="valid"),
            ]
        )

        self.assertEqual(groups[0]["representative_quote_validation_status"], "exact")

    def test_fuzzy_only_group_is_review_only(self) -> None:
        groups = build_fact_groups([_item("ev_1", quote_validation_status="fuzzy", a3_layer="review")])

        self.assertFalse(groups[0]["usable_for_a4"])
        self.assertEqual(groups[0]["a4_usage"], "review_only")

    def test_exact_plus_fuzzy_remains_usable_but_review_flagged(self) -> None:
        groups = build_fact_groups(
            [
                _item("ev_1", quote="Shared quote", quote_validation_status="exact", a3_layer="valid"),
                _item("ev_2", quote="Shared quote", quote_validation_status="fuzzy", a3_layer="review"),
            ]
        )

        self.assertTrue(groups[0]["usable_for_a4"])
        self.assertTrue(groups[0]["needs_review_before_publication"])
        self.assertIn("fuzzy_quote_evidence_present", groups[0]["review_reasons"])


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
        "claim": "Одинаковый claim",
        "quote": "Одинаковая цитата",
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


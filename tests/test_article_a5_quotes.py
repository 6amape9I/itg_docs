from __future__ import annotations

import unittest

from kb_rebuild.articles.a5.quotes import build_companion_quotes


class ArticleA5QuotesTests(unittest.TestCase):
    def test_compiled_article_creates_quotes_from_used_fact_groups(self) -> None:
        companion = build_companion_quotes(
            _article("compiled_article", used_fact_group_ids=["fg_1"]),
            fact_groups_by_id={"fg_1": _fact_group("fg_1", "definition")},
            source_fact_groups_path="fact_groups.jsonl",
            source_article_path="article.json",
        )

        self.assertEqual(companion["quotes_source_status"], "from_a3_fact_groups")
        self.assertEqual(len(companion["quotes"]), 1)
        self.assertEqual(companion["questions"][0]["question"], "Что такое Тег?")

    def test_invalid_quote_status_is_skipped(self) -> None:
        companion = build_companion_quotes(
            _article("compiled_article", used_fact_group_ids=["fg_1"]),
            fact_groups_by_id={"fg_1": _fact_group("fg_1", "definition", quote_status="fuzzy")},
            source_fact_groups_path="fact_groups.jsonl",
            source_article_path="article.json",
        )

        self.assertEqual(companion["quotes_source_status"], "empty_or_unavailable")
        self.assertEqual(companion["quotes"], [])

    def test_direct_copy_has_pending_manual_status(self) -> None:
        companion = build_companion_quotes(
            _article("direct_copy_article"),
            fact_groups_by_id={},
            source_fact_groups_path="fact_groups.jsonl",
            source_article_path="article.json",
        )

        self.assertEqual(companion["quotes_source_status"], "direct_copy_no_fact_groups")
        self.assertEqual(companion["questions_generation_status"], "pending_fact_extraction_or_manual")

    def test_duplicate_questions_get_section_suffix(self) -> None:
        companion = build_companion_quotes(
            _article("compiled_article", used_fact_group_ids=["fg_1", "fg_2"]),
            fact_groups_by_id={"fg_1": _fact_group("fg_1", "definition"), "fg_2": _fact_group("fg_2", "definition", section="Диагностика")},
            source_fact_groups_path="fact_groups.jsonl",
            source_article_path="article.json",
        )

        questions = [row["question"] for row in companion["questions"]]
        self.assertEqual(len(set(questions)), 2)
        self.assertIn("разделе «Диагностика»", questions[1])


def _article(status: str, *, used_fact_group_ids: list[str] | None = None) -> dict[str, object]:
    return {
        "tag_id": "tag_1",
        "canonical_tag_ru": "Тег",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "article_status": status,
        "needs_review_before_publication": False,
        "review_reasons": [],
        "sources": {"used_fact_group_ids": used_fact_group_ids or []},
    }


def _fact_group(fact_group_id: str, fact_type: str, *, quote_status: str = "exact", section: str = "Что это") -> dict[str, object]:
    return {
        "fact_group_id": fact_group_id,
        "fact_type": fact_type,
        "representative_claim": "Тег является тестовым.",
        "representative_quote": "Тег является тестовым.",
        "representative_quote_validation_status": quote_status,
        "source_doc_ids": ["doc_1"],
        "source_window_ids": ["win_1"],
        "section_hint": section,
        "usable_for_a4": True,
        "needs_review_before_publication": False,
    }


if __name__ == "__main__":
    unittest.main()


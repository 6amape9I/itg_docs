from __future__ import annotations

import unittest

from kb_rebuild.articles.a1.models import A1Config
from kb_rebuild.articles.a1.strategy_repair import repair_plan_row


class ArticleA1StrategyRepairTests(unittest.TestCase):
    def test_review_stub_alias_conflict_only_reroutes_to_extraction(self) -> None:
        row = _plan(strategy="review_stub", documents_count=2, review_reasons=["alias_conflict"])
        repaired = repair_plan_row(row, {}, A1Config())

        self.assertEqual(repaired["strategy"], "low_count_batch_extract")
        self.assertTrue(repaired["strategy_adjusted"])
        self.assertTrue(repaired["needs_review_before_publication"])
        self.assertEqual(repaired["publication_review_reasons"], ["alias_conflict"])

    def test_drug_policy_review_stays_review_stub(self) -> None:
        row = _plan(strategy="review_stub", review_reasons=["drug_policy_review"])
        repaired = repair_plan_row(row, {}, A1Config())

        self.assertEqual(repaired["strategy"], "review_stub")
        self.assertTrue(repaired["needs_review_before_article"])
        self.assertEqual(repaired["article_blocking_review_reasons"], ["drug_policy_review"])

    def test_merge_conflict_stays_review_stub(self) -> None:
        row = _plan(strategy="review_stub", review_reasons=["merge_conflict"])
        repaired = repair_plan_row(row, {}, A1Config())

        self.assertEqual(repaired["strategy"], "review_stub")
        self.assertEqual(repaired["article_blocking_review_reasons"], ["merge_conflict"])

    def test_context_only_article_candidate_false_stays_stub_only(self) -> None:
        row = _plan(strategy="stub_only", article_candidate=False, primary_role="context_only", source_windows_count=1)
        repaired = repair_plan_row(row, {}, A1Config())

        self.assertEqual(repaired["strategy"], "stub_only")
        self.assertFalse(repaired["strategy_adjusted"])


def _plan(
    *,
    strategy: str,
    article_candidate: bool = True,
    primary_role: str = "article_candidate",
    documents_count: int = 1,
    source_windows_count: int = 1,
    review_reasons: list[str] | None = None,
) -> dict[str, object]:
    return {
        "tag_id": "disease_a",
        "canonical_tag_ru": "Астма",
        "entity_type": "disease",
        "strategy": strategy,
        "article_candidate": article_candidate,
        "primary_role": primary_role,
        "documents_count": documents_count,
        "source_windows_count": source_windows_count,
        "source_window_ids": ["win1"],
        "review_reasons": review_reasons or [],
        "needs_review_before_article": strategy == "review_stub",
        "competing_article_candidate_tags_in_doc": 0,
    }


if __name__ == "__main__":
    unittest.main()

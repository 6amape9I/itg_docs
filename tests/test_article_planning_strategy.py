from __future__ import annotations

import unittest

from kb_rebuild.articles.planning.matching import AliasTerm
from kb_rebuild.articles.planning.models import A0Config
from kb_rebuild.articles.planning.strategy import select_strategy


class ArticlePlanningStrategyTests(unittest.TestCase):
    def test_context_only_becomes_stub_only(self) -> None:
        decision = select_strategy(
            config=A0Config(),
            source_index=_source(article_candidate=False, primary_role="context_only"),
            windows=[],
            aliases=[],
            doc_by_id={},
            article_candidate_tags_by_doc={},
        )

        self.assertEqual(decision.strategy, "stub_only")

    def test_critical_need_review_becomes_review_stub(self) -> None:
        decision = select_strategy(
            config=A0Config(),
            source_index=_source(need_review=True, review_reasons=["alias_conflict"]),
            windows=[_window()],
            aliases=[],
            doc_by_id={},
            article_candidate_tags_by_doc={},
        )

        self.assertEqual(decision.strategy, "review_stub")

    def test_clean_singleton_can_be_direct_copy_candidate(self) -> None:
        decision = select_strategy(
            config=A0Config(),
            source_index=_source(),
            windows=[_window(coverage=0.95)],
            aliases=[AliasTerm("астма", "Астма", "canonical", True)],
            doc_by_id={"doc1": {"doc_id": "doc1", "name": "Астма"}},
            article_candidate_tags_by_doc={"doc1": {"disease_a"}},
        )

        self.assertEqual(decision.strategy, "direct_copy_candidate")

    def test_singleton_mixed_doc_uses_single_doc_extract(self) -> None:
        decision = select_strategy(
            config=A0Config(),
            source_index=_source(),
            windows=[_window(coverage=0.95)],
            aliases=[AliasTerm("астма", "Астма", "canonical", True)],
            doc_by_id={"doc1": {"doc_id": "doc1", "name": "Астма"}},
            article_candidate_tags_by_doc={"doc1": {"disease_a", "disease_b"}},
        )

        self.assertEqual(decision.strategy, "single_doc_extract")

    def test_low_count_and_high_frequency_rules(self) -> None:
        low = select_strategy(
            config=A0Config(low_count_doc_threshold=3, high_frequency_doc_threshold=20),
            source_index=_source(documents_count=3, source_doc_ids=["d1", "d2", "d3"]),
            windows=[_window()],
            aliases=[],
            doc_by_id={},
            article_candidate_tags_by_doc={},
        )
        high = select_strategy(
            config=A0Config(low_count_doc_threshold=3, high_frequency_doc_threshold=20),
            source_index=_source(documents_count=21, source_doc_ids=[str(i) for i in range(21)]),
            windows=[_window()],
            aliases=[],
            doc_by_id={},
            article_candidate_tags_by_doc={},
        )

        self.assertEqual(low.strategy, "low_count_batch_extract")
        self.assertEqual(high.strategy, "high_frequency_map_reduce")

    def test_article_candidate_with_mentions_but_no_windows_is_review(self) -> None:
        decision = select_strategy(
            config=A0Config(),
            source_index=_source(mentions_count=1),
            windows=[],
            aliases=[],
            doc_by_id={},
            article_candidate_tags_by_doc={},
        )

        self.assertEqual(decision.strategy, "no_source_window_review")


def _source(
    *,
    article_candidate: bool = True,
    need_review: bool = False,
    primary_role: str = "article_candidate",
    review_reasons: list[str] | None = None,
    mentions_count: int = 1,
    documents_count: int = 1,
    source_doc_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "tag_id": "disease_a",
        "canonical_tag_ru": "Астма",
        "article_candidate": article_candidate,
        "need_review": need_review,
        "primary_role": primary_role,
        "review_reasons": review_reasons or [],
        "mentions_count": mentions_count,
        "documents_count": documents_count,
        "source_doc_ids": source_doc_ids or ["doc1"],
    }


def _window(*, coverage: float = 0.4) -> dict[str, object]:
    return {
        "window_id": "win_1",
        "window_quality": "high",
        "match_method": "alias_match",
        "coverage_ratio_estimate": coverage,
    }


if __name__ == "__main__":
    unittest.main()

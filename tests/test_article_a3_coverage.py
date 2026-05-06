from __future__ import annotations

import unittest

from kb_rebuild.articles.a3.coverage import build_tag_outputs


class ArticleA3CoverageTests(unittest.TestCase):
    def test_tag_fact_group_index_includes_all_a1_tags(self) -> None:
        statuses = [_status("tag_1"), _status("tag_2")]

        tag_index, a4_input, _, _ = build_tag_outputs(
            status_rows=statuses,
            task_results=[],
            valid_evidence=[],
            review_evidence=[],
            rejected_evidence=[],
            fact_groups=[],
        )

        self.assertEqual(len(tag_index), 2)
        self.assertEqual(len(a4_input), 2)

    def test_pending_tag_without_usable_evidence_goes_insufficient_review(self) -> None:
        statuses = [_status("tag_1", article_status="pending_single_doc_extract", a2_extraction_tasks_count=1)]

        tag_index, _, without_usable, _ = build_tag_outputs(
            status_rows=statuses,
            task_results=[{"task_id": "task_1", "tag_id": "tag_1"}],
            valid_evidence=[],
            review_evidence=[],
            rejected_evidence=[],
            fact_groups=[],
        )

        self.assertEqual(tag_index[0]["a4_strategy"], "insufficient_evidence_review")
        self.assertEqual(len(without_usable), 1)

    def test_direct_copy_goes_direct_copy_already_done(self) -> None:
        statuses = [_status("tag_1", article_status="direct_copy_article")]

        tag_index, _, _, _ = build_tag_outputs(
            status_rows=statuses,
            task_results=[],
            valid_evidence=[],
            review_evidence=[],
            rejected_evidence=[],
            fact_groups=[],
        )

        self.assertEqual(tag_index[0]["a4_strategy"], "direct_copy_already_done")

    def test_stub_and_review_stub_preserved(self) -> None:
        statuses = [_status("tag_1", article_status="stub_only"), _status("tag_2", article_status="review_stub")]

        tag_index, _, _, _ = build_tag_outputs(
            status_rows=statuses,
            task_results=[],
            valid_evidence=[],
            review_evidence=[],
            rejected_evidence=[],
            fact_groups=[],
        )

        self.assertEqual(tag_index[0]["a4_strategy"], "stub_only")
        self.assertEqual(tag_index[1]["a4_strategy"], "review_stub")


def _status(tag_id: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "tag_id": tag_id,
        "canonical_tag_ru": "Тег",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "article_status": "pending_single_doc_extract",
        "article_candidate": True,
        "a2_extraction_tasks_count": 0,
        "needs_review_before_publication": False,
        "review_reasons": [],
        "publication_review_reasons": [],
    }
    row.update(overrides)
    return row


if __name__ == "__main__":
    unittest.main()


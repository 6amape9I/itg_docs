from __future__ import annotations

import unittest

from kb_rebuild.articles.a1.task_queue import build_tasks_for_plan


class ArticleA1TaskQueueTests(unittest.TestCase):
    def test_extraction_task_created_for_single_doc(self) -> None:
        tasks, next_number = build_tasks_for_plan(
            plan=_plan("single_doc_extract"),
            source_strategy="single_doc_extract",
            article_status="pending_single_doc_extract",
            windows_by_id={"win1": _window()},
            next_task_number=1,
        )

        self.assertEqual(next_number, 2)
        self.assertEqual(tasks[0]["task_id"], "a2task_000000001")
        self.assertEqual(tasks[0]["priority"], "high")
        self.assertTrue(tasks[0]["window_text"])
        self.assertEqual(tasks[0]["block_ids"], ["b1"])

    def test_tasks_created_for_low_multi_high_strategies(self) -> None:
        for strategy, status in (
            ("low_count_batch_extract", "pending_low_count_batch_extract"),
            ("multi_doc_map_reduce", "pending_multi_doc_map_reduce"),
            ("high_frequency_map_reduce", "pending_high_frequency_map_reduce"),
        ):
            tasks, _ = build_tasks_for_plan(
                plan=_plan(strategy),
                source_strategy=strategy,
                article_status=status,
                windows_by_id={"win1": _window()},
                next_task_number=1,
            )
            self.assertEqual(len(tasks), 1)

    def test_no_tasks_for_stub_review_or_direct_copy(self) -> None:
        for strategy, status in (
            ("stub_only", "stub_only"),
            ("review_stub", "review_stub"),
            ("direct_copy_candidate", "direct_copy_article"),
        ):
            tasks, _ = build_tasks_for_plan(
                plan=_plan(strategy),
                source_strategy=strategy,
                article_status=status,
                windows_by_id={"win1": _window()},
                next_task_number=1,
            )
            self.assertEqual(tasks, [])

    def test_low_quality_window_has_low_priority_and_review_flag(self) -> None:
        tasks, _ = build_tasks_for_plan(
            plan=_plan("single_doc_extract"),
            source_strategy="single_doc_extract",
            article_status="pending_single_doc_extract",
            windows_by_id={"win1": _window(quality="low")},
            next_task_number=1,
        )

        self.assertEqual(tasks[0]["priority"], "low")
        self.assertTrue(tasks[0]["needs_review_before_publication"])
        self.assertIn("low_quality_source_window", tasks[0]["review_reasons"])


def _plan(strategy: str) -> dict[str, object]:
    return {
        "tag_id": "disease_a",
        "canonical_tag_ru": "Астма",
        "entity_type": "disease",
        "strategy": strategy,
        "article_candidate": True,
        "needs_review_before_article": False,
        "needs_review_before_publication": False,
        "source_window_ids": ["win1"],
    }


def _window(*, quality: str = "high") -> dict[str, object]:
    return {
        "window_id": "win1",
        "doc_id": "doc1",
        "document_name": "Астма",
        "window_text": "Астма текст",
        "window_char_length": 10,
        "block_ids": ["b1"],
        "block_indexes": [0],
        "heading_context": [],
        "match_method": "quote_match",
        "window_quality": quality,
    }


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from kb_rebuild.articles.a2.batch_builder import build_batches, filter_tasks


class ArticleA2BatchBuilderTests(unittest.TestCase):
    def test_groups_tasks_by_entity_strategy_priority(self) -> None:
        tasks = [
            _task("a2task_000000001", "disease", "single_doc_extract", "high"),
            _task("a2task_000000002", "disease", "single_doc_extract", "low"),
            _task("a2task_000000003", "symptom", "single_doc_extract", "high"),
        ]
        batches = build_batches(tasks, max_tasks_per_batch=8, batch_char_limit=10000)

        self.assertEqual([batch["batch_group_key"] for batch in batches], [
            "disease:single_doc_extract:high",
            "disease:single_doc_extract:low",
            "symptom:single_doc_extract:high",
        ])

    def test_respects_max_tasks_per_batch_and_ids_are_deterministic(self) -> None:
        tasks = [_task(f"a2task_{index:09d}", "disease", "single_doc_extract", "high") for index in range(1, 6)]
        batches = build_batches(tasks, max_tasks_per_batch=2, batch_char_limit=10000)

        self.assertEqual([batch["batch_id"] for batch in batches], ["a2batch_000001", "a2batch_000002", "a2batch_000003"])
        self.assertEqual([batch["tasks_count"] for batch in batches], [2, 2, 1])
        self.assertEqual(sum(batch["tasks_count"] for batch in batches), len(tasks))

    def test_respects_batch_char_limit(self) -> None:
        tasks = [
            _task("a2task_000000001", "disease", "single_doc_extract", "high", window_text="A" * 3000),
            _task("a2task_000000002", "disease", "single_doc_extract", "high", window_text="B" * 3000),
        ]
        batches = build_batches(tasks, max_tasks_per_batch=8, batch_char_limit=6500)

        self.assertEqual(len(batches), 2)
        self.assertEqual([task_id for batch in batches for task_id in batch["task_ids"]], [
            "a2task_000000001",
            "a2task_000000002",
        ])

    def test_filter_tasks_applies_filters_and_completed_ids(self) -> None:
        tasks = [
            _task("a2task_000000001", "disease", "single_doc_extract", "high"),
            _task("a2task_000000002", "disease", "multi_doc_map_reduce", "low"),
            _task("a2task_000000003", "disease", "single_doc_extract", "medium"),
        ]
        selected = filter_tasks(
            tasks,
            strategy_filter=("single_doc_extract",),
            priority_filter=("high", "medium"),
            completed_task_ids={"a2task_000000001"},
            limit=10,
        )

        self.assertEqual([task["task_id"] for task in selected], ["a2task_000000003"])


def _task(
    task_id: str,
    entity_type: str,
    strategy: str,
    priority: str,
    *,
    window_text: str = "Текст окна",
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "tag_id": f"tag_{task_id}",
        "canonical_tag_ru": "Тест",
        "entity_type": entity_type,
        "source_strategy": strategy,
        "priority": priority,
        "window_text": window_text,
        "estimated_input_chars": len(window_text),
    }


if __name__ == "__main__":
    unittest.main()


from __future__ import annotations

import unittest

from kb_rebuild.articles.a4.task_builder import build_compilation_tasks, select_fact_groups


class ArticleA4TaskBuilderTests(unittest.TestCase):
    def test_builds_tasks_only_for_compilable_ready_strategies(self) -> None:
        inputs = [
            _a4_input("tag_1", "compile_from_fact_groups", ["fg_1"]),
            _a4_input("tag_2", "compile_with_review_flag", ["fg_2"], review=True),
            _a4_input("tag_3", "direct_copy_already_done", ["fg_3"]),
            _a4_input("tag_4", "stub_only", ["fg_4"], ready=False),
            _a4_input("tag_5", "review_stub", ["fg_5"], ready=False),
            _a4_input("tag_6", "insufficient_evidence_review", ["fg_6"], ready=False),
        ]
        tasks = build_compilation_tasks(
            a4_inputs=inputs,
            fact_groups=[_fact("fg_1", "tag_1"), _fact("fg_2", "tag_2")],
            limit=None,
            strategy_filter=("compile_from_fact_groups", "compile_with_review_flag"),
            entity_type_filter=None,
            priority_filter=("high", "medium", "low"),
            max_fact_groups_per_tag=10,
            max_quotes_per_tag=10,
        )

        self.assertEqual([task["tag_id"] for task in tasks], ["tag_1", "tag_2"])
        self.assertEqual(tasks[1]["review_reasons"], ["publication_review_required"])

    def test_respects_max_fact_groups_per_tag_and_core_before_supporting(self) -> None:
        row = _a4_input("tag_1", "compile_from_fact_groups", ["fg_support", "fg_core", "fg_low"])
        groups = {
            row["fact_group_id"]: row
            for row in [
                _fact("fg_support", "tag_1", usage="supporting_fact", importance="high"),
                _fact("fg_core", "tag_1", usage="core_fact", importance="medium"),
                _fact("fg_low", "tag_1", usage="supporting_fact", importance="low"),
            ]
        }

        selected, excluded = select_fact_groups(row, fact_groups_by_id=groups, max_fact_groups=2, max_quotes=10)

        self.assertEqual([group["fact_group_id"] for group in selected], ["fg_core", "fg_support"])
        self.assertEqual(excluded, ["fg_low"])

    def test_resume_skips_completed_tag(self) -> None:
        tasks = build_compilation_tasks(
            a4_inputs=[_a4_input("tag_1", "compile_from_fact_groups", ["fg_1"])],
            fact_groups=[_fact("fg_1", "tag_1")],
            limit=None,
            strategy_filter=("compile_from_fact_groups", "compile_with_review_flag"),
            entity_type_filter=None,
            priority_filter=("high", "medium", "low"),
            max_fact_groups_per_tag=10,
            max_quotes_per_tag=10,
            completed_task_tag_ids={"tag_1"},
        )

        self.assertEqual(tasks, [])


def _a4_input(
    tag_id: str,
    strategy: str,
    fact_group_ids: list[str],
    *,
    ready: bool = True,
    review: bool = False,
) -> dict[str, object]:
    return {
        "tag_id": tag_id,
        "canonical_tag_ru": "Тестовый тег",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "a4_strategy": strategy,
        "ready_for_a4": ready,
        "article_status_from_a1": "pending",
        "needs_review_before_publication": review,
        "review_reasons": ["publication_review_required"] if review else [],
        "fact_group_ids": fact_group_ids,
        "source_documents_count": 1,
    }


def _fact(
    fact_group_id: str,
    tag_id: str,
    *,
    usage: str = "core_fact",
    importance: str = "high",
) -> dict[str, object]:
    return {
        "fact_group_id": fact_group_id,
        "tag_id": tag_id,
        "canonical_tag_ru": "Тестовый тег",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "fact_type": "definition",
        "section_hint": "Что это",
        "representative_claim": "Тестовый тег является примером.",
        "representative_quote": "Тестовый тег является примером.",
        "representative_quote_validation_status": "exact",
        "source_doc_ids": ["doc_1"],
        "source_documents_count": 1,
        "confidence": 0.9,
        "importance": importance,
        "a4_usage": usage,
        "usable_for_a4": True,
    }


if __name__ == "__main__":
    unittest.main()

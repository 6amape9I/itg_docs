from __future__ import annotations

from itertools import combinations
import unittest

from kb_rebuild.normalization.n2.grouping import build_candidate_groups
from kb_rebuild.normalization.n2.scope_conflict import extract_subtype_markers
from tests.test_normalization_n2_features import _node
from tests.test_normalization_n2_grouping import _pair


class NormalizationN22SubtypeConflictTests(unittest.TestCase):
    def test_different_type_markers_are_subtype_conflicts(self) -> None:
        examples = [
            ("Дефицит кофактора молибдена тип A", "Дефицит кофактора молибдена тип B"),
            ("Сахарный диабет 1 типа", "Сахарный диабет 2 типа"),
            ("Редкое заболевание подтип 1", "Редкое заболевание подтип 2"),
            ("Недостаточность комплекса I", "Недостаточность комплекса II"),
            ("Детский В-клеточный острый лимфобластный лейкоз", "Детский Т-клеточный острый лимфобластный лейкоз"),
            ("Катаракта 2 множественных типов", "Катаракта 3 множественных типов"),
        ]

        for left, right in examples:
            with self.subTest(left=left, right=right):
                group = _disease_group([left, right])

                self.assertEqual(group.candidate_group_status, "subtype_conflict")
                self.assertFalse(group.n3_ready)

    def test_base_vs_subtype_is_subtype_conflict(self) -> None:
        group = _disease_group(["Сахарный диабет", "Сахарный диабет 1 типа"])

        self.assertEqual(group.candidate_group_status, "subtype_conflict")
        self.assertIn("base_vs_subtype_conflict", group.quality_gate_flags)
        self.assertFalse(group.n3_ready)

    def test_same_subtype_marker_can_remain_n3_ready(self) -> None:
        labels = ["Сахарный диабет 1 типа", "Сахарный диабет типа 1", "Диабет 1-го типа"]

        group = _disease_group(labels)

        self.assertEqual(group.candidate_group_status, "n3_candidate")
        self.assertTrue(group.n3_ready)
        self.assertEqual(group.subtype_markers, ["type_1"])
        self.assertFalse(group.quality_gate_flags)

    def test_subtype_extractor_handles_type_word_order(self) -> None:
        self.assertEqual(extract_subtype_markers("Сахарный диабет типа 1"), {"type_1"})
        self.assertEqual(extract_subtype_markers("Катаракта 2 множественных типов"), {"type_2"})


def _disease_group(labels: list[str]):
    nodes = [_node(f"n{index}", "disease", label) for index, label in enumerate(labels, start=1)]
    pairs = [
        _pair(
            f"p{left_index}_{right_index}",
            f"n{left_index}",
            f"n{right_index}",
            left,
            right,
            status="candidate",
            reasons=["high_sequence_similarity"],
            clean_reasons=["high_sequence_similarity_without_scope_conflict"],
            score=0.9,
            entity_type="disease",
        )
        for (left_index, left), (right_index, right) in combinations(enumerate(labels, start=1), 2)
    ]
    groups = build_candidate_groups(nodes, pairs, [], high_priority_score=0.88)
    return groups[0]


if __name__ == "__main__":
    unittest.main()

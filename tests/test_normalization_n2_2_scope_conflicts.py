from __future__ import annotations

import unittest

from kb_rebuild.normalization.n2.grouping import build_candidate_groups
from kb_rebuild.normalization.n2.scope_conflict import scope_conflict_reasons
from tests.test_normalization_n2_features import _node
from tests.test_normalization_n2_grouping import _pair


class NormalizationN22ScopeConflictTests(unittest.TestCase):
    def test_disease_location_conflicts_are_not_n3_ready(self) -> None:
        examples = [
            ("Герминогенная опухоль яичка", "Герминогенная опухоль яичника"),
            ("Полип матки", "Полип носа"),
            ("Рак желудка", "Рак молочной железы"),
            ("Абсцесс печени", "Абсцесс лёгкого"),
        ]

        for left, right in examples:
            with self.subTest(left=left, right=right):
                group = _candidate_group("disease", left, right)

                self.assertEqual(group.candidate_group_status, "location_scope_conflict")
                self.assertIn("disease_location_conflict", group.quality_gate_flags)
                self.assertFalse(group.n3_ready)

    def test_diagnostic_method_scope_conflicts_are_detected(self) -> None:
        examples = [
            ("Рентгенография позвоночника", "Рентгенологическое исследование"),
            ("КТ и МРТ орбиты", "Магнитно-резонансная томография"),
            ("Биопсия кожи", "Биопсия"),
        ]

        for left, right in examples:
            with self.subTest(left=left, right=right):
                reasons = scope_conflict_reasons(
                    _node("n1", "diagnostic_method", left),
                    _node("n2", "diagnostic_method", right),
                )

                self.assertTrue(any("diagnostic_method" in reason for reason in reasons))
                group = _blocked_group("diagnostic_method", left, right, reasons)
                self.assertEqual(group.candidate_group_status, "location_scope_conflict")
                self.assertFalse(group.n3_ready)

    def test_base_diagnostic_aliases_do_not_create_scope_conflict(self) -> None:
        self.assertEqual(
            scope_conflict_reasons(
                _node("n1", "diagnostic_method", "МРТ"),
                _node("n2", "diagnostic_method", "Магнитно-резонансная томография"),
            ),
            [],
        )
        self.assertEqual(
            scope_conflict_reasons(
                _node("n1", "diagnostic_method", "КТ"),
                _node("n2", "diagnostic_method", "Компьютерная томография"),
            ),
            [],
        )

    def test_procedure_object_conflicts_are_detected(self) -> None:
        reasons = scope_conflict_reasons(
            _node("n1", "procedure", "Операция на сердце"),
            _node("n2", "procedure", "Операция на печени"),
        )

        self.assertEqual(reasons, ["procedure_object_scope_conflict"])


def _candidate_group(entity_type: str, left_label: str, right_label: str):
    groups = build_candidate_groups(
        [_node("n1", entity_type, left_label), _node("n2", entity_type, right_label)],
        [
            _pair(
                "p1",
                "n1",
                "n2",
                left_label,
                right_label,
                status="candidate",
                reasons=["high_sequence_similarity"],
                clean_reasons=["high_sequence_similarity_without_scope_conflict"],
                score=0.9,
                entity_type=entity_type,
            )
        ],
        [],
        high_priority_score=0.88,
    )
    return groups[0]


def _blocked_group(entity_type: str, left_label: str, right_label: str, blocking: list[str]):
    groups = build_candidate_groups(
        [_node("n1", entity_type, left_label), _node("n2", entity_type, right_label)],
        [],
        [
            _pair(
                "p1",
                "n1",
                "n2",
                left_label,
                right_label,
                status="blocked",
                blocking=blocking,
                score=0.9,
                entity_type=entity_type,
            )
        ],
        high_priority_score=0.88,
    )
    return groups[0]


if __name__ == "__main__":
    unittest.main()

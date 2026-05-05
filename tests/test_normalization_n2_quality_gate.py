from __future__ import annotations

import unittest

from kb_rebuild.normalization.n2.grouping import build_candidate_groups
from kb_rebuild.normalization.n2.report import build_quality_gate
from tests.test_normalization_n2_features import _node
from tests.test_normalization_n2_grouping import _pair


class NormalizationN2QualityGateTests(unittest.TestCase):
    def test_clean_group_passes_quality_gate(self) -> None:
        groups = build_candidate_groups(
            [_node("n1", "diagnostic_method", "Полимеразная цепная реакция"), _node("n2", "diagnostic_method", "ПЦР")],
            [_pair("p1", "n1", "n2", "Полимеразная цепная реакция", "ПЦР", reasons=["abbreviation_match"])],
            [],
            high_priority_score=0.88,
        )

        gate = build_quality_gate(groups)

        self.assertTrue(gate["passed"])
        self.assertEqual(gate["n3_candidate_groups_total"], 1)

    def test_unsafe_group_is_not_counted_as_recommended(self) -> None:
        groups = build_candidate_groups(
            [_node("n1", "diagnostic_method", "МРТ"), _node("n2", "diagnostic_method", "МРТ гипофиза")],
            [],
            [
                _pair(
                    "p1",
                    "n1",
                    "n2",
                    "МРТ",
                    "МРТ гипофиза",
                    status="blocked",
                    blocking=["diagnostic_method_scope_conflict", "parent_child_blocked", "parent_child_suspect"],
                )
            ],
            high_priority_score=0.88,
        )

        gate = build_quality_gate(groups)

        self.assertTrue(gate["passed"])
        self.assertEqual(gate["n3_candidate_groups_total"], 0)
        self.assertEqual(groups[0].candidate_group_status, "location_scope_conflict")


if __name__ == "__main__":
    unittest.main()

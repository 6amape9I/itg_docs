from __future__ import annotations

import unittest

from kb_rebuild.normalization.n2.grouping import build_candidate_groups
from kb_rebuild.normalization.n2.report import build_quality_gate
from tests.test_normalization_n2_features import _node
from tests.test_normalization_n2_grouping import _pair


class NormalizationN22QualityGateTests(unittest.TestCase):
    def test_low_score_sequence_similarity_is_not_n3_ready(self) -> None:
        group = _single_group(
            "disease",
            "Редкая болезнь A",
            "Редкая болезнь B",
            score=0.6,
            reasons=["high_sequence_similarity"],
            clean_reasons=["high_sequence_similarity_without_scope_conflict"],
        )

        self.assertEqual(group.candidate_group_status, "quality_score_rejected")
        self.assertFalse(group.n3_ready)
        self.assertIn("score_below_n3_threshold_without_hard_alias_reason", group.quality_gate_flags)

    def test_low_score_known_safe_abbreviation_is_not_n3_ready(self) -> None:
        group = _single_group(
            "diagnostic_method",
            "Магнитно-резонансная томография",
            "МРТ",
            score=0.45,
            reasons=["abbreviation_match"],
            clean_reasons=["known_safe_abbreviation_match"],
        )

        self.assertEqual(group.candidate_group_status, "quality_score_rejected")
        self.assertFalse(group.n3_ready)
        self.assertIn("score_below_n3_threshold_without_hard_alias_reason", group.quality_gate_flags)

    def test_low_score_explicit_parenthetical_alias_can_be_n3_ready(self) -> None:
        group = _single_group(
            "supplement",
            "HVP (Эйч Ви Пи)",
            "HVP",
            score=0.6,
            reasons=["parenthetical_alias_match"],
            clean_reasons=["explicit_parenthetical_alias_match"],
        )

        self.assertEqual(group.candidate_group_status, "n3_candidate")
        self.assertTrue(group.n3_ready)
        self.assertTrue(group.hard_alias_reason)
        self.assertTrue(group.score_gate_passed)

    def test_normal_score_clean_reason_is_n3_ready(self) -> None:
        group = _single_group(
            "disease",
            "Болезнь Аддисона",
            "Аддисонова болезнь",
            score=0.72,
            reasons=["high_sequence_similarity"],
            clean_reasons=["high_sequence_similarity_without_scope_conflict"],
        )

        self.assertEqual(group.candidate_group_status, "n3_candidate")
        self.assertTrue(group.n3_ready)

    def test_hard_exact_disease_modifier_exception_is_not_gate_violation(self) -> None:
        group = _single_group(
            "disease",
            "ОРВИ",
            "Острая респираторная вирусная инфекция",
            score=0.6,
            reasons=["exact_normalized_match"],
            clean_reasons=["canonical_alias_exact_match"],
            risks=["disease_modifier_mismatch"],
        )

        gate = build_quality_gate([group])

        self.assertEqual(group.candidate_group_status, "n3_candidate")
        self.assertTrue(group.n3_ready)
        self.assertEqual(gate["n3_groups_with_disease_modifier_mismatch"], 0)
        self.assertTrue(gate["passed"])


def _single_group(
    entity_type: str,
    left_label: str,
    right_label: str,
    *,
    score: float,
    reasons: list[str],
    clean_reasons: list[str],
    risks: list[str] | None = None,
):
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
                reasons=reasons,
                clean_reasons=clean_reasons,
                risks=risks,
                score=score,
                entity_type=entity_type,
            )
        ],
        [],
        high_priority_score=0.88,
    )
    return groups[0]


if __name__ == "__main__":
    unittest.main()

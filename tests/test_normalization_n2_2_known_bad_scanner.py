from __future__ import annotations

from dataclasses import replace
import unittest

from kb_rebuild.normalization.n2.grouping import build_candidate_groups
from kb_rebuild.normalization.n2.report import build_quality_gate, find_known_bad_n3_matches
from tests.test_normalization_n2_features import _node
from tests.test_normalization_n2_grouping import _pair


class NormalizationN22KnownBadScannerTests(unittest.TestCase):
    def test_known_bad_n3_group_fails_quality_gate(self) -> None:
        groups = _groups_for_labels("Врожденный гипотиреоз", "Герпетический энцефалит")

        matches = find_known_bad_n3_matches(groups)
        gate = build_quality_gate(groups, known_bad_matches=matches)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["reason"], "known_bad_n3_pattern")
        self.assertEqual(gate["n3_groups_matching_known_bad_examples"], 1)
        self.assertFalse(gate["passed"])

    def test_known_bad_scanner_ignores_non_n3_group(self) -> None:
        group = replace(_groups_for_labels("Анемия хронических заболеваний", "Желудочковые аритмии")[0], n3_ready=False)

        self.assertEqual(find_known_bad_n3_matches([group]), [])


def _groups_for_labels(left_label: str, right_label: str):
    return build_candidate_groups(
        [_node("n1", "disease", left_label), _node("n2", "disease", right_label)],
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
                entity_type="disease",
            )
        ],
        [],
        high_priority_score=0.88,
    )


if __name__ == "__main__":
    unittest.main()

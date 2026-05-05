from __future__ import annotations

from dataclasses import replace
import unittest

from kb_rebuild.normalization.n2.grouping import build_candidate_groups
from kb_rebuild.normalization.n2.models import CandidatePair
from tests.test_normalization_n2_features import _node


class NormalizationN2GroupingTests(unittest.TestCase):
    def test_transitive_conflict_does_not_create_unsafe_group(self) -> None:
        nodes = [_node("n1", "disease", "A"), _node("n2", "disease", "B"), _node("n3", "disease", "C")]
        pairs = [
            _pair("p1", "n1", "n2", "A", "B"),
            _pair("p2", "n2", "n3", "B", "C"),
        ]

        groups = build_candidate_groups(nodes, pairs, [], high_priority_score=0.88)

        self.assertEqual(len(groups), 2)
        self.assertTrue(all(len(group.node_ids) == 2 for group in groups))

    def test_high_priority_group_generated(self) -> None:
        nodes = [_node("n1", "diagnostic_method", "Иммуноферментный анализ"), _node("n2", "diagnostic_method", "ИФА")]
        groups = build_candidate_groups(
            nodes,
            [_pair("p1", "n1", "n2", "Иммуноферментный анализ", "ИФА", reasons=["abbreviation_match"])],
            [],
            high_priority_score=0.88,
        )

        self.assertEqual(groups[0].group_priority, "high")
        self.assertEqual(groups[0].entity_type, "diagnostic_method")

    def test_blocked_pair_becomes_blocked_review_group(self) -> None:
        nodes = [
            _node("n1", "microorganism", "Escherichia"),
            _node("n2", "microorganism", "Escherichia coli"),
        ]
        groups = build_candidate_groups(
            nodes,
            [],
            [_pair("p1", "n1", "n2", "Escherichia", "Escherichia coli", status="blocked", blocking=["taxonomic_level_conflict"])],
            high_priority_score=0.88,
        )

        self.assertEqual(groups[0].group_priority, "blocked_review")
        self.assertEqual(groups[0].candidate_group_status, "blocked_review")
        self.assertFalse(groups[0].recommended_for_n3)

    def test_group_counts_deduplicate_overlapping_mentions(self) -> None:
        base = replace(
            _node("n1", "drug_trade_name", "Берлиприл"),
            mention_ids=["m1", "m2"],
            mentions_count=2,
            article_candidate_count=2,
        )
        alias = replace(
            _node("n2", "drug_trade_name", "Берлиприл 10"),
            mention_ids=["m2"],
            mentions_count=1,
            article_candidate_count=1,
        )

        groups = build_candidate_groups(
            [base, alias],
            [_pair("p1", "n1", "n2", "Берлиприл", "Берлиприл 10", reasons=["product_variant_match"])],
            [],
            high_priority_score=0.88,
        )

        self.assertEqual(groups[0].mentions_count, 2)
        self.assertEqual(groups[0].article_candidate_count, 2)

    def test_ambiguous_abbreviation_group_not_n3_ready(self) -> None:
        nodes = [_node("n1", "diagnostic_method", "Квантифероновый тест"), _node("n2", "diagnostic_method", "Компьютерная томография")]
        groups = build_candidate_groups(
            nodes,
            [
                _pair(
                    "p1",
                    "n1",
                    "n2",
                    "Квантифероновый тест",
                    "Компьютерная томография",
                    status="low_confidence_candidate",
                    reasons=["abbreviation_match"],
                    clean_reasons=[],
                    weak_reasons=["ambiguous_abbreviation_match"],
                    risks=["ambiguous_abbreviation"],
                )
            ],
            [],
            high_priority_score=0.88,
        )

        self.assertEqual(groups[0].candidate_group_status, "ambiguous_abbreviation")
        self.assertFalse(groups[0].n3_ready)

    def test_hub_protection_demotes_large_parent_child_pattern(self) -> None:
        nodes = [_node("n0", "diagnostic_method", "МРТ")] + [
            _node(f"n{index}", "diagnostic_method", f"МРТ объект {index}") for index in range(1, 8)
        ]
        pairs = [
            _pair(
                f"p{index}",
                "n0",
                f"n{index}",
                "МРТ",
                f"МРТ объект {index}",
                reasons=["high_sequence_similarity"],
                clean_reasons=["high_sequence_similarity_without_scope_conflict"],
            )
            for index in range(1, 8)
        ]

        groups = build_candidate_groups(nodes, pairs, [], high_priority_score=0.88)

        self.assertTrue(any(group.candidate_group_status == "hub_parent_child_suspect" for group in groups))
        self.assertFalse(any(group.n3_ready for group in groups if "n0" in group.node_ids))


def _pair(
    pair_id: str,
    left: str,
    right: str,
    left_label: str,
    right_label: str,
    *,
    status: str = "high_priority_candidate",
    reasons: list[str] | None = None,
    clean_reasons: list[str] | None = None,
    weak_reasons: list[str] | None = None,
    risks: list[str] | None = None,
    blocking: list[str] | None = None,
) -> CandidatePair:
    candidate_reasons = reasons or ["high_sequence_similarity"]
    inferred_clean = clean_reasons if clean_reasons is not None else _clean_reasons_for(candidate_reasons)
    blocking_reasons = blocking or []
    return CandidatePair(
        pair_id=pair_id,
        left_node_id=left,
        right_node_id=right,
        entity_type="diagnostic_method" if "ИФА" in right_label else "disease" if left_label in {"A", "B"} else "microorganism",
        left_label=left_label,
        right_label=right_label,
        score=0.9,
        pair_status=status,
        candidate_reasons=candidate_reasons,
        clean_candidate_reasons=inferred_clean,
        weak_candidate_reasons=weak_reasons or [],
        risk_reasons=risks or [],
        blocking_reasons=blocking_reasons,
        candidate_quality="n3_ready" if status != "blocked" and inferred_clean and not blocking_reasons else status,
        scope_conflict_reasons=[reason for reason in blocking_reasons if "scope" in reason],
        abbreviation_source=["known_dictionary"] if "abbreviation_match" in candidate_reasons else [],
        generic_alias_match=False,
        n3_pair_ready=status != "blocked" and bool(inferred_clean) and not blocking_reasons,
        metrics={},
    )


def _clean_reasons_for(candidate_reasons: list[str]) -> list[str]:
    clean: list[str] = []
    if "abbreviation_match" in candidate_reasons:
        clean.append("known_safe_abbreviation_match")
    if "product_variant_match" in candidate_reasons:
        clean.append("product_variant_match")
    if "high_sequence_similarity" in candidate_reasons:
        clean.append("high_sequence_similarity_without_scope_conflict")
    return clean


if __name__ == "__main__":
    unittest.main()

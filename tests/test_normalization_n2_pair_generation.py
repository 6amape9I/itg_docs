from __future__ import annotations

import unittest

from kb_rebuild.normalization.n2.pair_generation import build_candidate_nodes, generate_candidate_pairs
from tests.test_normalization_n2_features import _node


class NormalizationN2PairGenerationTests(unittest.TestCase):
    def test_pairs_only_inside_entity_type(self) -> None:
        warnings: list[str] = []
        candidate, blocked, rejected = generate_candidate_pairs(
            [_node("n1", "disease", "Гастрит"), _node("n2", "symptom", "Гастрит")],
            min_score=0.72,
            high_priority_score=0.88,
            max_pairs_per_type=100,
            warnings=warnings,
        )

        self.assertEqual(candidate, [])
        self.assertEqual(blocked, [])
        self.assertEqual(rejected, [])

    def test_high_priority_pair_created_for_abbreviation(self) -> None:
        warnings: list[str] = []
        candidate, _, _ = generate_candidate_pairs(
            [_node("n1", "diagnostic_method", "Иммуноферментный анализ"), _node("n2", "diagnostic_method", "ИФА")],
            min_score=0.72,
            high_priority_score=0.88,
            max_pairs_per_type=100,
            warnings=warnings,
        )

        self.assertEqual(len(candidate), 1)
        self.assertEqual(candidate[0].pair_status, "high_priority_candidate")
        self.assertIn("abbreviation_match", candidate[0].candidate_reasons)

    def test_low_score_pair_rejected(self) -> None:
        warnings: list[str] = []
        _, _, rejected = generate_candidate_pairs(
            [_node("n1", "procedure", "альфа тест"), _node("n2", "procedure", "альфа процедура")],
            min_score=0.72,
            high_priority_score=0.88,
            max_pairs_per_type=100,
            warnings=warnings,
        )

        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].pair_status, "rejected_low_score")

    def test_blocked_pairs_written_separately(self) -> None:
        warnings: list[str] = []
        candidate, blocked, _ = generate_candidate_pairs(
            [
                _node("n1", "disease", "Сахарный диабет 1 типа", subtype_signature="type_1"),
                _node("n2", "disease", "Сахарный диабет 2 типа", subtype_signature="type_2"),
            ],
            min_score=0.72,
            high_priority_score=0.88,
            max_pairs_per_type=100,
            warnings=warnings,
        )

        self.assertEqual(candidate, [])
        self.assertEqual(len(blocked), 1)
        self.assertIn("disease_subtype_conflict", blocked[0].blocking_reasons)

    def test_product_review_cluster_expands_variant_alias_nodes(self) -> None:
        cluster = {
            "auto_cluster_id": "ac_000001",
            "entity_type": "drug_trade_name",
            "auto_cluster_key": "drug_trade_name::берлиприл",
            "canonical_display_candidate": "Берлиприл",
            "canonical_latin_candidate": "Berlipril",
            "aliases": ["Берлиприл", "Берлиприл 10", "Берлиприл 20 мг"],
            "normalized_aliases": ["берлиприл", "берлиприл 10", "берлиприл 20 мг"],
            "mention_ids": ["m1", "m2", "m3"],
            "documents_count": 3,
            "mentions_count": 3,
            "article_candidate_count": 3,
            "context_only_count": 0,
            "folder_candidate_count": 0,
            "risk_flags": ["contains_dosage", "possible_numeric_dosage_variant"],
            "routing_flags": ["article_candidate"],
            "cluster_status": "review_group",
            "merge_allowed": False,
        }
        mentions = [
            _mention("m1", "doc_1", "Берлиприл"),
            _mention("m2", "doc_2", "Берлиприл 10"),
            _mention("m3", "doc_3", "Берлиприл 20 мг"),
        ]

        nodes = build_candidate_nodes([cluster], mentions)
        variant_nodes = [node for node in nodes if node.cluster_status == "product_variant_alias"]

        self.assertEqual([node.label for node in variant_nodes], ["Берлиприл 10", "Берлиприл 20 мг"])
        self.assertEqual(variant_nodes[0].aliases, ["Берлиприл 10"])
        self.assertEqual(variant_nodes[0].mention_ids, ["m2"])

        warnings: list[str] = []
        candidate, blocked, rejected = generate_candidate_pairs(
            nodes,
            min_score=0.72,
            high_priority_score=0.88,
            max_pairs_per_type=100,
            warnings=warnings,
        )

        self.assertEqual(blocked, [])
        self.assertEqual(rejected, [])
        self.assertTrue(any("product_variant_match" in pair.candidate_reasons for pair in candidate))


def _mention(mention_id: str, doc_id: str, label: str) -> dict[str, object]:
    normalized = label.lower().replace("ё", "е")
    return {
        "mention_id": mention_id,
        "doc_id": doc_id,
        "document_name": label,
        "article_candidate": True,
        "tag_role": "article_candidate",
        "routing_flags": ["article_candidate"],
        "normalized": {
            "primary_norm": normalized,
            "candidate_ru_norm": normalized,
            "surface_norm": normalized,
        },
        "raw": {
            "canonical_candidate_ru": label,
            "surface": label,
        },
    }


if __name__ == "__main__":
    unittest.main()

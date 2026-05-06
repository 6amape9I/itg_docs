from __future__ import annotations

import unittest

from kb_rebuild.normalization.n4.canonical import canonical_tag_id, choose_canonical
from kb_rebuild.normalization.n4.models import FinalComponent, MergeEdge


class NormalizationN4CanonicalTests(unittest.TestCase):
    def test_choose_canonical_prefers_high_confidence_n3(self) -> None:
        component = FinalComponent(
            component_id="fc1",
            auto_cluster_ids=["ac1", "ac2"],
            entity_type="disease",
            edges=[
                _edge("n3c1", "Старое название", 0.8),
                _edge("n3c2", "Болезнь Аддисона", 0.99, latin="Addison disease"),
            ],
        )

        ru, latin, reasons = choose_canonical(component, {"ac1": _cluster("Аддисонова болезнь"), "ac2": _cluster("Болезнь Аддисона")})

        self.assertEqual(ru, "Болезнь Аддисона")
        self.assertEqual(latin, "Addison disease")
        self.assertIn("n3_canonical_ru_conflict", reasons)

    def test_choose_canonical_falls_back_to_auto_cluster(self) -> None:
        component = FinalComponent(component_id="fc1", auto_cluster_ids=["ac1"], entity_type="disease")

        ru, latin, reasons = choose_canonical(component, {"ac1": _cluster("Миопатия", latin="Myopathy")})

        self.assertEqual(ru, "Миопатия")
        self.assertEqual(latin, "Myopathy")
        self.assertEqual(reasons, [])

    def test_product_canonical_strips_dosage(self) -> None:
        component = FinalComponent(component_id="fc1", auto_cluster_ids=["ac1"], entity_type="drug_trade_name")

        ru, _, _ = choose_canonical(component, {"ac1": _cluster("Бетасерк 24 мг")})

        self.assertEqual(ru, "Бетасерк")

    def test_tag_id_is_deterministic(self) -> None:
        first = canonical_tag_id("disease", "Болезнь Аддисона", "Addison disease", ["аддисонова болезнь"])
        second = canonical_tag_id("disease", "Болезнь Аддисона", "Addison disease", ["аддисонова болезнь"])

        self.assertEqual(first, second)
        self.assertRegex(first, r"^disease_[0-9a-f]{10}$")


def _cluster(label: str, *, latin: str = "") -> dict[str, object]:
    return {
        "canonical_display_candidate": label,
        "canonical_latin_candidate": latin,
        "mentions_count": 1,
        "documents_count": 1,
        "article_candidate_count": 1,
        "confidence_stats": {"avg": 0.95},
    }


def _edge(n3_cluster_id: str, canonical_ru: str, confidence: float, *, latin: str = "") -> MergeEdge:
    return MergeEdge(
        n3_cluster_id=n3_cluster_id,
        source_candidate_group_id="cg1",
        entity_type="disease",
        node_ids=("n1", "n2"),
        auto_cluster_ids=("ac1", "ac2"),
        confidence=confidence,
        labels=("Аддисонова болезнь", "Болезнь Аддисона"),
        canonical_tag_ru=canonical_ru,
        canonical_tag_latin=latin,
        from_split=False,
        reason="",
    )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from kb_rebuild.normalization.n2.features import abbreviation_match, parenthetical_alias_match, score_pair_features
from kb_rebuild.normalization.n2.models import CandidateNode


class NormalizationN2FeaturesTests(unittest.TestCase):
    def test_exact_normalized_labels_score_high(self) -> None:
        pair = score_pair_features(_node("n1", "disease", "Гастрит"), _node("n2", "disease", "гастрит"))

        self.assertGreaterEqual(pair.score, 0.8)
        self.assertIn("exact_normalized_match", pair.candidate_reasons)

    def test_typo_labels_score_moderate(self) -> None:
        pair = score_pair_features(_node("n1", "disease", "гастрит"), _node("n2", "disease", "гастритт"))

        self.assertIn("high_sequence_similarity", pair.candidate_reasons)
        self.assertGreater(pair.score, 0.1)

    def test_abbreviation_detection(self) -> None:
        self.assertTrue(abbreviation_match(_node("n1", "diagnostic_method", "Иммуноферментный анализ"), _node("n2", "diagnostic_method", "ИФА")))
        self.assertTrue(abbreviation_match(_node("n1", "diagnostic_method", "Полимеразная цепная реакция"), _node("n2", "diagnostic_method", "ПЦР")))
        self.assertTrue(abbreviation_match(_node("n1", "diagnostic_method", "Магнитно-резонансная томография"), _node("n2", "diagnostic_method", "МРТ")))

    def test_parenthetical_alias_match(self) -> None:
        self.assertTrue(parenthetical_alias_match(_node("n1", "disease", "Вирус папилломы человека (ВПЧ)"), _node("n2", "disease", "ВПЧ")))

    def test_shared_latin_candidate(self) -> None:
        pair = score_pair_features(
            _node("n1", "disease", "Болезнь Ли-Фраумени", latin_label="li-fraumeni syndrome"),
            _node("n2", "disease", "Синдром Ли-Фраумени", latin_label="Li-Fraumeni syndrome"),
        )

        self.assertIn("shared_latin_candidate", pair.candidate_reasons)

    def test_product_variant_match(self) -> None:
        pair = score_pair_features(
            _node("n1", "drug_trade_name", "Берлиприл", product_key="берлиприл"),
            _node("n2", "drug_trade_name", "Берлиприл 20 мг", product_key="берлиприл"),
        )

        self.assertIn("product_variant_match", pair.candidate_reasons)


def _node(
    node_id: str,
    entity_type: str,
    label: str,
    *,
    latin_label: str = "",
    product_key: str = "",
    subtype_signature: str = "none",
    risk_flags: list[str] | None = None,
) -> CandidateNode:
    normalized = label.lower().replace("ё", "е")
    return CandidateNode(
        node_id=node_id,
        auto_cluster_id=node_id.replace("n", "ac"),
        entity_type=entity_type,
        label=label,
        normalized_label=normalized,
        latin_label=latin_label.lower(),
        aliases=[label],
        normalized_aliases=[normalized],
        mention_ids=[f"m_{node_id}"],
        documents=[{"doc_id": f"doc_{node_id}", "document_name": label}],
        mentions_count=1,
        documents_count=1,
        article_candidate_count=1,
        context_only_count=0,
        folder_candidate_count=0,
        risk_flags=risk_flags or [],
        routing_flags=["article_candidate"],
        cluster_status="isolated_mention",
        merge_allowed=False,
        subtype_signature=subtype_signature,
        product_key=product_key,
    )


if __name__ == "__main__":
    unittest.main()

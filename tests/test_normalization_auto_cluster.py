from __future__ import annotations

import unittest

from kb_rebuild.normalization.auto_cluster import build_auto_cluster_key, build_auto_clusters
from kb_rebuild.normalization.mentions import normalize_mention
from kb_rebuild.normalization.models import TagMention


class NormalizationAutoClusterTests(unittest.TestCase):
    def test_identical_normalized_disease_merges(self) -> None:
        mentions = [
            normalize_mention(_mention("m_0000001_00", "doc_1", "Ахондроплазия.", "Ахондроплазия", "disease")),
            normalize_mention(_mention("m_0000002_00", "doc_2", "ахондроплазия", "ахондроплазия", "disease")),
        ]
        clusters = build_auto_clusters(mentions)

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].mentions_count, 2)
        self.assertEqual(clusters[0].auto_cluster_key, "disease::ахондроплазия")

    def test_different_entity_types_do_not_merge(self) -> None:
        mentions = [
            normalize_mention(_mention("m_0000001_00", "doc_1", "Гастрит", "Гастрит", "disease")),
            normalize_mention(_mention("m_0000002_00", "doc_2", "Гастрит", "Гастрит", "symptom")),
        ]

        self.assertEqual(len(build_auto_clusters(mentions)), 2)

    def test_drug_dosage_variants_merge_by_product_norm(self) -> None:
        mentions = [
            normalize_mention(
                _mention(
                    "m_0000001_00",
                    "doc_1",
                    "Вольтарен эмульгель гель для наружного применения 2%",
                    "Вольтарен эмульгель гель для наружного применения 2%",
                    "drug_trade_name",
                )
            ),
            normalize_mention(
                _mention("m_0000002_00", "doc_2", "Вольтарен эмульгель", "Вольтарен эмульгель", "drug_trade_name")
            ),
        ]
        clusters = build_auto_clusters(mentions)

        self.assertEqual(len(clusters), 1)
        self.assertEqual(build_auto_cluster_key(mentions[0]), "drug_trade_name::вольтарен эмульгель")

    def test_specific_disease_terms_keep_distinct_keys(self) -> None:
        mentions = [
            normalize_mention(_mention("m_0000001_00", "doc_1", "Гастрит", "Гастрит", "disease")),
            normalize_mention(_mention("m_0000002_00", "doc_2", "Хронический гастрит", "Хронический гастрит", "disease")),
        ]
        clusters = build_auto_clusters(mentions)

        self.assertEqual(len(clusters), 2)
        self.assertTrue(any(cluster.review_required for cluster in clusters))

    def test_abbreviation_is_review_required_and_not_auto_merged(self) -> None:
        mentions = [
            normalize_mention(_mention("m_0000001_00", "doc_1", "ИФА", "ИФА", "diagnostic_method")),
            normalize_mention(_mention("m_0000002_00", "doc_2", "ифа", "ифа", "diagnostic_method")),
        ]
        clusters = build_auto_clusters(mentions)

        self.assertEqual(len(clusters), 2)
        self.assertTrue(all(cluster.review_required for cluster in clusters))

    def test_microorganism_genus_and_species_do_not_merge(self) -> None:
        mentions = [
            normalize_mention(_mention("m_0000001_00", "doc_1", "Escherichia", "Escherichia", "microorganism")),
            normalize_mention(_mention("m_0000002_00", "doc_2", "Escherichia coli", "Escherichia coli", "microorganism")),
        ]

        self.assertEqual(len(build_auto_clusters(mentions)), 2)


def _mention(
    mention_id: str,
    doc_id: str,
    surface: str,
    canonical_candidate_ru: str,
    entity_type: str,
    *,
    confidence: float = 0.95,
) -> TagMention:
    return TagMention(
        mention_id=mention_id,
        doc_id=doc_id,
        document_name=surface,
        entity_index=0,
        surface=surface,
        canonical_candidate_ru=canonical_candidate_ru,
        canonical_candidate_latin="",
        entity_type=entity_type,
        tag_role="article_candidate",
        article_candidate=True,
        is_primary=True,
        confidence=confidence,
        evidence_quotes=[surface],
        quote_validation_status="all_exact",
        quote_validation_details=[],
        provider="gemini_direct",
        model="gemini-3-flash-preview",
        prompt_version="tagging_v2_gemini",
        schema_version="document_tagging_v2",
        source_file="tags.jsonl",
    )


if __name__ == "__main__":
    unittest.main()

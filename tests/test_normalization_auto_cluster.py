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
        self.assertEqual(clusters[0].canonical_display_candidate, "Вольтарен эмульгель")

    def test_product_canonical_display_prefers_clean_alias(self) -> None:
        mentions = [
            normalize_mention(_mention("m_0000001_00", "doc_1", "Берлиприл 20 мг", "Берлиприл 20 мг", "drug_trade_name")),
            normalize_mention(_mention("m_0000002_00", "doc_2", "Берлиприл 5 мг", "Берлиприл 5 мг", "drug_trade_name")),
            normalize_mention(_mention("m_0000003_00", "doc_3", "Берлиприл", "Берлиприл", "drug_trade_name")),
        ]
        clusters = build_auto_clusters(mentions)

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].canonical_display_candidate, "Берлиприл")

    def test_trailing_numeric_product_variants_group_for_review(self) -> None:
        mentions = [
            normalize_mention(_mention("m_0000001_00", "doc_1", "Берлиприл 10", "Берлиприл 10", "drug_trade_name")),
            normalize_mention(_mention("m_0000002_00", "doc_2", "Берлиприл 20", "Берлиприл 20", "drug_trade_name")),
        ]
        clusters = build_auto_clusters(mentions)

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].auto_cluster_key, "drug_trade_name::берлиприл")
        self.assertEqual(clusters[0].cluster_status, "review_group")
        self.assertFalse(clusters[0].merge_allowed)
        self.assertIn("possible_numeric_dosage_variant", clusters[0].blocking_flags)

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

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].cluster_status, "review_group")
        self.assertFalse(clusters[0].merge_allowed)
        self.assertIn("very_short_alias", clusters[0].blocking_flags)
        self.assertIn("possible_abbreviation", clusters[0].blocking_flags)

    def test_short_alias_review_group_does_not_duplicate_rows(self) -> None:
        mentions = [
            normalize_mention(_mention("m_0000001_00", "doc_1", "ARX", "ARX", "biological_substance")),
            normalize_mention(_mention("m_0000002_00", "doc_2", "ARX", "ARX", "biological_substance")),
            normalize_mention(_mention("m_0000003_00", "doc_3", "ARX", "ARX", "biological_substance")),
        ]
        clusters = build_auto_clusters(mentions)

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].auto_cluster_key, "biological_substance::arx")
        self.assertEqual(clusters[0].mentions_count, 3)
        self.assertEqual(clusters[0].cluster_status, "review_group")
        self.assertIn("very_short_alias", clusters[0].blocking_flags)

    def test_disease_subtype_keys_are_distinct_and_reviewed(self) -> None:
        mentions = [
            normalize_mention(_mention("m_0000001_00", "doc_1", "GM1 ганглиозидоз", "GM1 ганглиозидоз", "disease")),
            normalize_mention(_mention("m_0000002_00", "doc_2", "GM1 ганглиозидоз тип 1", "GM1 ганглиозидоз тип 1", "disease")),
            normalize_mention(_mention("m_0000003_00", "doc_3", "GM1 ганглиозидоз тип 2", "GM1 ганглиозидоз тип 2", "disease")),
        ]
        keys = [build_auto_cluster_key(mention) for mention in mentions]
        clusters = build_auto_clusters(mentions)

        self.assertEqual(len(set(keys)), 3)
        self.assertIn("disease::gm1 ганглиозидоз тип 1::type_1", keys)
        self.assertIn("disease::gm1 ганглиозидоз тип 2::type_2", keys)
        reviewed = [cluster for cluster in clusters if "has_type_subtype_marker" in cluster.risk_flags]
        self.assertEqual(len(reviewed), 2)
        self.assertTrue(all(cluster.review_required for cluster in reviewed))

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

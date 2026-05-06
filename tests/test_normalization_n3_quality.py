import unittest

from kb_rebuild.normalization.n3.quality import build_quality_diagnostics, find_known_bad_accepted_clusters


def _cluster(labels: list[str], entity_type: str = "disease") -> dict:
    return {
        "n3_cluster_id": "n3c_000001",
        "source_candidate_group_id": "cg_test",
        "entity_type": entity_type,
        "canonical_tag_ru": labels[0],
        "labels": labels,
        "node_ids": [f"n{index}" for index, _ in enumerate(labels, start=1)],
    }


class NormalizationN3QualityTests(unittest.TestCase):
    def test_known_bad_accepted_cluster_fails_quality(self) -> None:
        diagnostics = build_quality_diagnostics(
            accepted_clusters=[_cluster(["Стеноз гортани", "Стеноз пищевода"])],
            split_groups=[],
        )

        self.assertFalse(diagnostics["passed"])
        self.assertEqual(diagnostics["known_bad_accepted_clusters"], 1)

    def test_hepatitis_variants_fail_quality(self) -> None:
        matches = find_known_bad_accepted_clusters([_cluster(["Вирус гепатита A", "Вирус гепатита B"], "microorganism")])

        self.assertTrue(any(item["reason"] == "hepatitis_variant_conflict" for item in matches))

    def test_hepatitis_d_and_delta_alias_passes_quality(self) -> None:
        matches = find_known_bad_accepted_clusters([_cluster(["Вирус гепатита D", "Вирус гепатита дельта"], "microorganism")])

        self.assertFalse(any(item["reason"] == "hepatitis_variant_conflict" for item in matches))

    def test_streptococcus_groups_fail_quality(self) -> None:
        matches = find_known_bad_accepted_clusters(
            [_cluster(["Стрептококк группы A", "Стрептококки группы B"], "microorganism")]
        )

        self.assertTrue(any(item["reason"] == "streptococcus_group_conflict" for item in matches))

    def test_rbc_supplement_mix_fails_quality(self) -> None:
        matches = find_known_bad_accepted_clusters(
            [_cluster(["Жевательный кальций RBC", "Железо RBC"], "supplement")]
        )

        self.assertTrue(any(item["reason"] == "rbc_supplement_conflict" for item in matches))

    def test_rbc_same_product_variants_pass_quality(self) -> None:
        matches = find_known_bad_accepted_clusters(
            [_cluster(["Железо rbc", "Железо(RBC)"], "supplement")]
        )

        self.assertFalse(any(item["reason"] == "rbc_supplement_conflict" for item in matches))

    def test_split_with_covered_nodes_passes_quality(self) -> None:
        diagnostics = build_quality_diagnostics(
            accepted_clusters=[],
            split_groups=[
                {
                    "input_node_ids": ["n1", "n2", "n3"],
                    "subclusters": [
                        {"node_ids": ["n1", "n2"]},
                        {"node_ids": ["n3"]},
                    ],
                    "rejected_labels": [],
                }
            ],
        )

        self.assertTrue(diagnostics["passed"])

    def test_reject_without_accepted_clusters_passes_quality(self) -> None:
        diagnostics = build_quality_diagnostics(accepted_clusters=[], split_groups=[])

        self.assertTrue(diagnostics["passed"])


if __name__ == "__main__":
    unittest.main()

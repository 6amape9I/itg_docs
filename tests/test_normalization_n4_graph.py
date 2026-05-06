from __future__ import annotations

import unittest

from kb_rebuild.normalization.n4.graph import build_graph_components, drug_trade_name_active_substance_conflict


class NormalizationN4GraphTests(unittest.TestCase):
    def test_every_auto_cluster_becomes_component_without_merge(self) -> None:
        result = build_graph_components(
            auto_clusters=[_cluster("ac1", "disease", "А"), _cluster("ac2", "disease", "Б")],
            candidate_nodes=[],
            accepted_clusters=[],
        )

        self.assertEqual(len(result.components), 2)
        self.assertEqual(set(result.auto_cluster_to_component_id), {"ac1", "ac2"})

    def test_n3_accepted_cluster_merges_auto_clusters(self) -> None:
        result = build_graph_components(
            auto_clusters=[_cluster("ac1", "disease", "А"), _cluster("ac2", "disease", "Б")],
            candidate_nodes=[_node("n1", "ac1"), _node("n2", "ac2")],
            accepted_clusters=[_accepted("n3c1", ["n1", "n2"])],
        )

        self.assertEqual(len(result.components), 1)
        self.assertEqual(result.components[0].auto_cluster_ids, ["ac1", "ac2"])
        self.assertEqual(result.components[0].n3_cluster_ids, ["n3c1"])

    def test_overlapping_accepted_clusters_deduplicate_into_one_component(self) -> None:
        result = build_graph_components(
            auto_clusters=[_cluster("ac1", "disease", "А"), _cluster("ac2", "disease", "Б"), _cluster("ac3", "disease", "В")],
            candidate_nodes=[_node("n1", "ac1"), _node("n2", "ac2"), _node("n3", "ac3")],
            accepted_clusters=[_accepted("n3c1", ["n1", "n2"]), _accepted("n3c2", ["n2", "n3"])],
        )

        self.assertEqual(len(result.components), 1)
        self.assertEqual(result.components[0].auto_cluster_ids, ["ac1", "ac2", "ac3"])

    def test_rejected_constraint_marks_review(self) -> None:
        result = build_graph_components(
            auto_clusters=[_cluster("ac1", "disease", "А"), _cluster("ac2", "disease", "Б")],
            candidate_nodes=[_node("n1", "ac1"), _node("n2", "ac2")],
            accepted_clusters=[_accepted("n3c1", ["n1", "n2"], confidence=0.95)],
            rejected_groups=[{"input_node_ids": ["n1", "n2"], "entity_type": "disease"}],
        )

        self.assertIn("rejected_constraint_conflict", result.components[0].review_reasons)

    def test_unknown_node_id_goes_to_merge_conflicts(self) -> None:
        result = build_graph_components(
            auto_clusters=[_cluster("ac1", "disease", "А"), _cluster("ac2", "disease", "Б")],
            candidate_nodes=[_node("n1", "ac1")],
            accepted_clusters=[_accepted("n3c1", ["n1", "n_missing"])],
        )

        self.assertEqual(len(result.components), 2)
        self.assertEqual(result.merge_conflicts[0]["conflict_type"], "unknown_node_id")

    def test_drug_policy_conflict_blocks_trade_name_active_substance_merge(self) -> None:
        self.assertTrue(drug_trade_name_active_substance_conflict(["Амловас", "Амлодипин"]))
        result = build_graph_components(
            auto_clusters=[
                _cluster("ac1", "drug_trade_name", "Амловас"),
                _cluster("ac2", "drug_trade_name", "Амлодипин"),
            ],
            candidate_nodes=[_node("n1", "ac1"), _node("n2", "ac2")],
            accepted_clusters=[
                _accepted(
                    "n3c1",
                    ["n1", "n2"],
                    entity_type="drug_trade_name",
                    labels=["Амловас", "Амлодипин"],
                )
            ],
        )

        self.assertEqual(len(result.components), 2)
        self.assertEqual(result.merge_conflicts[0]["conflict_type"], "drug_trade_name_active_substance_conflict")
        self.assertEqual(result.drug_policy_review[0]["alias_status"], "blocked_active_substance_candidate")


def _cluster(auto_cluster_id: str, entity_type: str, label: str) -> dict[str, object]:
    return {"auto_cluster_id": auto_cluster_id, "entity_type": entity_type, "canonical_display_candidate": label}


def _node(node_id: str, auto_cluster_id: str) -> dict[str, object]:
    return {"node_id": node_id, "auto_cluster_id": auto_cluster_id}


def _accepted(
    n3_cluster_id: str,
    node_ids: list[str],
    *,
    entity_type: str = "disease",
    labels: list[str] | None = None,
    confidence: float = 1.0,
) -> dict[str, object]:
    return {
        "n3_cluster_id": n3_cluster_id,
        "source_candidate_group_id": "cg1",
        "entity_type": entity_type,
        "node_ids": node_ids,
        "labels": labels or ["А", "Б"],
        "canonical_tag_ru": "А",
        "canonical_tag_latin": "",
        "confidence": confidence,
        "reason": "",
    }


if __name__ == "__main__":
    unittest.main()

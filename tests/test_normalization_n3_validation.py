import unittest

from tests.test_normalization_n3_schema import _accept_response, _group
from kb_rebuild.normalization.n3.models import N3InputGroup
from kb_rebuild.normalization.n3.schema import validate_decision_response


def _three_node_group() -> N3InputGroup:
    base = _group()
    return N3InputGroup(
        candidate_group_id=base.candidate_group_id,
        entity_type=base.entity_type,
        group_labels=["Мерцательная аритмия", "Фибрилляция предсердий", "Мегалобластная анемия"],
        node_ids=["n1", "n2", "n3"],
        group_score=base.group_score,
        candidate_reasons=base.candidate_reasons,
        clean_candidate_reasons=base.clean_candidate_reasons,
        weak_candidate_reasons=base.weak_candidate_reasons,
        group_risk_flags=base.group_risk_flags,
        mentions_count=3,
        documents_count=3,
        article_candidate_count=3,
        context_only_count=0,
        sample_documents=[],
    )


class NormalizationN3ValidationTests(unittest.TestCase):
    def test_unknown_decision_fails(self) -> None:
        response = _accept_response()
        response["decision"] = "merge_everything"

        parsed, errors = validate_decision_response(response, _group())

        self.assertIsNone(parsed)
        self.assertTrue(any("unknown decision" in error for error in errors))

    def test_unknown_node_id_fails(self) -> None:
        response = _accept_response()
        response["subclusters"][0]["node_ids"] = ["n1", "missing"]

        parsed, errors = validate_decision_response(response, _group())

        self.assertIsNone(parsed)
        self.assertTrue(any("unknown node_id" in error for error in errors))

    def test_accept_without_canonical_tag_ru_fails(self) -> None:
        response = _accept_response()
        response["canonical_tag_ru"] = ""
        response["subclusters"][0]["canonical_tag_ru"] = ""

        parsed, errors = validate_decision_response(response, _group())

        self.assertIsNone(parsed)
        self.assertTrue(any("canonical_tag_ru" in error for error in errors))

    def test_split_with_overlapping_node_ids_fails(self) -> None:
        group = _three_node_group()
        response = {
            **_accept_response(),
            "decision": "split_into_subclusters",
            "canonical_tag_ru": "",
            "canonical_tag_latin": "",
            "subclusters": [
                {
                    "subcluster_id": "sc_001",
                    "decision": "same_entity",
                    "canonical_tag_ru": "Фибрилляция предсердий",
                    "canonical_tag_latin": "",
                    "labels": ["Мерцательная аритмия", "Фибрилляция предсердий"],
                    "node_ids": ["n1", "n2"],
                    "confidence": 0.9,
                    "reason": "синонимы",
                },
                {
                    "subcluster_id": "sc_002",
                    "decision": "singleton",
                    "canonical_tag_ru": "",
                    "canonical_tag_latin": "",
                    "labels": ["Фибрилляция предсердий"],
                    "node_ids": ["n2"],
                    "confidence": 0.9,
                    "reason": "duplicate",
                },
            ],
            "rejected_labels": [{"label": "Мегалобластная анемия", "node_id": "n3", "reason": "distinct"}],
        }

        parsed, errors = validate_decision_response(response, group)

        self.assertIsNone(parsed)
        self.assertTrue(any("overlap" in error for error in errors))

    def test_split_with_uncovered_node_ids_fails_unless_rejected(self) -> None:
        group = _three_node_group()
        response = {
            **_accept_response(),
            "decision": "split_into_subclusters",
            "canonical_tag_ru": "",
            "canonical_tag_latin": "",
            "subclusters": [
                {
                    "subcluster_id": "sc_001",
                    "decision": "same_entity",
                    "canonical_tag_ru": "Фибрилляция предсердий",
                    "canonical_tag_latin": "",
                    "labels": ["Мерцательная аритмия", "Фибрилляция предсердий"],
                    "node_ids": ["n1", "n2"],
                    "confidence": 0.9,
                    "reason": "синонимы",
                }
            ],
            "rejected_labels": [],
        }

        parsed, errors = validate_decision_response(response, group)
        self.assertIsNone(parsed)
        self.assertTrue(any("uncovered" in error for error in errors))

        response["rejected_labels"] = [{"label": "Мегалобластная анемия", "node_id": "n3", "reason": "distinct"}]
        parsed, errors = validate_decision_response(response, group)
        self.assertEqual(errors, [])
        self.assertEqual(parsed["decision"], "split_into_subclusters")


if __name__ == "__main__":
    unittest.main()

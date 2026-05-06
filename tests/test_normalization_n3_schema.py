import json
import unittest

from kb_rebuild.normalization.n3.models import N3InputGroup
from kb_rebuild.normalization.n3.schema import parse_decision_json, validate_decision_response


def _group() -> N3InputGroup:
    return N3InputGroup(
        candidate_group_id="cg_test",
        entity_type="disease",
        group_labels=["Аддисонова болезнь", "Болезнь Аддисона"],
        node_ids=["n1", "n2"],
        group_score=0.95,
        candidate_reasons=["exact_normalized_match"],
        clean_candidate_reasons=["canonical_alias_exact_match"],
        weak_candidate_reasons=[],
        group_risk_flags=[],
        mentions_count=2,
        documents_count=2,
        article_candidate_count=2,
        context_only_count=0,
        sample_documents=[],
    )


def _accept_response() -> dict:
    return {
        "candidate_group_id": "cg_test",
        "decision": "accept_same_entity",
        "confidence": 0.94,
        "canonical_tag_ru": "Болезнь Аддисона",
        "canonical_tag_latin": "Addison disease",
        "entity_type": "disease",
        "subclusters": [
            {
                "subcluster_id": "sc_001",
                "decision": "same_entity",
                "canonical_tag_ru": "Болезнь Аддисона",
                "canonical_tag_latin": "Addison disease",
                "labels": ["Аддисонова болезнь", "Болезнь Аддисона"],
                "node_ids": ["n1", "n2"],
                "confidence": 0.94,
                "reason": "синонимы одной болезни",
            }
        ],
        "rejected_labels": [],
        "reason": "все labels обозначают одну сущность",
        "risk_flags": [],
        "requires_human_review": False,
    }


class NormalizationN3SchemaTests(unittest.TestCase):
    def test_valid_accept_response_passes(self) -> None:
        parsed, errors = validate_decision_response(_accept_response(), _group())

        self.assertEqual(errors, [])
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["decision"], "accept_same_entity")

    def test_valid_reject_response_passes(self) -> None:
        group = _group()
        response = _accept_response()
        response.update(
            {
                "decision": "reject_distinct_entities",
                "confidence": 0.88,
                "canonical_tag_ru": "",
                "canonical_tag_latin": "",
                "subclusters": [],
                "rejected_labels": [
                    {"label": "Аддисонова болезнь", "node_id": "n1", "reason": "distinct"},
                    {"label": "Болезнь Аддисона", "node_id": "n2", "reason": "distinct"},
                ],
                "reason": "merge не подтвержден",
            }
        )

        parsed, errors = validate_decision_response(response, group)

        self.assertEqual(errors, [])
        self.assertEqual(parsed["decision"], "reject_distinct_entities")

    def test_valid_split_response_passes(self) -> None:
        group = N3InputGroup(
            **{
                **_group().__dict__,
                "group_labels": ["Мерцательная аритмия", "Фибрилляция предсердий", "Мегалобластная анемия"],
                "node_ids": ["n1", "n2", "n3"],
            }
        )
        response = {
            **_accept_response(),
            "decision": "split_into_subclusters",
            "confidence": 0.91,
            "canonical_tag_ru": "",
            "canonical_tag_latin": "",
            "subclusters": [
                {
                    "subcluster_id": "sc_001",
                    "decision": "same_entity",
                    "canonical_tag_ru": "Фибрилляция предсердий",
                    "canonical_tag_latin": "Atrial fibrillation",
                    "labels": ["Мерцательная аритмия", "Фибрилляция предсердий"],
                    "node_ids": ["n1", "n2"],
                    "confidence": 0.91,
                    "reason": "синонимы",
                },
                {
                    "subcluster_id": "sc_002",
                    "decision": "singleton",
                    "canonical_tag_ru": "",
                    "canonical_tag_latin": "",
                    "labels": ["Мегалобластная анемия"],
                    "node_ids": ["n3"],
                    "confidence": 0.9,
                    "reason": "отдельная болезнь",
                },
            ],
            "rejected_labels": [],
            "entity_type": "disease",
            "reason": "частичный alias-subcluster",
        }

        parsed, errors = validate_decision_response(response, group)

        self.assertEqual(errors, [])
        self.assertEqual(parsed["decision"], "split_into_subclusters")

    def test_parse_json_fence(self) -> None:
        parsed, errors = parse_decision_json("```json\n" + json.dumps(_accept_response(), ensure_ascii=False) + "\n```")

        self.assertEqual(errors, [])
        self.assertEqual(parsed["candidate_group_id"], "cg_test")


if __name__ == "__main__":
    unittest.main()

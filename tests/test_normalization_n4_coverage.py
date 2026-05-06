from __future__ import annotations

import unittest

from kb_rebuild.normalization.n4.links import audit_coverage


class NormalizationN4CoverageTests(unittest.TestCase):
    def test_coverage_passes_when_raw_and_canonical_values_are_aliases(self) -> None:
        audit, missing_aliases = audit_coverage(
            mentions=[_mention()],
            links=[_link("disease_a")],
            canonical_rows=[{"tag_id": "disease_a", "entity_type": "disease", "canonical_tag_ru": "Болезнь Аддисона", "canonical_tag_latin": ""}],
            alias_rows=[
                _alias("disease_a", "Аддисонова болезнь"),
                _alias("disease_a", "Addison disease"),
                _alias("disease_a", "болезнь аддисона"),
            ],
            missing_mentions=[],
        )

        self.assertTrue(audit["passed"])
        self.assertEqual(missing_aliases, [])

    def test_coverage_fails_if_alias_missing(self) -> None:
        audit, missing_aliases = audit_coverage(
            mentions=[_mention()],
            links=[_link("disease_a")],
            canonical_rows=[{"tag_id": "disease_a", "entity_type": "disease", "canonical_tag_ru": "Болезнь Аддисона", "canonical_tag_latin": ""}],
            alias_rows=[],
            missing_mentions=[],
        )

        self.assertFalse(audit["passed"])
        self.assertGreater(len(missing_aliases), 0)


def _mention() -> dict[str, object]:
    return {
        "mention_id": "m1",
        "doc_id": "doc1",
        "document_name": "Doc",
        "entity_type": "disease",
        "raw": {
            "surface": "Аддисонова болезнь",
            "canonical_candidate_ru": "Болезнь Аддисона",
            "canonical_candidate_latin": "Addison disease",
        },
        "normalized": {
            "primary_norm": "болезнь аддисона",
            "surface_norm": "аддисонова болезнь",
            "candidate_ru_norm": "болезнь аддисона",
            "candidate_latin_norm": "addison disease",
        },
    }


def _link(tag_id: str) -> dict[str, object]:
    return {"mention_id": "m1", "doc_id": "doc1", "tag_id": tag_id}


def _alias(tag_id: str, alias: str) -> dict[str, object]:
    return {"tag_id": tag_id, "entity_type": "disease", "alias": alias, "alias_latin": "", "alias_status": "active"}


if __name__ == "__main__":
    unittest.main()

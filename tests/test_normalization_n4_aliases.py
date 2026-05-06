from __future__ import annotations

import unittest

from kb_rebuild.normalization.n4.aliases import (
    build_alias_records,
    build_component_alias_candidates,
    find_alias_conflicts,
    mark_alias_conflicts,
)
from kb_rebuild.normalization.n4.models import FinalComponent


class NormalizationN4AliasTests(unittest.TestCase):
    def test_alias_candidates_include_raw_and_normalized_mention_values(self) -> None:
        component = FinalComponent(component_id="fc1", auto_cluster_ids=["ac1"], entity_type="disease")
        candidates = build_component_alias_candidates(
            component,
            {
                "ac1": {
                    "canonical_display_candidate": "Болезнь Аддисона",
                    "canonical_latin_candidate": "Addison disease",
                    "aliases": ["Аддисонова болезнь"],
                    "normalized_aliases": ["аддисонова болезнь"],
                }
            },
            [_mention()],
            "Болезнь Аддисона",
            "Addison disease",
        )
        aliases = {candidate["alias"] for candidate in candidates}
        alias_norms = {alias.lower() for alias in aliases}

        self.assertIn("Болезнь Аддисона", aliases)
        self.assertIn("Аддисонова болезнь", aliases)
        self.assertIn("addison disease", alias_norms)

    def test_alias_conflicts_mark_alias_rows(self) -> None:
        canonical = [
            {"tag_id": "disease_a", "entity_type": "disease", "canonical_tag_ru": "А", "canonical_tag_latin": ""},
            {"tag_id": "disease_b", "entity_type": "disease", "canonical_tag_ru": "Б", "canonical_tag_latin": ""},
        ]
        aliases = [
            _alias("disease_a", "disease", "Общий alias"),
            _alias("disease_b", "disease", "Общий alias"),
        ]

        conflicts = find_alias_conflicts(aliases, canonical)
        mark_alias_conflicts(aliases, conflicts)

        self.assertEqual(len(conflicts), 1)
        self.assertTrue(all(row["conflict_alias"] for row in aliases))
        self.assertTrue(all(row["need_review"] for row in aliases))

    def test_blocked_alias_status_is_not_active(self) -> None:
        rows = build_alias_records(
            tag_id="drug_trade_name_a",
            entity_type="drug_trade_name",
            candidates=[{"alias": "Амлодипин", "alias_source": "n3_label"}],
            mention_norm_counts={},
            blocked_norms={"амлодипин"},
        )

        self.assertEqual(rows[0]["alias_status"], "blocked_active_substance_candidate")
        self.assertFalse(rows[0]["active"])


def _mention() -> dict[str, object]:
    return {
        "raw": {
            "surface": "Аддисонова болезнь",
            "canonical_candidate_ru": "Болезнь Аддисона",
            "canonical_candidate_latin": "Addison disease",
        },
        "normalized": {
            "surface_norm": "аддисонова болезнь",
            "candidate_ru_norm": "болезнь аддисона",
            "candidate_latin_norm": "addison disease",
            "primary_norm": "болезнь аддисона",
        },
    }


def _alias(tag_id: str, entity_type: str, alias: str) -> dict[str, object]:
    return {
        "tag_id": tag_id,
        "entity_type": entity_type,
        "alias": alias,
        "alias_norm": alias.lower(),
        "alias_latin": "",
        "alias_status": "active",
        "need_review": False,
        "review_reasons": [],
        "conflict_alias": False,
    }


if __name__ == "__main__":
    unittest.main()

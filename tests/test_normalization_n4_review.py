from __future__ import annotations

import json
import unittest

from kb_rebuild.normalization.n4.review import REVIEW_FIELDS, specialist_review_rows, specialist_review_sample


class NormalizationN4ReviewTests(unittest.TestCase):
    def test_specialist_review_has_exact_columns_and_json_aliases(self) -> None:
        rows = specialist_review_rows(
            [_tag("disease_a", "Болезнь Аддисона", "", need_review=True)],
            {"disease_a": ["Аддисонова болезнь"]},
        )

        self.assertEqual(list(rows[0]), REVIEW_FIELDS)
        self.assertEqual(rows[0]["canonical_tag_latin"], "null")
        self.assertEqual(rows[0]["need_review"], "true")
        self.assertEqual(json.loads(rows[0]["aliases"]), ["Аддисонова болезнь"])

    def test_sample_respects_size_and_prioritizes_need_review(self) -> None:
        tags = [
            _tag("disease_a", "А", "", need_review=True, mentions_count=10),
            _tag("disease_b", "Б", "", need_review=False, mentions_count=100),
        ]

        sample = specialist_review_sample(tags, {"disease_a": [], "disease_b": []}, sample_size=1)

        self.assertEqual(len(sample), 1)
        self.assertEqual(sample[0]["canonical_tag_ru"], "А")


def _tag(tag_id: str, ru: str, latin: str, *, need_review: bool, mentions_count: int = 1) -> dict[str, object]:
    return {
        "tag_id": tag_id,
        "canonical_tag_ru": ru,
        "canonical_tag_latin": latin,
        "entity_type": "disease",
        "need_review": need_review,
        "review_reasons": ["alias_conflict"] if need_review else [],
        "mentions_count": mentions_count,
        "documents_count": mentions_count,
    }


if __name__ == "__main__":
    unittest.main()

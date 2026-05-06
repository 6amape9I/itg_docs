from __future__ import annotations

import unittest

from kb_rebuild.articles.planning.matching import AliasTerm, find_match_hits
from kb_rebuild.articles.planning.models import A0Config


class ArticlePlanningMatchingTests(unittest.TestCase):
    def test_quote_match_finds_block(self) -> None:
        hits = find_match_hits(
            config=A0Config(),
            tag_id="disease_a",
            aliases=[AliasTerm("астма", "Астма", "canonical", True)],
            doc={"name": "Doc", "text_length_chars": 50},
            blocks=[_block(0, "Бронхиальная астма - хроническое заболевание")],
            mention_ids=["m1"],
            quote_context={"m1": ["Бронхиальная астма - хроническое заболевание"]},
            allow_short_document_fallback=True,
        )

        self.assertEqual(hits[0].method, "quote_match")
        self.assertEqual(hits[0].quality, "high")

    def test_alias_match_uses_normalized_yo_e(self) -> None:
        hits = find_match_hits(
            config=A0Config(),
            tag_id="symptom_a",
            aliases=[AliasTerm("елка", "Ёлка", "canonical", True)],
            doc={"name": "Doc", "text_length_chars": 20},
            blocks=[_block(0, "елка упоминается в тексте")],
            mention_ids=["m1"],
            quote_context={},
            allow_short_document_fallback=False,
        )

        self.assertEqual(hits[0].method, "alias_match")

    def test_title_match_when_block_match_absent(self) -> None:
        hits = find_match_hits(
            config=A0Config(),
            tag_id="disease_a",
            aliases=[AliasTerm("астма", "Астма", "canonical", True)],
            doc={"name": "Астма", "text_length_chars": 20},
            blocks=[_block(0, "Описание без названия")],
            mention_ids=["m1"],
            quote_context={},
            allow_short_document_fallback=False,
        )

        self.assertEqual(hits[0].method, "title_match")

    def test_no_fuzzy_overmatch_for_too_short_alias(self) -> None:
        hits = find_match_hits(
            config=A0Config(),
            tag_id="x",
            aliases=[AliasTerm("ад", "Ад", "alias", False)],
            doc={"name": "Doc", "text_length_chars": 20},
            blocks=[_block(0, "гладкий текст")],
            mention_ids=["m1"],
            quote_context={},
            allow_short_document_fallback=False,
        )

        self.assertEqual(hits[0].method, "mention_only_fallback")
        self.assertTrue(hits[0].needs_review)


def _block(index: int, text: str) -> dict[str, object]:
    return {"doc_id": "doc1", "block_id": f"b{index}", "block_index": index, "block_type": "paragraph", "text": text}


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from kb_rebuild.articles.a1.direct_copy import source_blocks_to_editorjs, validate_direct_copy


class ArticleA1DirectCopyTests(unittest.TestCase):
    def test_accepted_direct_copy_candidate(self) -> None:
        validation = validate_direct_copy(
            _plan(),
            windows_by_id={"win1": _window(coverage=0.9)},
            docs_by_id={"doc1": {"doc_id": "doc1", "text_length_chars": 10}},
            blocks_by_doc={"doc1": [_block("paragraph", "Астма текст")]},
        )

        self.assertTrue(validation.accepted)

    def test_rejects_competing_article_tags(self) -> None:
        validation = validate_direct_copy(
            _plan(competing=1),
            windows_by_id={"win1": _window(coverage=0.9)},
            docs_by_id={"doc1": {"doc_id": "doc1", "text_length_chars": 10}},
            blocks_by_doc={"doc1": [_block("paragraph", "Астма текст")]},
        )

        self.assertFalse(validation.accepted)
        self.assertIn("competing_article_candidate_tags_in_doc", validation.rejection_reasons)

    def test_rejects_low_coverage(self) -> None:
        validation = validate_direct_copy(
            _plan(),
            windows_by_id={"win1": _window(coverage=0.2)},
            docs_by_id={"doc1": {"doc_id": "doc1", "text_length_chars": 10}},
            blocks_by_doc={"doc1": [_block("paragraph", "Астма текст")]},
        )

        self.assertFalse(validation.accepted)
        self.assertIn("coverage_below_threshold", validation.rejection_reasons)

    def test_direct_copy_preserves_source_block_metadata(self) -> None:
        blocks = source_blocks_to_editorjs([_block("paragraph", "Астма текст")])

        self.assertEqual(blocks[0]["metadata"]["source_block_id"], "b1")
        self.assertEqual(blocks[0]["metadata"]["source_block_index"], 0)


def _plan(*, competing: int = 0) -> dict[str, object]:
    return {
        "tag_id": "disease_a",
        "canonical_tag_ru": "Астма",
        "strategy": "direct_copy_candidate",
        "article_candidate": True,
        "needs_review_before_article": False,
        "documents_count": 1,
        "source_windows_count": 1,
        "competing_article_candidate_tags_in_doc": competing,
        "source_window_ids": ["win1"],
        "source_doc_ids": ["doc1"],
    }


def _window(*, coverage: float) -> dict[str, object]:
    return {"window_id": "win1", "window_quality": "high", "coverage_ratio_estimate": coverage, "match_method": "quote_match"}


def _block(block_type: str, text: str) -> dict[str, object]:
    return {"doc_id": "doc1", "block_id": "b1", "block_index": 0, "block_type": block_type, "text": text}


if __name__ == "__main__":
    unittest.main()

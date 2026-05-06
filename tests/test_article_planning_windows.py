from __future__ import annotations

import unittest

from kb_rebuild.articles.planning.models import A0Config, MatchHit
from kb_rebuild.articles.planning.windows import build_windows_for_tag_doc


class ArticlePlanningWindowsTests(unittest.TestCase):
    def test_matched_block_header_and_neighbors_are_included(self) -> None:
        windows = build_windows_for_tag_doc(
            config=A0Config(max_neighbor_blocks=1, max_window_chars=1000),
            tag=_tag(),
            doc=_doc(),
            blocks=[
                _block(0, "header", "Раздел"),
                _block(1, "paragraph", "До"),
                _block(2, "paragraph", "Астма"),
                _block(3, "paragraph", "После"),
            ],
            hits=[MatchHit("alias_match", "high", (2,), matched_aliases=("астма",))],
            mention_ids=["m1"],
        )

        self.assertEqual(windows[0].block_indexes, [0, 1, 2, 3])
        self.assertEqual(windows[0].heading_context, ["Раздел"])

    def test_overlapping_windows_merge(self) -> None:
        windows = build_windows_for_tag_doc(
            config=A0Config(max_neighbor_blocks=0, max_window_chars=1000),
            tag=_tag(),
            doc=_doc(),
            blocks=[_block(0, "paragraph", "Астма"), _block(1, "paragraph", "Лечение астмы")],
            hits=[
                MatchHit("alias_match", "high", (0,), matched_aliases=("астма",)),
                MatchHit("alias_match", "high", (1,), matched_aliases=("астма",)),
            ],
            mention_ids=["m1"],
        )

        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].block_indexes, [0, 1])

    def test_max_window_chars_trims_non_required_neighbors(self) -> None:
        windows = build_windows_for_tag_doc(
            config=A0Config(max_neighbor_blocks=1, max_window_chars=20),
            tag=_tag(),
            doc=_doc(),
            blocks=[
                _block(0, "paragraph", "очень длинный соседний текст"),
                _block(1, "paragraph", "Астма"),
                _block(2, "paragraph", "еще один длинный сосед"),
            ],
            hits=[MatchHit("alias_match", "high", (1,), matched_aliases=("астма",))],
            mention_ids=["m1"],
        )

        self.assertEqual(windows[0].block_indexes, [1])
        self.assertEqual(windows[0].window_text, "Астма")


def _tag() -> dict[str, object]:
    return {"tag_id": "disease_a", "canonical_tag_ru": "Астма", "canonical_tag_latin": "Asthma", "entity_type": "disease"}


def _doc() -> dict[str, object]:
    return {"doc_id": "doc1", "name": "Астма", "text_length_chars": 100}


def _block(index: int, block_type: str, text: str) -> dict[str, object]:
    return {"doc_id": "doc1", "block_id": f"b{index}", "block_index": index, "block_type": block_type, "text": text}


if __name__ == "__main__":
    unittest.main()

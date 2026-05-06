from __future__ import annotations

import unittest

from kb_rebuild.normalization.n4.links import build_document_links, build_document_tags_by_doc


class NormalizationN4LinksTests(unittest.TestCase):
    def test_every_mention_gets_link_and_doc_tags_deduplicate_tag_id(self) -> None:
        mentions = [_mention("m1", "doc1"), _mention("m2", "doc1")]
        links, missing = build_document_links(
            mentions=mentions,
            mention_to_auto_cluster={"m1": "ac1", "m2": "ac2"},
            auto_cluster_to_tag_id={"ac1": "disease_a", "ac2": "disease_a"},
            tags_by_id={
                "disease_a": {
                    "tag_id": "disease_a",
                    "canonical_tag_ru": "Болезнь Аддисона",
                    "canonical_tag_latin": "Addison disease",
                    "normalization_source": "n3_accepted",
                    "need_review": False,
                    "review_reasons": [],
                }
            },
        )
        by_doc = build_document_tags_by_doc(links)

        self.assertEqual(len(links), 2)
        self.assertEqual(missing, [])
        self.assertEqual(len(by_doc), 1)
        self.assertEqual(len(by_doc[0]["tags"]), 1)


def _mention(mention_id: str, doc_id: str) -> dict[str, object]:
    return {
        "mention_id": mention_id,
        "doc_id": doc_id,
        "document_name": "Doc",
        "entity_type": "disease",
        "tag_role": "article_candidate",
        "article_candidate": True,
        "confidence": 0.9,
        "raw": {"surface": "Аддисонова болезнь", "canonical_candidate_ru": "Болезнь Аддисона", "canonical_candidate_latin": ""},
    }


if __name__ == "__main__":
    unittest.main()

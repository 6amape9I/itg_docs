from __future__ import annotations

import unittest

from kb_rebuild.articles.a5.report import build_coverage_audit, entity_type_distribution_rows, manual_qa_rows, status_distribution_rows


class ArticleA5ReportTests(unittest.TestCase):
    def test_coverage_audit_preserves_counts_and_quality(self) -> None:
        audit = build_coverage_audit(counts={"final_tags_total": 2}, quality={"passed": True})

        self.assertEqual(audit["stage"], "article_a5_final_export_assembly")
        self.assertEqual(audit["counts"]["final_tags_total"], 2)
        self.assertTrue(audit["quality"]["passed"])

    def test_distribution_rows_are_deterministic(self) -> None:
        rows = [
            {"entity_type": "disease", "article_status": "compiled_article"},
            {"entity_type": "disease", "article_status": "compiled_article"},
            {"entity_type": "symptom", "article_status": "stub_only"},
        ]

        self.assertEqual(status_distribution_rows(rows)[0], {"article_status": "compiled_article", "count": 2})
        self.assertEqual(entity_type_distribution_rows(rows)[0], {"entity_type": "disease", "article_status": "compiled_article", "count": 2})

    def test_manual_qa_includes_all_small_insufficient_set(self) -> None:
        rows = [{"article_status": "insufficient_evidence_review", "tag_id": f"tag_{index}"} for index in range(3)]

        self.assertEqual(len(manual_qa_rows(rows)), 3)


if __name__ == "__main__":
    unittest.main()


from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kb_rebuild.articles.a3.models import A3Config
from kb_rebuild.articles.a3.report import build_manifest, build_report


class ArticleA3ReportTests(unittest.TestCase):
    def test_report_counts_consistent_and_quality_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = A3Config.from_data_dir(root, out_dir=root / "out")
            report = build_report(
                created_at="2026-05-06T00:00:00Z",
                config=config,
                inputs={
                    "a2_evidence_items_jsonl": root / "a2" / "evidence_items.jsonl",
                    "a2_task_results_jsonl": root / "a2" / "evidence_task_results.jsonl",
                    "article_status_index_jsonl": root / "a1" / "article_status_index.jsonl",
                },
                evidence_items_total=1,
                valid_evidence=[{"evidence_item_id": "ev_1", "a3_layer": "valid", "quote_validation_status": "exact", "entity_type": "disease", "fact_type": "definition"}],
                review_evidence=[],
                rejected_evidence=[],
                deduped_evidence=[{"evidence_item_id": "ev_1"}],
                duplicate_rows=[],
                fact_groups=[_fact_group()],
                tag_index=[{"tag_id": "tag_1", "ready_for_a4": True, "core_fact_groups": 1, "supporting_fact_groups": 0}],
                coverage_counts={"final_tags_total": 1},
                warnings=[],
            )

            self.assertEqual(report["counts"]["valid_evidence_items"], 1)
            self.assertTrue(report["quality"]["passed"])

    def test_manifest_has_stage_version_a3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = A3Config.from_data_dir(root, out_dir=root / "out")
            manifest = build_manifest(
                created_at="2026-05-06T00:00:00Z",
                config=config,
                inputs={"a2_report_json": root / "a2" / "a2_report.json"},
                outputs={"a3_report_json": root / "out" / "a3_report.json"},
            )

            self.assertEqual(manifest["stage_version"], "a3.0")


def _fact_group() -> dict[str, object]:
    return {
        "fact_group_id": "fg_1",
        "tag_id": "tag_1",
        "canonical_tag_ru": "Тег",
        "entity_type": "disease",
        "usable_for_a4": True,
        "a4_usage": "core_fact",
        "valid_evidence_count": 1,
        "quote_status_counts": {"exact": 1, "normalized_exact": 0, "fuzzy": 0, "not_found": 0},
    }


if __name__ == "__main__":
    unittest.main()


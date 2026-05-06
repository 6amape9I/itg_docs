from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kb_rebuild.articles.a2.models import A2Config
from kb_rebuild.articles.a2.report import build_manifest, build_report


class ArticleA2ReportTests(unittest.TestCase):
    def test_report_counts_are_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = A2Config.from_data_dir(root, out_dir=root / "out")
            inputs = {
                "a2_task_queue_jsonl": root / "a1" / "a2_extraction_task_queue.jsonl",
                "a1_manifest_json": root / "a1" / "a1_manifest.json",
            }
            batches = [{"batch_id": "a2batch_000001", "task_ids": ["a2task_000000001"]}]
            task_results = [
                {
                    "task_id": "a2task_000000001",
                    "tag_id": "tag_1",
                    "status": "success",
                    "_task": {"entity_type": "disease", "source_strategy": "single_doc_extract"},
                }
            ]
            evidence_items = [
                {
                    "task_id": "a2task_000000001",
                    "fact_type": "definition",
                    "quote_validation_status": "exact",
                }
            ]

            report = build_report(
                created_at="2026-05-06T00:00:00Z",
                config=config,
                inputs=inputs,
                task_results=task_results,
                evidence_items=evidence_items,
                batches=batches,
                batch_reports=[{"status": "success", "latency_ms": 100}],
                invalid_llm_responses=[],
                quote_validation_issues=[],
                stats={"no_unknown_task_ids": True},
                stop_reason=None,
                warnings=[],
            )

            self.assertEqual(report["counts"]["tasks_processed"], 1)
            self.assertEqual(report["counts"]["evidence_items_valid_quotes"], 1)
            self.assertTrue(report["quality"]["all_processed_tasks_have_result"])
            self.assertEqual(report["quote_validation"]["exact"], 1)

    def test_manifest_has_stage_version_a2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = A2Config.from_data_dir(root, out_dir=root / "out")
            manifest = build_manifest(
                created_at="2026-05-06T00:00:00Z",
                config=config,
                inputs={"a1_manifest_json": root / "a1" / "a1_manifest.json"},
                outputs={"a2_report_json": root / "out" / "a2_report.json"},
            )

            self.assertEqual(manifest["stage_version"], "a2.0")
            self.assertEqual(manifest["prompt_version"], "a2_evidence_extract_v1")


if __name__ == "__main__":
    unittest.main()


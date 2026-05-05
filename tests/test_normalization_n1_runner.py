from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kb_rebuild.io.jsonl import read_jsonl
from kb_rebuild.normalization.n1_runner import N1Config, run_normalization_n1


class NormalizationN1RunnerTests(unittest.TestCase):
    def test_runner_creates_required_files_and_preserves_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            tagging_dir = data_dir / "tagging"
            tagging_dir.mkdir(parents=True)
            active_path = tagging_dir / "document_tags_raw_active.jsonl"
            active_path.write_text(_active_fixture(), encoding="utf-8")
            before = active_path.read_text(encoding="utf-8")
            (tagging_dir / "tagging_active_manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": "tagging_test",
                        "provider": "gemini_direct",
                        "model": "gemini-3-flash-preview",
                        "prompt_version": "tagging_v2_gemini",
                        "schema_version": "document_tagging_v2",
                        "documents_tagged": 2,
                        "documents_failed": 0,
                    }
                ),
                encoding="utf-8",
            )
            config = N1Config.from_data_dir(data_dir)

            report = run_normalization_n1(config)

            self.assertEqual(active_path.read_text(encoding="utf-8"), before)
            self.assertEqual(report["counts"]["mentions_total"], 2)
            self.assertEqual(report["counts"]["failed_documents"], 0)
            self.assertTrue(report["warnings"])
            for filename in (
                "tag_mentions_raw.jsonl",
                "tag_mentions_normalized.jsonl",
                "tags_raw.csv",
                "auto_clusters.jsonl",
                "auto_clusters.csv",
                "normalization_n1_report.json",
                "normalization_n1_manifest.json",
                "type_role_stats.csv",
                "suspicious_mentions.jsonl",
                "risk_mentions.jsonl",
                "routing_mentions.jsonl",
                "failed_documents_snapshot.jsonl",
                "quote_issue_mentions.jsonl",
                "singleton_entity_candidates.csv",
                "singleton_entity_candidates.jsonl",
                "cluster_duplicate_diagnostics.csv",
            ):
                self.assertTrue((data_dir / "normalization" / filename).exists(), filename)
            self.assertEqual(len(read_jsonl(data_dir / "normalization" / "failed_documents_snapshot.jsonl")), 0)
            self.assertEqual(report["stage_version"], "n1.1")
            self.assertIn("risk_mentions", report["counts"])
            self.assertIn("routing_mentions", report["counts"])
            self.assertIn("cluster_status_counts", report)
            singleton_rows = read_jsonl(data_dir / "normalization" / "singleton_entity_candidates.jsonl")
            self.assertTrue(any(row["recommended_fast_path"] for row in singleton_rows))

    def test_runner_writes_failed_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            tagging_dir = data_dir / "tagging"
            tagging_dir.mkdir(parents=True)
            (tagging_dir / "document_tags_raw_active.jsonl").write_text(_active_fixture(), encoding="utf-8")
            (tagging_dir / "document_tagging_failures_active.jsonl").write_text(
                '{"doc_id":"doc_3","document_name":"Vitamax(бад)","failure_reason":"empty_clean_text"}\n',
                encoding="utf-8",
            )

            report = run_normalization_n1(N1Config.from_data_dir(data_dir))
            failed_snapshot = read_jsonl(data_dir / "normalization" / "failed_documents_snapshot.jsonl")

            self.assertEqual(report["counts"]["failed_documents"], 1)
            self.assertEqual(failed_snapshot[0]["suggested_followup"], "name_only_recovery_after_normalization")

    def test_singleton_with_competing_article_candidate_is_not_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            tagging_dir = data_dir / "tagging"
            tagging_dir.mkdir(parents=True)
            (tagging_dir / "document_tags_raw_active.jsonl").write_text(
                json.dumps(
                    {
                        "doc_id": "doc_1",
                        "document_name": "Гастрит и язва",
                        "entities": [
                            {
                                "surface": "Гастрит",
                                "canonical_candidate_ru": "Гастрит",
                                "canonical_candidate_latin": "Gastritis",
                                "entity_type": "disease",
                                "article_candidate": True,
                                "tag_role": "article_candidate",
                                "is_primary": True,
                                "confidence": 0.95,
                                "evidence_quotes": ["Гастрит"],
                                "quote_validation_status": "all_exact",
                                "quote_validation_details": [{"status": "exact"}],
                            },
                            {
                                "surface": "Язва желудка",
                                "canonical_candidate_ru": "Язва желудка",
                                "canonical_candidate_latin": "Gastric ulcer",
                                "entity_type": "disease",
                                "article_candidate": True,
                                "tag_role": "article_candidate",
                                "is_primary": False,
                                "confidence": 0.92,
                                "evidence_quotes": ["язва желудка"],
                                "quote_validation_status": "all_exact",
                                "quote_validation_details": [{"status": "exact"}],
                            },
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            run_normalization_n1(N1Config.from_data_dir(data_dir))
            singleton_rows = read_jsonl(data_dir / "normalization" / "singleton_entity_candidates.jsonl")

        self.assertEqual(len(singleton_rows), 2)
        self.assertTrue(all(not row["recommended_fast_path"] for row in singleton_rows))
        self.assertTrue(all(row["has_competing_article_candidates"] for row in singleton_rows))


def _active_fixture() -> str:
    return (
        json.dumps(
            {
                "doc_id": "doc_1",
                "document_name": "Гастрит",
                "provider": "gemini_direct",
                "model": "gemini-3-flash-preview",
                "prompt_version": "tagging_v2_gemini",
                "schema_version": "document_tagging_v2",
                "entities": [
                    {
                        "surface": "Гастрит.",
                        "canonical_candidate_ru": "Гастрит",
                        "canonical_candidate_latin": "Gastritis",
                        "entity_type": "disease",
                        "article_candidate": True,
                        "tag_role": "article_candidate",
                        "is_primary": True,
                        "confidence": 0.95,
                        "evidence_quotes": ["Гастрит"],
                        "quote_validation_status": "all_exact",
                        "quote_validation_details": [{"status": "exact"}],
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n"
        + json.dumps(
            {
                "doc_id": "doc_2",
                "document_name": "Хронический гастрит",
                "provider": "gemini_direct",
                "model": "gemini-3-flash-preview",
                "prompt_version": "tagging_v2_gemini",
                "schema_version": "document_tagging_v2",
                "entities": [
                    {
                        "surface": "Хронический гастрит",
                        "canonical_candidate_ru": "Хронический гастрит",
                        "canonical_candidate_latin": "Chronic gastritis",
                        "entity_type": "disease",
                        "article_candidate": True,
                        "tag_role": "article_candidate",
                        "is_primary": True,
                        "confidence": 0.9,
                        "evidence_quotes": ["Хронический гастрит"],
                        "quote_validation_status": "all_exact",
                        "quote_validation_details": [{"status": "exact"}],
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n"
    )


if __name__ == "__main__":
    unittest.main()

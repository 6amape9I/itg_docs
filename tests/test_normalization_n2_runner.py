from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kb_rebuild.io.jsonl import read_jsonl, write_jsonl
from kb_rebuild.normalization.n2.runner import N2Config, run_normalization_n2


class NormalizationN2RunnerTests(unittest.TestCase):
    def test_runner_creates_required_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            norm_dir = data_dir / "normalization"
            _write_n1_inputs(norm_dir)

            report = run_normalization_n2(N2Config.from_data_dir(data_dir))

            out = norm_dir / "n2"
            for filename in (
                "candidate_nodes.jsonl",
                "candidate_pairs.jsonl",
                "blocked_pairs.jsonl",
                "rejected_pairs.jsonl",
                "candidate_groups.jsonl",
                "candidate_groups.csv",
                "high_priority_candidate_groups.csv",
                "singleton_fast_path_candidates.csv",
                "candidate_generation_report.json",
                "candidate_generation_manifest.json",
            ):
                self.assertTrue((out / filename).exists(), filename)
            self.assertEqual(report["source_stage_version"], "n1.1")
            self.assertEqual(report["counts"]["nodes_total"], 2)
            self.assertEqual(report["counts"]["candidate_pairs_total"], 1)
            self.assertEqual(len(read_jsonl(out / "candidate_groups.jsonl")), 1)

    def test_runner_refuses_non_n1_1_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            norm_dir = data_dir / "normalization"
            _write_n1_inputs(norm_dir, stage_version="n1")

            with self.assertRaises(ValueError):
                run_normalization_n2(N2Config.from_data_dir(data_dir))

    def test_runner_refuses_duplicate_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            norm_dir = data_dir / "normalization"
            _write_n1_inputs(norm_dir)
            (norm_dir / "cluster_duplicate_diagnostics.csv").write_text(
                "duplicate_key,duplicate_type,rows_count,entity_type,canonical_display_candidates,auto_cluster_ids,reason\n"
                "x,entity_type_auto_cluster_key,2,disease,a,ac_1; ac_2,duplicate\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                run_normalization_n2(N2Config.from_data_dir(data_dir))


def _write_n1_inputs(norm_dir: Path, *, stage_version: str = "n1.1") -> None:
    norm_dir.mkdir(parents=True)
    (norm_dir / "normalization_n1_manifest.json").write_text(
        json.dumps({"stage": "normalization_n1", "stage_version": stage_version}),
        encoding="utf-8",
    )
    (norm_dir / "cluster_duplicate_diagnostics.csv").write_text(
        "duplicate_key,duplicate_type,rows_count,entity_type,canonical_display_candidates,auto_cluster_ids,reason\n",
        encoding="utf-8",
    )
    clusters = [
        _cluster("ac_000001", "diagnostic_method", "Иммуноферментный анализ", ["Иммуноферментный анализ"], ["m1"]),
        _cluster("ac_000002", "diagnostic_method", "ИФА", ["ИФА"], ["m2"]),
    ]
    mentions = [
        _mention("m1", "doc_1", "Иммуноферментный анализ"),
        _mention("m2", "doc_2", "ИФА"),
    ]
    singletons = [
        {
            "candidate_id": "sec_0000001",
            "doc_id": "doc_1",
            "document_name": "Иммуноферментный анализ",
            "entity_type": "diagnostic_method",
            "canonical_display_candidate": "Иммуноферментный анализ",
            "canonical_latin_candidate": "ELISA",
            "surface": "Иммуноферментный анализ",
            "confidence": 0.95,
            "quote_validation_status": "all_exact",
            "mentions_count": 1,
            "documents_count": 1,
            "document_article_candidate_count": 1,
            "has_competing_article_candidates": False,
            "competing_article_candidates": [],
            "recommended_fast_path": True,
            "review_required": False,
            "review_reasons": [],
        }
    ]
    write_jsonl(norm_dir / "auto_clusters.jsonl", clusters)
    write_jsonl(norm_dir / "tag_mentions_normalized.jsonl", mentions)
    write_jsonl(norm_dir / "singleton_entity_candidates.jsonl", singletons)


def _cluster(auto_cluster_id: str, entity_type: str, label: str, aliases: list[str], mention_ids: list[str]) -> dict[str, object]:
    return {
        "auto_cluster_id": auto_cluster_id,
        "entity_type": entity_type,
        "auto_cluster_key": f"{entity_type}::{label.lower()}",
        "canonical_display_candidate": label,
        "canonical_latin_candidate": "ELISA" if label == "Иммуноферментный анализ" else "",
        "aliases": aliases,
        "normalized_aliases": [alias.lower() for alias in aliases],
        "mention_ids": mention_ids,
        "documents_count": 1,
        "mentions_count": 1,
        "article_candidate_count": 1,
        "context_only_count": 0,
        "folder_candidate_count": 0,
        "risk_flags": [],
        "routing_flags": ["article_candidate"],
        "cluster_status": "isolated_mention",
        "merge_allowed": False,
    }


def _mention(mention_id: str, doc_id: str, label: str) -> dict[str, object]:
    return {
        "mention_id": mention_id,
        "doc_id": doc_id,
        "document_name": label,
    }


if __name__ == "__main__":
    unittest.main()

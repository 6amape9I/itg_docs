from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from kb_rebuild.io.jsonl import read_jsonl, write_jsonl
from kb_rebuild.normalization.n4.runner import N4Config, run_normalization_n4


class NormalizationN4RunnerTests(unittest.TestCase):
    def test_runner_creates_required_outputs_and_full_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_fixture(Path(tmp))
            config = N4Config.from_data_dir(data_dir, review_sample_size=2)

            report = run_normalization_n4(config)

            for filename in (
                "tags_canonical.csv",
                "tag_aliases.csv",
                "document_tag_links_normalized.jsonl",
                "document_tag_links_normalized.csv",
                "document_tags_normalized_by_doc.jsonl",
                "final_canonical_tag_names.csv",
                "specialist_review_full.csv",
                "specialist_review_sample.csv",
                "canonical_review_detailed.csv",
                "coverage_audit.json",
                "coverage_audit_missing_mentions.csv",
                "coverage_audit_missing_aliases.csv",
                "alias_conflicts.csv",
                "merge_conflicts.jsonl",
                "drug_policy_review.csv",
                "unresolved_review_groups.jsonl",
                "final_normalization_report.json",
                "final_normalization_manifest.json",
            ):
                self.assertTrue((config.out_dir / filename).exists(), filename)
            self.assertTrue(report["coverage_audit"]["passed"])
            self.assertTrue(report["quality"]["all_auto_clusters_covered"])
            self.assertEqual(report["counts"]["mentions_total"], 3)
            self.assertEqual(report["counts"]["document_tag_links_total"], 3)
            self.assertEqual(report["counts"]["final_canonical_tags_total"], 2)
            self.assertEqual(report["counts"]["merged_n3_tags"], 1)
            self.assertEqual(report["counts"]["standalone_auto_cluster_tags"], 1)
            self.assertEqual(len(read_jsonl(config.out_dir / "document_tag_links_normalized.jsonl")), 3)
            with (config.out_dir / "final_canonical_tag_names.csv").open("r", encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh)
                self.assertEqual(next(reader), ["tag_id", "canonical_tag_ru", "canonical_tag_latin", "entity_type", "need_review"])
            with (config.out_dir / "specialist_review_full.csv").open("r", encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh)
                self.assertEqual(next(reader), ["canonical_tag_ru", "canonical_tag_latin", "aliases", "need_review"])

    def test_runner_refuses_bad_n3_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_fixture(Path(tmp), n3_quality_passed=False)

            with self.assertRaisesRegex(ValueError, "N3 quality"):
                run_normalization_n4(N4Config.from_data_dir(data_dir))


def _write_fixture(root: Path, *, n3_quality_passed: bool = True) -> Path:
    data_dir = root / "data"
    norm_dir = data_dir / "normalization"
    n2_dir = norm_dir / "n2"
    n3_dir = norm_dir / "n3"
    n3_dir.mkdir(parents=True)
    n2_dir.mkdir(parents=True)

    mentions = [
        _mention("m1", "doc1", "Аддисонова болезнь", "Болезнь Аддисона", "Addison disease"),
        _mention("m2", "doc2", "Болезнь Аддисона", "Болезнь Аддисона", "Addison disease"),
        _mention("m3", "doc2", "Миопатия", "Миопатия", "Myopathy"),
    ]
    clusters = [
        _cluster("ac1", "disease", "Аддисонова болезнь", "Addison disease", ["m1"]),
        _cluster("ac2", "disease", "Болезнь Аддисона", "Addison disease", ["m2"]),
        _cluster("ac3", "disease", "Миопатия", "Myopathy", ["m3"]),
    ]
    write_jsonl(norm_dir / "auto_clusters.jsonl", clusters)
    write_jsonl(norm_dir / "tag_mentions_normalized.jsonl", mentions)
    write_jsonl(norm_dir / "tag_mentions_raw.jsonl", mentions)
    _write_json(
        norm_dir / "normalization_n1_report.json",
        {
            "stage": "normalization_n1",
            "stage_version": "n1.1",
            "counts": {"mentions_total": 3, "auto_clusters_total": 3, "documents_with_tags": 2},
        },
    )
    _write_json(norm_dir / "normalization_n1_manifest.json", {"stage": "normalization_n1", "stage_version": "n1.1"})
    write_jsonl(
        n2_dir / "candidate_nodes.jsonl",
        [
            {"node_id": "n1", "auto_cluster_id": "ac1"},
            {"node_id": "n2", "auto_cluster_id": "ac2"},
            {"node_id": "n3", "auto_cluster_id": "ac3"},
        ],
    )
    _write_json(n2_dir / "candidate_generation_manifest.json", {"stage_version": "n2.2"})
    _write_json(n2_dir / "candidate_generation_report.json", {"stage_version": "n2.2"})
    write_jsonl(
        n3_dir / "accepted_clusters.jsonl",
        [
            {
                "n3_cluster_id": "n3c1",
                "source_candidate_group_id": "cg1",
                "entity_type": "disease",
                "canonical_tag_ru": "Болезнь Аддисона",
                "canonical_tag_latin": "Addison disease",
                "labels": ["Аддисонова болезнь", "Болезнь Аддисона"],
                "node_ids": ["n1", "n2"],
                "confidence": 1.0,
                "from_split": False,
                "reason": "синонимы",
            }
        ],
    )
    write_jsonl(n3_dir / "rejected_groups.jsonl", [])
    write_jsonl(n3_dir / "split_groups.jsonl", [])
    write_jsonl(n3_dir / "web_or_human_review_groups.jsonl", [])
    write_jsonl(n3_dir / "llm_group_decisions.jsonl", [])
    _write_json(
        n3_dir / "n3_report.json",
        {"stage": "normalization_n3_llm_validation", "stage_version": "n3.0", "quality": {"passed": n3_quality_passed}},
    )
    _write_json(n3_dir / "n3_manifest.json", {"stage": "normalization_n3_llm_validation", "stage_version": "n3.0"})
    _write_json(n3_dir / "n3_quality_diagnostics.json", {})
    return data_dir


def _cluster(auto_cluster_id: str, entity_type: str, label: str, latin: str, mention_ids: list[str]) -> dict[str, object]:
    return {
        "auto_cluster_id": auto_cluster_id,
        "entity_type": entity_type,
        "canonical_display_candidate": label,
        "canonical_latin_candidate": latin,
        "aliases": [label],
        "normalized_aliases": [label.lower()],
        "mention_ids": mention_ids,
        "mentions_count": len(mention_ids),
        "documents_count": len(mention_ids),
        "article_candidate_count": len(mention_ids),
        "context_only_count": 0,
        "folder_candidate_count": 0,
        "review_required": False,
        "review_reasons": [],
        "risk_flags": [],
        "routing_flags": ["article_candidate"],
        "confidence_stats": {"avg": 0.95},
    }


def _mention(mention_id: str, doc_id: str, surface: str, ru: str, latin: str) -> dict[str, object]:
    return {
        "mention_id": mention_id,
        "doc_id": doc_id,
        "document_name": "Doc",
        "entity_type": "disease",
        "tag_role": "article_candidate",
        "article_candidate": True,
        "confidence": 0.95,
        "raw": {"surface": surface, "canonical_candidate_ru": ru, "canonical_candidate_latin": latin},
        "normalized": {
            "surface_norm": surface.lower(),
            "candidate_ru_norm": ru.lower(),
            "candidate_latin_norm": latin.lower(),
            "primary_norm": ru.lower(),
            "display_candidate_ru": ru,
            "display_candidate_latin": latin,
        },
    }


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

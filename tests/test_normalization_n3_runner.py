import json
import tempfile
import unittest
from pathlib import Path

from kb_rebuild.llm.providers import LLMCompletion
from kb_rebuild.normalization.n3.runner import N3Config, run_normalization_n3


class FakeGeminiClient:
    provider_name = "gemini_direct"
    api_keys_count = 1

    def __init__(self, responses: list[dict | str]) -> None:
        self.responses = list(responses)
        self.payloads: list[dict] = []

    def chat_completion(self, payload: dict) -> LLMCompletion:
        if not self.responses:
            raise AssertionError("unexpected Gemini request")
        self.payloads.append(payload)
        value = self.responses.pop(0)
        content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return LLMCompletion(
            raw={"candidates": [{"content": {"parts": [{"text": content}]}, "finishReason": "STOP"}]},
            content=content,
            usage={"prompt_tokens": 10, "completion_tokens": 20, "reasoning_tokens": 0},
            model="models/gemini-3-flash-preview",
            finish_reason="STOP",
            latency_ms=5,
            api_key_index=0,
        )


def _accept_response(group_id: str = "cg_test") -> dict:
    return {
        "candidate_group_id": group_id,
        "decision": "accept_same_entity",
        "confidence": 0.96,
        "canonical_tag_ru": "Болезнь Аддисона",
        "canonical_tag_latin": "Addison disease",
        "entity_type": "disease",
        "subclusters": [
            {
                "subcluster_id": "sc_001",
                "decision": "same_entity",
                "canonical_tag_ru": "Болезнь Аддисона",
                "canonical_tag_latin": "Addison disease",
                "labels": ["Аддисонова болезнь", "Болезнь Аддисона"],
                "node_ids": ["n1", "n2"],
                "confidence": 0.96,
                "reason": "синонимы одной болезни",
            }
        ],
        "rejected_labels": [],
        "reason": "синонимы одной болезни",
        "risk_flags": [],
        "requires_human_review": False,
    }


def _split_response(group_id: str = "cg_test") -> dict:
    return {
        "candidate_group_id": group_id,
        "decision": "split_into_subclusters",
        "confidence": 0.91,
        "canonical_tag_ru": "",
        "canonical_tag_latin": "",
        "entity_type": "disease",
        "subclusters": [
            {
                "subcluster_id": "sc_001",
                "decision": "same_entity",
                "canonical_tag_ru": "Фибрилляция предсердий",
                "canonical_tag_latin": "",
                "labels": ["Мерцательная аритмия", "Фибрилляция предсердий"],
                "node_ids": ["n1", "n2"],
                "confidence": 0.91,
                "reason": "синонимы",
            },
            {
                "subcluster_id": "sc_002",
                "decision": "singleton",
                "canonical_tag_ru": "",
                "canonical_tag_latin": "",
                "labels": ["Мегалобластная анемия"],
                "node_ids": ["n3"],
                "confidence": 0.9,
                "reason": "отдельная болезнь",
            },
        ],
        "rejected_labels": [],
        "reason": "частичный alias-subcluster",
        "risk_flags": [],
        "requires_human_review": False,
    }


class NormalizationN3RunnerTests(unittest.TestCase):
    def test_refuses_non_n2_2_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_fixture(Path(tmp), manifest_stage="n2.1")

            with self.assertRaisesRegex(ValueError, "stage_version=n2.2"):
                run_normalization_n3(N3Config.from_data_dir(data_dir), client=FakeGeminiClient([]))

    def test_creates_all_required_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_fixture(Path(tmp))
            config = N3Config.from_data_dir(data_dir, max_retries=0)

            report = run_normalization_n3(config, client=FakeGeminiClient([_accept_response()]))

            self.assertEqual(report["counts"]["groups_processed"], 1)
            self.assertEqual(report["counts"]["accepted_clusters_total"], 1)
            for filename in (
                "llm_group_decisions.jsonl",
                "accepted_clusters.jsonl",
                "rejected_groups.jsonl",
                "split_groups.jsonl",
                "web_or_human_review_groups.jsonl",
                "n3_report.json",
                "n3_manifest.json",
                "n3_quality_diagnostics.json",
            ):
                self.assertTrue((config.out_dir / filename).exists(), filename)

    def test_handles_invalid_llm_response_as_review_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_fixture(Path(tmp))
            config = N3Config.from_data_dir(data_dir, max_retries=0)

            report = run_normalization_n3(config, client=FakeGeminiClient(["{}"]))

            self.assertEqual(report["counts"]["invalid_llm_responses"], 1)
            self.assertEqual(report["counts"]["review_groups_total"], 1)
            failures = _read_jsonl(config.out_dir / "validation_failures.jsonl")
            self.assertEqual(len(failures), 1)

    def test_retry_uses_larger_output_budget_and_minimal_thinking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_fixture(Path(tmp))
            config = N3Config.from_data_dir(
                data_dir,
                max_retries=1,
                max_output_tokens=100,
                repair_max_output_tokens=250,
            )
            client = FakeGeminiClient(["{}", _accept_response()])

            report = run_normalization_n3(config, client=client)

            self.assertEqual(report["counts"]["invalid_llm_responses"], 0)
            self.assertEqual(client.payloads[0]["generationConfig"]["maxOutputTokens"], 100)
            self.assertEqual(client.payloads[1]["generationConfig"]["maxOutputTokens"], 200)
            self.assertEqual(client.payloads[1]["generationConfig"]["thinkingConfig"], {"thinkingLevel": "minimal"})

    def test_writes_accepted_clusters_from_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = _write_fixture(
                Path(tmp),
                labels=["Мерцательная аритмия", "Фибрилляция предсердий", "Мегалобластная анемия"],
                node_ids=["n1", "n2", "n3"],
            )
            config = N3Config.from_data_dir(data_dir, max_retries=0)

            report = run_normalization_n3(config, client=FakeGeminiClient([_split_response()]))

            self.assertEqual(report["counts"]["split_into_subclusters"], 1)
            self.assertEqual(report["counts"]["accepted_clusters_from_split"], 1)
            clusters = _read_jsonl(config.out_dir / "accepted_clusters.jsonl")
            self.assertEqual(clusters[0]["labels"], ["Мерцательная аритмия", "Фибрилляция предсердий"])


def _write_fixture(
    root: Path,
    *,
    manifest_stage: str = "n2.2",
    report_stage: str = "n2.2",
    quality_passed: bool = True,
    labels: list[str] | None = None,
    node_ids: list[str] | None = None,
) -> Path:
    labels = labels or ["Аддисонова болезнь", "Болезнь Аддисона"]
    node_ids = node_ids or ["n1", "n2"]
    data_dir = root / "data"
    n2_dir = data_dir / "normalization" / "n2"
    n2_dir.mkdir(parents=True, exist_ok=True)
    _write_json(n2_dir / "candidate_generation_manifest.json", {"stage_version": manifest_stage})
    _write_json(n2_dir / "candidate_generation_report.json", {"stage_version": report_stage, "quality_gate": {"passed": quality_passed}})
    _write_json(n2_dir / "group_quality_diagnostics.json", {"passed": True})
    _write_jsonl(
        n2_dir / "candidate_nodes.jsonl",
        [
            {
                "node_id": node_id,
                "label": label,
                "normalized_label": label.lower(),
                "aliases": [label],
                "normalized_aliases": [label.lower()],
                "latin_label": "",
                "mentions_count": 1,
                "documents_count": 1,
                "risk_flags": [],
                "routing_flags": ["article_candidate"],
            }
            for label, node_id in zip(labels, node_ids)
        ],
    )
    _write_jsonl(
        n2_dir / "n3_candidate_groups.jsonl",
        [
            {
                "candidate_group_id": "cg_test",
                "entity_type": "disease",
                "group_labels": labels,
                "node_ids": node_ids,
                "group_score": 0.95,
                "candidate_reasons": ["exact_normalized_match"],
                "clean_candidate_reasons": ["canonical_alias_exact_match"],
                "weak_candidate_reasons": [],
                "group_risk_flags": [],
                "mentions_count": len(labels),
                "documents_count": len(labels),
                "article_candidate_count": len(labels),
                "context_only_count": 0,
                "sample_documents": [],
            }
        ],
    )
    return data_dir


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kb_rebuild.articles.a2.models import A2Config
from kb_rebuild.articles.a2.runner import run_article_a2_extraction
from kb_rebuild.io.jsonl import read_jsonl, write_jsonl
from kb_rebuild.llm.gemini_client import GeminiError


@dataclass(frozen=True)
class FakeCompletion:
    raw: dict[str, Any]
    content: str
    usage: dict[str, int]
    model: str = "gemini-3-flash-preview"
    finish_reason: str = "STOP"
    latency_ms: int = 50
    api_key_index: int = 0
    usage_source: str = "api"


class FakeGeminiClient:
    provider_name = "gemini_direct"

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = list(responses or [])
        self.payloads: list[dict[str, Any]] = []
        self.api_keys_count = 1

    def chat_completion(self, payload: dict[str, Any]) -> FakeCompletion:
        self.payloads.append(payload)
        if self.responses:
            response = self.responses.pop(0)
        else:
            response = _valid_response(_batch_id_from_payload(payload), _task_ids_from_payload(payload))
        return FakeCompletion(
            raw={"candidates": []},
            content=json.dumps(response, ensure_ascii=False),
            usage={"prompt_tokens": 100, "completion_tokens": 50, "reasoning_tokens": 0},
        )


class SplitAwareFakeGeminiClient(FakeGeminiClient):
    def chat_completion(self, payload: dict[str, Any]) -> FakeCompletion:
        self.payloads.append(payload)
        batch_id = _batch_id_from_payload(payload)
        task_ids = _task_ids_from_payload(payload)
        if batch_id == "a2batch_000001":
            response = {"batch_id": batch_id, "task_results": []}
        else:
            response = _valid_response(batch_id, task_ids)
        return FakeCompletion(
            raw={},
            content=json.dumps(response, ensure_ascii=False),
            usage={"prompt_tokens": 100, "completion_tokens": 50, "reasoning_tokens": 0},
        )


class NonRetryableErrorClient(FakeGeminiClient):
    def chat_completion(self, payload: dict[str, Any]) -> FakeCompletion:
        self.payloads.append(payload)
        raise GeminiError(
            "Gemini HTTP 400 on key_index=0",
            status_code=400,
            response_body='{"error":{"message":"User location is not supported for the API use."}}',
            api_key_index=0,
        )


class ArticleA2RunnerTests(unittest.TestCase):
    def test_fake_gemini_client_returns_valid_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root, [_task("a2task_000000001")])
            config = _config(root, limit=1, max_inflight=1)
            report = run_article_a2_extraction(config, client=FakeGeminiClient())

            self.assertEqual(report["counts"]["tasks_processed"], 1)
            self.assertEqual(report["counts"]["evidence_items_total"], 1)
            self.assertTrue((config.out_dir / "evidence_items.jsonl").exists())

    def test_cache_hit_skips_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root, [_task("a2task_000000001")])
            config = _config(root, limit=1, max_inflight=1, resume=False)
            client = FakeGeminiClient()
            run_article_a2_extraction(config, client=client)
            self.assertEqual(len(client.payloads), 1)

            second_client = FakeGeminiClient()
            second_report = run_article_a2_extraction(config, client=second_client)

            self.assertEqual(len(second_client.payloads), 0)
            self.assertEqual(second_report["llm"]["cache_hits"], 1)

    def test_invalid_response_triggers_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root, [_task("a2task_000000001")])
            config = _config(root, limit=1, max_inflight=1, max_retries=1)
            client = FakeGeminiClient(
                responses=[
                    {"batch_id": "a2batch_000001", "task_results": []},
                    _valid_response("a2batch_000001", ["a2task_000000001"]),
                ]
            )
            report = run_article_a2_extraction(config, client=client)

            self.assertEqual(len(client.payloads), 2)
            self.assertEqual(report["counts"]["tasks_processed"], 1)
            self.assertGreaterEqual(report["llm"]["schema_validation_failures"], 1)

    def test_unrepaired_invalid_response_goes_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root, [_task("a2task_000000001")])
            config = _config(root, limit=1, max_inflight=1, max_retries=0)
            client = FakeGeminiClient(responses=[{"batch_id": "a2batch_000001", "task_results": []}])
            report = run_article_a2_extraction(config, client=client)

            self.assertEqual(report["counts"]["tasks_failed"], 1)
            failed = read_jsonl(config.out_dir / "failed_tasks.jsonl")
            self.assertEqual(failed[0]["status"], "failed")

    def test_batch_split_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root, [_task("a2task_000000001"), _task("a2task_000000002")])
            config = _config(root, limit=2, max_inflight=1, max_retries=0, max_tasks_per_batch=2)
            report = run_article_a2_extraction(config, client=SplitAwareFakeGeminiClient())

            self.assertEqual(report["counts"]["tasks_processed"], 2)
            self.assertEqual(report["counts"]["batch_splits"], 1)
            self.assertEqual(report["counts"]["tasks_failed"], 0)

    def test_non_retryable_provider_error_does_not_split_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root, [_task("a2task_000000001"), _task("a2task_000000002")])
            config = _config(root, limit=2, max_inflight=1, max_retries=3, max_tasks_per_batch=2)
            client = NonRetryableErrorClient()
            report = run_article_a2_extraction(config, client=client)

            self.assertEqual(len(client.payloads), 1)
            self.assertEqual(report["counts"]["batch_splits"], 0)
            self.assertEqual(report["counts"]["tasks_failed"], 2)

    def test_budget_stop_is_graceful(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root, [_task("a2task_000000001")])
            config = _config(root, limit=1, max_inflight=1, max_cost_usd=0.0)
            client = FakeGeminiClient()
            report = run_article_a2_extraction(config, client=client)

            self.assertEqual(len(client.payloads), 0)
            self.assertEqual(report["stop_reason"], "max_cost_reached")
            self.assertEqual(report["counts"]["tasks_failed"], 1)

    def test_resume_skips_completed_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root, [_task("a2task_000000001")])
            config = _config(root, limit=1, max_inflight=1, resume=True)
            run_article_a2_extraction(config, client=FakeGeminiClient())

            second_client = FakeGeminiClient()
            report = run_article_a2_extraction(config, client=second_client)

            self.assertEqual(len(second_client.payloads), 0)
            self.assertEqual(report["counts"]["tasks_requested"], 0)


def _config(root: Path, **kwargs: Any) -> A2Config:
    return A2Config.from_data_dir(
        root,
        a1_dir=root / "articles" / "a1",
        planning_dir=root / "articles" / "planning",
        normalization_final_dir=root / "normalization" / "final",
        out_dir=root / "articles" / "a2",
        structured_output_mode="prompt_json",
        max_output_tokens=1200,
        repair_max_output_tokens=2400,
        **kwargs,
    )


def _write_inputs(root: Path, tasks: list[dict[str, Any]]) -> None:
    a1_dir = root / "articles" / "a1"
    planning_dir = root / "articles" / "planning"
    final_dir = root / "normalization" / "final"
    a1_dir.mkdir(parents=True, exist_ok=True)
    planning_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(a1_dir / "a2_extraction_task_queue.jsonl", tasks)
    write_jsonl(a1_dir / "article_status_index.jsonl", [])
    write_jsonl(a1_dir / "tag_work_plan_adjusted.jsonl", [])
    write_jsonl(planning_dir / "source_block_windows.jsonl", [])
    (a1_dir / "a1_report.json").write_text(
        json.dumps({"stage": "article_a1_entity_json_bootstrap", "quality": {"passed": True}}),
        encoding="utf-8",
    )
    (a1_dir / "a1_manifest.json").write_text(json.dumps({"stage_version": "a1.0"}), encoding="utf-8")
    (final_dir / "tags_canonical.csv").write_text("tag_id,canonical_tag_ru\n", encoding="utf-8")
    (final_dir / "tag_aliases.csv").write_text("tag_id,alias\n", encoding="utf-8")


def _task(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "tag_id": f"tag_{task_id}",
        "canonical_tag_ru": "Тестовая сущность",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "source_strategy": "single_doc_extract",
        "doc_id": "doc_1",
        "document_name": "Тестовый документ",
        "window_id": "win_1",
        "block_ids": ["b1"],
        "block_indexes": [1],
        "heading_context": [],
        "window_text": "Тестовая сущность является примером для проверки цитаты.",
        "window_quality": "high",
        "match_method": "quote_match",
        "priority": "high",
        "estimated_input_chars": 58,
        "needs_review_before_publication": False,
        "review_reasons": [],
    }


def _valid_response(batch_id: str, task_ids: list[str]) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "task_results": [
            {
                "task_id": task_id,
                "tag_id": f"tag_{task_id}",
                "decision": "evidence_extracted",
                "relevance": "direct",
                "confidence": 0.9,
                "evidence_items": [
                    {
                        "fact_type": "definition",
                        "section_hint": "Что это",
                        "claim": "Сущность является примером.",
                        "quote": "Тестовая сущность является примером для проверки цитаты.",
                        "importance": "medium",
                        "confidence": 0.9,
                    }
                ],
                "reason": "",
            }
            for task_id in task_ids
        ],
    }


def _batch_id_from_payload(payload: dict[str, Any]) -> str:
    text = payload["contents"][0]["parts"][0]["text"]
    marker = '"batch_id": "'
    return text.split(marker, 1)[1].split('"', 1)[0]


def _task_ids_from_payload(payload: dict[str, Any]) -> list[str]:
    text = payload["contents"][0]["parts"][0]["text"]
    ids: list[str] = []
    marker = '"task_id": "'
    rest = text
    while marker in rest:
        rest = rest.split(marker, 1)[1]
        ids.append(rest.split('"', 1)[0])
    return ids


if __name__ == "__main__":
    unittest.main()

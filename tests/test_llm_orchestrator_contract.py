from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from threading import Barrier, Lock
from typing import Any
from unittest.mock import patch

from kb_rebuild.io.jsonl import read_jsonl, write_jsonl
from kb_rebuild.llm.cache import build_cache_key
from kb_rebuild.llm.openrouter_client import (
    OpenRouterClient,
    OpenRouterCompletion,
    OpenRouterError,
    parse_api_key_list,
)
from kb_rebuild.llm.schema_validation import load_document_tagging_schema, validate_tagging_response
from kb_rebuild.llm.tagging import TaggingConfig, run_tagging_calibration


class FakeClient:
    def __init__(self, content: str, fail_on_call: bool = False) -> None:
        self.content = content
        self.fail_on_call = fail_on_call
        self.calls = 0

    def chat_completion(self, payload: dict[str, Any]) -> OpenRouterCompletion:
        self.calls += 1
        if self.fail_on_call:
            raise AssertionError("external client must not be called")
        return OpenRouterCompletion(
            raw={
                "id": "fake",
                "model": payload["model"],
                "choices": [
                    {
                        "message": {"content": self.content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            },
            content=self.content,
            usage={"prompt_tokens": 100, "completion_tokens": 50, "reasoning_tokens": 0},
            model=payload["model"],
            finish_reason="stop",
            latency_ms=12,
        )


VALID_RESPONSE = """{
  "doc_id": "doc_000001_a1b2c3d4",
  "entities": [
    {
      "surface": "гастрит",
      "canonical_candidate_ru": "Гастрит",
      "canonical_candidate_latin": "Gastritis",
      "entity_type": "disease",
      "is_primary": true,
      "confidence": 0.94,
      "evidence_quotes": ["Гастрит является воспалением слизистой оболочки желудка"],
      "comment": "Документ посвящён гастриту"
    }
  ]
}"""


INVALID_ENTITY_TYPE_RESPONSE = """{
  "doc_id": "doc_000001_a1b2c3d4",
  "entities": [
    {
      "surface": "лечение",
      "canonical_candidate_ru": "Лечение",
      "canonical_candidate_latin": "",
      "entity_type": "treatment",
      "is_primary": true,
      "confidence": 0.5,
      "evidence_quotes": ["Гастрит является воспалением слизистой оболочки желудка"],
      "comment": "Невалидный тип"
    }
  ]
}"""


class LLMOrchestratorContractTests(unittest.TestCase):
    def test_cache_key_is_stable(self) -> None:
        params = {
            "temperature": 0,
            "max_tokens": 1600,
            "provider": {"require_parameters": True, "sort": "throughput"},
            "request_kind": "initial",
        }
        key1 = build_cache_key(
            model="deepseek/deepseek-v4-flash",
            prompt_version="tagging_v1",
            schema_version="document_tagging_v1",
            doc_id="doc_000001_a1b2c3d4",
            input_hash="abc",
            request_params=params,
        )
        key2 = build_cache_key(
            model="deepseek/deepseek-v4-flash",
            prompt_version="tagging_v1",
            schema_version="document_tagging_v1",
            doc_id="doc_000001_a1b2c3d4",
            input_hash="abc",
            request_params=dict(reversed(list(params.items()))),
        )
        self.assertEqual(key1, key2)

    def test_api_key_list_parser_accepts_common_separators(self) -> None:
        self.assertEqual(parse_api_key_list("k1,k2; k3\\nk4,k2"), ["k1", "k2", "k3", "k4"])

    def test_openrouter_client_rotates_api_keys(self) -> None:
        client = OpenRouterClient(api_keys=["k1", "k2"])
        self.assertEqual(client.api_keys_count, 2)
        self.assertEqual(client._next_api_key(), "k1")
        self.assertEqual(client._next_api_key(), "k2")
        self.assertEqual(client._next_api_key(), "k1")

    def test_openrouter_client_wraps_read_timeout(self) -> None:
        client = OpenRouterClient(api_keys=["k1"], timeout_seconds=1)
        with patch(
            "kb_rebuild.llm.openrouter_client.request.urlopen",
            side_effect=TimeoutError("read timed out"),
        ):
            with self.assertRaises(OpenRouterError) as raised:
                client.chat_completion({"model": "deepseek/deepseek-v4-flash", "messages": []})
        self.assertTrue(raised.exception.retryable)
        self.assertIn("timed out", str(raised.exception))

    def test_same_input_uses_cache_without_calling_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            _write_parsed_fixture(data_dir)
            config = _config(data_dir, resume=False)

            first_client = FakeClient(VALID_RESPONSE)
            first_report = run_tagging_calibration(config, client=first_client)
            self.assertEqual(first_report["documents_tagged"], 1)
            self.assertEqual(first_client.calls, 1)

            second_client = FakeClient(VALID_RESPONSE, fail_on_call=True)
            second_report = run_tagging_calibration(config, client=second_client)
            self.assertEqual(second_report["cache_hits"], 1)
            self.assertEqual(second_client.calls, 0)

    def test_schema_accepts_valid_response(self) -> None:
        schema = load_document_tagging_schema()
        errors = validate_tagging_response(
            value=__import__("json").loads(VALID_RESPONSE),
            schema=schema,
            expected_doc_id="doc_000001_a1b2c3d4",
        )
        self.assertEqual(errors, [])

    def test_schema_rejects_unknown_entity_type(self) -> None:
        schema = load_document_tagging_schema()
        errors = validate_tagging_response(
            value=__import__("json").loads(INVALID_ENTITY_TYPE_RESPONSE),
            schema=schema,
            expected_doc_id="doc_000001_a1b2c3d4",
        )
        self.assertTrue(any("invalid entity_type" in error for error in errors))

    def test_budget_limiter_stops_before_api_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            _write_parsed_fixture(data_dir)
            client = FakeClient(VALID_RESPONSE, fail_on_call=True)
            report = run_tagging_calibration(
                _config(data_dir, max_cost_usd=0.0),
                client=client,
            )
            self.assertEqual(report["documents_tagged"], 0)
            self.assertEqual(report["documents_failed"], 0)
            self.assertIn("budget_limit_reached", report["stop_reason"])
            self.assertEqual(client.calls, 0)

    def test_failure_file_created_for_invalid_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            _write_parsed_fixture(data_dir)
            client = FakeClient(INVALID_ENTITY_TYPE_RESPONSE)
            report = run_tagging_calibration(
                _config(data_dir, max_retries=0, fallback_model=None),
                client=client,
            )
            self.assertEqual(report["documents_tagged"], 0)
            self.assertEqual(report["documents_failed"], 1)
            failures = read_jsonl(data_dir / "tagging" / "document_tagging_failures.jsonl")
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["failure_reason"], "llm_tagging_failed")

    def test_retry_failures_keeps_successes_but_retries_failed_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            _write_parsed_fixture(data_dir)

            invalid_client = FakeClient(INVALID_ENTITY_TYPE_RESPONSE)
            failed_report = run_tagging_calibration(
                _config(data_dir, max_retries=0, fallback_model=None),
                client=invalid_client,
            )
            self.assertEqual(failed_report["documents_failed"], 1)

            valid_client = FakeClient(VALID_RESPONSE)
            recovered_report = run_tagging_calibration(
                _config(data_dir, max_retries=0, fallback_model=None, resume=True, retry_failures=True),
                client=valid_client,
            )
            self.assertEqual(recovered_report["documents_tagged"], 1)
            self.assertEqual(valid_client.calls, 1)

    def test_parallel_workers_require_multiple_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            _write_parsed_fixture(data_dir)
            client = type("SingleKeyClient", (), {"api_keys": ["k1"], "endpoint": "https://example.test", "timeout_seconds": 1})()
            with self.assertRaises(ValueError):
                run_tagging_calibration(_config(data_dir, parallel_workers=2), client=client)

    def test_parallel_workers_process_documents_with_separate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            _write_two_parsed_fixtures(data_dir)
            calls_by_key: Counter[str] = Counter()
            lock = Lock()
            barrier = Barrier(2)

            class FakeParallelOpenRouterClient:
                def __init__(self, api_keys: list[str], endpoint: str, timeout_seconds: int) -> None:
                    self.api_key = api_keys[0]

                def chat_completion(self, payload: dict[str, Any]) -> OpenRouterCompletion:
                    user_message = str(payload["messages"][1]["content"])
                    doc_id = user_message.split("DOC_ID:\n", 1)[1].split("\n", 1)[0]
                    with lock:
                        calls_by_key[self.api_key] += 1
                    barrier.wait(timeout=2)
                    content = json.dumps(
                        {
                            "doc_id": doc_id,
                            "entities": [
                                {
                                    "surface": "гастрит",
                                    "canonical_candidate_ru": "Гастрит",
                                    "canonical_candidate_latin": "Gastritis",
                                    "entity_type": "disease",
                                    "is_primary": True,
                                    "confidence": 0.94,
                                    "evidence_quotes": [
                                        "Гастрит является воспалением слизистой оболочки желудка"
                                    ],
                                    "comment": "Документ посвящён гастриту",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                    return OpenRouterCompletion(
                        raw={"model": payload["model"], "choices": [], "usage": {}},
                        content=content,
                        usage={"prompt_tokens": 100, "completion_tokens": 50, "reasoning_tokens": 0},
                        model=payload["model"],
                        finish_reason="stop",
                        latency_ms=12,
                    )

            key_list_client = type(
                "KeyListClient",
                (),
                {"api_keys": ["k1", "k2"], "endpoint": "https://example.test", "timeout_seconds": 1},
            )()
            with patch("kb_rebuild.llm.tagging.OpenRouterClient", FakeParallelOpenRouterClient):
                report = run_tagging_calibration(
                    _config(data_dir, limit=2, parallel_workers=2, fallback_model=None),
                    client=key_list_client,
                )

            self.assertEqual(report["documents_tagged"], 2)
            self.assertEqual(set(calls_by_key), {"k1", "k2"})


def _config(
    data_dir: Path,
    max_cost_usd: float = 5.0,
    max_retries: int = 2,
    fallback_model: str | None = "google/gemini-3.1-flash-lite-preview",
    resume: bool = False,
    retry_failures: bool = False,
    parallel_workers: int = 1,
    limit: int = 1,
) -> TaggingConfig:
    return TaggingConfig(
        data_dir=data_dir,
        limit=limit,
        model="deepseek/deepseek-v4-flash",
        fallback_model=fallback_model,
        max_cost_usd=max_cost_usd,
        max_retries=max_retries,
        retry_backoff_seconds=0,
        request_delay_seconds=0,
        rate_limit_backoff_seconds=0,
        resume=resume,
        retry_failures=retry_failures,
        parallel_workers=parallel_workers,
    )


def _write_parsed_fixture(data_dir: Path) -> None:
    write_jsonl(
        data_dir / "parsed" / "parsed_documents.jsonl",
        [
            {
                "doc_id": "doc_000001_a1b2c3d4",
                "row_index": 1,
                "name": "Гастрит",
                "description": "",
                "content_hash": "hash",
                "parse_status": "ok",
                "parse_errors": [],
                "clean_text": "Гастрит является воспалением слизистой оболочки желудка.",
                "text_length_chars": 58,
                "blocks_count": 1,
                "non_empty_blocks_count": 1,
                "block_types": {"paragraph": 1},
            }
        ],
    )


def _write_two_parsed_fixtures(data_dir: Path) -> None:
    records = []
    for index in range(1, 3):
        records.append(
            {
                "doc_id": f"doc_{index:06d}_a1b2c3d4",
                "row_index": index,
                "name": f"Гастрит {index}",
                "description": "",
                "content_hash": "hash",
                "parse_status": "ok",
                "parse_errors": [],
                "clean_text": "Гастрит является воспалением слизистой оболочки желудка.",
                "text_length_chars": 58,
                "blocks_count": 1,
                "non_empty_blocks_count": 1,
                "block_types": {"paragraph": 1},
            }
        )
    write_jsonl(data_dir / "parsed" / "parsed_documents.jsonl", records)


if __name__ == "__main__":
    unittest.main()

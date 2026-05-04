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
from kb_rebuild.cli import _parse_optional_model
from kb_rebuild.llm.cache import build_cache_key
from kb_rebuild.llm.openrouter_client import (
    OpenRouterClient,
    OpenRouterCompletion,
    OpenRouterError,
    parse_api_key_list,
)
from kb_rebuild.llm.rate_limiter import AdaptiveRateLimiter
from kb_rebuild.llm.schema_validation import (
    expand_compact_batch_response,
    load_compact_document_tagging_schema,
    load_document_tagging_batch_v2_schema,
    load_document_tagging_schema,
    load_document_tagging_v2_schema,
    schema_for_openrouter_lite,
    validate_compact_batch_response,
    validate_tagging_batch_response,
    validate_tagging_response,
)
from kb_rebuild.llm.tagging import (
    TaggingConfig,
    run_tagging_calibration,
    summarize_quote_statuses,
    validate_quote_in_text,
)
from kb_rebuild.llm.tagging_batch import BatchTaggingConfig, run_batch_tagging_calibration


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


VALID_V2_RESPONSE = {
    "doc_id": "doc_000001_a1b2c3d4",
    "entities": [
        {
            "surface": "гастрит",
            "canonical_candidate_ru": "Гастрит",
            "canonical_candidate_latin": "Gastritis",
            "entity_type": "disease",
            "article_candidate": True,
            "tag_role": "article_candidate",
            "is_primary": True,
            "confidence": 0.94,
            "evidence_quotes": ["Гастрит является воспалением слизистой оболочки желудка"],
            "comment": "Документ посвящён гастриту",
        }
    ],
}


class FakeBatchClient:
    def __init__(self, entity_type: str = "disease") -> None:
        self.entity_type = entity_type
        self.calls = 0

    def chat_completion(self, payload: dict[str, Any]) -> OpenRouterCompletion:
        self.calls += 1
        user_message = str(payload["messages"][1]["content"])
        doc_ids = _extract_doc_ids_from_batch_message(user_message)
        content = json.dumps(
            {
                "documents": [
                    {
                        "doc_id": doc_id,
                        "entities": [
                            {
                                "surface": "гастрит",
                                "canonical_candidate_ru": "Гастрит",
                                "canonical_candidate_latin": "Gastritis",
                                "entity_type": self.entity_type,
                                "article_candidate": True,
                                "tag_role": "article_candidate",
                                "is_primary": True,
                                "confidence": 0.94,
                                "evidence_quotes": [
                                    "Гастрит является воспалением слизистой оболочки желудка"
                                ],
                                "comment": "Документ посвящён гастриту",
                            }
                        ],
                    }
                    for doc_id in doc_ids
                ]
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

    def test_schema_v2_accepts_valid_response(self) -> None:
        errors = validate_tagging_response(
            value=VALID_V2_RESPONSE,
            schema=load_document_tagging_v2_schema(),
            expected_doc_id="doc_000001_a1b2c3d4",
        )
        self.assertEqual(errors, [])

    def test_schema_v2_rejects_unknown_entity_type(self) -> None:
        value = json.loads(json.dumps(VALID_V2_RESPONSE, ensure_ascii=False))
        value["entities"][0]["entity_type"] = "bad_type"
        errors = validate_tagging_response(
            value=value,
            schema=load_document_tagging_v2_schema(),
            expected_doc_id="doc_000001_a1b2c3d4",
        )
        self.assertTrue(any("invalid entity_type" in error for error in errors))

    def test_schema_v2_requires_tag_role(self) -> None:
        value = json.loads(json.dumps(VALID_V2_RESPONSE, ensure_ascii=False))
        value["entities"][0].pop("tag_role")
        errors = validate_tagging_response(
            value=value,
            schema=load_document_tagging_v2_schema(),
            expected_doc_id="doc_000001_a1b2c3d4",
        )
        self.assertTrue(any("missing required field tag_role" in error for error in errors))

    def test_schema_v2_requires_article_candidate(self) -> None:
        value = json.loads(json.dumps(VALID_V2_RESPONSE, ensure_ascii=False))
        value["entities"][0].pop("article_candidate")
        errors = validate_tagging_response(
            value=value,
            schema=load_document_tagging_v2_schema(),
            expected_doc_id="doc_000001_a1b2c3d4",
        )
        self.assertTrue(any("missing required field article_candidate" in error for error in errors))

    def test_schema_lite_removes_openrouter_strict_keywords(self) -> None:
        lite = schema_for_openrouter_lite(load_document_tagging_v2_schema())
        serialized = json.dumps(lite, ensure_ascii=False)
        self.assertNotIn("minLength", serialized)
        self.assertNotIn("additionalProperties", serialized)
        self.assertIn("article_candidate", serialized)

    def test_batch_schema_accepts_valid_response(self) -> None:
        schema = load_document_tagging_batch_v2_schema()
        errors = validate_tagging_batch_response(
            {"documents": [VALID_V2_RESPONSE]},
            schema,
            {"doc_000001_a1b2c3d4"},
        )
        self.assertEqual(errors, [])

    def test_batch_validator_rejects_extra_doc_id(self) -> None:
        schema = load_document_tagging_batch_v2_schema()
        errors = validate_tagging_batch_response(
            {"documents": [VALID_V2_RESPONSE]},
            schema,
            {"doc_000002_a1b2c3d4"},
        )
        self.assertTrue(any("unexpected doc_id" in error for error in errors))

    def test_batch_validator_rejects_missing_doc_id(self) -> None:
        schema = load_document_tagging_batch_v2_schema()
        errors = validate_tagging_batch_response(
            {"documents": []},
            schema,
            {"doc_000001_a1b2c3d4"},
        )
        self.assertTrue(any("missing doc_id doc_000001_a1b2c3d4" in error for error in errors))

    def test_compact_schema_validates_and_expands_response(self) -> None:
        compact = {
            "docs": [
                {
                    "d": "doc_000001_a1b2c3d4",
                    "e": [
                        {
                            "s": "гастрит",
                            "ru": "Гастрит",
                            "t": "disease",
                            "r": "article",
                            "c": 0.94,
                            "q": "Гастрит является воспалением слизистой оболочки желудка",
                        }
                    ],
                }
            ]
        }
        errors = validate_compact_batch_response(
            compact,
            load_compact_document_tagging_schema(),
            {"doc_000001_a1b2c3d4"},
        )
        self.assertEqual(errors, [])
        expanded = expand_compact_batch_response(compact)
        entity = expanded["documents"][0]["entities"][0]
        self.assertEqual(expanded["documents"][0]["doc_id"], "doc_000001_a1b2c3d4")
        self.assertEqual(entity["surface"], "гастрит")
        self.assertEqual(entity["tag_role"], "article_candidate")
        self.assertTrue(entity["article_candidate"])
        self.assertEqual(entity["evidence_quotes"], ["Гастрит является воспалением слизистой оболочки желудка"])

    def test_quote_validator_distinguishes_statuses(self) -> None:
        text = "Гастрит&nbsp;является\nвоспалением слизистой оболочки желудка."
        self.assertEqual(validate_quote_in_text("Гастрит&nbsp;является", text), "exact")
        self.assertEqual(
            validate_quote_in_text("Гастрит является воспалением слизистой оболочки желудка", text),
            "normalized",
        )
        self.assertEqual(
            validate_quote_in_text("Гастрит является воспалением слизистой желудка", text),
            "fuzzy",
        )
        self.assertEqual(validate_quote_in_text("бронхит", text), "not_found")
        self.assertEqual(summarize_quote_statuses(["exact", "normalized"]), "all_found")

    def test_fallback_model_none_parser(self) -> None:
        self.assertIsNone(_parse_optional_model("none"))
        self.assertIsNone(_parse_optional_model(" OFF "))
        self.assertEqual(_parse_optional_model("deepseek/deepseek-v4-flash"), "deepseek/deepseek-v4-flash")

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

    def test_active_output_replaces_duplicate_doc_id_and_moves_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            _write_parsed_fixture(data_dir)
            first_report = run_batch_tagging_calibration(
                _batch_config(data_dir, max_output_tokens=6000),
                client=FakeBatchClient(entity_type="disease"),
            )
            self.assertEqual(first_report["documents_tagged"], 1)

            second_report = run_batch_tagging_calibration(
                _batch_config(data_dir, max_output_tokens=6001, resume=False),
                client=FakeBatchClient(entity_type="medical_concept"),
            )
            self.assertEqual(second_report["active_duplicate_doc_ids"], 0)
            active = read_jsonl(data_dir / "tagging" / "document_tags_raw_active.jsonl")
            alias = read_jsonl(data_dir / "tagging" / "document_tags_raw.jsonl")
            history = read_jsonl(data_dir / "tagging" / "document_tags_raw_history.jsonl")
            self.assertEqual(len(active), 1)
            self.assertEqual(len(alias), 1)
            self.assertEqual(len(history), 1)
            self.assertEqual(active[0]["entities"][0]["entity_type"], "medical_concept")
            self.assertEqual(history[0]["entities"][0]["entity_type"], "disease")

    def test_batch_experiment_output_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            _write_parsed_fixture(data_dir)
            report = run_batch_tagging_calibration(
                _batch_config(data_dir, experiment_name="gemini_flash_strict"),
                client=FakeBatchClient(),
            )
            self.assertEqual(report["experiment_name"], "gemini_flash_strict")
            self.assertTrue(
                (data_dir / "tagging" / "experiments" / "gemini_flash_strict" / "document_tags_raw_active.jsonl").exists()
            )
            self.assertFalse((data_dir / "tagging" / "document_tags_raw_active.jsonl").exists())

    def test_rate_limiter_enforces_start_interval(self) -> None:
        now = [0.0]
        sleeps: list[float] = []

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            now[0] += seconds

        limiter = AdaptiveRateLimiter(
            max_inflight=1,
            min_request_interval_seconds=5,
            time_fn=lambda: now[0],
            sleep_fn=sleep,
        )
        limiter.acquire().release()
        limiter.acquire().release()
        self.assertEqual(sleeps, [5.0])

    def test_rate_limiter_429_sets_global_cooldown(self) -> None:
        now = [0.0]
        sleeps: list[float] = []

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            now[0] += seconds

        limiter = AdaptiveRateLimiter(
            max_inflight=4,
            min_request_interval_seconds=0,
            rate_limit_backoff_seconds=10,
            max_rate_limit_backoff_seconds=30,
            time_fn=lambda: now[0],
            sleep_fn=sleep,
        )
        cooldown = limiter.notify_error(
            OpenRouterError("OpenRouter HTTP 429", status_code=429, response_headers={"Retry-After": "20"}),
            attempt_index=0,
        )
        self.assertEqual(cooldown, 20.0)
        limiter.acquire().release()
        self.assertEqual(sleeps, [20.0])
        snapshot = limiter.snapshot()
        self.assertEqual(snapshot["cooldown_events_count"], 1)
        self.assertEqual(snapshot["retry_after_values_seconds"], [20.0])


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


def _batch_config(
    data_dir: Path,
    *,
    max_output_tokens: int = 6000,
    resume: bool = True,
    experiment_name: str | None = None,
) -> BatchTaggingConfig:
    return BatchTaggingConfig(
        data_dir=data_dir,
        limit=1,
        model="deepseek/deepseek-v4-flash",
        fallback_model=None,
        max_cost_usd=5,
        max_retries=0,
        batch_size=5,
        batch_char_limit=50000,
        prompt_char_limit_per_doc=16000,
        max_output_tokens=max_output_tokens,
        max_inflight=1,
        min_request_interval_seconds=0,
        rate_limit_backoff_seconds=0,
        max_rate_limit_backoff_seconds=0,
        resume=resume,
        experiment_name=experiment_name,
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


def _extract_doc_ids_from_batch_message(user_message: str) -> list[str]:
    doc_ids: list[str] = []
    lines = user_message.splitlines()
    for index, line in enumerate(lines[:-1]):
        if line.strip() == "DOC_ID:":
            doc_ids.append(lines[index + 1].strip())
    return doc_ids


if __name__ == "__main__":
    unittest.main()

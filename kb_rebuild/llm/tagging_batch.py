from __future__ import annotations

import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from kb_rebuild.io.jsonl import read_jsonl, write_jsonl
from kb_rebuild.llm.cache import LLMCache, build_cache_key, sha256_text
from kb_rebuild.llm.models import (
    PRIMARY_TAGGING_MODEL,
    calculate_cost_usd,
    estimate_request_cost_usd,
    validate_model_id,
)
from kb_rebuild.llm.openrouter_client import OpenRouterClient, OpenRouterCompletion, OpenRouterError
from kb_rebuild.llm.rate_limiter import AdaptiveRateLimiter
from kb_rebuild.llm.schema_validation import (
    expand_compact_batch_response,
    load_compact_document_tagging_schema,
    load_document_tagging_batch_v2_schema,
    schema_for_openrouter,
    schema_for_openrouter_lite,
    schema_version,
    validate_compact_batch_response,
    validate_tagging_batch_response,
)
from kb_rebuild.llm.tagging import (
    parse_json_content,
    summarize_quote_statuses,
    utc_now,
    validate_quote_in_text,
)


PROMPT_VERSION_V2 = "tagging_v2"
DEFAULT_BATCH_SIZE = 5
DEFAULT_BATCH_CHAR_LIMIT = 50_000
DEFAULT_PROMPT_CHAR_LIMIT_PER_DOC = 16_000
DEFAULT_MAX_OUTPUT_TOKENS = 6_000


@dataclass(frozen=True)
class BatchTaggingConfig:
    data_dir: Path
    limit: int | None = 100
    model: str = PRIMARY_TAGGING_MODEL
    fallback_model: str | None = None
    max_cost_usd: float = 5.0
    max_retries: int = 3
    batch_size: int = DEFAULT_BATCH_SIZE
    batch_char_limit: int = DEFAULT_BATCH_CHAR_LIMIT
    prompt_char_limit_per_doc: int = DEFAULT_PROMPT_CHAR_LIMIT_PER_DOC
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    temperature: float = 0.0
    provider_sort: str = "throughput"
    resume: bool = True
    retry_failures: bool = False
    max_inflight: int = 1
    min_request_interval_seconds: float = 5.0
    rate_limit_backoff_seconds: float = 120.0
    max_rate_limit_backoff_seconds: float = 300.0
    structured_output_mode: str = "strict"
    experiment_name: str | None = None
    prompt_version: str = PROMPT_VERSION_V2
    output_schema_version: str = "document_tagging_v2"
    tagging_text_mode: str = "full"
    tagging_char_limit: int = 8000


@dataclass(frozen=True)
class OutputPaths:
    tagging_dir: Path
    reports_dir: Path
    active_success_path: Path
    history_success_path: Path
    active_failures_path: Path
    history_failures_path: Path
    manifest_path: Path
    report_path: Path
    alias_success_path: Path | None


class BatchTaggingRunner:
    def __init__(
        self,
        config: BatchTaggingConfig,
        client: OpenRouterClient | Any,
        logger: logging.Logger | None = None,
        rate_limiter: AdaptiveRateLimiter | None = None,
    ) -> None:
        _validate_config(config)
        self.config = config
        self.client = client
        self.logger = logger or logging.getLogger(__name__)
        self.paths = _output_paths(config.data_dir, config.experiment_name)
        self.cache = LLMCache(config.data_dir / "llm_cache")
        self.prompt_text = _load_prompt(config.prompt_version)
        self.batch_schema = (
            load_compact_document_tagging_schema()
            if config.output_schema_version == "compact_tagging_v2"
            else load_document_tagging_batch_v2_schema()
        )
        self.schema_version = schema_version(self.batch_schema)
        self.rate_limiter = rate_limiter or AdaptiveRateLimiter(
            max_inflight=config.max_inflight,
            min_request_interval_seconds=config.min_request_interval_seconds,
            rate_limit_backoff_seconds=config.rate_limit_backoff_seconds,
            max_rate_limit_backoff_seconds=config.max_rate_limit_backoff_seconds,
            jitter_seconds=1.0 if config.max_inflight > 1 else 0.0,
        )
        self.run_id = f"tagging_{utc_now().replace('-', '').replace(':', '').replace('T', '_').replace('Z', '')}"
        self.models_used: set[str] = set()
        self.stats: dict[str, Any] = {
            "llm_api_attempts_total": 0,
            "llm_success_count": 0,
            "llm_error_count": 0,
            "llm_requests_count": 0,
            "llm_retries_count": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "estimated_cost_usd": 0.0,
            "latencies_ms": [],
            "invalid_json_count": 0,
            "http_status_counts": {},
            "rate_limit_count": 0,
            "batch_requests_count": 0,
            "batch_documents_requested": 0,
            "batch_documents_succeeded": 0,
            "batch_documents_failed": 0,
            "batch_split_count": 0,
            "notes": [],
            "suspicious_notes": [],
        }
        self._merge_lock = Lock()

    def run(self) -> dict[str, Any]:
        parsed_path = self.config.data_dir / "parsed" / "parsed_documents.jsonl"
        if not parsed_path.exists():
            raise FileNotFoundError(f"missing parsed artifact: {parsed_path}")

        documents = read_jsonl(parsed_path)
        selected_documents = documents[: self.config.limit] if self.config.limit else documents
        active_success_by_doc = _records_by_doc_id(_read_jsonl_if_exists(self.paths.active_success_path))
        active_failure_by_doc = _records_by_doc_id(_read_jsonl_if_exists(self.paths.active_failures_path))
        success_history = _read_jsonl_if_exists(self.paths.history_success_path)
        failure_history = _read_jsonl_if_exists(self.paths.history_failures_path)

        started_at = utc_now()
        stop_reason: str | None = None
        work_documents: list[dict[str, Any]] = []

        for document in selected_documents:
            doc_id = str(document.get("doc_id", ""))
            clean_text = str(document.get("clean_text", ""))
            if not doc_id:
                failure = self._failure_record(document, "missing_doc_id", ["parsed document has no doc_id"], 0)
                _replace_active_failure(active_failure_by_doc, active_success_by_doc, failure_history, success_history, failure)
                continue
            if not clean_text.strip():
                failure = self._failure_record(
                    document,
                    "empty_clean_text",
                    ["clean_text is empty; no evidence quotes can be validated"],
                    0,
                )
                _replace_active_failure(active_failure_by_doc, active_success_by_doc, failure_history, success_history, failure)
                continue
            if self.config.resume and _active_success_matches(active_success_by_doc.get(doc_id), self.config):
                continue
            if (
                self.config.resume
                and not self.config.retry_failures
                and _active_failure_matches(active_failure_by_doc.get(doc_id), self.config)
            ):
                continue
            work_documents.append(document)

        batches = _make_batches(
            work_documents,
            batch_size=self.config.batch_size,
            batch_char_limit=self.config.batch_char_limit,
            prompt_char_limit_per_doc=self.config.prompt_char_limit_per_doc,
        )
        if self.config.max_inflight > 1 and len(batches) > 1:
            stop_reason = self._process_batches_parallel(
                batches,
                active_success_by_doc=active_success_by_doc,
                active_failure_by_doc=active_failure_by_doc,
                success_history=success_history,
                failure_history=failure_history,
            )
            if stop_reason:
                self.stats["notes"].append(stop_reason)
        else:
            for batch in batches:
                outcome = self._process_batch(
                    batch,
                    active_success_by_doc=active_success_by_doc,
                    active_failure_by_doc=active_failure_by_doc,
                    success_history=success_history,
                    failure_history=failure_history,
                )
                if outcome:
                    stop_reason = outcome
                    self.stats["notes"].append(outcome)
                    break

        active_success_records = list(active_success_by_doc.values())
        active_failure_records = list(active_failure_by_doc.values())
        write_jsonl(self.paths.active_success_path, active_success_records)
        write_jsonl(self.paths.history_success_path, success_history)
        write_jsonl(self.paths.active_failures_path, active_failure_records)
        write_jsonl(self.paths.history_failures_path, failure_history)
        if self.paths.alias_success_path is not None:
            write_jsonl(self.paths.alias_success_path, active_success_records)

        report = self._build_report(
            selected_documents=selected_documents,
            active_success_records=active_success_records,
            active_failure_records=active_failure_records,
            started_at=started_at,
            stop_reason=stop_reason,
        )
        self.paths.reports_dir.mkdir(parents=True, exist_ok=True)
        with self.paths.report_path.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        self._write_manifest(report)
        return report

    def _process_batches_parallel(
        self,
        batches: list[list[dict[str, Any]]],
        *,
        active_success_by_doc: dict[str, dict[str, Any]],
        active_failure_by_doc: dict[str, dict[str, Any]],
        success_history: list[dict[str, Any]],
        failure_history: list[dict[str, Any]],
    ) -> str | None:
        stop_reason: str | None = None

        def process_one(batch: list[dict[str, Any]]) -> dict[str, Any]:
            worker = BatchTaggingRunner(
                config=self.config,
                client=self.client,
                logger=self.logger,
                rate_limiter=self.rate_limiter,
            )
            worker.run_id = self.run_id
            local_success_by_doc: dict[str, dict[str, Any]] = {}
            local_failure_by_doc: dict[str, dict[str, Any]] = {}
            local_success_history: list[dict[str, Any]] = []
            local_failure_history: list[dict[str, Any]] = []
            local_stop = worker._process_batch(
                batch,
                active_success_by_doc=local_success_by_doc,
                active_failure_by_doc=local_failure_by_doc,
                success_history=local_success_history,
                failure_history=local_failure_history,
            )
            return {
                "success_by_doc": local_success_by_doc,
                "failure_by_doc": local_failure_by_doc,
                "success_history": local_success_history,
                "failure_history": local_failure_history,
                "stats": worker.stats,
                "models_used": worker.models_used,
                "stop_reason": local_stop,
            }

        with ThreadPoolExecutor(max_workers=self.config.max_inflight) as executor:
            futures = [executor.submit(process_one, batch) for batch in batches]
            for future in as_completed(futures):
                result = future.result()
                _merge_batch_stats(self.stats, result["stats"])
                self.models_used.update(result["models_used"])
                for record in result["success_by_doc"].values():
                    _replace_active_success(active_success_by_doc, active_failure_by_doc, success_history, failure_history, record)
                for record in result["failure_by_doc"].values():
                    _replace_active_failure(active_failure_by_doc, active_success_by_doc, failure_history, success_history, record)
                success_history.extend(result["success_history"])
                failure_history.extend(result["failure_history"])
                if result["stop_reason"] and stop_reason is None:
                    stop_reason = str(result["stop_reason"])
        return stop_reason

    def _process_batch(
        self,
        documents: list[dict[str, Any]],
        *,
        active_success_by_doc: dict[str, dict[str, Any]],
        active_failure_by_doc: dict[str, dict[str, Any]],
        success_history: list[dict[str, Any]],
        failure_history: list[dict[str, Any]],
    ) -> str | None:
        if not documents:
            return None

        result = self._try_batch(documents)
        if result["status"] == "ok":
            parsed_documents = result["documents"]
            for document in documents:
                doc_id = str(document.get("doc_id", ""))
                parsed = parsed_documents[doc_id]
                success = self._success_record_from_parsed(
                    document=document,
                    parsed=parsed,
                    model=str(result["model"]),
                    requested_model=str(result["requested_model"]),
                    usage=result["usage"],
                    estimated_cost_usd=float(result["estimated_cost_usd"]) / max(1, len(documents)),
                    latency_ms=int(result["latency_ms"]),
                    finish_reason=str(result["finish_reason"]),
                    cache_key=str(result["cache_key"]),
                    from_cache=bool(result["from_cache"]),
                    input_metadata=result["input_metadata_by_doc"][doc_id],
                )
                _replace_active_success(active_success_by_doc, active_failure_by_doc, success_history, failure_history, success)
                self.stats["batch_documents_succeeded"] += 1
            return None

        if result["status"] == "stopped":
            return str(result["stop_reason"])

        if len(documents) > 1:
            self.stats["batch_split_count"] += 1
            midpoint = max(1, len(documents) // 2)
            left = self._process_batch(
                documents[:midpoint],
                active_success_by_doc=active_success_by_doc,
                active_failure_by_doc=active_failure_by_doc,
                success_history=success_history,
                failure_history=failure_history,
            )
            if left:
                return left
            return self._process_batch(
                documents[midpoint:],
                active_success_by_doc=active_success_by_doc,
                active_failure_by_doc=active_failure_by_doc,
                success_history=success_history,
                failure_history=failure_history,
            )

        document = documents[0]
        failure = self._failure_record(
            document,
            "llm_batch_tagging_failed",
            [str(error) for error in result.get("errors", [])][-20:],
            int(result.get("attempts", 0)),
        )
        _replace_active_failure(active_failure_by_doc, active_success_by_doc, failure_history, success_history, failure)
        self.stats["batch_documents_failed"] += 1
        return None

    def _try_batch(self, documents: list[dict[str, Any]]) -> dict[str, Any]:
        model_sequence = [self.config.model]
        if self.config.fallback_model and self.config.fallback_model not in model_sequence:
            model_sequence.append(self.config.fallback_model)

        last_errors: list[str] = []
        attempts = 0
        for model_index, model in enumerate(model_sequence):
            for attempt_index in range(self.config.max_retries + 1):
                request_kind = "initial" if attempt_index == 0 else "repair"
                if model_index > 0:
                    request_kind = "fallback" if attempt_index == 0 else "fallback_repair"

                context = self._request_context(documents, model, request_kind, attempt_index)
                cached = self.cache.get(context["cache_key"])
                if cached is not None:
                    cached_status = cached.get("validation_status")
                    if cached_status == "valid" and isinstance(cached.get("response_parsed"), dict):
                        self.stats["cache_hits"] += 1
                        self.stats["batch_documents_requested"] += len(documents)
                        documents_by_id = _parsed_documents_by_id(self._expanded_response(cached["response_parsed"]))
                        return {
                            "status": "ok",
                            "documents": documents_by_id,
                            "model": str(cached.get("model") or model),
                            "requested_model": model,
                            "usage": _safe_usage(cached.get("usage")),
                            "estimated_cost_usd": float(cached.get("estimated_cost_usd") or 0.0),
                            "latency_ms": int(cached.get("latency_ms") or 0),
                            "finish_reason": str(cached.get("finish_reason") or ""),
                            "cache_key": context["cache_key"],
                            "from_cache": True,
                            "input_metadata_by_doc": context["input_metadata_by_doc"],
                        }
                    if cached_status == "error":
                        _add_unique_note(self.stats, "ignored cached error responses and retried live batch")
                    elif self.config.retry_failures:
                        _add_unique_note(self.stats, "ignored cached invalid batch responses because retry_failures is enabled")
                    else:
                        self.stats["cache_hits"] += 1
                        self.stats["invalid_json_count"] += 1
                        last_errors.extend(str(error) for error in cached.get("validation_errors", []))
                        continue

                self.stats["cache_misses"] += 1
                preflight_cost = estimate_request_cost_usd(
                    model_id=model,
                    input_chars=int(context["prompt_chars"]),
                    max_output_tokens=self.config.max_output_tokens,
                )
                if float(self.stats["estimated_cost_usd"]) + preflight_cost > self.config.max_cost_usd:
                    return {
                        "status": "stopped",
                        "stop_reason": (
                            "budget_limit_reached: "
                            f"spent={float(self.stats['estimated_cost_usd']):.6f}, "
                            f"next_estimate={preflight_cost:.6f}, "
                            f"limit={self.config.max_cost_usd:.6f}"
                        ),
                    }

                try:
                    attempts += 1
                    self.stats["llm_api_attempts_total"] += 1
                    self.stats["batch_requests_count"] += 1
                    self.stats["batch_documents_requested"] += len(documents)
                    with self.rate_limiter.acquire():
                        completion = self.client.chat_completion(context["payload"])
                    self.rate_limiter.notify_success()
                except OpenRouterError as exc:
                    attempts += 0
                    self.stats["llm_error_count"] += 1
                    self._record_http_error(exc)
                    self._write_error_cache(context, model, exc)
                    last_errors.append(f"{model}: {exc}")
                    if exc.status_code == 429:
                        self.stats["rate_limit_count"] += 1
                        self.rate_limiter.notify_error(exc, attempt_index)
                    if exc.looks_like_structured_output_error:
                        break
                    if exc.retryable and attempt_index < self.config.max_retries:
                        self.stats["llm_retries_count"] += 1
                        continue
                    break

                self.stats["llm_success_count"] += 1
                self.stats["llm_requests_count"] += 1
                self.models_used.add(completion.model or model)
                self.stats["latencies_ms"].append(completion.latency_ms)
                cost_usd = calculate_cost_usd(model, **completion.usage)
                self.stats["estimated_cost_usd"] = round(float(self.stats["estimated_cost_usd"]) + cost_usd, 8)

                parsed, parse_errors = parse_json_content(completion.content)
                validation_errors = list(parse_errors)
                expected_doc_ids = {str(document.get("doc_id", "")) for document in documents}
                expanded_parsed = parsed
                if parsed is not None:
                    if self.config.output_schema_version == "compact_tagging_v2":
                        validation_errors.extend(validate_compact_batch_response(parsed, self.batch_schema, expected_doc_ids))
                        if not validation_errors:
                            expanded_parsed = expand_compact_batch_response(parsed)
                    else:
                        validation_errors.extend(validate_tagging_batch_response(parsed, self.batch_schema, expected_doc_ids))

                cache_record = self._cache_record(
                    context=context,
                    completion=completion,
                    parsed=parsed,
                    validation_errors=validation_errors,
                    cost_usd=cost_usd,
                    validation_status="valid" if not validation_errors else "invalid",
                )
                self.cache.set(context["cache_key"], cache_record)

                if not validation_errors and expanded_parsed is not None:
                    return {
                        "status": "ok",
                        "documents": _parsed_documents_by_id(expanded_parsed),
                        "model": completion.model or model,
                        "requested_model": model,
                        "usage": completion.usage,
                        "estimated_cost_usd": cost_usd,
                        "latency_ms": completion.latency_ms,
                        "finish_reason": completion.finish_reason,
                        "cache_key": context["cache_key"],
                        "from_cache": False,
                        "input_metadata_by_doc": context["input_metadata_by_doc"],
                    }

                self.stats["invalid_json_count"] += 1
                last_errors.extend(validation_errors)
                if attempt_index < self.config.max_retries:
                    self.stats["llm_retries_count"] += 1
                    continue
                break

        return {"status": "failed", "errors": last_errors, "attempts": attempts}

    def _expanded_response(self, parsed: dict[str, Any]) -> dict[str, Any]:
        if self.config.output_schema_version == "compact_tagging_v2":
            return expand_compact_batch_response(parsed)
        return parsed

    def _request_context(
        self,
        documents: list[dict[str, Any]],
        model: str,
        request_kind: str,
        attempt_index: int,
    ) -> dict[str, Any]:
        user_message, input_metadata_by_doc = build_batch_user_message(
            documents,
            prompt_char_limit_per_doc=self.config.prompt_char_limit_per_doc,
            tagging_text_mode=self.config.tagging_text_mode,
            tagging_char_limit=self.config.tagging_char_limit,
        )
        system_message = self.prompt_text
        if self.config.structured_output_mode == "prompt_json":
            system_message += "\n\nВерни строго JSON без markdown. Local schema validation будет обязательной."
        if request_kind in {"repair", "fallback_repair"}:
            system_message += (
                "\n\nПредыдущий batch-ответ был невалиден. Исправь ответ: верни строго один JSON-объект "
                "с массивом documents, без markdown, без лишних полей, с теми же DOC_ID."
            )
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]
        provider = {"require_parameters": True, "sort": self.config.provider_sort}
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "provider": provider,
        }
        if self.config.structured_output_mode in {"strict", "schema_lite"}:
            openrouter_schema = (
                schema_for_openrouter_lite(self.batch_schema)
                if self.config.structured_output_mode == "schema_lite"
                else schema_for_openrouter(self.batch_schema)
            )
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "document_tagging_batch",
                    "strict": True,
                    "schema": openrouter_schema,
                },
            }

        prompt_chars = sum(len(str(message.get("content", ""))) for message in messages)
        input_hash = sha256_text(
            json.dumps(
                {
                    "documents": input_metadata_by_doc,
                    "structured_output_mode": self.config.structured_output_mode,
                    "output_schema_version": self.config.output_schema_version,
                    "prompt_version": self.config.prompt_version,
                    "tagging_text_mode": self.config.tagging_text_mode,
                    "tagging_char_limit": self.config.tagging_char_limit,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        request_params = {
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "provider": provider,
            "batch_size": len(documents),
            "batch_char_limit": self.config.batch_char_limit,
            "prompt_char_limit_per_doc": self.config.prompt_char_limit_per_doc,
            "request_kind": request_kind,
            "attempt_index": attempt_index,
            "structured_output_mode": self.config.structured_output_mode,
            "experiment_name": self.config.experiment_name,
            "output_schema_version": self.config.output_schema_version,
            "prompt_version": self.config.prompt_version,
            "tagging_text_mode": self.config.tagging_text_mode,
            "tagging_char_limit": self.config.tagging_char_limit,
        }
        cache_key = build_cache_key(
            model=model,
            prompt_version=self.config.prompt_version,
            schema_version=self.schema_version,
            doc_id="batch:" + ",".join(str(document.get("doc_id", "")) for document in documents),
            input_hash=input_hash,
            request_params=request_params,
        )
        return {
            "payload": payload,
            "cache_key": cache_key,
            "prompt_chars": prompt_chars,
            "input_hash": input_hash,
            "input_metadata_by_doc": input_metadata_by_doc,
            "request_params": request_params,
        }

    def _success_record_from_parsed(
        self,
        *,
        document: dict[str, Any],
        parsed: dict[str, Any],
        model: str,
        requested_model: str,
        usage: dict[str, int],
        estimated_cost_usd: float,
        latency_ms: int,
        finish_reason: str,
        cache_key: str,
        from_cache: bool,
        input_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        clean_text = str(document.get("clean_text", ""))
        entities = []
        for entity in parsed.get("entities", []):
            entity_copy = dict(entity)
            quote_statuses = [validate_quote_in_text(str(quote), clean_text) for quote in entity_copy.get("evidence_quotes", [])]
            entity_copy["quote_validation_details"] = [
                {"index": index, "status": status}
                for index, status in enumerate(quote_statuses)
            ]
            entity_copy["quote_validation_status"] = summarize_quote_statuses(quote_statuses)
            entities.append(entity_copy)

        return {
            "doc_id": str(document.get("doc_id", "")),
            "document_name": str(document.get("name", "")),
            "model": model,
            "requested_model": requested_model,
            "prompt_version": self.config.prompt_version,
            "schema_version": "document_tagging_v2",
            "raw_schema_version": self.config.output_schema_version,
            "batch_schema_version": self.schema_version,
            "structured_output_mode": self.config.structured_output_mode,
            "experiment_name": self.config.experiment_name,
            "run_id": self.run_id,
            "entities": entities,
            "validation_status": "valid",
            "cache_key": cache_key,
            "from_cache": from_cache,
            "usage": usage,
            "estimated_cost_usd": round(estimated_cost_usd, 8),
            "latency_ms": latency_ms,
            "finish_reason": finish_reason,
            "input_metadata": input_metadata,
            "created_at": utc_now(),
        }

    def _failure_record(
        self,
        document: dict[str, Any],
        failure_reason: str,
        error_messages: list[str],
        attempts: int,
    ) -> dict[str, Any]:
        clean_text = str(document.get("clean_text", ""))
        return {
            "doc_id": str(document.get("doc_id", "")),
            "document_name": str(document.get("name", "")),
            "model": self.config.model,
            "requested_model": self.config.model,
            "prompt_version": self.config.prompt_version,
            "schema_version": "document_tagging_v2",
            "raw_schema_version": self.config.output_schema_version,
            "batch_schema_version": self.schema_version,
            "structured_output_mode": self.config.structured_output_mode,
            "experiment_name": self.config.experiment_name,
            "run_id": self.run_id,
            "validation_status": "failed",
            "failure_reason": failure_reason,
            "error_messages": error_messages,
            "attempts": attempts,
            "input_metadata": {
                "source_text_length_chars": len(clean_text),
                "prompt_char_limit": self.config.prompt_char_limit_per_doc,
                "input_truncated": len(clean_text) > self.config.prompt_char_limit_per_doc,
            },
            "created_at": utc_now(),
        }

    def _cache_record(
        self,
        *,
        context: dict[str, Any],
        completion: OpenRouterCompletion,
        parsed: dict[str, Any] | None,
        validation_errors: list[str],
        cost_usd: float,
        validation_status: str,
    ) -> dict[str, Any]:
        return {
            "cache_key": context["cache_key"],
            "created_at": utc_now(),
            "model": completion.model,
            "prompt_version": self.config.prompt_version,
            "schema_version": self.schema_version,
            "input_hash": context["input_hash"],
            "request": {
                "redacted": True,
                "parameters": context["request_params"],
                "input_metadata_by_doc": context["input_metadata_by_doc"],
            },
            "response_raw": completion.raw,
            "response_parsed": parsed,
            "usage": completion.usage,
            "estimated_cost_usd": cost_usd,
            "latency_ms": completion.latency_ms,
            "finish_reason": completion.finish_reason,
            "validation_status": validation_status,
            "validation_errors": validation_errors,
        }

    def _write_error_cache(self, context: dict[str, Any], model: str, error: OpenRouterError) -> None:
        record = {
            "cache_key": context["cache_key"],
            "created_at": utc_now(),
            "model": model,
            "prompt_version": self.config.prompt_version,
            "schema_version": self.schema_version,
            "input_hash": context["input_hash"],
            "request": {
                "redacted": True,
                "parameters": context["request_params"],
                "input_metadata_by_doc": context["input_metadata_by_doc"],
            },
            "response_raw": {
                "error": str(error),
                "status_code": error.status_code,
                "response_body_sample": error.response_body[:2000],
            },
            "response_parsed": None,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0},
            "estimated_cost_usd": 0.0,
            "latency_ms": 0,
            "finish_reason": "",
            "validation_status": "error",
            "validation_errors": [str(error)],
        }
        self.cache.set(context["cache_key"], record)

    def _record_http_error(self, error: OpenRouterError) -> None:
        status_key = str(error.status_code or "network")
        counts = self.stats["http_status_counts"]
        counts[status_key] = int(counts.get(status_key, 0)) + 1

    def _build_report(
        self,
        *,
        selected_documents: list[dict[str, Any]],
        active_success_records: list[dict[str, Any]],
        active_failure_records: list[dict[str, Any]],
        started_at: str,
        stop_reason: str | None,
    ) -> dict[str, Any]:
        selected_doc_ids = {str(document.get("doc_id", "")) for document in selected_documents}
        selected_successes = [record for record in active_success_records if str(record.get("doc_id", "")) in selected_doc_ids]
        selected_failures = [record for record in active_failure_records if str(record.get("doc_id", "")) in selected_doc_ids]
        entities_by_type: Counter[str] = Counter()
        entities_by_role: Counter[str] = Counter()
        quote_summary: Counter[str] = Counter()
        entities_total = 0
        for record in selected_successes:
            for entity in record.get("entities", []):
                if not isinstance(entity, dict):
                    continue
                entities_total += 1
                entity_type = entity.get("entity_type")
                tag_role = entity.get("tag_role")
                if isinstance(entity_type, str):
                    entities_by_type[entity_type] += 1
                if isinstance(tag_role, str):
                    entities_by_role[tag_role] += 1
                for detail in entity.get("quote_validation_details", []):
                    if not isinstance(detail, dict):
                        continue
                    quote_status = detail.get("status")
                    if quote_status == "exact":
                        quote_summary["found"] += 1
                    elif quote_status == "normalized":
                        quote_summary["normalized_found"] += 1
                    elif isinstance(quote_status, str):
                        quote_summary[quote_status] += 1
        latencies = self.stats["latencies_ms"]
        limiter_snapshot = self.rate_limiter.snapshot()
        report = {
            "stage": "tagging_batch_calibration",
            "run_id": self.run_id,
            "experiment_name": self.config.experiment_name,
            "started_at": started_at,
            "finished_at": utc_now(),
            "wall_clock_seconds": _seconds_between(started_at, utc_now()),
            "documents_requested": len(selected_documents),
            "documents_tagged": len(selected_successes),
            "documents_failed": len(selected_failures),
            "entities_total": entities_total,
            "entities_by_type": dict(sorted(entities_by_type.items())),
            "entities_by_role": dict(sorted(entities_by_role.items())),
            "models_used": sorted(self.models_used | {str(record.get("model", "")) for record in selected_successes if record.get("model")}),
            "prompt_version": self.config.prompt_version,
            "schema_version": "document_tagging_v2",
            "raw_schema_version": self.config.output_schema_version,
            "batch_schema_version": self.schema_version,
            "structured_output_mode": self.config.structured_output_mode,
            "llm_api_attempts_total": self.stats["llm_api_attempts_total"],
            "llm_success_count": self.stats["llm_success_count"],
            "llm_error_count": self.stats["llm_error_count"],
            "llm_requests_count": self.stats["llm_requests_count"],
            "llm_retries_count": self.stats["llm_retries_count"],
            "http_status_counts": dict(sorted(self.stats["http_status_counts"].items())),
            "http_429_count": int(self.stats["http_status_counts"].get("429", 0)),
            "rate_limit_count": self.stats["rate_limit_count"],
            "retry_after_values": limiter_snapshot["retry_after_values_seconds"],
            "retry_after_values_seconds": limiter_snapshot["retry_after_values_seconds"],
            "cooldown_events_count": limiter_snapshot["cooldown_events_count"],
            "cooldown_seconds_total": limiter_snapshot["cooldown_seconds_total"],
            "batch_requests_count": self.stats["batch_requests_count"],
            "batch_documents_requested": self.stats["batch_documents_requested"],
            "batch_documents_succeeded": self.stats["batch_documents_succeeded"],
            "batch_documents_failed": self.stats["batch_documents_failed"],
            "batch_split_count": self.stats["batch_split_count"],
            "batch_size": self.config.batch_size,
            "max_inflight": self.config.max_inflight,
            "active_records_count": len(active_success_records),
            "active_duplicate_doc_ids": _duplicate_doc_id_count(active_success_records),
            "quote_validation_summary": dict(sorted(quote_summary.items())),
            "cache_hits": self.stats["cache_hits"],
            "cache_misses": self.stats["cache_misses"],
            "estimated_cost_usd": round(float(self.stats["estimated_cost_usd"]), 8),
            "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
            "invalid_json_count": self.stats["invalid_json_count"],
            "budget_limit_usd": self.config.max_cost_usd,
            "stop_reason": stop_reason,
            "notes": self.stats["notes"],
            "suspicious_notes": self.stats["suspicious_notes"],
        }
        wall_clock_seconds = float(report["wall_clock_seconds"])
        wall_clock_hours = wall_clock_seconds / 3600 if wall_clock_seconds > 0 else 0.0
        token_total = _usage_tokens_total(selected_successes)
        report["requests_per_hour_effective"] = round(float(report["llm_api_attempts_total"]) / wall_clock_hours, 3) if wall_clock_hours else 0.0
        report["documents_per_hour_effective"] = round(len(selected_successes) / wall_clock_hours, 3) if wall_clock_hours else 0.0
        report["tokens_per_hour_effective"] = round(token_total / wall_clock_hours, 3) if wall_clock_hours else 0.0
        return report

    def _write_manifest(self, report: dict[str, Any]) -> None:
        manifest = {
            "run_id": self.run_id,
            "model": self.config.model,
            "fallback_model": self.config.fallback_model,
            "prompt_version": self.config.prompt_version,
            "schema_version": "document_tagging_v2",
            "raw_schema_version": self.config.output_schema_version,
            "batch_schema_version": self.schema_version,
            "structured_output_mode": self.config.structured_output_mode,
            "experiment_name": self.config.experiment_name,
            "limit": self.config.limit,
            "documents_requested": report.get("documents_requested", 0),
            "documents_tagged": report.get("documents_tagged", 0),
            "documents_failed": report.get("documents_failed", 0),
            "created_at": utc_now(),
            "active_success_path": str(self.paths.active_success_path),
            "active_failures_path": str(self.paths.active_failures_path),
        }
        self.paths.tagging_dir.mkdir(parents=True, exist_ok=True)
        with self.paths.manifest_path.open("w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")


def run_batch_tagging_calibration(
    config: BatchTaggingConfig,
    client: OpenRouterClient | Any | None = None,
    logger: logging.Logger | None = None,
    rate_limiter: AdaptiveRateLimiter | None = None,
) -> dict[str, Any]:
    actual_client = client if client is not None else OpenRouterClient()
    return BatchTaggingRunner(config=config, client=actual_client, logger=logger, rate_limiter=rate_limiter).run()


def build_batch_user_message(
    documents: list[dict[str, Any]],
    *,
    prompt_char_limit_per_doc: int,
    tagging_text_mode: str = "full",
    tagging_char_limit: int = 8000,
) -> tuple[str, dict[str, dict[str, Any]]]:
    parts = ["DOCUMENTS:"]
    metadata_by_doc: dict[str, dict[str, Any]] = {}
    for document in documents:
        doc_id = str(document.get("doc_id", ""))
        document_name = str(document.get("name", ""))
        clean_text = str(document.get("clean_text", ""))
        limit = min(prompt_char_limit_per_doc, tagging_char_limit) if tagging_text_mode == "compact" else prompt_char_limit_per_doc
        clean_text_for_prompt = _build_tagging_text(document_name, clean_text, tagging_text_mode, limit)
        truncated = clean_text_for_prompt != clean_text
        parts.append(
            "<DOCUMENT>\n"
            f"DOC_ID:\n{doc_id}\n\n"
            f"DOCUMENT_NAME:\n{document_name}\n\n"
            f"CLEAN_TEXT:\n{clean_text_for_prompt}\n"
            "</DOCUMENT>"
        )
        metadata_by_doc[doc_id] = {
            "doc_id": doc_id,
            "document_name": document_name,
            "source_text_length_chars": len(clean_text),
            "prompt_text_length_chars": len(clean_text_for_prompt),
            "input_truncated": truncated,
            "prompt_char_limit": limit,
            "tagging_text_mode": tagging_text_mode,
            "input_hash": sha256_text(
                json.dumps(
                    {
                        "doc_id": doc_id,
                        "document_name": document_name,
                        "clean_text": clean_text_for_prompt,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            ),
        }
    return "\n\n".join(parts), metadata_by_doc


def _validate_config(config: BatchTaggingConfig) -> None:
    validate_model_id(config.model)
    if config.fallback_model is not None:
        validate_model_id(config.fallback_model)
    if config.limit is not None and config.limit <= 0:
        raise ValueError("limit must be positive or None")
    if config.max_cost_usd < 0:
        raise ValueError("max_cost_usd must be >= 0")
    if config.max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    if config.batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if config.batch_char_limit <= 0:
        raise ValueError("batch_char_limit must be > 0")
    if config.prompt_char_limit_per_doc <= 0:
        raise ValueError("prompt_char_limit_per_doc must be > 0")
    if config.max_output_tokens <= 0:
        raise ValueError("max_output_tokens must be > 0")
    if config.max_inflight <= 0:
        raise ValueError("max_inflight must be > 0")
    if config.structured_output_mode not in {"strict", "schema_lite", "prompt_json"}:
        raise ValueError("structured_output_mode must be strict, schema_lite or prompt_json")
    if config.output_schema_version not in {"document_tagging_v2", "compact_tagging_v2"}:
        raise ValueError("output_schema_version must be document_tagging_v2 or compact_tagging_v2")
    if config.prompt_version not in {"tagging_v2", "tagging_v2_compact"}:
        raise ValueError("prompt_version must be tagging_v2 or tagging_v2_compact")
    if config.tagging_text_mode not in {"full", "compact"}:
        raise ValueError("tagging_text_mode must be full or compact")
    if config.tagging_char_limit <= 0:
        raise ValueError("tagging_char_limit must be > 0")
    if config.experiment_name is not None and not config.experiment_name.replace("_", "").replace("-", "").isalnum():
        raise ValueError("experiment_name may contain only letters, digits, '-' and '_'")


def _make_batches(
    documents: list[dict[str, Any]],
    *,
    batch_size: int,
    batch_char_limit: int,
    prompt_char_limit_per_doc: int,
) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for document in documents:
        clean_text = str(document.get("clean_text", ""))
        chars = min(len(clean_text), prompt_char_limit_per_doc)
        if current and (len(current) >= batch_size or current_chars + chars > batch_char_limit):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(document)
        current_chars += chars
    if current:
        batches.append(current)
    return batches


def _output_paths(data_dir: Path, experiment_name: str | None) -> OutputPaths:
    if experiment_name:
        tagging_dir = data_dir / "tagging" / "experiments" / experiment_name
        reports_dir = tagging_dir
        alias_success_path = None
        active_failures_path = tagging_dir / "document_tagging_failures.jsonl"
    else:
        tagging_dir = data_dir / "tagging"
        reports_dir = data_dir / "reports"
        alias_success_path = tagging_dir / "document_tags_raw.jsonl"
        active_failures_path = tagging_dir / "document_tagging_failures_active.jsonl"
    return OutputPaths(
        tagging_dir=tagging_dir,
        reports_dir=reports_dir,
        active_success_path=tagging_dir / "document_tags_raw_active.jsonl",
        history_success_path=tagging_dir / "document_tags_raw_history.jsonl",
        active_failures_path=active_failures_path,
        history_failures_path=tagging_dir / "document_tagging_failures_history.jsonl",
        manifest_path=tagging_dir / "tagging_active_manifest.json",
        report_path=reports_dir / "tagging_report.json",
        alias_success_path=alias_success_path,
    )


def _load_prompt(prompt_version: str) -> str:
    prompts = {
        "tagging_v2": "tagging_v2.md",
        "tagging_v2_compact": "tagging_v2_compact.md",
    }
    return (Path(__file__).parent / "prompts" / prompts[prompt_version]).read_text(encoding="utf-8")


def _build_tagging_text(document_name: str, clean_text: str, mode: str, char_limit: int) -> str:
    if mode == "full" or len(clean_text) <= char_limit:
        return clean_text[:char_limit]
    tail_size = min(1500, max(0, char_limit // 5))
    head_size = max(0, char_limit - tail_size)
    head = clean_text[:head_size]
    tail = clean_text[-tail_size:] if tail_size else ""
    return f"{head}\n\n[...]\n\n{tail}"


def _parsed_documents_by_id(parsed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    documents = parsed.get("documents", [])
    if not isinstance(documents, list):
        return {}
    return {
        str(document.get("doc_id", "")): document
        for document in documents
        if isinstance(document, dict)
    }


def _records_by_doc_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        doc_id = str(record.get("doc_id", ""))
        if doc_id:
            result[doc_id] = record
    return result


def _replace_active_success(
    active_success_by_doc: dict[str, dict[str, Any]],
    active_failure_by_doc: dict[str, dict[str, Any]],
    success_history: list[dict[str, Any]],
    failure_history: list[dict[str, Any]],
    record: dict[str, Any],
) -> None:
    doc_id = str(record.get("doc_id", ""))
    previous_success = active_success_by_doc.get(doc_id)
    if previous_success is not None and previous_success != record:
        success_history.append(previous_success)
    previous_failure = active_failure_by_doc.pop(doc_id, None)
    if previous_failure is not None:
        failure_history.append(previous_failure)
    active_success_by_doc[doc_id] = record


def _replace_active_failure(
    active_failure_by_doc: dict[str, dict[str, Any]],
    active_success_by_doc: dict[str, dict[str, Any]],
    failure_history: list[dict[str, Any]],
    success_history: list[dict[str, Any]],
    record: dict[str, Any],
) -> None:
    doc_id = str(record.get("doc_id", ""))
    previous_success = active_success_by_doc.pop(doc_id, None)
    if previous_success is not None:
        success_history.append(previous_success)
    previous = active_failure_by_doc.get(doc_id)
    if previous is not None and previous != record:
        failure_history.append(previous)
    active_failure_by_doc[doc_id] = record


def _active_success_matches(record: dict[str, Any] | None, config: BatchTaggingConfig) -> bool:
    if not record:
        return False
    return (
        record.get("requested_model") == config.model
        and record.get("prompt_version") == config.prompt_version
        and record.get("schema_version") == "document_tagging_v2"
        and record.get("raw_schema_version", "document_tagging_v2") == config.output_schema_version
        and record.get("structured_output_mode") == config.structured_output_mode
        and record.get("validation_status") == "valid"
    )


def _active_failure_matches(record: dict[str, Any] | None, config: BatchTaggingConfig) -> bool:
    if not record:
        return False
    return (
        record.get("requested_model") == config.model
        and record.get("prompt_version") == config.prompt_version
        and record.get("schema_version") == "document_tagging_v2"
        and record.get("raw_schema_version", "document_tagging_v2") == config.output_schema_version
        and record.get("structured_output_mode") == config.structured_output_mode
        and record.get("validation_status") == "failed"
    )


def _duplicate_doc_id_count(records: list[dict[str, Any]]) -> int:
    counts: Counter[str] = Counter(str(record.get("doc_id", "")) for record in records if record.get("doc_id"))
    return sum(count - 1 for count in counts.values() if count > 1)


def _seconds_between(started_at: str, finished_at: str) -> float:
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return max(0.0, round((finished - started).total_seconds(), 3))


def _usage_tokens_total(records: list[dict[str, Any]]) -> int:
    total = 0
    for record in records:
        usage = record.get("usage")
        if not isinstance(usage, dict):
            continue
        total += int(usage.get("prompt_tokens") or 0)
        total += int(usage.get("completion_tokens") or 0)
        total += int(usage.get("reasoning_tokens") or 0)
    return total


def _safe_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
    return {
        "prompt_tokens": int(value.get("prompt_tokens") or 0),
        "completion_tokens": int(value.get("completion_tokens") or 0),
        "reasoning_tokens": int(value.get("reasoning_tokens") or 0),
    }


def _merge_batch_stats(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        "llm_api_attempts_total",
        "llm_success_count",
        "llm_error_count",
        "llm_requests_count",
        "llm_retries_count",
        "cache_hits",
        "cache_misses",
        "invalid_json_count",
        "rate_limit_count",
        "batch_requests_count",
        "batch_documents_requested",
        "batch_documents_succeeded",
        "batch_documents_failed",
        "batch_split_count",
    ):
        target[key] = int(target.get(key, 0)) + int(source.get(key, 0))
    target["estimated_cost_usd"] = round(
        float(target.get("estimated_cost_usd", 0.0)) + float(source.get("estimated_cost_usd", 0.0)),
        8,
    )
    target.setdefault("latencies_ms", []).extend(source.get("latencies_ms", []))
    target_status_counts = target.setdefault("http_status_counts", {})
    for status, count in source.get("http_status_counts", {}).items():
        target_status_counts[status] = int(target_status_counts.get(status, 0)) + int(count)
    for key in ("notes", "suspicious_notes"):
        target_items = target.setdefault(key, [])
        for item in source.get(key, []):
            if item not in target_items:
                target_items.append(item)


def _add_unique_note(stats: dict[str, Any], note: str) -> None:
    notes = stats.setdefault("notes", [])
    if note not in notes:
        notes.append(note)


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return read_jsonl(path)

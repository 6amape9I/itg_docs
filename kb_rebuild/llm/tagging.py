from __future__ import annotations

import json
import logging
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from threading import Event, Lock
from typing import Any

from kb_rebuild.io.jsonl import read_jsonl, write_jsonl
from kb_rebuild.llm.cache import LLMCache, build_cache_key, sha256_text
from kb_rebuild.llm.models import (
    FALLBACK_TAGGING_MODEL,
    NORMALIZATION_MODEL,
    PRIMARY_TAGGING_MODEL,
    calculate_cost_usd,
    estimate_request_cost_usd,
    validate_model_id,
)
from kb_rebuild.llm.openrouter_client import (
    OPENROUTER_CHAT_COMPLETIONS_URL,
    OpenRouterClient,
    OpenRouterCompletion,
    OpenRouterError,
)
from kb_rebuild.llm.schema_validation import (
    load_document_tagging_schema,
    schema_for_openrouter,
    schema_version,
    validate_tagging_response,
)


PROMPT_VERSION = "tagging_v1"
DEFAULT_MAX_OUTPUT_TOKENS = 3200
DEFAULT_PROMPT_CHAR_LIMIT = 16000


@dataclass(frozen=True)
class TaggingConfig:
    data_dir: Path
    limit: int | None = 100
    model: str = PRIMARY_TAGGING_MODEL
    fallback_model: str | None = FALLBACK_TAGGING_MODEL
    max_cost_usd: float = 5.0
    max_retries: int = 2
    prompt_char_limit: int = DEFAULT_PROMPT_CHAR_LIMIT
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    temperature: float = 0.0
    provider_sort: str = "throughput"
    resume: bool = True
    retry_failures: bool = False
    retry_backoff_seconds: float = 1.0
    request_delay_seconds: float = 2.0
    rate_limit_backoff_seconds: float = 30.0
    parallel_workers: int = 1


@dataclass
class DocumentTaggingOutcome:
    status: str
    success_record: dict[str, Any] | None = None
    failure_record: dict[str, Any] | None = None
    stop_reason: str | None = None


@dataclass(frozen=True)
class BudgetReservation:
    amount_usd: float


class SharedBudgetTracker:
    def __init__(self, max_cost_usd: float) -> None:
        self.max_cost_usd = max_cost_usd
        self._reserved_or_spent_usd = 0.0
        self._lock = Lock()

    @property
    def reserved_or_spent_usd(self) -> float:
        with self._lock:
            return self._reserved_or_spent_usd

    def reserve(self, amount_usd: float) -> BudgetReservation | None:
        with self._lock:
            if self._reserved_or_spent_usd + amount_usd > self.max_cost_usd:
                return None
            self._reserved_or_spent_usd = round(self._reserved_or_spent_usd + amount_usd, 8)
        return BudgetReservation(amount_usd=amount_usd)

    def commit(self, reservation: BudgetReservation, actual_cost_usd: float) -> None:
        with self._lock:
            self._reserved_or_spent_usd = round(
                self._reserved_or_spent_usd - reservation.amount_usd + actual_cost_usd,
                8,
            )

    def release(self, reservation: BudgetReservation) -> None:
        with self._lock:
            self._reserved_or_spent_usd = round(
                max(0.0, self._reserved_or_spent_usd - reservation.amount_usd),
                8,
            )


class TaggingRunner:
    def __init__(
        self,
        config: TaggingConfig,
        client: OpenRouterClient | Any,
        logger: logging.Logger | None = None,
        budget_tracker: SharedBudgetTracker | None = None,
    ) -> None:
        validate_model_id(config.model)
        if config.fallback_model is not None:
            validate_model_id(config.fallback_model)
        if config.limit is not None and config.limit <= 0:
            raise ValueError("limit must be positive or None")
        if config.max_cost_usd < 0:
            raise ValueError("max_cost_usd must be >= 0")
        if config.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if config.prompt_char_limit <= 0:
            raise ValueError("prompt_char_limit must be > 0")
        if config.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be > 0")
        if config.request_delay_seconds < 0:
            raise ValueError("request_delay_seconds must be >= 0")
        if config.rate_limit_backoff_seconds < 0:
            raise ValueError("rate_limit_backoff_seconds must be >= 0")
        if config.parallel_workers <= 0:
            raise ValueError("parallel_workers must be > 0")

        self.config = config
        self.client = client
        self.logger = logger or logging.getLogger(__name__)
        self.budget_tracker = budget_tracker
        self.cache = LLMCache(config.data_dir / "llm_cache")
        self.prompt_text = _load_prompt()
        self.schema = load_document_tagging_schema()
        self.schema_version = schema_version(self.schema)
        self.models_used: set[str] = set()
        self.stats: dict[str, Any] = {
            "llm_requests_count": 0,
            "llm_retries_count": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "estimated_cost_usd": 0.0,
            "latencies_ms": [],
            "invalid_json_count": 0,
            "notes": [],
            "rate_limit_count": 0,
            "sleep_seconds_total": 0.0,
        }
        self._last_live_request_finished_at: float | None = None

    def run(self) -> dict[str, Any]:
        parsed_path = self.config.data_dir / "parsed" / "parsed_documents.jsonl"
        if not parsed_path.exists():
            raise FileNotFoundError(f"missing parsed artifact: {parsed_path}")

        documents = read_jsonl(parsed_path)
        selected_documents = documents[: self.config.limit] if self.config.limit else documents

        tagging_dir = self.config.data_dir / "tagging"
        reports_dir = self.config.data_dir / "reports"
        success_path = tagging_dir / "document_tags_raw.jsonl"
        failures_path = tagging_dir / "document_tagging_failures.jsonl"
        report_path = reports_dir / "tagging_report.json"

        success_records = _read_jsonl_if_exists(success_path)
        failure_records = _read_jsonl_if_exists(failures_path)
        success_by_key = {_record_key(record): record for record in success_records}
        failure_by_key = {_record_key(record): record for record in failure_records}

        started_at = utc_now()
        processed_keys: set[tuple[str, str, str, str]] = set()
        stop_reason: str | None = None
        current_model_record_keys: set[tuple[str, str, str, str]] = set()

        for document in selected_documents:
            doc_id = str(document.get("doc_id", ""))
            record_key = (doc_id, self.config.model, PROMPT_VERSION, self.schema_version)
            current_model_record_keys.add(record_key)

            if self.config.resume and record_key in success_by_key:
                processed_keys.add(record_key)
                continue
            if self.config.resume and not self.config.retry_failures and record_key in failure_by_key:
                processed_keys.add(record_key)
                continue

            outcome = self.tag_document(document)
            if outcome.stop_reason:
                stop_reason = outcome.stop_reason
                self.stats["notes"].append(outcome.stop_reason)
                break
            if outcome.status == "ok" and outcome.success_record is not None:
                success_by_key[_record_key(outcome.success_record)] = outcome.success_record
                failure_by_key.pop(record_key, None)
                processed_keys.add(record_key)
            elif outcome.failure_record is not None:
                failure_by_key[_record_key(outcome.failure_record)] = outcome.failure_record
                processed_keys.add(record_key)

        write_jsonl(success_path, success_by_key.values())
        write_jsonl(failures_path, failure_by_key.values())

        report = self._build_report(
            selected_documents=selected_documents,
            success_by_key=success_by_key,
            failure_by_key=failure_by_key,
            current_model_record_keys=current_model_record_keys,
            stop_reason=stop_reason,
            started_at=started_at,
        )
        reports_dir.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        return report

    def tag_document(self, document: dict[str, Any]) -> DocumentTaggingOutcome:
        doc_id = str(document.get("doc_id", ""))
        document_name = str(document.get("name", ""))
        clean_text = str(document.get("clean_text", ""))
        if not doc_id:
            return DocumentTaggingOutcome(
                status="failed",
                failure_record=self._failure_record(
                    document=document,
                    model=self.config.model,
                    failure_reason="missing_doc_id",
                    error_messages=["parsed document has no doc_id"],
                    attempts=0,
                ),
            )
        if not clean_text.strip():
            return DocumentTaggingOutcome(
                status="failed",
                failure_record=self._failure_record(
                    document=document,
                    model=self.config.model,
                    failure_reason="empty_clean_text",
                    error_messages=["clean_text is empty; no evidence quotes can be validated"],
                    attempts=0,
                ),
            )

        model_sequence = [self.config.model]
        if self.config.fallback_model and self.config.fallback_model not in model_sequence:
            model_sequence.append(self.config.fallback_model)

        last_errors: list[str] = []
        total_attempts = 0
        for model_index, model in enumerate(model_sequence):
            for attempt_index in range(self.config.max_retries + 1):
                request_kind = "initial" if attempt_index == 0 else "repair"
                if model_index > 0 and attempt_index == 0:
                    request_kind = "fallback"
                elif model_index > 0:
                    request_kind = "fallback_repair"

                request_context = self._request_context(document, model, request_kind, attempt_index)
                cached = self.cache.get(request_context["cache_key"])
                if cached is not None:
                    cached_status = cached.get("validation_status")
                    if cached_status == "valid" and isinstance(cached.get("response_parsed"), dict):
                        self.stats["cache_hits"] += 1
                        return self._success_from_parsed(
                            document=document,
                            parsed=cached["response_parsed"],
                            requested_model=model,
                            model=str(cached.get("model") or model),
                            usage=_safe_usage(cached.get("usage")),
                            estimated_cost_usd=float(cached.get("estimated_cost_usd") or 0.0),
                            latency_ms=int(cached.get("latency_ms") or 0),
                            finish_reason=str(cached.get("finish_reason") or ""),
                            cache_key=request_context["cache_key"],
                            from_cache=True,
                            input_metadata=request_context["input_metadata"],
                        )
                    if cached_status == "error":
                        note = "ignored cached error responses and retried live requests"
                        if note not in self.stats["notes"]:
                            self.stats["notes"].append(note)
                    elif self.config.retry_failures:
                        note = "ignored cached invalid responses because retry_failures is enabled"
                        if note not in self.stats["notes"]:
                            self.stats["notes"].append(note)
                    else:
                        self.stats["cache_hits"] += 1
                        cached_errors = cached.get("validation_errors")
                        if isinstance(cached_errors, list):
                            last_errors.extend(str(error) for error in cached_errors)
                        self.stats["invalid_json_count"] += 1
                        total_attempts += 1
                        continue

                self.stats["cache_misses"] += 1
                preflight_cost = estimate_request_cost_usd(
                    model_id=model,
                    input_chars=request_context["prompt_chars"],
                    max_output_tokens=self.config.max_output_tokens,
                )
                budget_reservation: BudgetReservation | None = None
                if self.budget_tracker is not None:
                    budget_reservation = self.budget_tracker.reserve(preflight_cost)
                    budget_spent = self.budget_tracker.reserved_or_spent_usd
                    budget_exceeded = budget_reservation is None
                else:
                    budget_spent = float(self.stats["estimated_cost_usd"])
                    budget_exceeded = budget_spent + preflight_cost > self.config.max_cost_usd
                if budget_exceeded:
                    reason = (
                        "budget_limit_reached: "
                        f"spent={budget_spent:.6f}, "
                        f"next_estimate={preflight_cost:.6f}, "
                        f"limit={self.config.max_cost_usd:.6f}"
                    )
                    return DocumentTaggingOutcome(status="stopped", stop_reason=reason)

                try:
                    self._sleep_before_live_request()
                    completion = self.client.chat_completion(request_context["payload"])
                    self._last_live_request_finished_at = time.monotonic()
                except OpenRouterError as exc:
                    self._last_live_request_finished_at = time.monotonic()
                    if budget_reservation is not None:
                        self.budget_tracker.release(budget_reservation)
                    total_attempts += 1
                    last_errors.append(f"{model}: {exc}")
                    self._write_error_cache(
                        request_context=request_context,
                        model=model,
                        error=exc,
                    )
                    if exc.looks_like_structured_output_error:
                        break
                    if exc.status_code == 429:
                        self.stats["rate_limit_count"] += 1
                    if exc.retryable and attempt_index < self.config.max_retries:
                        self.stats["llm_retries_count"] += 1
                        self._sleep_before_retry(attempt_index, exc)
                        continue
                    break

                total_attempts += 1
                self.stats["llm_requests_count"] += 1
                self.models_used.add(completion.model or model)
                self.stats["latencies_ms"].append(completion.latency_ms)
                cost_usd = calculate_cost_usd(model, **completion.usage)
                if budget_reservation is not None:
                    self.budget_tracker.commit(budget_reservation, cost_usd)
                self.stats["estimated_cost_usd"] = round(self.stats["estimated_cost_usd"] + cost_usd, 8)

                parsed, parse_errors = parse_json_content(completion.content)
                validation_errors: list[str] = parse_errors
                if parsed is not None:
                    validation_errors = validate_tagging_response(parsed, self.schema, expected_doc_id=doc_id)

                cache_record = self._cache_record(
                    request_context=request_context,
                    completion=completion,
                    parsed=parsed,
                    validation_errors=validation_errors,
                    cost_usd=cost_usd,
                    validation_status="valid" if not validation_errors else "invalid",
                )
                self.cache.set(request_context["cache_key"], cache_record)

                if not validation_errors and parsed is not None:
                    return self._success_from_parsed(
                        document=document,
                        parsed=parsed,
                        requested_model=model,
                        model=completion.model or model,
                        usage=completion.usage,
                        estimated_cost_usd=cost_usd,
                        latency_ms=completion.latency_ms,
                        finish_reason=completion.finish_reason,
                        cache_key=request_context["cache_key"],
                        from_cache=False,
                        input_metadata=request_context["input_metadata"],
                    )

                self.stats["invalid_json_count"] += 1
                last_errors.extend(validation_errors)
                if attempt_index < self.config.max_retries:
                    self.stats["llm_retries_count"] += 1
                    self._sleep_before_retry(attempt_index, None)
                    continue
                break

        return DocumentTaggingOutcome(
            status="failed",
            failure_record=self._failure_record(
                document=document,
                model=self.config.model,
                failure_reason="llm_tagging_failed",
                error_messages=last_errors[-20:],
                attempts=total_attempts,
            ),
        )

    def _request_context(
        self,
        document: dict[str, Any],
        model: str,
        request_kind: str,
        attempt_index: int,
    ) -> dict[str, Any]:
        doc_id = str(document.get("doc_id", ""))
        document_name = str(document.get("name", ""))
        clean_text = str(document.get("clean_text", ""))
        truncated = len(clean_text) > self.config.prompt_char_limit
        clean_text_for_prompt = clean_text[: self.config.prompt_char_limit] if truncated else clean_text
        user_message = build_user_message(
            doc_id=doc_id,
            document_name=document_name,
            clean_text=clean_text_for_prompt,
        )
        system_message = self.prompt_text
        if request_kind in {"repair", "fallback_repair"}:
            system_message += (
                "\n\nПредыдущий ответ был невалиден. Исправь ответ: верни строго один JSON-объект "
                "по схеме, без markdown, без лишних полей, с тем же DOC_ID."
            )
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]
        provider = {
            "require_parameters": True,
            "sort": self.config.provider_sort,
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "document_tagging",
                    "strict": True,
                    "schema": schema_for_openrouter(self.schema),
                },
            },
            "provider": provider,
        }
        prompt_chars = sum(len(str(message.get("content", ""))) for message in messages)
        input_hash = sha256_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "document_name": document_name,
                    "clean_text": clean_text_for_prompt,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        request_params = {
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "provider": provider,
            "prompt_char_limit": self.config.prompt_char_limit,
            "request_kind": request_kind,
            "attempt_index": attempt_index,
        }
        cache_key = build_cache_key(
            model=model,
            prompt_version=PROMPT_VERSION,
            schema_version=self.schema_version,
            doc_id=doc_id,
            input_hash=input_hash,
            request_params=request_params,
        )
        input_metadata = {
            "doc_id": doc_id,
            "document_name": document_name,
            "source_text_length_chars": len(clean_text),
            "prompt_text_length_chars": len(clean_text_for_prompt),
            "input_truncated": truncated,
            "prompt_char_limit": self.config.prompt_char_limit,
            "input_hash": input_hash,
            "request_kind": request_kind,
            "attempt_index": attempt_index,
        }
        return {
            "payload": payload,
            "cache_key": cache_key,
            "prompt_chars": prompt_chars,
            "input_metadata": input_metadata,
            "request_params": request_params,
        }

    def _success_from_parsed(
        self,
        *,
        document: dict[str, Any],
        parsed: dict[str, Any],
        requested_model: str,
        model: str,
        usage: dict[str, int],
        estimated_cost_usd: float,
        latency_ms: int,
        finish_reason: str,
        cache_key: str,
        from_cache: bool,
        input_metadata: dict[str, Any],
    ) -> DocumentTaggingOutcome:
        entities = []
        clean_text = str(document.get("clean_text", ""))
        for entity in parsed.get("entities", []):
            entity_copy = dict(entity)
            quote_statuses = [
                validate_quote_in_text(str(quote), clean_text)
                for quote in entity_copy.get("evidence_quotes", [])
            ]
            entity_copy["quote_validation_details"] = [
                {"index": index, "status": status}
                for index, status in enumerate(quote_statuses)
            ]
            entity_copy["quote_validation_status"] = summarize_quote_statuses(quote_statuses)
            entities.append(entity_copy)

        record = {
            "doc_id": str(document.get("doc_id", "")),
            "document_name": str(document.get("name", "")),
            "model": model,
            "requested_model": requested_model,
            "prompt_version": PROMPT_VERSION,
            "schema_version": self.schema_version,
            "entities": entities,
            "validation_status": "valid",
            "cache_key": cache_key,
            "from_cache": from_cache,
            "usage": usage,
            "estimated_cost_usd": estimated_cost_usd,
            "latency_ms": latency_ms,
            "finish_reason": finish_reason,
            "input_metadata": input_metadata,
            "created_at": utc_now(),
        }
        return DocumentTaggingOutcome(status="ok", success_record=record)

    def _failure_record(
        self,
        *,
        document: dict[str, Any],
        model: str,
        failure_reason: str,
        error_messages: list[str],
        attempts: int,
    ) -> dict[str, Any]:
        clean_text = str(document.get("clean_text", ""))
        return {
            "doc_id": str(document.get("doc_id", "")),
            "document_name": str(document.get("name", "")),
            "model": model,
            "requested_model": model,
            "prompt_version": PROMPT_VERSION,
            "schema_version": self.schema_version,
            "validation_status": "failed",
            "failure_reason": failure_reason,
            "error_messages": error_messages,
            "attempts": attempts,
            "input_metadata": {
                "source_text_length_chars": len(clean_text),
                "prompt_char_limit": self.config.prompt_char_limit,
                "input_truncated": len(clean_text) > self.config.prompt_char_limit,
            },
            "created_at": utc_now(),
        }

    def _cache_record(
        self,
        *,
        request_context: dict[str, Any],
        completion: OpenRouterCompletion,
        parsed: dict[str, Any] | None,
        validation_errors: list[str],
        cost_usd: float,
        validation_status: str,
    ) -> dict[str, Any]:
        return {
            "cache_key": request_context["cache_key"],
            "created_at": utc_now(),
            "model": completion.model,
            "prompt_version": PROMPT_VERSION,
            "schema_version": self.schema_version,
            "input_hash": request_context["input_metadata"]["input_hash"],
            "request": {
                "redacted": True,
                "parameters": request_context["request_params"],
                "input_metadata": request_context["input_metadata"],
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

    def _write_error_cache(
        self,
        *,
        request_context: dict[str, Any],
        model: str,
        error: OpenRouterError,
    ) -> None:
        record = {
            "cache_key": request_context["cache_key"],
            "created_at": utc_now(),
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "schema_version": self.schema_version,
            "input_hash": request_context["input_metadata"]["input_hash"],
            "request": {
                "redacted": True,
                "parameters": request_context["request_params"],
                "input_metadata": request_context["input_metadata"],
            },
            "response_raw": {
                "error": str(error),
                "status_code": error.status_code,
                "response_body": error.response_body[:2000],
            },
            "response_parsed": None,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0},
            "estimated_cost_usd": 0.0,
            "latency_ms": 0,
            "finish_reason": "",
            "validation_status": "error",
            "validation_errors": [str(error)],
        }
        self.cache.set(request_context["cache_key"], record)

    def _sleep_before_live_request(self) -> None:
        if self.config.request_delay_seconds <= 0 or self._last_live_request_finished_at is None:
            return
        elapsed = time.monotonic() - self._last_live_request_finished_at
        remaining = self.config.request_delay_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)

    def _sleep_before_retry(self, attempt_index: int, error: OpenRouterError | None) -> None:
        retry_delay = self.config.retry_backoff_seconds * (2 ** attempt_index)
        if error is not None and error.status_code == 429:
            retry_after = error.retry_after_seconds
            rate_limit_delay = self.config.rate_limit_backoff_seconds * (2 ** attempt_index)
            retry_delay = max(retry_delay, rate_limit_delay, retry_after or 0.0)
        if retry_delay > 0:
            self._sleep(retry_delay)

    def _sleep(self, seconds: float) -> None:
        self.stats["sleep_seconds_total"] = round(
            float(self.stats["sleep_seconds_total"]) + seconds,
            3,
        )
        time.sleep(seconds)

    def _build_report(
        self,
        *,
        selected_documents: list[dict[str, Any]],
        success_by_key: dict[tuple[str, str, str, str], dict[str, Any]],
        failure_by_key: dict[tuple[str, str, str, str], dict[str, Any]],
        current_model_record_keys: set[tuple[str, str, str, str]],
        stop_reason: str | None,
        started_at: str,
    ) -> dict[str, Any]:
        selected_current_successes = [
            success_by_key[key]
            for key in current_model_record_keys
            if key in success_by_key
        ]
        selected_current_failures = [
            failure_by_key[key]
            for key in current_model_record_keys
            if key in failure_by_key
        ]
        entities_by_type: Counter[str] = Counter()
        entities_total = 0
        for record in selected_current_successes:
            for entity in record.get("entities", []):
                if isinstance(entity, dict):
                    entities_total += 1
                    entity_type = entity.get("entity_type")
                    if isinstance(entity_type, str):
                        entities_by_type[entity_type] += 1

        latencies = self.stats["latencies_ms"]
        avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
        notes = list(self.stats["notes"])
        if stop_reason and stop_reason not in notes:
            notes.append(stop_reason)

        return {
            "stage": "tagging_calibration",
            "started_at": started_at,
            "finished_at": utc_now(),
            "documents_requested": len(selected_documents),
            "documents_tagged": len(selected_current_successes),
            "documents_failed": len(selected_current_failures),
            "entities_total": entities_total,
            "entities_by_type": dict(sorted(entities_by_type.items())),
            "models_used": sorted(self.models_used | {record.get("model", "") for record in selected_current_successes}),
            "llm_requests_count": self.stats["llm_requests_count"],
            "llm_retries_count": self.stats["llm_retries_count"],
            "cache_hits": self.stats["cache_hits"],
            "cache_misses": self.stats["cache_misses"],
            "estimated_cost_usd": round(float(self.stats["estimated_cost_usd"]), 8),
            "avg_latency_ms": avg_latency,
            "invalid_json_count": self.stats["invalid_json_count"],
            "rate_limit_count": self.stats["rate_limit_count"],
            "sleep_seconds_total": round(float(self.stats["sleep_seconds_total"]), 3),
            "budget_limit_usd": self.config.max_cost_usd,
            "stop_reason": stop_reason,
            "notes": notes,
        }


class ParallelTaggingRunner(TaggingRunner):
    def __init__(
        self,
        config: TaggingConfig,
        client: OpenRouterClient | Any,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(config=config, client=client, logger=logger)
        self.shared_budget_tracker = SharedBudgetTracker(config.max_cost_usd)

    def run(self) -> dict[str, Any]:
        parsed_path = self.config.data_dir / "parsed" / "parsed_documents.jsonl"
        if not parsed_path.exists():
            raise FileNotFoundError(f"missing parsed artifact: {parsed_path}")

        api_keys = list(getattr(self.client, "api_keys", []) or [])
        if len(api_keys) < 2:
            raise ValueError("parallel_workers > 1 requires at least two OpenRouter API keys")
        active_workers = min(self.config.parallel_workers, len(api_keys))

        documents = read_jsonl(parsed_path)
        selected_documents = documents[: self.config.limit] if self.config.limit else documents

        tagging_dir = self.config.data_dir / "tagging"
        reports_dir = self.config.data_dir / "reports"
        success_path = tagging_dir / "document_tags_raw.jsonl"
        failures_path = tagging_dir / "document_tagging_failures.jsonl"
        report_path = reports_dir / "tagging_report.json"

        success_records = _read_jsonl_if_exists(success_path)
        failure_records = _read_jsonl_if_exists(failures_path)
        success_by_key = {_record_key(record): record for record in success_records}
        failure_by_key = {_record_key(record): record for record in failure_records}

        started_at = utc_now()
        current_model_record_keys: set[tuple[str, str, str, str]] = set()
        work_documents: deque[dict[str, Any]] = deque()
        for document in selected_documents:
            doc_id = str(document.get("doc_id", ""))
            record_key = (doc_id, self.config.model, PROMPT_VERSION, self.schema_version)
            current_model_record_keys.add(record_key)

            if self.config.resume and record_key in success_by_key:
                continue
            if self.config.resume and not self.config.retry_failures and record_key in failure_by_key:
                continue
            work_documents.append(document)

        stop_event = Event()
        work_lock = Lock()
        result_lock = Lock()
        stop_reason: str | None = None

        def worker(worker_index: int) -> dict[str, Any]:
            worker_config = replace(self.config, parallel_workers=1)
            worker_client = OpenRouterClient(
                api_keys=[api_keys[worker_index]],
                endpoint=str(getattr(self.client, "endpoint", "")) or OPENROUTER_CHAT_COMPLETIONS_URL,
                timeout_seconds=int(getattr(self.client, "timeout_seconds", 120)),
            )
            worker_runner = TaggingRunner(
                config=worker_config,
                client=worker_client,
                logger=self.logger,
                budget_tracker=self.shared_budget_tracker,
            )
            outcomes: list[DocumentTaggingOutcome] = []
            local_stop_reason: str | None = None
            while not stop_event.is_set():
                with work_lock:
                    if not work_documents:
                        break
                    document = work_documents.popleft()

                outcome = worker_runner.tag_document(document)
                outcomes.append(outcome)
                if outcome.stop_reason:
                    local_stop_reason = outcome.stop_reason
                    stop_event.set()
                    break

            return {
                "worker_index": worker_index,
                "outcomes": outcomes,
                "stats": worker_runner.stats,
                "models_used": worker_runner.models_used,
                "stop_reason": local_stop_reason,
            }

        with ThreadPoolExecutor(max_workers=active_workers) as executor:
            futures = [executor.submit(worker, index) for index in range(active_workers)]
            for future in as_completed(futures):
                worker_result = future.result()
                with result_lock:
                    _merge_stats_into(self.stats, worker_result["stats"])
                    self.models_used.update(worker_result["models_used"])
                    if worker_result.get("stop_reason") and stop_reason is None:
                        stop_reason = str(worker_result["stop_reason"])
                    for outcome in worker_result["outcomes"]:
                        if outcome.status == "ok" and outcome.success_record is not None:
                            success_by_key[_record_key(outcome.success_record)] = outcome.success_record
                            failure_by_key.pop(_record_key(outcome.success_record), None)
                        elif outcome.failure_record is not None:
                            failure_by_key[_record_key(outcome.failure_record)] = outcome.failure_record

        note = f"parallel_workers_active={active_workers}; api_key_count={len(api_keys)}"
        if note not in self.stats["notes"]:
            self.stats["notes"].append(note)
        if active_workers < self.config.parallel_workers:
            self.stats["notes"].append(
                f"parallel_workers_requested={self.config.parallel_workers}; capped_by_api_key_count"
            )
        if stop_reason:
            self.stats["notes"].append(stop_reason)

        write_jsonl(success_path, success_by_key.values())
        write_jsonl(failures_path, failure_by_key.values())

        report = self._build_report(
            selected_documents=selected_documents,
            success_by_key=success_by_key,
            failure_by_key=failure_by_key,
            current_model_record_keys=current_model_record_keys,
            stop_reason=stop_reason,
            started_at=started_at,
        )
        reports_dir.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        return report


def run_tagging_calibration(
    config: TaggingConfig,
    client: OpenRouterClient | Any | None = None,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    actual_client = client if client is not None else OpenRouterClient()
    if config.parallel_workers > 1:
        return ParallelTaggingRunner(config=config, client=actual_client, logger=logger).run()
    return TaggingRunner(config=config, client=actual_client, logger=logger).run()


def build_user_message(doc_id: str, document_name: str, clean_text: str) -> str:
    return (
        f"DOC_ID:\n{doc_id}\n\n"
        f"DOCUMENT_NAME:\n{document_name}\n\n"
        f"CLEAN_TEXT:\n{clean_text}\n"
    )


def parse_json_content(content: str) -> tuple[dict[str, Any] | None, list[str]]:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON: {exc}"]
    if not isinstance(parsed, dict):
        return None, ["JSON response must be an object"]
    return parsed, []


def validate_quote_in_text(quote: str, clean_text: str) -> str:
    quote_norm = _normalize_for_quote_match(quote)
    text_norm = _normalize_for_quote_match(clean_text)
    if not quote_norm:
        return "not_found"
    if quote_norm in text_norm:
        return "found"
    if len(quote_norm) < 12 or not text_norm:
        return "not_found"

    window_size = min(len(text_norm), max(len(quote_norm) + 20, int(len(quote_norm) * 1.25)))
    step = max(1, len(quote_norm) // 3)
    best_ratio = 0.0
    for start in range(0, max(1, len(text_norm) - window_size + 1), step):
        window = text_norm[start : start + window_size]
        best_ratio = max(best_ratio, SequenceMatcher(None, quote_norm, window).ratio())
        if best_ratio >= 0.86:
            return "fuzzy"
    return "not_found"


def summarize_quote_statuses(statuses: list[str]) -> str:
    if not statuses:
        return "no_quotes"
    if any(status == "not_found" for status in statuses):
        return "not_found"
    if any(status == "fuzzy" for status in statuses):
        return "fuzzy"
    return "found"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_prompt() -> str:
    path = Path(__file__).parent / "prompts" / "tagging_v1.md"
    return path.read_text(encoding="utf-8")


def _normalize_for_quote_match(value: str) -> str:
    return " ".join(value.lower().split())


def _safe_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
    return {
        "prompt_tokens": int(value.get("prompt_tokens") or 0),
        "completion_tokens": int(value.get("completion_tokens") or 0),
        "reasoning_tokens": int(value.get("reasoning_tokens") or 0),
    }


def _merge_stats_into(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("llm_requests_count", "llm_retries_count", "cache_hits", "cache_misses", "invalid_json_count", "rate_limit_count"):
        target[key] = int(target.get(key, 0)) + int(source.get(key, 0))
    target["estimated_cost_usd"] = round(
        float(target.get("estimated_cost_usd", 0.0)) + float(source.get("estimated_cost_usd", 0.0)),
        8,
    )
    target["sleep_seconds_total"] = round(
        float(target.get("sleep_seconds_total", 0.0)) + float(source.get("sleep_seconds_total", 0.0)),
        3,
    )
    target.setdefault("latencies_ms", []).extend(source.get("latencies_ms", []))
    target_notes = target.setdefault("notes", [])
    for note in source.get("notes", []):
        if note not in target_notes:
            target_notes.append(note)


def _record_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record.get("doc_id", "")),
        _requested_model_key(record),
        str(record.get("prompt_version", "")),
        str(record.get("schema_version", "")),
    )


def _requested_model_key(record: dict[str, Any]) -> str:
    requested_model = record.get("requested_model")
    if isinstance(requested_model, str) and requested_model:
        return requested_model
    model = str(record.get("model", ""))
    for configured_model in (PRIMARY_TAGGING_MODEL, NORMALIZATION_MODEL, FALLBACK_TAGGING_MODEL):
        if model == configured_model or model.startswith(f"{configured_model}-"):
            return configured_model
    return model


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return read_jsonl(path)

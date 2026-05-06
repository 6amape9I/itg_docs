from __future__ import annotations

import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from kb_rebuild.articles.a2.batch_builder import build_batches, filter_tasks
from kb_rebuild.articles.a2.models import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    STAGE,
    STAGE_VERSION,
    A2Config,
)
from kb_rebuild.articles.a2.prompt import build_batch_prompt
from kb_rebuild.articles.a2.report import (
    BATCH_REPORT_FIELDS,
    EVIDENCE_ITEM_FIELDS,
    MANUAL_QA_FIELDS,
    TASK_RESULT_FIELDS,
    build_cost_latency_report,
    build_manifest,
    build_quality_diagnostics,
    build_report,
    manual_qa_rows,
    scrub_internal_task,
    utc_now,
    write_csv,
    write_json,
)
from kb_rebuild.articles.a2.schema import A2_RESPONSE_SCHEMA, parse_response_json, validate_batch_response
from kb_rebuild.articles.a2.validation import validate_quote
from kb_rebuild.io.jsonl import read_jsonl, write_jsonl
from kb_rebuild.llm.cache import LLMCache, build_cache_key, sha256_text
from kb_rebuild.llm.gemini_client import GeminiClient, GeminiError
from kb_rebuild.llm.gemini_schema import schema_for_gemini
from kb_rebuild.llm.models import calculate_cost_usd, estimate_request_cost_usd, validate_direct_gemini_model_id
from kb_rebuild.llm.providers import completion_api_key_index, completion_usage_source


OUTPUT_FILENAMES = {
    "evidence_extraction_batches_jsonl": "evidence_extraction_batches.jsonl",
    "evidence_task_results_jsonl": "evidence_task_results.jsonl",
    "evidence_items_jsonl": "evidence_items.jsonl",
    "no_evidence_tasks_jsonl": "no_evidence_tasks.jsonl",
    "review_tasks_jsonl": "review_tasks.jsonl",
    "failed_tasks_jsonl": "failed_tasks.jsonl",
    "invalid_llm_responses_jsonl": "invalid_llm_responses.jsonl",
    "quote_validation_issues_jsonl": "quote_validation_issues.jsonl",
    "evidence_items_csv": "evidence_items.csv",
    "task_results_csv": "task_results.csv",
    "batch_report_csv": "batch_report.csv",
    "a2_report_json": "a2_report.json",
    "a2_manifest_json": "a2_manifest.json",
    "evidence_quality_diagnostics_json": "evidence_quality_diagnostics.json",
    "cost_latency_report_json": "cost_latency_report.json",
    "manual_qa_sample_csv": "manual_qa_sample.csv",
    "smoke_50_report_json": "smoke_50_report.json",
    "smoke_200_report_json": "smoke_200_report.json",
}


def run_article_a2_extraction(config: A2Config, client: Any | None = None) -> dict[str, Any]:
    return ArticleA2Runner(config=config, client=client).run()


class ArticleA2Runner:
    def __init__(self, config: A2Config, client: Any | None = None) -> None:
        self.config = config
        self.client = client
        self.outputs = {name: config.out_dir / filename for name, filename in OUTPUT_FILENAMES.items()}
        self.inputs = {
            "a2_task_queue_jsonl": config.a1_dir / "a2_extraction_task_queue.jsonl",
            "article_status_index_jsonl": config.a1_dir / "article_status_index.jsonl",
            "tag_work_plan_adjusted_jsonl": config.a1_dir / "tag_work_plan_adjusted.jsonl",
            "a1_report_json": config.a1_dir / "a1_report.json",
            "a1_manifest_json": config.a1_dir / "a1_manifest.json",
            "source_block_windows_jsonl": config.planning_dir / "source_block_windows.jsonl",
            "tags_canonical_csv": config.normalization_final_dir / "tags_canonical.csv",
            "tag_aliases_csv": config.normalization_final_dir / "tag_aliases.csv",
            "publication_review_queue_jsonl": config.a1_dir / "publication_review_queue.jsonl",
            "hard_review_queue_jsonl": config.a1_dir / "hard_review_queue.jsonl",
            "direct_copy_articles_jsonl": config.a1_dir / "direct_copy_articles.jsonl",
            "pending_extraction_articles_jsonl": config.a1_dir / "pending_extraction_articles.jsonl",
        }
        self.cache = LLMCache(config.out_dir / "llm_cache")
        self.stats: dict[str, Any] = {
            "requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "invalid_json_count": 0,
            "schema_validation_failures": 0,
            "http_status_counts": {},
            "estimated_cost_usd": 0.0,
            "batch_splits": 0,
            "no_unknown_task_ids": True,
        }
        self._stats_lock = threading.Lock()
        self._reserved_cost_usd = 0.0
        self._stop_reason: str | None = None

    def run(self) -> dict[str, Any]:
        created_at = utc_now()
        warnings: list[str] = []
        self._validate_config()
        self._validate_inputs()

        all_tasks = read_jsonl(self.inputs["a2_task_queue_jsonl"])
        completed_task_ids = self._completed_task_ids() if self.config.resume else set()
        selected_tasks = filter_tasks(
            all_tasks,
            task_filter=self.config.task_filter,
            strategy_filter=self.config.strategy_filter,
            priority_filter=self.config.priority_filter,
            limit=self.config.limit,
            completed_task_ids=completed_task_ids if not self.config.retry_failures else set(),
        )
        batches = build_batches(
            selected_tasks,
            max_tasks_per_batch=self.config.max_tasks_per_batch,
            batch_char_limit=self.config.batch_char_limit,
        )

        batch_outcomes = self._process_batches(batches)
        task_results: list[dict[str, Any]] = []
        evidence_items: list[dict[str, Any]] = []
        no_evidence_tasks: list[dict[str, Any]] = []
        review_tasks: list[dict[str, Any]] = []
        failed_tasks: list[dict[str, Any]] = []
        quote_validation_issues: list[dict[str, Any]] = []
        invalid_llm_responses: list[dict[str, Any]] = []
        batch_reports: list[dict[str, Any]] = []

        for outcome in batch_outcomes:
            task_results.extend(outcome["task_results"])
            evidence_items.extend(outcome["evidence_items"])
            quote_validation_issues.extend(outcome["quote_validation_issues"])
            invalid_llm_responses.extend(outcome["invalid_llm_responses"])
            batch_reports.extend(outcome["batch_reports"])

        for index, item in enumerate(evidence_items, start=1):
            item["evidence_item_id"] = f"ev_{index:09d}"

        for result in task_results:
            status = str(result.get("status") or "")
            if status == "no_evidence":
                no_evidence_tasks.append(result)
            elif status == "review":
                review_tasks.append(result)
            elif status == "failed":
                failed_tasks.append(result)

        report = build_report(
            created_at=created_at,
            config=self.config,
            inputs=self.inputs,
            task_results=task_results,
            evidence_items=evidence_items,
            batches=batches,
            batch_reports=batch_reports,
            invalid_llm_responses=invalid_llm_responses,
            quote_validation_issues=quote_validation_issues,
            stats=self.stats,
            stop_reason=self._stop_reason,
            warnings=warnings,
        )
        manifest = build_manifest(created_at=created_at, config=self.config, inputs=self.inputs, outputs=self.outputs)
        self._write_outputs(
            batches=batches,
            task_results=task_results,
            evidence_items=evidence_items,
            no_evidence_tasks=no_evidence_tasks,
            review_tasks=review_tasks,
            failed_tasks=failed_tasks,
            invalid_llm_responses=invalid_llm_responses,
            quote_validation_issues=quote_validation_issues,
            batch_reports=batch_reports,
            report=report,
            manifest=manifest,
        )
        return report

    def _process_batches(self, batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not batches:
            return []
        if self.config.max_inflight == 1 or len(batches) == 1:
            return [self._process_batch(batch, split_depth=0) for batch in batches]

        results: list[dict[str, Any] | None] = [None] * len(batches)
        executor = ThreadPoolExecutor(max_workers=self.config.max_inflight)
        futures: dict[Future[dict[str, Any]], int] = {
            executor.submit(self._process_batch, batch, 0): index for index, batch in enumerate(batches)
        }
        try:
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        except Exception:
            for future in futures:
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)
        return [item for item in results if item is not None]

    def _process_batch(self, batch: dict[str, Any], split_depth: int) -> dict[str, Any]:
        last_errors: list[str] = []
        invalid_records: list[dict[str, Any]] = []
        terminal_provider_error = False
        for attempt_index in range(self.config.max_retries + 1):
            context = self._request_context(batch, repair_errors=last_errors if attempt_index else None, attempt_index=attempt_index)
            cached = self.cache.get(context["cache_key"])
            if cached and cached.get("validation_status") == "valid" and isinstance(cached.get("response_parsed"), dict):
                self._increment_stat("cache_hits")
                return self._outcome_from_parsed(
                    batch=batch,
                    parsed=dict(cached["response_parsed"]),
                    model=str(cached.get("model") or self.config.model),
                    provider=str(cached.get("provider") or self.config.provider),
                    batch_report=self._batch_report(
                        batch,
                        status="success",
                        attempts=attempt_index + 1,
                        split_depth=split_depth,
                        cache_hit=True,
                        latency_ms=int(cached.get("latency_ms") or 0),
                        estimated_cost_usd=float(cached.get("estimated_cost_usd") or 0.0),
                    ),
                )

            self._increment_stat("cache_misses")
            preflight_cost = estimate_request_cost_usd(
                model_id=self.config.model,
                input_chars=int(context["prompt_chars"]),
                max_output_tokens=int(context["max_output_tokens"]),
            )
            if not self._reserve_request_budget(preflight_cost):
                self._stop_reason = "max_cost_reached"
                return self._failed_outcome(batch, "max_cost_reached", split_depth)
            try:
                completion = self._client().chat_completion(context["payload"])
            except GeminiError as exc:
                self._release_request_budget(preflight_cost)
                self._write_error_cache(context, exc)
                self._record_http_status(exc.status_code)
                last_errors = [str(exc)]
                invalid_records.append(
                    {
                        "batch_id": batch["batch_id"],
                        "task_ids": batch.get("task_ids", []),
                        "attempt_index": attempt_index,
                        "errors": last_errors,
                        "status_code": exc.status_code,
                        "response_body": exc.response_body[:4000],
                        "created_at": utc_now(),
                    }
                )
                if exc.retryable and attempt_index < self.config.max_retries:
                    continue
                terminal_provider_error = not exc.retryable
                break

            self._increment_stat("requests")
            cost_usd = calculate_cost_usd(self.config.model, **_safe_usage(completion.usage))
            self._finish_request_budget(preflight_cost, cost_usd)
            parsed_raw, parse_errors = parse_response_json(completion.content)
            parsed: dict[str, Any] | None = None
            validation_errors = list(parse_errors)
            if parse_errors:
                self._increment_stat("invalid_json_count")
            if parsed_raw is not None:
                parsed, validation_errors = validate_batch_response(parsed_raw, batch)
            if validation_errors:
                self._increment_stat("schema_validation_failures")
                last_errors = validation_errors
                invalid_records.append(
                    {
                        "batch_id": batch["batch_id"],
                        "task_ids": batch.get("task_ids", []),
                        "attempt_index": attempt_index,
                        "errors": validation_errors,
                        "response_content": completion.content[:4000],
                        "created_at": utc_now(),
                    }
                )
            self.cache.set(
                context["cache_key"],
                {
                    "cache_key": context["cache_key"],
                    "batch_id": batch["batch_id"],
                    "task_ids": batch.get("task_ids", []),
                    "model": completion.model or self.config.model,
                    "requested_model": self.config.model,
                    "provider": self.config.provider,
                    "response_raw": completion.raw,
                    "response_content": completion.content,
                    "response_parsed": parsed_raw,
                    "validation_errors": validation_errors,
                    "validation_status": "valid" if parsed is not None and not validation_errors else "invalid",
                    "usage": completion.usage,
                    "usage_source": completion_usage_source(completion),
                    "estimated_cost_usd": cost_usd,
                    "latency_ms": completion.latency_ms,
                    "finish_reason": completion.finish_reason,
                    "api_key_index": completion_api_key_index(completion),
                    "created_at": utc_now(),
                },
            )
            if parsed is not None and not validation_errors:
                return self._outcome_from_parsed(
                    batch=batch,
                    parsed=parsed,
                    model=completion.model or self.config.model,
                    provider=self.config.provider,
                    batch_report=self._batch_report(
                        batch,
                        status="success",
                        attempts=attempt_index + 1,
                        split_depth=split_depth,
                        cache_hit=False,
                        latency_ms=completion.latency_ms,
                        estimated_cost_usd=cost_usd,
                    ),
                    invalid_records=invalid_records,
                )

        if terminal_provider_error:
            return _merge_outcomes(
                [
                    {"invalid_llm_responses": invalid_records, "batch_reports": []},
                    self._failed_outcome(batch, "; ".join(last_errors), split_depth, include_invalid_record=False),
                ]
            )

        if len(batch.get("tasks", [])) > 1:
            self._increment_stat("batch_splits")
            left, right = _split_batch(batch)
            left_outcome = self._process_batch(left, split_depth + 1)
            right_outcome = self._process_batch(right, split_depth + 1)
            return _merge_outcomes(
                [
                    {"invalid_llm_responses": invalid_records, "batch_reports": []},
                    left_outcome,
                    right_outcome,
                ]
            )
        return _merge_outcomes(
            [
                {"invalid_llm_responses": invalid_records, "batch_reports": []},
                self._failed_outcome(
                    batch,
                    "; ".join(last_errors) or "schema invalid after retries",
                    split_depth,
                    include_invalid_record=False,
                ),
            ]
        )

    def _outcome_from_parsed(
        self,
        *,
        batch: dict[str, Any],
        parsed: dict[str, Any],
        model: str,
        provider: str,
        batch_report: dict[str, Any],
        invalid_records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        task_by_id = {str(task.get("task_id") or ""): task for task in batch.get("tasks", [])}
        task_results: list[dict[str, Any]] = []
        evidence_items: list[dict[str, Any]] = []
        quote_issues: list[dict[str, Any]] = []
        for parsed_result in parsed.get("task_results", []):
            task = task_by_id[str(parsed_result.get("task_id") or "")]
            result, items, issues = self._materialize_task_result(
                parsed_result=parsed_result,
                task=task,
                batch_id=str(batch.get("batch_id") or ""),
                model=model,
                provider=provider,
            )
            task_results.append(result)
            evidence_items.extend(items)
            quote_issues.extend(issues)
        return {
            "task_results": task_results,
            "evidence_items": evidence_items,
            "quote_validation_issues": quote_issues,
            "invalid_llm_responses": invalid_records or [],
            "batch_reports": [batch_report],
        }

    def _materialize_task_result(
        self,
        *,
        parsed_result: dict[str, Any],
        task: dict[str, Any],
        batch_id: str,
        model: str,
        provider: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        created_at = utc_now()
        items: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        valid_quote_count = 0
        invalid_quote_count = 0
        review_reasons = [str(item) for item in task.get("review_reasons", [])]
        publication_review = bool(task.get("needs_review_before_publication"))
        for item in parsed_result.get("evidence_items", []):
            quote_result = validate_quote(str(item.get("quote") or ""), str(task.get("window_text") or ""))
            if quote_result.status == "not_found":
                invalid_quote_count += 1
            else:
                valid_quote_count += 1
            item_review_reasons = list(review_reasons)
            if quote_result.review_required:
                item_review_reasons.append(f"quote_validation:{quote_result.status}")
            if quote_result.status == "not_found":
                issue = _quote_issue(task, item, batch_id, quote_result.reason, quote_result.status, created_at)
                issues.append(issue)
            items.append(
                {
                    "evidence_item_id": "",
                    "task_id": str(task.get("task_id") or ""),
                    "batch_id": batch_id,
                    "tag_id": str(task.get("tag_id") or ""),
                    "canonical_tag_ru": str(task.get("canonical_tag_ru") or ""),
                    "canonical_tag_latin": _nullable_string(task.get("canonical_tag_latin")),
                    "entity_type": str(task.get("entity_type") or ""),
                    "doc_id": str(task.get("doc_id") or ""),
                    "document_name": str(task.get("document_name") or ""),
                    "window_id": str(task.get("window_id") or ""),
                    "block_ids": list(task.get("block_ids") or []),
                    "block_indexes": list(task.get("block_indexes") or []),
                    "heading_context": list(task.get("heading_context") or []),
                    "fact_type": str(item.get("fact_type") or ""),
                    "section_hint": str(item.get("section_hint") or ""),
                    "claim": str(item.get("claim") or ""),
                    "quote": str(item.get("quote") or ""),
                    "quote_validation_status": quote_result.status,
                    "importance": str(item.get("importance") or ""),
                    "confidence": float(item.get("confidence") or 0.0),
                    "relevance": str(parsed_result.get("relevance") or ""),
                    "source_strategy": str(task.get("source_strategy") or ""),
                    "window_quality": str(task.get("window_quality") or ""),
                    "match_method": str(task.get("match_method") or ""),
                    "needs_review_before_publication": publication_review or quote_result.review_required,
                    "review_reasons": item_review_reasons,
                    "model": model,
                    "provider": provider,
                    "prompt_version": PROMPT_VERSION,
                    "schema_version": SCHEMA_VERSION,
                    "created_at": created_at,
                }
            )

        decision = str(parsed_result.get("decision") or "")
        relevance = str(parsed_result.get("relevance") or "")
        status = _task_status(
            decision=decision,
            relevance=relevance,
            items_count=len(items),
            valid_quote_count=valid_quote_count,
            invalid_quote_count=invalid_quote_count,
            window_quality=str(task.get("window_quality") or ""),
            publication_review=publication_review,
        )
        reason_parts = [str(parsed_result.get("reason") or "").strip()]
        if publication_review:
            reason_parts.append("publication_review")
        if str(task.get("window_quality") or "") == "low":
            reason_parts.append("low_quality_source_window")
        if invalid_quote_count:
            reason_parts.append(f"invalid_quote_items={invalid_quote_count}")
        result_decision = "needs_review" if status == "review" and decision == "evidence_extracted" and valid_quote_count == 0 else decision
        result = {
            "task_id": str(task.get("task_id") or ""),
            "tag_id": str(task.get("tag_id") or ""),
            "decision": result_decision,
            "relevance": relevance,
            "evidence_items_count": len(items),
            "valid_quote_items_count": valid_quote_count,
            "invalid_quote_items_count": invalid_quote_count,
            "confidence": float(parsed_result.get("confidence") or 0.0),
            "batch_id": batch_id,
            "status": status,
            "reason": "; ".join(part for part in reason_parts if part),
            "_task": task,
        }
        return result, items, issues

    def _failed_outcome(
        self,
        batch: dict[str, Any],
        reason: str,
        split_depth: int,
        *,
        include_invalid_record: bool = True,
    ) -> dict[str, Any]:
        task_results = []
        for task in batch.get("tasks", []):
            task_results.append(
                {
                    "task_id": str(task.get("task_id") or ""),
                    "tag_id": str(task.get("tag_id") or ""),
                    "decision": "needs_review",
                    "relevance": "unclear",
                    "evidence_items_count": 0,
                    "valid_quote_items_count": 0,
                    "invalid_quote_items_count": 0,
                    "confidence": 0.0,
                    "batch_id": str(batch.get("batch_id") or ""),
                    "status": "failed",
                    "reason": reason,
                    "_task": task,
                }
            )
        return {
            "task_results": task_results,
            "evidence_items": [],
            "quote_validation_issues": [],
            "invalid_llm_responses": [
                {
                    "batch_id": batch.get("batch_id"),
                    "task_ids": batch.get("task_ids", []),
                    "errors": [reason],
                    "created_at": utc_now(),
                }
            ]
            if include_invalid_record
            else [],
            "batch_reports": [
                self._batch_report(
                    batch,
                    status="failed",
                    attempts=self.config.max_retries + 1,
                    split_depth=split_depth,
                    cache_hit=False,
                    latency_ms=0,
                    estimated_cost_usd=0.0,
                    error=reason,
                )
            ],
        }

    def _request_context(
        self,
        batch: dict[str, Any],
        *,
        repair_errors: list[str] | None,
        attempt_index: int,
    ) -> dict[str, Any]:
        prompt = build_batch_prompt(batch, repair_errors=repair_errors)
        max_output_tokens = self._max_output_tokens_for_attempt(attempt_index)
        generation_config: dict[str, Any] = {
            "temperature": self.config.temperature,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "application/json",
        }
        if self.config.thinking_level is not None:
            generation_config["thinkingConfig"] = {"thinkingLevel": self.config.thinking_level}
        if self.config.structured_output_mode in {"gemini_schema", "gemini_schema_lite"}:
            generation_config["responseJsonSchema"] = schema_for_gemini(
                A2_RESPONSE_SCHEMA,
                lite=self.config.structured_output_mode == "gemini_schema_lite",
            )
        payload = {
            "model": self.config.model,
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }
        input_hash = sha256_text(
            json.dumps(
                {
                    "stage": STAGE,
                    "batch_id": batch.get("batch_id"),
                    "task_ids": batch.get("task_ids", []),
                    "tasks": batch.get("tasks", []),
                    "prompt_hash": sha256_text(prompt),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        request_params = {
            "stage": STAGE,
            "provider": self.config.provider,
            "temperature": self.config.temperature,
            "max_output_tokens": max_output_tokens,
            "thinking_level": self.config.thinking_level,
            "structured_output_mode": self.config.structured_output_mode,
            "attempt_index": attempt_index,
            "payload_shape": "gemini_generate_content",
        }
        cache_key = build_cache_key(
            provider=self.config.provider,
            model=self.config.model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            doc_id=str(batch.get("batch_id") or ",".join(batch.get("task_ids", []))),
            input_hash=input_hash,
            request_params=request_params,
        )
        return {
            "payload": payload,
            "cache_key": cache_key,
            "prompt_chars": len(prompt),
            "max_output_tokens": max_output_tokens,
        }

    def _write_outputs(
        self,
        *,
        batches: list[dict[str, Any]],
        task_results: list[dict[str, Any]],
        evidence_items: list[dict[str, Any]],
        no_evidence_tasks: list[dict[str, Any]],
        review_tasks: list[dict[str, Any]],
        failed_tasks: list[dict[str, Any]],
        invalid_llm_responses: list[dict[str, Any]],
        quote_validation_issues: list[dict[str, Any]],
        batch_reports: list[dict[str, Any]],
        report: dict[str, Any],
        manifest: dict[str, Any],
    ) -> None:
        self.config.out_dir.mkdir(parents=True, exist_ok=True)
        public_batches = [{key: value for key, value in batch.items() if key != "tasks"} for batch in batches]
        public_task_results = scrub_internal_task(task_results)
        public_no_evidence = scrub_internal_task(no_evidence_tasks)
        public_review = scrub_internal_task(review_tasks)
        public_failed = scrub_internal_task(failed_tasks)
        write_jsonl(self.outputs["evidence_extraction_batches_jsonl"], public_batches)
        write_jsonl(self.outputs["evidence_task_results_jsonl"], public_task_results)
        write_jsonl(self.outputs["evidence_items_jsonl"], evidence_items)
        write_jsonl(self.outputs["no_evidence_tasks_jsonl"], public_no_evidence)
        write_jsonl(self.outputs["review_tasks_jsonl"], public_review)
        write_jsonl(self.outputs["failed_tasks_jsonl"], public_failed)
        write_jsonl(self.outputs["invalid_llm_responses_jsonl"], invalid_llm_responses)
        write_jsonl(self.outputs["quote_validation_issues_jsonl"], quote_validation_issues)
        write_csv(self.outputs["evidence_items_csv"], EVIDENCE_ITEM_FIELDS, evidence_items)
        write_csv(self.outputs["task_results_csv"], TASK_RESULT_FIELDS, public_task_results)
        write_csv(self.outputs["batch_report_csv"], BATCH_REPORT_FIELDS, batch_reports)
        write_json(self.outputs["a2_report_json"], report)
        write_json(self.outputs["a2_manifest_json"], manifest)
        write_json(self.outputs["evidence_quality_diagnostics_json"], build_quality_diagnostics(report, quote_validation_issues))
        write_json(self.outputs["cost_latency_report_json"], build_cost_latency_report(report, batch_reports))
        write_csv(
            self.outputs["manual_qa_sample_csv"],
            MANUAL_QA_FIELDS,
            manual_qa_rows(task_results=task_results, evidence_items=evidence_items, quote_validation_issues=quote_validation_issues),
        )
        if self.config.experiment_name == "smoke_50":
            write_json(self.outputs["smoke_50_report_json"], report)
        if self.config.experiment_name == "smoke_200":
            write_json(self.outputs["smoke_200_report_json"], report)

    def _validate_config(self) -> None:
        if self.config.provider != "gemini_direct":
            raise ValueError("A2 currently supports only provider=gemini_direct")
        validate_direct_gemini_model_id(self.config.model)
        if self.config.structured_output_mode not in {"gemini_schema", "gemini_schema_lite", "prompt_json"}:
            raise ValueError("structured_output_mode must be gemini_schema, gemini_schema_lite or prompt_json")
        if self.config.limit is not None and self.config.limit == 4000:
            raise ValueError("A2 test run with --limit 4000 is forbidden")
        if self.config.max_tasks_per_batch < 1:
            raise ValueError("max_tasks_per_batch must be >= 1")
        if self.config.max_inflight < 1:
            raise ValueError("max_inflight must be >= 1")
        if self.config.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.config.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be > 0")
        if self.config.repair_max_output_tokens < self.config.max_output_tokens:
            raise ValueError("repair_max_output_tokens must be >= max_output_tokens")
        if self.config.thinking_level is not None and self.config.thinking_level not in {"minimal", "low", "medium", "high"}:
            raise ValueError("thinking_level must be minimal, low, medium, high or None")

    def _validate_inputs(self) -> None:
        required = (
            "a2_task_queue_jsonl",
            "article_status_index_jsonl",
            "tag_work_plan_adjusted_jsonl",
            "a1_report_json",
            "a1_manifest_json",
            "source_block_windows_jsonl",
            "tags_canonical_csv",
            "tag_aliases_csv",
        )
        for name in required:
            path = self.inputs[name]
            if not path.exists():
                raise FileNotFoundError(f"missing A2 input {name}: {path}")
        a1_report = _read_json(self.inputs["a1_report_json"])
        if a1_report.get("stage") != "article_a1_entity_json_bootstrap":
            raise ValueError("A2 requires a1_report stage=article_a1_entity_json_bootstrap")
        if not bool(a1_report.get("quality", {}).get("passed")):
            raise ValueError("A2 refuses to run unless a1_report.quality.passed=true")

    def _completed_task_ids(self) -> set[str]:
        path = self.outputs["evidence_task_results_jsonl"]
        if not path.exists():
            return set()
        completed: set[str] = set()
        for row in read_jsonl(path):
            status = str(row.get("status") or "")
            if status in {"success", "no_evidence", "review"} or (status == "failed" and not self.config.retry_failures):
                completed.add(str(row.get("task_id") or ""))
        return completed

    def _client(self) -> Any:
        if self.client is None:
            self.client = GeminiClient()
        return self.client

    def _max_output_tokens_for_attempt(self, attempt_index: int) -> int:
        if attempt_index <= 0:
            return self.config.max_output_tokens
        scaled = self.config.max_output_tokens * (2 ** attempt_index)
        return min(self.config.repair_max_output_tokens, max(self.config.max_output_tokens, scaled))

    def _increment_stat(self, key: str, value: int = 1) -> None:
        with self._stats_lock:
            self.stats[key] = int(self.stats.get(key, 0) or 0) + value

    def _reserve_request_budget(self, preflight_cost: float) -> bool:
        with self._stats_lock:
            committed = float(self.stats["estimated_cost_usd"])
            projected = committed + self._reserved_cost_usd + preflight_cost
            if projected > self.config.max_cost_usd:
                return False
            self._reserved_cost_usd = round(self._reserved_cost_usd + preflight_cost, 8)
            return True

    def _finish_request_budget(self, preflight_cost: float, actual_cost: float) -> None:
        with self._stats_lock:
            self._reserved_cost_usd = max(0.0, round(self._reserved_cost_usd - preflight_cost, 8))
            self.stats["estimated_cost_usd"] = round(float(self.stats["estimated_cost_usd"]) + actual_cost, 8)

    def _release_request_budget(self, preflight_cost: float) -> None:
        with self._stats_lock:
            self._reserved_cost_usd = max(0.0, round(self._reserved_cost_usd - preflight_cost, 8))

    def _record_http_status(self, status_code: int | None) -> None:
        key = str(status_code or "network")
        with self._stats_lock:
            counts = self.stats.setdefault("http_status_counts", {})
            counts[key] = int(counts.get(key, 0) or 0) + 1

    def _write_error_cache(self, context: dict[str, Any], error: GeminiError) -> None:
        self.cache.set(
            context["cache_key"],
            {
                "cache_key": context["cache_key"],
                "validation_status": "error",
                "error": str(error),
                "status_code": error.status_code,
                "response_body": error.response_body[:2000],
                "created_at": utc_now(),
            },
        )

    def _batch_report(
        self,
        batch: dict[str, Any],
        *,
        status: str,
        attempts: int,
        split_depth: int,
        cache_hit: bool,
        latency_ms: int,
        estimated_cost_usd: float,
        error: str = "",
    ) -> dict[str, Any]:
        return {
            "batch_id": str(batch.get("batch_id") or ""),
            "task_ids": list(batch.get("task_ids") or []),
            "entity_type": str(batch.get("entity_type") or ""),
            "source_strategy": str(batch.get("source_strategy") or ""),
            "priority": str(batch.get("priority") or ""),
            "tasks_count": int(batch.get("tasks_count") or len(batch.get("tasks", []))),
            "input_chars": int(batch.get("input_chars") or 0),
            "batch_group_key": str(batch.get("batch_group_key") or ""),
            "status": status,
            "attempts": attempts,
            "split_depth": split_depth,
            "cache_hit": cache_hit,
            "latency_ms": latency_ms,
            "estimated_cost_usd": estimated_cost_usd,
            "error": error,
        }


def _task_status(
    *,
    decision: str,
    relevance: str,
    items_count: int,
    valid_quote_count: int,
    invalid_quote_count: int,
    window_quality: str,
    publication_review: bool,
) -> str:
    if decision == "no_relevant_information":
        return "no_evidence"
    if decision in {"needs_review", "invalid_or_unclear_source", "related_only"}:
        return "review"
    if relevance in {"related", "unclear"}:
        return "review"
    if window_quality == "low" or publication_review:
        return "review"
    if items_count and valid_quote_count == 0:
        return "review"
    if invalid_quote_count:
        return "review"
    return "success"


def _quote_issue(
    task: dict[str, Any],
    item: dict[str, Any],
    batch_id: str,
    reason: str,
    status: str,
    created_at: str,
) -> dict[str, Any]:
    return {
        "task_id": str(task.get("task_id") or ""),
        "batch_id": batch_id,
        "tag_id": str(task.get("tag_id") or ""),
        "canonical_tag_ru": str(task.get("canonical_tag_ru") or ""),
        "entity_type": str(task.get("entity_type") or ""),
        "document_name": str(task.get("document_name") or ""),
        "window_id": str(task.get("window_id") or ""),
        "fact_type": str(item.get("fact_type") or ""),
        "claim": str(item.get("claim") or ""),
        "quote": str(item.get("quote") or ""),
        "quote_validation_status": status,
        "confidence": float(item.get("confidence") or 0.0),
        "reason": reason,
        "created_at": created_at,
    }


def _split_batch(batch: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    tasks = list(batch.get("tasks", []))
    midpoint = max(1, len(tasks) // 2)
    left_tasks = tasks[:midpoint]
    right_tasks = tasks[midpoint:]
    return _child_batch(batch, left_tasks, "s1"), _child_batch(batch, right_tasks, "s2")


def _child_batch(parent: dict[str, Any], tasks: list[dict[str, Any]], suffix: str) -> dict[str, Any]:
    input_chars = 4000 + sum(max(int(task.get("estimated_input_chars") or 0), len(str(task.get("window_text") or ""))) for task in tasks)
    return {
        "batch_id": f"{parent.get('batch_id')}_{suffix}",
        "task_ids": [str(task.get("task_id") or "") for task in tasks],
        "entity_type": parent.get("entity_type", ""),
        "source_strategy": parent.get("source_strategy", ""),
        "priority": parent.get("priority", ""),
        "tasks_count": len(tasks),
        "input_chars": input_chars,
        "batch_group_key": parent.get("batch_group_key", ""),
        "tasks": tasks,
    }


def _merge_outcomes(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    merged = {
        "task_results": [],
        "evidence_items": [],
        "quote_validation_issues": [],
        "invalid_llm_responses": [],
        "batch_reports": [],
    }
    for outcome in outcomes:
        for key in merged:
            merged[key].extend(outcome.get(key, []))
    return merged


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def _safe_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        "prompt_tokens": int(value.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(value.get("completion_tokens", 0) or 0),
        "reasoning_tokens": int(value.get("reasoning_tokens", 0) or 0),
    }


def _nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None

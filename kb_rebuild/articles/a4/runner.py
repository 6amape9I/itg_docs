from __future__ import annotations

import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from kb_rebuild.articles.a4.models import PROMPT_VERSION, SCHEMA_VERSION, STAGE, STAGE_VERSION, A4Config
from kb_rebuild.articles.a4.prompt import build_batch_prompt
from kb_rebuild.articles.a4.report import (
    ARTICLE_DRAFT_FIELDS,
    BATCH_REPORT_FIELDS,
    MANUAL_QA_FIELDS,
    article_draft_csv_rows,
    build_cost_latency_report,
    build_manifest,
    build_quality_diagnostics,
    build_report,
    manual_qa_rows,
    utc_now,
    write_csv,
    write_json,
)
from kb_rebuild.articles.a4.schema import A4_RESPONSE_SCHEMA, parse_response_json, validate_batch_response
from kb_rebuild.articles.a4.task_builder import build_batches, build_compilation_tasks, status_updates_for_all_inputs
from kb_rebuild.articles.a4.validation import article_quality_issues
from kb_rebuild.io.jsonl import read_jsonl, write_jsonl
from kb_rebuild.llm.cache import LLMCache, build_cache_key, sha256_text
from kb_rebuild.llm.gemini_client import GeminiClient, GeminiError
from kb_rebuild.llm.gemini_schema import schema_for_gemini
from kb_rebuild.llm.models import calculate_cost_usd, estimate_request_cost_usd, validate_direct_gemini_model_id
from kb_rebuild.llm.providers import completion_api_key_index, completion_usage_source


OUTPUT_FILENAMES = {
    "article_compilation_tasks_jsonl": "article_compilation_tasks.jsonl",
    "article_compilation_batches_jsonl": "article_compilation_batches.jsonl",
    "article_drafts_jsonl": "article_drafts.jsonl",
    "article_status_updates_jsonl": "article_status_updates.jsonl",
    "article_compilation_failures_jsonl": "article_compilation_failures.jsonl",
    "article_compilation_review_jsonl": "article_compilation_review.jsonl",
    "invalid_llm_responses_jsonl": "invalid_llm_responses.jsonl",
    "article_quality_issues_jsonl": "article_quality_issues.jsonl",
    "article_drafts_csv": "article_drafts.csv",
    "batch_report_csv": "batch_report.csv",
    "manual_qa_articles_sample_csv": "manual_qa_articles_sample.csv",
    "a4_report_json": "a4_report.json",
    "a4_manifest_json": "a4_manifest.json",
    "article_quality_diagnostics_json": "article_quality_diagnostics.json",
    "cost_latency_report_json": "cost_latency_report.json",
    "smoke_50_report_json": "smoke_50_report.json",
    "smoke_200_report_json": "smoke_200_report.json",
}


def run_article_a4_compilation(config: A4Config, client: Any | None = None) -> dict[str, Any]:
    return ArticleA4Runner(config=config, client=client).run()


class ArticleA4Runner:
    def __init__(self, config: A4Config, client: Any | None = None) -> None:
        self.config = config
        self.client = client
        self.outputs = {name: config.out_dir / filename for name, filename in OUTPUT_FILENAMES.items()}
        self.inputs = {
            "a4_compilation_input_jsonl": config.a3_dir / "a4_compilation_input.jsonl",
            "fact_groups_jsonl": config.a3_dir / "fact_groups.jsonl",
            "tag_fact_group_index_jsonl": config.a3_dir / "tag_fact_group_index.jsonl",
            "a3_report_json": config.a3_dir / "a3_report.json",
            "a3_manifest_json": config.a3_dir / "a3_manifest.json",
            "article_status_index_jsonl": config.a1_dir / "article_status_index.jsonl",
            "a1_report_json": config.a1_dir / "a1_report.json",
            "a1_manifest_json": config.a1_dir / "a1_manifest.json",
            "tags_canonical_csv": config.normalization_final_dir / "tags_canonical.csv",
            "tag_aliases_csv": config.normalization_final_dir / "tag_aliases.csv",
            "entities_dir": config.entities_dir,
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
            "no_unknown_fact_group_ids": True,
        }
        self._stats_lock = threading.Lock()
        self._reserved_cost_usd = 0.0
        self._stop_reason: str | None = None

    def run(self) -> dict[str, Any]:
        created_at = utc_now()
        warnings: list[str] = []
        self._validate_config()
        self._validate_inputs()

        a4_inputs = read_jsonl(self.inputs["a4_compilation_input_jsonl"])
        fact_groups = read_jsonl(self.inputs["fact_groups_jsonl"])
        completed_tag_ids = self._completed_tag_ids() if self.config.resume else set()
        tasks = build_compilation_tasks(
            a4_inputs=a4_inputs,
            fact_groups=fact_groups,
            limit=self.config.limit,
            strategy_filter=self.config.strategy_filter,
            entity_type_filter=self.config.entity_type_filter,
            priority_filter=self.config.priority_filter,
            max_fact_groups_per_tag=self.config.max_fact_groups_per_tag,
            max_quotes_per_tag=self.config.max_quotes_per_tag,
            completed_task_tag_ids=completed_tag_ids,
            retry_failures=self.config.retry_failures,
        )
        batches = build_batches(
            tasks,
            max_tags_per_batch=self.config.max_tags_per_batch,
            batch_char_limit=self.config.batch_char_limit,
        )

        status_updates = status_updates_for_all_inputs(a4_inputs, tasks)
        article_drafts: list[dict[str, Any]] = []
        failed_tasks: list[dict[str, Any]] = []
        review_rows: list[dict[str, Any]] = []
        invalid_llm_responses: list[dict[str, Any]] = []
        quality_issues: list[dict[str, Any]] = []
        batch_reports: list[dict[str, Any]] = []

        for batch, outcome in self._process_batches(batches):
            article_drafts.extend(outcome["article_drafts"])
            failed_tasks.extend(outcome["failed_tasks"])
            review_rows.extend(outcome["review_rows"])
            invalid_llm_responses.extend(outcome["invalid_llm_responses"])
            quality_issues.extend(outcome["article_quality_issues"])
            batch_reports.extend(outcome["batch_reports"])

        self._write_compiled_article_files(article_drafts)
        status_updates.extend(_result_status_updates(article_drafts, failed_tasks))
        report = build_report(
            created_at=created_at,
            config=self.config,
            inputs=self.inputs,
            tasks=tasks,
            batches=batches,
            article_drafts=article_drafts,
            failed_tasks=failed_tasks,
            batch_reports=batch_reports,
            invalid_llm_responses=invalid_llm_responses,
            article_quality_issues=quality_issues,
            stats=self.stats,
            stop_reason=self._stop_reason,
            warnings=warnings,
        )
        manifest = build_manifest(created_at=created_at, config=self.config, inputs=self.inputs, outputs=self.outputs)
        self._write_outputs(
            tasks=tasks,
            batches=batches,
            article_drafts=article_drafts,
            status_updates=status_updates,
            failed_tasks=failed_tasks,
            review_rows=review_rows,
            invalid_llm_responses=invalid_llm_responses,
            article_quality_issues=quality_issues,
            batch_reports=batch_reports,
            report=report,
            manifest=manifest,
        )
        return report

    def _process_batches(self, batches: list[dict[str, Any]]):
        if not batches:
            return
        if self.config.max_inflight == 1 or len(batches) == 1:
            for batch in batches:
                yield batch, self._process_batch(batch, split_depth=0)
            return

        executor = ThreadPoolExecutor(max_workers=self.config.max_inflight)
        futures: dict[Future[dict[str, Any]], int] = {
            executor.submit(self._process_batch, batch, 0): index for index, batch in enumerate(batches)
        }
        try:
            for future in as_completed(futures):
                index = futures[future]
                yield batches[index], future.result()
        except Exception:
            for future in futures:
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)

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
                    "response_parsed": parsed,
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
        tasks_by_id = {str(task.get("task_id") or ""): task for task in batch.get("tasks", [])}
        article_drafts: list[dict[str, Any]] = []
        review_rows: list[dict[str, Any]] = []
        quality_issues: list[dict[str, Any]] = []
        for parsed_article in parsed.get("articles", []):
            task = tasks_by_id[str(parsed_article.get("task_id") or "")]
            draft = self._materialize_article(
                parsed_article=parsed_article,
                task=task,
                batch_id=str(batch.get("batch_id") or ""),
                model=model,
                provider=provider,
            )
            article_drafts.append(draft)
            if draft.get("needs_review_before_publication") or draft.get("article_status") != "compiled_article":
                review_rows.append(_review_row_from_draft(draft))
            quality_issues.extend(article_quality_issues(parsed_article, task))
        return {
            "article_drafts": article_drafts,
            "failed_tasks": [],
            "review_rows": review_rows,
            "invalid_llm_responses": invalid_records or [],
            "article_quality_issues": quality_issues,
            "batch_reports": [batch_report],
        }

    def _materialize_article(
        self,
        *,
        parsed_article: dict[str, Any],
        task: dict[str, Any],
        batch_id: str,
        model: str,
        provider: str,
    ) -> dict[str, Any]:
        created_at = utc_now()
        used_ids = [str(item) for item in parsed_article.get("used_fact_group_ids", [])]
        source_doc_ids = _source_doc_ids(task, used_ids)
        entity_type = str(task.get("entity_type") or "unknown")
        tag_id = str(task.get("tag_id") or "")
        article_file_path = self.config.out_dir / "compiled_articles" / entity_type / f"{tag_id}.json"
        return {
            "task_id": str(task.get("task_id") or ""),
            "batch_id": batch_id,
            "tag_id": tag_id,
            "canonical_tag_ru": str(task.get("canonical_tag_ru") or ""),
            "canonical_tag_latin": _nullable_string(task.get("canonical_tag_latin")),
            "entity_type": entity_type,
            "a4_strategy": str(task.get("a4_strategy") or ""),
            "article_status_from_a1": str(task.get("article_status_from_a1") or ""),
            "article_status": str(parsed_article.get("article_status") or ""),
            "source_stage": "A4",
            "title": str(parsed_article.get("title") or ""),
            "summary": str(parsed_article.get("summary") or ""),
            "content_format": "editorjs",
            "content": parsed_article.get("content"),
            "used_fact_group_ids": used_ids,
            "unused_fact_group_ids": [str(item) for item in parsed_article.get("unused_fact_group_ids", [])],
            "fact_group_ids": [str(item) for item in task.get("fact_group_ids", [])],
            "core_fact_group_ids": [str(item) for item in task.get("core_fact_group_ids", [])],
            "source_doc_ids": source_doc_ids,
            "source_documents_count": len(source_doc_ids),
            "task_needs_review_before_publication": bool(task.get("needs_review_before_publication")),
            "needs_review_before_publication": bool(parsed_article.get("needs_review_before_publication")),
            "review_reasons": [str(item) for item in parsed_article.get("review_reasons", [])],
            "confidence": float(parsed_article.get("confidence") or 0.0),
            "reason": str(parsed_article.get("reason") or ""),
            "model": model,
            "provider": provider,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "created_at": created_at,
            "article_file_path": str(article_file_path),
        }

    def _failed_outcome(
        self,
        batch: dict[str, Any],
        reason: str,
        split_depth: int,
        *,
        include_invalid_record: bool = True,
    ) -> dict[str, Any]:
        failed_tasks = []
        review_rows = []
        for task in batch.get("tasks", []):
            row = {
                "task_id": str(task.get("task_id") or ""),
                "batch_id": str(batch.get("batch_id") or ""),
                "tag_id": str(task.get("tag_id") or ""),
                "canonical_tag_ru": str(task.get("canonical_tag_ru") or ""),
                "entity_type": str(task.get("entity_type") or ""),
                "a4_strategy": str(task.get("a4_strategy") or ""),
                "needs_review_before_publication": True,
                "review_reasons": [*list(task.get("review_reasons") or []), "a4_compilation_failed"],
                "reason": reason,
                "status": "failed",
                "created_at": utc_now(),
            }
            failed_tasks.append(row)
            review_rows.append(row)
        return {
            "article_drafts": [],
            "failed_tasks": failed_tasks,
            "review_rows": review_rows,
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
            "article_quality_issues": [],
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
                A4_RESPONSE_SCHEMA,
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

    def _write_compiled_article_files(self, article_drafts: list[dict[str, Any]]) -> None:
        for draft in article_drafts:
            path = Path(str(draft.get("article_file_path") or ""))
            write_json(path, _compiled_article_payload(draft))

    def _write_outputs(
        self,
        *,
        tasks: list[dict[str, Any]],
        batches: list[dict[str, Any]],
        article_drafts: list[dict[str, Any]],
        status_updates: list[dict[str, Any]],
        failed_tasks: list[dict[str, Any]],
        review_rows: list[dict[str, Any]],
        invalid_llm_responses: list[dict[str, Any]],
        article_quality_issues: list[dict[str, Any]],
        batch_reports: list[dict[str, Any]],
        report: dict[str, Any],
        manifest: dict[str, Any],
    ) -> None:
        self.config.out_dir.mkdir(parents=True, exist_ok=True)
        public_tasks = [_scrub_task(task) for task in tasks]
        public_batches = [{key: value for key, value in batch.items() if key != "tasks"} for batch in batches]
        write_jsonl(self.outputs["article_compilation_tasks_jsonl"], public_tasks)
        write_jsonl(self.outputs["article_compilation_batches_jsonl"], public_batches)
        write_jsonl(self.outputs["article_drafts_jsonl"], article_drafts)
        write_jsonl(self.outputs["article_status_updates_jsonl"], status_updates)
        write_jsonl(self.outputs["article_compilation_failures_jsonl"], failed_tasks)
        write_jsonl(self.outputs["article_compilation_review_jsonl"], review_rows)
        write_jsonl(self.outputs["invalid_llm_responses_jsonl"], invalid_llm_responses)
        write_jsonl(self.outputs["article_quality_issues_jsonl"], article_quality_issues)
        write_csv(self.outputs["article_drafts_csv"], ARTICLE_DRAFT_FIELDS, article_draft_csv_rows(article_drafts))
        write_csv(self.outputs["batch_report_csv"], BATCH_REPORT_FIELDS, batch_reports)
        write_csv(self.outputs["manual_qa_articles_sample_csv"], MANUAL_QA_FIELDS, manual_qa_rows(article_drafts, failed_tasks))
        write_json(self.outputs["a4_report_json"], report)
        write_json(self.outputs["a4_manifest_json"], manifest)
        write_json(self.outputs["article_quality_diagnostics_json"], build_quality_diagnostics(report, article_quality_issues))
        write_json(self.outputs["cost_latency_report_json"], build_cost_latency_report(report, batch_reports))
        if self.config.experiment_name == "smoke_50":
            write_json(self.outputs["smoke_50_report_json"], report)
        if self.config.experiment_name == "smoke_200":
            write_json(self.outputs["smoke_200_report_json"], report)

    def _validate_config(self) -> None:
        if self.config.provider != "gemini_direct":
            raise ValueError("A4 currently supports only provider=gemini_direct")
        validate_direct_gemini_model_id(self.config.model)
        if self.config.structured_output_mode not in {"gemini_schema", "gemini_schema_lite", "prompt_json"}:
            raise ValueError("structured_output_mode must be gemini_schema, gemini_schema_lite or prompt_json")
        if self.config.limit is None:
            raise ValueError("A4 production/no-limit run is forbidden in this implementation turn; pass an explicit smoke --limit")
        if self.config.limit == 4000:
            raise ValueError("A4 test run with --limit 4000 is forbidden")
        if any(str(part).startswith("production") for part in self.config.out_dir.parts):
            raise ValueError("A4 production output paths are forbidden without separate architect approval")
        if self.config.max_tags_per_batch < 1:
            raise ValueError("max_tags_per_batch must be >= 1")
        if self.config.max_fact_groups_per_tag < 1:
            raise ValueError("max_fact_groups_per_tag must be >= 1")
        if self.config.max_quotes_per_tag < 1:
            raise ValueError("max_quotes_per_tag must be >= 1")
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
            "a4_compilation_input_jsonl",
            "fact_groups_jsonl",
            "tag_fact_group_index_jsonl",
            "a3_report_json",
            "a3_manifest_json",
            "article_status_index_jsonl",
            "a1_report_json",
            "a1_manifest_json",
            "tags_canonical_csv",
            "tag_aliases_csv",
        )
        for name in required:
            path = self.inputs[name]
            if not path.exists():
                raise FileNotFoundError(f"missing A4 input {name}: {path}")
        if not self.inputs["entities_dir"].exists():
            raise FileNotFoundError(f"missing A4 input entities_dir: {self.inputs['entities_dir']}")

        a3_report = _read_json(self.inputs["a3_report_json"])
        if a3_report.get("stage") != "article_a3_evidence_dedupe_fact_grouping":
            raise ValueError("A4 requires a3_report stage=article_a3_evidence_dedupe_fact_grouping")
        if not bool(a3_report.get("quality", {}).get("passed")):
            raise ValueError("A4 refuses to run unless a3_report.quality.passed=true")
        if int(a3_report.get("counts", {}).get("ready_for_a4_tags", 0) or 0) <= 0:
            raise ValueError("A4 requires ready_for_a4_tags > 0")

        a1_report = _read_json(self.inputs["a1_report_json"])
        if a1_report.get("stage") != "article_a1_entity_json_bootstrap":
            raise ValueError("A4 requires a1_report stage=article_a1_entity_json_bootstrap")
        if not bool(a1_report.get("quality", {}).get("passed")):
            raise ValueError("A4 refuses to run unless a1_report.quality.passed=true")

    def _completed_tag_ids(self) -> set[str]:
        path = self.outputs["article_drafts_jsonl"]
        if not path.exists():
            return set()
        completed: set[str] = set()
        for row in read_jsonl(path):
            if str(row.get("article_status") or "") in {"compiled_article", "compiled_with_review_flag"}:
                completed.add(str(row.get("tag_id") or ""))
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
            "tag_ids": list(batch.get("tag_ids") or []),
            "entity_types": list(batch.get("entity_types") or []),
            "a4_strategies": list(batch.get("a4_strategies") or []),
            "tasks_count": int(batch.get("tasks_count") or len(batch.get("tasks", []))),
            "input_chars": int(batch.get("input_chars") or 0),
            "status": status,
            "attempts": attempts,
            "split_depth": split_depth,
            "cache_hit": cache_hit,
            "latency_ms": latency_ms,
            "estimated_cost_usd": estimated_cost_usd,
            "error": error,
        }


def _compiled_article_payload(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag_id": draft.get("tag_id"),
        "canonical_tag_ru": draft.get("canonical_tag_ru"),
        "canonical_tag_latin": draft.get("canonical_tag_latin"),
        "entity_type": draft.get("entity_type"),
        "article_status": draft.get("article_status"),
        "source_stage": "A4",
        "a4_strategy": draft.get("a4_strategy"),
        "title": draft.get("title"),
        "summary": draft.get("summary"),
        "content_format": "editorjs",
        "content": draft.get("content"),
        "needs_review_before_publication": draft.get("needs_review_before_publication"),
        "review_reasons": draft.get("review_reasons", []),
        "used_fact_group_ids": draft.get("used_fact_group_ids", []),
        "unused_fact_group_ids": draft.get("unused_fact_group_ids", []),
        "sources": {
            "fact_group_ids": draft.get("used_fact_group_ids", []),
            "source_doc_ids": draft.get("source_doc_ids", []),
            "source_documents_count": draft.get("source_documents_count", 0),
        },
        "provenance": {
            "a3_input": "data/articles/a3/a4_compilation_input.jsonl",
            "stage": STAGE,
            "stage_version": STAGE_VERSION,
            "task_id": draft.get("task_id"),
            "batch_id": draft.get("batch_id"),
            "model": draft.get("model"),
            "provider": draft.get("provider"),
            "prompt_version": draft.get("prompt_version"),
            "schema_version": draft.get("schema_version"),
            "created_at": draft.get("created_at"),
        },
    }


def _review_row_from_draft(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": draft.get("task_id", ""),
        "batch_id": draft.get("batch_id", ""),
        "tag_id": draft.get("tag_id", ""),
        "canonical_tag_ru": draft.get("canonical_tag_ru", ""),
        "entity_type": draft.get("entity_type", ""),
        "a4_strategy": draft.get("a4_strategy", ""),
        "article_status": draft.get("article_status", ""),
        "needs_review_before_publication": draft.get("needs_review_before_publication", False),
        "review_reasons": draft.get("review_reasons", []),
        "article_file_path": draft.get("article_file_path", ""),
        "reason": draft.get("reason", ""),
        "created_at": draft.get("created_at", ""),
    }


def _source_doc_ids(task: dict[str, Any], used_fact_group_ids: list[str]) -> list[str]:
    allowed = set(used_fact_group_ids)
    source_doc_ids: set[str] = set()
    for group in task.get("fact_groups", []):
        if not isinstance(group, dict):
            continue
        if str(group.get("fact_group_id") or "") not in allowed:
            continue
        for doc_id in group.get("source_doc_ids", []) or []:
            if str(doc_id):
                source_doc_ids.add(str(doc_id))
    return sorted(source_doc_ids)


def _result_status_updates(article_drafts: list[dict[str, Any]], failed_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for draft in article_drafts:
        rows.append(
            {
                "tag_id": draft.get("tag_id"),
                "task_id": draft.get("task_id"),
                "canonical_tag_ru": draft.get("canonical_tag_ru"),
                "entity_type": draft.get("entity_type"),
                "a4_strategy": draft.get("a4_strategy"),
                "ready_for_a4": True,
                "status_update": "compiled",
                "article_status": draft.get("article_status"),
                "article_file_path": draft.get("article_file_path"),
                "needs_review_before_publication": draft.get("needs_review_before_publication"),
                "review_reasons": draft.get("review_reasons", []),
            }
        )
    for row in failed_tasks:
        rows.append(
            {
                "tag_id": row.get("tag_id"),
                "task_id": row.get("task_id"),
                "canonical_tag_ru": row.get("canonical_tag_ru"),
                "entity_type": row.get("entity_type"),
                "a4_strategy": row.get("a4_strategy"),
                "ready_for_a4": True,
                "status_update": "failed",
                "article_status": "a4_compilation_failed",
                "article_file_path": "",
                "needs_review_before_publication": True,
                "review_reasons": row.get("review_reasons", []),
            }
        )
    return rows


def _split_batch(batch: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    tasks = list(batch.get("tasks", []))
    midpoint = max(1, len(tasks) // 2)
    left_tasks = tasks[:midpoint]
    right_tasks = tasks[midpoint:]
    return _child_batch(batch, left_tasks, "s1"), _child_batch(batch, right_tasks, "s2")


def _child_batch(parent: dict[str, Any], tasks: list[dict[str, Any]], suffix: str) -> dict[str, Any]:
    return {
        "batch_id": f"{parent.get('batch_id')}_{suffix}",
        "task_ids": [str(task.get("task_id") or "") for task in tasks],
        "tag_ids": [str(task.get("tag_id") or "") for task in tasks],
        "entity_types": sorted({str(task.get("entity_type") or "") for task in tasks}),
        "a4_strategies": sorted({str(task.get("a4_strategy") or "") for task in tasks}),
        "tasks_count": len(tasks),
        "input_chars": 4000 + sum(int(task.get("estimated_input_chars") or 0) for task in tasks),
        "tasks": tasks,
    }


def _merge_outcomes(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    merged = {
        "article_drafts": [],
        "failed_tasks": [],
        "review_rows": [],
        "invalid_llm_responses": [],
        "article_quality_issues": [],
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


def _scrub_task(task: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in task.items() if key != "fact_groups"}

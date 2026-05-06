from __future__ import annotations

import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kb_rebuild.io.jsonl import read_jsonl, write_jsonl
from kb_rebuild.llm.cache import LLMCache, build_cache_key, sha256_text
from kb_rebuild.llm.gemini_client import GeminiClient, GeminiError
from kb_rebuild.llm.gemini_schema import schema_for_gemini
from kb_rebuild.llm.models import (
    GEMINI_3_FLASH_PREVIEW,
    calculate_cost_usd,
    estimate_request_cost_usd,
    validate_direct_gemini_model_id,
)
from kb_rebuild.llm.providers import completion_api_key_index, completion_usage_source
from kb_rebuild.llm.tagging import utc_now
from kb_rebuild.normalization.n3.models import (
    N3Decision,
    N3InputGroup,
    N3RejectedLabel,
    N3Subcluster,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    STAGE_VERSION,
)
from kb_rebuild.normalization.n3.prompt import build_group_prompt
from kb_rebuild.normalization.n3.quality import find_known_bad_accepted_clusters, build_quality_diagnostics
from kb_rebuild.normalization.n3.report import (
    accepted_cluster_csv_rows,
    build_report,
    decision_csv_rows,
    group_csv_rows,
    partition_decisions,
    write_csv,
    write_json,
)
from kb_rebuild.normalization.n3.schema import (
    N3_RESPONSE_SCHEMA,
    invalid_response_review_decision,
    parse_decision_json,
    validate_decision_response,
)


@dataclass(frozen=True)
class N3Config:
    data_dir: Path = Path("data")
    normalization_dir: Path = Path("data/normalization")
    n2_dir: Path = Path("data/normalization/n2")
    out_dir: Path = Path("data/normalization/n3")
    provider: str = "gemini_direct"
    model: str = GEMINI_3_FLASH_PREVIEW
    batch_size: int = 1
    max_inflight: int = 8
    max_retries: int = 3
    max_cost_usd: float = 20.0
    structured_output_mode: str = "gemini_schema"
    enable_web_review: bool = False
    web_review_model: str = "gemini-2.5-flash"
    web_review_limit: int = 50
    no_overwrite: bool = False
    max_output_tokens: int = 6000
    repair_max_output_tokens: int = 12000
    thinking_level: str | None = "minimal"
    temperature: float = 0.0

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Path,
        *,
        normalization_dir: Path | None = None,
        n2_dir: Path | None = None,
        out_dir: Path | None = None,
        provider: str = "gemini_direct",
        model: str = GEMINI_3_FLASH_PREVIEW,
        batch_size: int = 1,
        max_inflight: int = 8,
        max_retries: int = 3,
        max_cost_usd: float = 20.0,
        structured_output_mode: str = "gemini_schema",
        enable_web_review: bool = False,
        web_review_model: str = "gemini-2.5-flash",
        web_review_limit: int = 50,
        no_overwrite: bool = False,
        max_output_tokens: int = 6000,
        repair_max_output_tokens: int = 12000,
        thinking_level: str | None = "minimal",
    ) -> "N3Config":
        norm_dir = normalization_dir or data_dir / "normalization"
        return cls(
            data_dir=data_dir,
            normalization_dir=norm_dir,
            n2_dir=n2_dir or norm_dir / "n2",
            out_dir=out_dir or norm_dir / "n3",
            provider=provider,
            model=model,
            batch_size=batch_size,
            max_inflight=max_inflight,
            max_retries=max_retries,
            max_cost_usd=max_cost_usd,
            structured_output_mode=structured_output_mode,
            enable_web_review=enable_web_review,
            web_review_model=web_review_model,
            web_review_limit=web_review_limit,
            no_overwrite=no_overwrite,
            max_output_tokens=max_output_tokens,
            repair_max_output_tokens=repair_max_output_tokens,
            thinking_level=thinking_level,
        )


OUTPUT_FILENAMES = {
    "llm_group_decisions_jsonl": "llm_group_decisions.jsonl",
    "accepted_clusters_jsonl": "accepted_clusters.jsonl",
    "rejected_groups_jsonl": "rejected_groups.jsonl",
    "split_groups_jsonl": "split_groups.jsonl",
    "web_or_human_review_groups_jsonl": "web_or_human_review_groups.jsonl",
    "n3_report_json": "n3_report.json",
    "n3_manifest_json": "n3_manifest.json",
    "llm_group_decisions_csv": "llm_group_decisions.csv",
    "accepted_clusters_csv": "accepted_clusters.csv",
    "split_groups_csv": "split_groups.csv",
    "rejected_groups_csv": "rejected_groups.csv",
    "review_groups_csv": "review_groups.csv",
    "validation_failures_jsonl": "validation_failures.jsonl",
    "known_bad_decision_checks_csv": "known_bad_decision_checks.csv",
    "known_bad_accepted_clusters_csv": "known_bad_accepted_clusters.csv",
    "n3_quality_diagnostics_json": "n3_quality_diagnostics.json",
}


def run_normalization_n3(config: N3Config, client: Any | None = None) -> dict[str, Any]:
    return NormalizationN3Runner(config=config, client=client).run()


class NormalizationN3Runner:
    def __init__(self, config: N3Config, client: Any | None = None) -> None:
        self.config = config
        self.paths = {name: config.out_dir / filename for name, filename in OUTPUT_FILENAMES.items()}
        self.inputs = {
            "n3_candidate_groups": config.n2_dir / "n3_candidate_groups.jsonl",
            "n2_manifest": config.n2_dir / "candidate_generation_manifest.json",
            "n2_report": config.n2_dir / "candidate_generation_report.json",
            "n2_diagnostics": config.n2_dir / "group_quality_diagnostics.json",
            "candidate_nodes": config.n2_dir / "candidate_nodes.jsonl",
            "candidate_pairs": config.n2_dir / "candidate_pairs.jsonl",
            "auto_clusters": config.normalization_dir / "auto_clusters.jsonl",
            "tag_mentions_normalized": config.normalization_dir / "tag_mentions_normalized.jsonl",
        }
        self.client = client
        self.cache = LLMCache(config.out_dir / "llm_cache")
        self.stats = {
            "estimated_cost_usd": 0.0,
            "requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "invalid_llm_responses": 0,
        }
        self._reserved_cost_usd = 0.0
        self._stats_lock = threading.Lock()

    def run(self) -> dict[str, Any]:
        created_at = utc_now()
        warnings: list[str] = []
        self._validate_config()
        self._validate_inputs()
        if self.config.no_overwrite:
            self._refuse_overwrite()

        groups = self._load_groups()
        decisions, validation_failures = self._process_groups(groups)

        accepted_clusters, rejected_groups, split_groups, review_groups = partition_decisions(decisions)
        known_bad_matches = find_known_bad_accepted_clusters(accepted_clusters)
        quality = build_quality_diagnostics(
            accepted_clusters=accepted_clusters,
            split_groups=split_groups,
            known_bad_matches=known_bad_matches,
        )

        self.config.out_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(self.paths["llm_group_decisions_jsonl"], (decision.to_dict() for decision in decisions))
        write_jsonl(self.paths["accepted_clusters_jsonl"], accepted_clusters)
        write_jsonl(self.paths["rejected_groups_jsonl"], rejected_groups)
        write_jsonl(self.paths["split_groups_jsonl"], split_groups)
        write_jsonl(self.paths["web_or_human_review_groups_jsonl"], review_groups)
        write_jsonl(self.paths["validation_failures_jsonl"], validation_failures)

        write_csv(self.paths["llm_group_decisions_csv"], _decision_csv_fields(), decision_csv_rows(decisions))
        write_csv(self.paths["accepted_clusters_csv"], _accepted_csv_fields(), accepted_cluster_csv_rows(accepted_clusters))
        write_csv(self.paths["split_groups_csv"], _group_csv_fields(), group_csv_rows(split_groups))
        write_csv(self.paths["rejected_groups_csv"], _group_csv_fields(), group_csv_rows(rejected_groups))
        write_csv(self.paths["review_groups_csv"], _group_csv_fields(), group_csv_rows(review_groups))
        write_csv(
            self.paths["known_bad_decision_checks_csv"],
            ["n3_cluster_id", "source_candidate_group_id", "labels", "reason"],
            known_bad_matches,
        )
        write_csv(
            self.paths["known_bad_accepted_clusters_csv"],
            ["n3_cluster_id", "source_candidate_group_id", "labels", "reason"],
            known_bad_matches,
        )
        write_json(self.paths["n3_quality_diagnostics_json"], quality)

        report = build_report(
            created_at=created_at,
            n2_manifest_path=self.inputs["n2_manifest"],
            n3_candidate_groups_path=self.inputs["n3_candidate_groups"],
            decisions=decisions,
            accepted_clusters=accepted_clusters,
            rejected_groups=rejected_groups,
            split_groups=split_groups,
            review_groups=review_groups,
            validation_failures=validation_failures,
            known_bad_matches=known_bad_matches,
            estimated_cost_usd=float(self.stats["estimated_cost_usd"]),
            requests=int(self.stats["requests"]),
            cache_hits=int(self.stats["cache_hits"]),
            cache_misses=int(self.stats["cache_misses"]),
            warnings=warnings,
        )
        write_json(self.paths["n3_report_json"], report)
        write_json(self.paths["n3_manifest_json"], self._build_manifest(created_at))
        return report

    def _validate_config(self) -> None:
        if self.config.provider != "gemini_direct":
            raise ValueError("N3 currently supports only provider=gemini_direct")
        validate_direct_gemini_model_id(self.config.model)
        if self.config.batch_size != 1:
            raise ValueError("N3 currently supports only batch_size=1")
        if self.config.max_inflight < 1:
            raise ValueError("max_inflight must be >= 1")
        if self.config.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be > 0")
        if self.config.repair_max_output_tokens < self.config.max_output_tokens:
            raise ValueError("repair_max_output_tokens must be >= max_output_tokens")
        if self.config.thinking_level is not None and self.config.thinking_level not in {"minimal", "low", "medium", "high"}:
            raise ValueError("thinking_level must be minimal, low, medium, high or None")
        if self.config.structured_output_mode not in {"gemini_schema", "gemini_schema_lite", "prompt_json"}:
            raise ValueError(f"unsupported structured output mode: {self.config.structured_output_mode}")

    def _validate_inputs(self) -> None:
        for name, path in self.inputs.items():
            if name in {"candidate_pairs", "auto_clusters", "tag_mentions_normalized"}:
                continue
            if not path.exists():
                raise FileNotFoundError(f"missing N3 input {name}: {path}")
        n2_manifest = _read_json(self.inputs["n2_manifest"])
        n2_report = _read_json(self.inputs["n2_report"])
        if n2_manifest.get("stage_version") != "n2.2":
            raise ValueError("N3 requires N2 manifest stage_version=n2.2")
        if n2_report.get("stage_version") != "n2.2":
            raise ValueError("N3 requires N2 report stage_version=n2.2")
        if not n2_report.get("quality_gate", {}).get("passed"):
            raise ValueError("N3 refuses to run unless N2 quality_gate.passed=true")

    def _refuse_overwrite(self) -> None:
        existing = [str(path) for name, path in self.paths.items() if name != "n3_quality_diagnostics_json" and path.exists()]
        if existing:
            raise FileExistsError("N3 output exists and --no-overwrite was set: " + ", ".join(existing[:10]))

    def _load_groups(self) -> list[N3InputGroup]:
        n2_groups = read_jsonl(self.inputs["n3_candidate_groups"])
        nodes_by_id = {
            str(node.get("node_id", "")): node
            for node in read_jsonl(self.inputs["candidate_nodes"])
            if str(node.get("node_id", ""))
        }
        groups = [N3InputGroup.from_n2_group(group, nodes_by_id) for group in n2_groups]
        for group in groups:
            if not group.candidate_group_id or len(group.node_ids) < 2:
                raise ValueError(f"invalid N3 group input: {group.candidate_group_id}")
        return groups

    def _process_groups(self, groups: list[N3InputGroup]) -> tuple[list[N3Decision], list[dict[str, Any]]]:
        if self.config.max_inflight == 1 or len(groups) <= 1:
            decisions: list[N3Decision] = []
            validation_failures: list[dict[str, Any]] = []
            for group in groups:
                decision, failures = self._process_group(group)
                decisions.append(decision)
                validation_failures.extend(failures)
            return decisions, validation_failures

        results: list[tuple[N3Decision, list[dict[str, Any]]] | None] = [None] * len(groups)
        executor = ThreadPoolExecutor(max_workers=self.config.max_inflight)
        futures: dict[Future[tuple[N3Decision, list[dict[str, Any]]]], int] = {
            executor.submit(self._process_group, group): index for index, group in enumerate(groups)
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

        decisions = []
        validation_failures = []
        for item in results:
            if item is None:
                raise RuntimeError("N3 parallel processing finished with a missing group result")
            decision, failures = item
            decisions.append(decision)
            validation_failures.extend(failures)
        return decisions, validation_failures

    def _process_group(self, group: N3InputGroup) -> tuple[N3Decision, list[dict[str, Any]]]:
        last_errors: list[str] = []
        failures: list[dict[str, Any]] = []
        for attempt_index in range(self.config.max_retries + 1):
            context = self._request_context(group, repair_errors=last_errors if attempt_index else None, attempt_index=attempt_index)
            cached = self.cache.get(context["cache_key"])
            if cached:
                self._increment_stat("cache_hits")
                if cached.get("validation_status") == "valid" and isinstance(cached.get("response_parsed"), dict):
                    parsed = dict(cached["response_parsed"])
                    decision = self._decision_from_parsed(
                        group=group,
                        parsed=parsed,
                        model=str(cached.get("model") or self.config.model),
                        usage=_safe_usage(cached.get("usage")),
                        estimated_cost_usd=float(cached.get("estimated_cost_usd") or 0.0),
                        latency_ms=int(cached.get("latency_ms") or 0),
                        cache_key=context["cache_key"],
                        from_cache=True,
                    )
                    return decision, []
                if cached.get("validation_status") == "invalid":
                    last_errors = _safe_error_list(cached.get("validation_errors")) or ["cached invalid LLM response"]
                    if attempt_index < self.config.max_retries:
                        continue
                    break

            self._increment_stat("cache_misses")
            preflight_cost = estimate_request_cost_usd(
                model_id=self.config.model,
                input_chars=int(context["prompt_chars"]),
                max_output_tokens=int(context["max_output_tokens"]),
            )
            self._reserve_request_budget(preflight_cost)

            try:
                completion = self._client().chat_completion(context["payload"])
            except GeminiError as exc:
                self._release_request_budget(preflight_cost)
                self._write_error_cache(context, exc)
                if exc.retryable and attempt_index < self.config.max_retries:
                    last_errors = [str(exc)]
                    continue
                last_errors = [str(exc)]
                break

            self._increment_stat("requests")
            cost_usd = calculate_cost_usd(self.config.model, **completion.usage)
            self._finish_request_budget(preflight_cost, cost_usd)
            parsed_raw, parse_errors = parse_decision_json(completion.content)
            parsed: dict[str, Any] | None = None
            validation_errors = list(parse_errors)
            if parsed_raw is not None:
                parsed, validation_errors = validate_decision_response(parsed_raw, group)
            self.cache.set(
                context["cache_key"],
                {
                    "cache_key": context["cache_key"],
                    "candidate_group_id": group.candidate_group_id,
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
                decision = self._decision_from_parsed(
                    group=group,
                    parsed=parsed,
                    model=completion.model or self.config.model,
                    usage=completion.usage,
                    estimated_cost_usd=cost_usd,
                    latency_ms=completion.latency_ms,
                    cache_key=context["cache_key"],
                    from_cache=False,
                )
                return decision, []
            last_errors = validation_errors or ["unknown invalid LLM response"]
            if attempt_index < self.config.max_retries:
                continue

        self._increment_stat("invalid_llm_responses")
        fallback = invalid_response_review_decision(group, last_errors)
        failures.append(
            {
                "candidate_group_id": group.candidate_group_id,
                "entity_type": group.entity_type,
                "errors": last_errors,
                "created_at": utc_now(),
            }
        )
        decision = self._decision_from_parsed(
            group=group,
            parsed=fallback,
            model=self.config.model,
            usage={},
            estimated_cost_usd=0.0,
            latency_ms=0,
            cache_key="",
            from_cache=False,
        )
        return decision, failures

    def _client(self) -> Any:
        if self.client is None:
            self.client = GeminiClient()
        return self.client

    def _increment_stat(self, key: str, value: int = 1) -> None:
        with self._stats_lock:
            self.stats[key] = int(self.stats.get(key, 0)) + value

    def _reserve_request_budget(self, preflight_cost: float) -> None:
        with self._stats_lock:
            committed = float(self.stats["estimated_cost_usd"])
            projected = committed + self._reserved_cost_usd + preflight_cost
            if projected > self.config.max_cost_usd:
                raise RuntimeError(
                    "N3 budget limit reached before request: "
                    f"spent={committed:.6f}, reserved={self._reserved_cost_usd:.6f}, "
                    f"next_estimate={preflight_cost:.6f}, limit={self.config.max_cost_usd:.6f}"
                )
            self._reserved_cost_usd = round(self._reserved_cost_usd + preflight_cost, 8)

    def _finish_request_budget(self, preflight_cost: float, actual_cost: float) -> None:
        with self._stats_lock:
            self._reserved_cost_usd = max(0.0, round(self._reserved_cost_usd - preflight_cost, 8))
            self.stats["estimated_cost_usd"] = round(float(self.stats["estimated_cost_usd"]) + actual_cost, 8)

    def _release_request_budget(self, preflight_cost: float) -> None:
        with self._stats_lock:
            self._reserved_cost_usd = max(0.0, round(self._reserved_cost_usd - preflight_cost, 8))

    def _request_context(
        self,
        group: N3InputGroup,
        *,
        repair_errors: list[str] | None,
        attempt_index: int,
    ) -> dict[str, Any]:
        prompt = build_group_prompt(group, repair_errors=repair_errors)
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
                N3_RESPONSE_SCHEMA,
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
                    "stage": "normalization_n3",
                    "group": group.to_prompt_payload(),
                    "prompt_hash": sha256_text(prompt),
                    "web_review_enabled": self.config.enable_web_review,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        request_params = {
            "stage": "normalization_n3",
            "provider": self.config.provider,
            "temperature": self.config.temperature,
            "max_output_tokens": max_output_tokens,
            "thinking_level": self.config.thinking_level,
            "structured_output_mode": self.config.structured_output_mode,
            "attempt_index": attempt_index,
            "web_review_enabled": self.config.enable_web_review,
            "payload_shape": "gemini_generate_content",
        }
        cache_key = build_cache_key(
            provider=self.config.provider,
            model=self.config.model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            doc_id=group.candidate_group_id,
            input_hash=input_hash,
            request_params=request_params,
        )
        return {
            "payload": payload,
            "cache_key": cache_key,
            "prompt_chars": len(prompt),
            "max_output_tokens": max_output_tokens,
            "request_params": request_params,
        }

    def _max_output_tokens_for_attempt(self, attempt_index: int) -> int:
        if attempt_index <= 0:
            return self.config.max_output_tokens
        scaled = self.config.max_output_tokens * (2 ** attempt_index)
        return min(self.config.repair_max_output_tokens, max(self.config.max_output_tokens, scaled))

    def _decision_from_parsed(
        self,
        *,
        group: N3InputGroup,
        parsed: dict[str, Any],
        model: str,
        usage: dict[str, int],
        estimated_cost_usd: float,
        latency_ms: int,
        cache_key: str,
        from_cache: bool,
    ) -> N3Decision:
        return N3Decision(
            candidate_group_id=group.candidate_group_id,
            entity_type=group.entity_type,
            input_group_labels=group.group_labels,
            input_node_ids=group.node_ids,
            decision=str(parsed.get("decision", "")),
            confidence=float(parsed.get("confidence", 0.0) or 0.0),
            canonical_tag_ru=str(parsed.get("canonical_tag_ru", "")),
            canonical_tag_latin=str(parsed.get("canonical_tag_latin", "")),
            subclusters=[N3Subcluster.from_dict(item) for item in parsed.get("subclusters", []) if isinstance(item, dict)],
            rejected_labels=[
                N3RejectedLabel.from_dict(item) for item in parsed.get("rejected_labels", []) if isinstance(item, dict)
            ],
            reason=str(parsed.get("reason", "")),
            risk_flags=[str(flag) for flag in parsed.get("risk_flags", [])],
            requires_human_review=bool(parsed.get("requires_human_review", False)),
            model=model,
            provider=self.config.provider,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            usage=usage,
            estimated_cost_usd=estimated_cost_usd,
            latency_ms=latency_ms,
            cache_key=cache_key,
            from_cache=from_cache,
            created_at=utc_now(),
        )

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

    def _build_manifest(self, created_at: str) -> dict[str, Any]:
        return {
            "stage": "normalization_n3_llm_validation",
            "stage_version": STAGE_VERSION,
            "created_at": created_at,
            "source_n2_manifest": str(self.inputs["n2_manifest"]),
            "source_n2_stage_version": "n2.2",
            "inputs": {key: str(path) for key, path in self.inputs.items()},
            "outputs": {key: str(path) for key, path in self.paths.items()},
            "model": self.config.model,
            "provider": self.config.provider,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
        }


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


def _safe_error_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _decision_csv_fields() -> list[str]:
    return [
        "candidate_group_id",
        "entity_type",
        "decision",
        "confidence",
        "canonical_tag_ru",
        "canonical_tag_latin",
        "input_group_labels",
        "input_node_ids",
        "requires_human_review",
        "risk_flags",
        "reason",
        "model",
        "estimated_cost_usd",
        "cache_key",
        "from_cache",
    ]


def _accepted_csv_fields() -> list[str]:
    return [
        "n3_cluster_id",
        "source_candidate_group_id",
        "entity_type",
        "canonical_tag_ru",
        "canonical_tag_latin",
        "labels",
        "node_ids",
        "confidence",
        "decision_source",
        "reason",
    ]


def _group_csv_fields() -> list[str]:
    return [
        "candidate_group_id",
        "entity_type",
        "decision",
        "confidence",
        "input_group_labels",
        "input_node_ids",
        "requires_human_review",
        "risk_flags",
        "reason",
    ]

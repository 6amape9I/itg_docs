from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable
from urllib import error, parse, request

from kb_rebuild.llm.models import estimate_tokens_from_chars
from kb_rebuild.llm.openrouter_client import parse_api_key_list
from kb_rebuild.llm.providers import LLMProviderError


GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiError(LLMProviderError):
    @property
    def retry_after_seconds(self) -> float | None:
        for header_name, header_value in self.response_headers.items():
            if header_name.lower() != "retry-after":
                continue
            stripped = header_value.strip()
            try:
                return max(0.0, float(stripped))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(stripped)
                except (TypeError, ValueError):
                    return None
                return max(0.0, retry_at.timestamp() - time.time())
        return None


@dataclass(frozen=True)
class GeminiCompletion:
    raw: dict[str, Any]
    content: str
    usage: dict[str, int]
    model: str
    finish_reason: str
    latency_ms: int
    api_key_index: int
    usage_source: str = "api"


class GeminiClient:
    provider_name = "gemini_direct"

    def __init__(
        self,
        api_key: str | None = None,
        api_keys: list[str] | None = None,
        endpoint_base: str = GEMINI_API_BASE_URL,
        timeout_seconds: int | None = None,
        rate_limit_backoff_seconds: float = 120.0,
        max_rate_limit_backoff_seconds: float = 300.0,
        time_fn: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        if api_keys is not None:
            self.api_keys = _dedupe_keys(api_keys)
        else:
            loaded_keys = load_gemini_keys_from_env()
            if loaded_keys:
                self.api_keys = loaded_keys
            elif api_key:
                self.api_keys = [api_key]
            else:
                self.api_keys = []
        self.endpoint_base = endpoint_base.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.rate_limit_backoff_seconds = rate_limit_backoff_seconds
        self.max_rate_limit_backoff_seconds = max_rate_limit_backoff_seconds
        self.time_fn = time_fn or time.monotonic
        self.sleep_fn = sleep_fn or time.sleep

        self._lock = threading.Lock()
        self._next_key_index = 0
        self._cooldown_until = [0.0 for _ in self.api_keys]
        self._disabled = [False for _ in self.api_keys]
        self._key_stats: dict[str, dict[str, Any]] = {
            str(index): {
                "requests": 0,
                "success": 0,
                "errors": 0,
                "http_429": 0,
                "cooldown_events": 0,
                "disabled": False,
            }
            for index in range(len(self.api_keys))
        }

    @property
    def api_keys_count(self) -> int:
        return len(self.api_keys)

    def chat_completion(self, payload: dict[str, Any]) -> GeminiCompletion:
        if not self.api_keys:
            raise GeminiError("GEMINI_KEY_LIST or GEMINI_API_KEY is not set")
        model = str(payload.get("model", "")).strip()
        if not model:
            raise GeminiError("Gemini payload has no model")

        key_index = self._select_key_index()
        api_key = self.api_keys[key_index]
        body_payload = {key: value for key, value in payload.items() if key != "model"}
        body = json.dumps(body_payload, ensure_ascii=False).encode("utf-8")
        endpoint = self._generate_content_url(model)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-goog-api-key": api_key,
        }
        req = request.Request(endpoint, data=body, headers=headers, method="POST")
        started = time.monotonic()
        self._record_key_request(key_index)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            gemini_error = GeminiError(
                f"Gemini HTTP {exc.code} on key_index={key_index}",
                status_code=exc.code,
                response_body=response_body,
                response_headers=dict(exc.headers.items()),
                api_key_index=key_index,
            )
            self.notify_http_error(
                key_index=key_index,
                status_code=exc.code,
                response_headers=dict(exc.headers.items()),
                attempt_index=0,
            )
            raise gemini_error from exc
        except error.URLError as exc:
            self._record_key_error(key_index)
            raise GeminiError(
                f"Gemini request failed on key_index={key_index}: {exc.reason}",
                response_body=str(exc.reason),
                api_key_index=key_index,
            ) from exc
        except TimeoutError as exc:
            self._record_key_error(key_index)
            raise GeminiError(
                f"Gemini request timed out on key_index={key_index}: {exc}",
                response_body=str(exc),
                api_key_index=key_index,
            ) from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            raw = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            self._record_key_error(key_index)
            raise GeminiError(
                f"Gemini returned non-JSON response on key_index={key_index}: {exc}",
                api_key_index=key_index,
            ) from exc
        if not isinstance(raw, dict):
            self._record_key_error(key_index)
            raise GeminiError(f"Gemini response must be an object on key_index={key_index}", api_key_index=key_index)

        completion = _parse_completion(
            raw=raw,
            fallback_model=model,
            latency_ms=latency_ms,
            api_key_index=key_index,
            request_payload=body_payload,
        )
        self._record_key_success(key_index)
        return completion

    def list_models(self) -> dict[str, Any]:
        if not self.api_keys:
            raise GeminiError("GEMINI_KEY_LIST or GEMINI_API_KEY is not set")
        key_index = self._select_key_index()
        api_key = self.api_keys[key_index]
        endpoint = f"{self.endpoint_base}/models?{parse.urlencode({'key': api_key})}"
        req = request.Request(endpoint, headers={"Accept": "application/json"}, method="GET")
        self._record_key_request(key_index)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            gemini_error = GeminiError(
                f"Gemini models.list HTTP {exc.code} on key_index={key_index}",
                status_code=exc.code,
                response_body=response_body,
                response_headers=dict(exc.headers.items()),
                api_key_index=key_index,
            )
            self.notify_http_error(
                key_index=key_index,
                status_code=exc.code,
                response_headers=dict(exc.headers.items()),
                attempt_index=0,
            )
            raise gemini_error from exc
        except error.URLError as exc:
            self._record_key_error(key_index)
            raise GeminiError(
                f"Gemini models.list failed on key_index={key_index}: {exc.reason}",
                response_body=str(exc.reason),
                api_key_index=key_index,
            ) from exc
        try:
            raw = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            self._record_key_error(key_index)
            raise GeminiError(f"Gemini models.list returned non-JSON response: {exc}", api_key_index=key_index) from exc
        if not isinstance(raw, dict):
            self._record_key_error(key_index)
            raise GeminiError("Gemini models.list response must be an object", api_key_index=key_index)
        self._record_key_success(key_index)
        return raw

    def notify_http_error(
        self,
        *,
        key_index: int,
        status_code: int | None,
        response_headers: dict[str, str] | None = None,
        attempt_index: int = 0,
    ) -> None:
        if key_index < 0 or key_index >= len(self.api_keys):
            return
        headers = response_headers or {}
        with self._lock:
            stats = self._key_stats.setdefault(str(key_index), _empty_key_stats())
            stats["errors"] = int(stats.get("errors", 0)) + 1
            if status_code == 429:
                stats["http_429"] = int(stats.get("http_429", 0)) + 1
                stats["cooldown_events"] = int(stats.get("cooldown_events", 0)) + 1
                self._cooldown_until[key_index] = max(
                    self._cooldown_until[key_index],
                    self.time_fn() + self._cooldown_seconds(headers, attempt_index),
                )
            if status_code in {401, 403}:
                self._disabled[key_index] = True
                stats["disabled"] = True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "provider": self.provider_name,
                "keys_count": len(self.api_keys),
                "key_stats": json.loads(json.dumps(self._key_stats, sort_keys=True)),
            }

    def _select_key_index(self) -> int:
        while True:
            with self._lock:
                if not self.api_keys:
                    raise GeminiError("GEMINI_KEY_LIST or GEMINI_API_KEY is not set")
                now = self.time_fn()
                best_wait: float | None = None
                for offset in range(len(self.api_keys)):
                    index = (self._next_key_index + offset) % len(self.api_keys)
                    if self._disabled[index]:
                        continue
                    wait = max(0.0, self._cooldown_until[index] - now)
                    if wait <= 0.0:
                        self._next_key_index = (index + 1) % len(self.api_keys)
                        return index
                    best_wait = wait if best_wait is None else min(best_wait, wait)
                if all(self._disabled):
                    raise GeminiError("all Gemini API keys are disabled")
                wait_for = max(best_wait or 0.01, 0.01)
            self.sleep_fn(wait_for)

    def _generate_content_url(self, model: str) -> str:
        path_model = model.removeprefix("models/")
        return f"{self.endpoint_base}/models/{path_model}:generateContent"

    def _record_key_request(self, key_index: int) -> None:
        with self._lock:
            stats = self._key_stats.setdefault(str(key_index), _empty_key_stats())
            stats["requests"] = int(stats.get("requests", 0)) + 1

    def _record_key_success(self, key_index: int) -> None:
        with self._lock:
            stats = self._key_stats.setdefault(str(key_index), _empty_key_stats())
            stats["success"] = int(stats.get("success", 0)) + 1

    def _record_key_error(self, key_index: int) -> None:
        with self._lock:
            stats = self._key_stats.setdefault(str(key_index), _empty_key_stats())
            stats["errors"] = int(stats.get("errors", 0)) + 1

    def _cooldown_seconds(self, response_headers: dict[str, str], attempt_index: int) -> float:
        retry_after = _retry_after_seconds(response_headers)
        backoff = self.rate_limit_backoff_seconds * (2 ** max(0, attempt_index))
        cooldown = max(backoff, retry_after or 0.0)
        return min(cooldown, self.max_rate_limit_backoff_seconds)


def load_dotenv_gemini_keys(env_path: Path) -> None:
    if not env_path.exists():
        return
    key_list_value = ""
    single_key_value = ""
    with env_path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key == "GEMINI_KEY_LIST" and value:
                key_list_value = value
            elif key == "GEMINI_API_KEY" and value:
                single_key_value = value
    if key_list_value and not os.environ.get("GEMINI_KEY_LIST"):
        os.environ["GEMINI_KEY_LIST"] = key_list_value
    if single_key_value and not os.environ.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = single_key_value


def load_gemini_keys_from_env() -> list[str]:
    key_list = parse_gemini_key_list(os.environ.get("GEMINI_KEY_LIST", ""))
    if key_list:
        return key_list
    single = os.environ.get("GEMINI_API_KEY", "").strip()
    return [single] if single else []


def parse_gemini_key_list(raw_value: str) -> list[str]:
    return parse_api_key_list(raw_value)


def _parse_completion(
    *,
    raw: dict[str, Any],
    fallback_model: str,
    latency_ms: int,
    api_key_index: int,
    request_payload: dict[str, Any],
) -> GeminiCompletion:
    candidates = raw.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeminiError("Gemini response has no candidates", api_key_index=api_key_index)
    first = candidates[0]
    if not isinstance(first, dict):
        raise GeminiError("Gemini candidate must be an object", api_key_index=api_key_index)
    content = first.get("content")
    if not isinstance(content, dict):
        raise GeminiError("Gemini candidate.content must be an object", api_key_index=api_key_index)
    parts = content.get("parts")
    text_parts: list[str] = []
    if isinstance(parts, list):
        for item in parts:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
    content_text = "\n".join(text_parts)
    usage, usage_source = _extract_usage(raw.get("usageMetadata"), request_payload, content_text)
    return GeminiCompletion(
        raw=raw,
        content=content_text,
        usage=usage,
        model=str(raw.get("modelVersion") or f"models/{fallback_model.removeprefix('models/')}"),
        finish_reason=str(first.get("finishReason") or ""),
        latency_ms=latency_ms,
        api_key_index=api_key_index,
        usage_source=usage_source,
    )


def _extract_usage(
    raw_usage: Any,
    request_payload: dict[str, Any],
    content_text: str,
) -> tuple[dict[str, int], str]:
    if isinstance(raw_usage, dict):
        return (
            {
                "prompt_tokens": _safe_int(raw_usage.get("promptTokenCount", 0)),
                "completion_tokens": _safe_int(raw_usage.get("candidatesTokenCount", 0)),
                "reasoning_tokens": _safe_int(raw_usage.get("thoughtsTokenCount", 0)),
            },
            "api",
        )
    prompt_chars = _payload_text_chars(request_payload)
    return (
        {
            "prompt_tokens": estimate_tokens_from_chars(prompt_chars),
            "completion_tokens": estimate_tokens_from_chars(len(content_text)),
            "reasoning_tokens": 0,
        },
        "estimated",
    )


def _payload_text_chars(payload: dict[str, Any]) -> int:
    total = 0
    contents = payload.get("contents")
    if not isinstance(contents, list):
        return total
    for content in contents:
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                total += len(part["text"])
    return total


def _retry_after_seconds(response_headers: dict[str, str]) -> float | None:
    for header_name, header_value in response_headers.items():
        if header_name.lower() != "retry-after":
            continue
        stripped = header_value.strip()
        try:
            return max(0.0, float(stripped))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(stripped)
            except (TypeError, ValueError):
                return None
            return max(0.0, retry_at.timestamp() - time.time())
    return None


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _dedupe_keys(keys: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if not isinstance(key, str):
            continue
        stripped = key.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        result.append(stripped)
    return result


def _empty_key_stats() -> dict[str, Any]:
    return {
        "requests": 0,
        "success": 0,
        "errors": 0,
        "http_429": 0,
        "cooldown_events": 0,
        "disabled": False,
    }

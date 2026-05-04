from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib import error, request


OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str = "",
        response_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.response_headers = response_headers or {}

    @property
    def retryable(self) -> bool:
        if "OPENROUTER_API_KEY is not set" in str(self):
            return False
        return self.status_code is None or self.status_code == 429 or self.status_code >= 500

    @property
    def looks_like_structured_output_error(self) -> bool:
        body = self.response_body.lower()
        needles = ("response_format", "json_schema", "structured", "require_parameters", "unsupported parameter")
        return self.status_code == 400 and any(needle in body for needle in needles)

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
class OpenRouterCompletion:
    raw: dict[str, Any]
    content: str
    usage: dict[str, int]
    model: str
    finish_reason: str
    latency_ms: int


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None = None,
        api_keys: list[str] | None = None,
        use_api_key_list: bool = False,
        endpoint: str = OPENROUTER_CHAT_COMPLETIONS_URL,
        timeout_seconds: int = 120,
    ) -> None:
        if api_keys is not None:
            self.api_keys = _dedupe_keys(api_keys)
        elif use_api_key_list:
            self.api_keys = parse_api_key_list(os.environ.get("OPENROUTER_API_KEY_LIST", ""))
        else:
            single_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
            self.api_keys = [single_key] if single_key else []
        if not self.api_keys and api_key:
            self.api_keys = [api_key]
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self._next_key_index = 0

    def chat_completion(self, payload: dict[str, Any]) -> OpenRouterCompletion:
        api_key = self._next_api_key()
        if not api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is not set")

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        req = request.Request(self.endpoint, data=body, headers=headers, method="POST")
        started = time.monotonic()
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            raise OpenRouterError(
                f"OpenRouter HTTP {exc.code}",
                status_code=exc.code,
                response_body=response_body,
                response_headers=dict(exc.headers.items()),
            ) from exc
        except error.URLError as exc:
            raise OpenRouterError(f"OpenRouter request failed: {exc.reason}", response_body=str(exc.reason)) from exc
        except TimeoutError as exc:
            raise OpenRouterError(f"OpenRouter request timed out: {exc}", response_body=str(exc)) from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            raw = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise OpenRouterError(f"OpenRouter returned non-JSON response: {exc}") from exc

        if not isinstance(raw, dict):
            raise OpenRouterError("OpenRouter response must be a JSON object")
        return _parse_completion(raw, fallback_model=str(payload.get("model", "")), latency_ms=latency_ms)

    @property
    def api_keys_count(self) -> int:
        return len(self.api_keys)

    def _next_api_key(self) -> str:
        if not self.api_keys:
            return ""
        key = self.api_keys[self._next_key_index % len(self.api_keys)]
        self._next_key_index += 1
        return key


def load_dotenv_openrouter_key(env_path: Path) -> None:
    if not env_path.exists():
        return
    fallback_value = ""
    key_list_value = ""
    with env_path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key == "OPENROUTER_API_KEY" and value and not os.environ.get("OPENROUTER_API_KEY"):
                os.environ["OPENROUTER_API_KEY"] = value
                continue
            if key == "OPEN_ROUTER_KEY" and value:
                fallback_value = value
            if key == "OPENROUTER_API_KEY_LIST" and value:
                key_list_value = value
        if fallback_value and not os.environ.get("OPENROUTER_API_KEY"):
            os.environ["OPENROUTER_API_KEY"] = fallback_value
        if key_list_value and not os.environ.get("OPENROUTER_API_KEY_LIST"):
            os.environ["OPENROUTER_API_KEY_LIST"] = key_list_value


def parse_api_key_list(raw_value: str) -> list[str]:
    if not raw_value:
        return []
    stripped = raw_value.strip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return _dedupe_keys(str(item).strip() for item in parsed if str(item).strip())

    normalized = stripped.replace("\\n", "\n").replace(";", ",")
    parts: list[str] = []
    for chunk in normalized.splitlines():
        parts.extend(chunk.split(","))
    return _dedupe_keys(part.strip().strip('"').strip("'") for part in parts if part.strip())


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


def _parse_completion(raw: dict[str, Any], fallback_model: str, latency_ms: int) -> OpenRouterCompletion:
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenRouterError("OpenRouter response has no choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise OpenRouterError("OpenRouter choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise OpenRouterError("OpenRouter choice.message must be an object")
    content = message.get("content")
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        content_text = "\n".join(text_parts)
    elif isinstance(content, str):
        content_text = content
    else:
        content_text = ""

    return OpenRouterCompletion(
        raw=raw,
        content=content_text,
        usage=_extract_usage(raw.get("usage")),
        model=str(raw.get("model") or fallback_model),
        finish_reason=str(first_choice.get("finish_reason") or ""),
        latency_ms=latency_ms,
    )


def _extract_usage(raw_usage: Any) -> dict[str, int]:
    if not isinstance(raw_usage, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
    reasoning_tokens = raw_usage.get("reasoning_tokens", 0)
    completion_details = raw_usage.get("completion_tokens_details")
    if isinstance(completion_details, dict):
        reasoning_tokens = completion_details.get("reasoning_tokens", reasoning_tokens)
    return {
        "prompt_tokens": _safe_int(raw_usage.get("prompt_tokens", 0)),
        "completion_tokens": _safe_int(raw_usage.get("completion_tokens", 0)),
        "reasoning_tokens": _safe_int(reasoning_tokens),
    }


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0

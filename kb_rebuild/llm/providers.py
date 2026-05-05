from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMCompletion:
    raw: dict[str, Any]
    content: str
    usage: dict[str, int]
    model: str
    finish_reason: str
    latency_ms: int
    api_key_index: int | None = None
    usage_source: str = "api"


class LLMClientProtocol(Protocol):
    @property
    def provider_name(self) -> str:
        ...

    def chat_completion(self, payload: dict[str, Any]) -> LLMCompletion:
        ...


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str = "",
        response_headers: dict[str, str] | None = None,
        api_key_index: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.response_headers = response_headers or {}
        self.api_key_index = api_key_index

    @property
    def retryable(self) -> bool:
        return self.status_code is None or self.status_code == 429 or self.status_code >= 500

    @property
    def looks_like_structured_output_error(self) -> bool:
        body = self.response_body.lower()
        needles = (
            "response_format",
            "json_schema",
            "responsejsonschema",
            "response_json_schema",
            "structured",
            "generationconfig",
            "unsupported parameter",
        )
        return self.status_code == 400 and any(needle in body for needle in needles)

    @property
    def retry_after_seconds(self) -> float | None:
        return None


def completion_api_key_index(completion: Any) -> int | None:
    value = getattr(completion, "api_key_index", None)
    return value if isinstance(value, int) else None


def completion_usage_source(completion: Any) -> str:
    value = getattr(completion, "usage_source", None)
    return value if isinstance(value, str) and value else "api"


def client_provider_name(client: Any, configured_provider: str) -> str:
    value = getattr(client, "provider_name", None)
    return value if isinstance(value, str) and value else configured_provider


def client_key_stats(client: Any) -> dict[str, Any]:
    snapshot = getattr(client, "snapshot", None)
    if not callable(snapshot):
        return {}
    value = snapshot()
    if not isinstance(value, dict):
        return {}
    key_stats = value.get("key_stats")
    return key_stats if isinstance(key_stats, dict) else {}


def client_keys_count(client: Any) -> int:
    value = getattr(client, "api_keys_count", None)
    return value if isinstance(value, int) else 0

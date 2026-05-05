from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class LLMCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def path_for_key(self, cache_key: str) -> Path:
        return self.cache_dir / f"{cache_key}.json"

    def get(self, cache_key: str) -> dict[str, Any] | None:
        path = self.path_for_key(cache_key)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            value = json.load(fh)
        if not isinstance(value, dict):
            raise ValueError(f"cache record must be object: {path}")
        return value

    def set(self, cache_key: str, record: dict[str, Any]) -> None:
        path = self.path_for_key(cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        tmp_path.replace(path)


def build_cache_key(
    *,
    provider: str = "openrouter",
    model: str,
    prompt_version: str,
    schema_version: str,
    doc_id: str,
    input_hash: str,
    request_params: dict[str, Any],
) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "doc_id": doc_id,
        "input_hash": input_hash,
        "request_params": request_params,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from kb_rebuild.io.jsonl import read_jsonl


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return read_json(path)


def load_jsonl_by_key(path: Path, key: str) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(path)
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        by_key[value] = row
    return by_key


def load_canonical_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return [dict(row) for row in reader]


def require_paths(paths: dict[str, Path]) -> None:
    missing = [f"{name}: {path}" for name, path in paths.items() if not path.exists()]
    if missing:
        raise ValueError("A5 input paths missing: " + "; ".join(missing))


def assert_report_passed(report: dict[str, Any], *, name: str) -> None:
    quality = report.get("quality") if isinstance(report.get("quality"), dict) else {}
    if quality.get("passed") is not True:
        raise ValueError(f"{name} quality gate is not passed")


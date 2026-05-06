from __future__ import annotations

import json
import re
from typing import Any

from kb_rebuild.articles.a2.models import DECISIONS, FACT_TYPES, IMPORTANCE_VALUES, RELEVANCE_VALUES


A2_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["batch_id", "task_results"],
    "properties": {
        "batch_id": {"type": "string"},
        "task_results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["task_id", "tag_id", "decision", "relevance", "confidence", "evidence_items", "reason"],
                "properties": {
                    "task_id": {"type": "string"},
                    "tag_id": {"type": "string"},
                    "decision": {"type": "string", "enum": sorted(DECISIONS)},
                    "relevance": {"type": "string", "enum": sorted(RELEVANCE_VALUES)},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence_items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["fact_type", "section_hint", "claim", "quote", "importance", "confidence"],
                            "properties": {
                                "fact_type": {"type": "string", "enum": sorted(FACT_TYPES)},
                                "section_hint": {"type": "string"},
                                "claim": {"type": "string"},
                                "quote": {"type": "string"},
                                "importance": {"type": "string", "enum": sorted(IMPORTANCE_VALUES)},
                                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            },
                        },
                    },
                    "reason": {"type": "string"},
                },
            },
        },
    },
}


def parse_response_json(content: str) -> tuple[dict[str, Any] | None, list[str]]:
    text = content.strip()
    if text.startswith("```"):
        text = _strip_code_fence(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"invalid_json: {exc}"]
    if not isinstance(parsed, dict):
        return None, ["response root must be an object"]
    return parsed, []


def validate_batch_response(parsed: dict[str, Any], batch: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    expected_batch_id = str(batch.get("batch_id") or "")
    if parsed.get("batch_id") != expected_batch_id:
        errors.append(f"batch_id mismatch: expected {expected_batch_id}, got {parsed.get('batch_id')}")

    task_results = parsed.get("task_results")
    if not isinstance(task_results, list):
        return None, errors + ["task_results must be a list"]

    tasks_by_id = {str(task.get("task_id") or ""): task for task in batch.get("tasks", [])}
    expected_task_ids = set(tasks_by_id)
    seen_task_ids: set[str] = set()
    normalized_results: list[dict[str, Any]] = []

    for index, result in enumerate(task_results):
        if not isinstance(result, dict):
            errors.append(f"task_results[{index}] must be an object")
            continue
        task_id = str(result.get("task_id") or "")
        if task_id not in expected_task_ids:
            errors.append(f"unknown task_id: {task_id}")
            continue
        if task_id in seen_task_ids:
            errors.append(f"duplicate task_id: {task_id}")
            continue
        seen_task_ids.add(task_id)
        task = tasks_by_id[task_id]
        item_errors = _validate_task_result(result, task)
        if item_errors:
            errors.extend(f"{task_id}: {error}" for error in item_errors)
            continue
        normalized_results.append(_normalized_task_result(result))

    missing = sorted(expected_task_ids - seen_task_ids)
    if missing:
        errors.append("missing task_id results: " + ", ".join(missing[:20]))
    if errors:
        return None, errors
    return {"batch_id": expected_batch_id, "task_results": normalized_results}, []


def _validate_task_result(result: dict[str, Any], task: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if str(result.get("tag_id") or "") != str(task.get("tag_id") or ""):
        errors.append("tag_id mismatch")
    decision = str(result.get("decision") or "")
    if decision not in DECISIONS:
        errors.append(f"invalid decision: {decision}")
    relevance = str(result.get("relevance") or "")
    if relevance not in RELEVANCE_VALUES:
        errors.append(f"invalid relevance: {relevance}")
    confidence = result.get("confidence")
    if not _valid_score(confidence):
        errors.append("confidence must be in [0,1]")
    evidence_items = result.get("evidence_items")
    if not isinstance(evidence_items, list):
        errors.append("evidence_items must be a list")
        return errors
    if decision == "evidence_extracted" and not evidence_items:
        errors.append("evidence_extracted requires evidence_items")
    if decision != "evidence_extracted" and evidence_items:
        errors.append(f"{decision} must not include evidence_items")
    for index, item in enumerate(evidence_items):
        if not isinstance(item, dict):
            errors.append(f"evidence_items[{index}] must be an object")
            continue
        errors.extend(f"evidence_items[{index}]: {error}" for error in _validate_evidence_item(item))
    if not isinstance(result.get("reason", ""), str):
        errors.append("reason must be a string")
    return errors


def _validate_evidence_item(item: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    fact_type = str(item.get("fact_type") or "")
    if fact_type not in FACT_TYPES:
        errors.append(f"invalid fact_type: {fact_type}")
    importance = str(item.get("importance") or "")
    if importance not in IMPORTANCE_VALUES:
        errors.append(f"invalid importance: {importance}")
    if not str(item.get("claim") or "").strip():
        errors.append("claim must be non-empty")
    if len(str(item.get("claim") or "")) > 700:
        errors.append("claim is too long")
    if not str(item.get("quote") or "").strip():
        errors.append("quote must be non-empty")
    if not _valid_score(item.get("confidence")):
        errors.append("confidence must be in [0,1]")
    return errors


def _normalized_task_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": str(result.get("task_id") or ""),
        "tag_id": str(result.get("tag_id") or ""),
        "decision": str(result.get("decision") or ""),
        "relevance": str(result.get("relevance") or ""),
        "confidence": float(result.get("confidence") or 0.0),
        "evidence_items": [_normalized_evidence_item(item) for item in result.get("evidence_items", [])],
        "reason": str(result.get("reason") or ""),
    }


def _normalized_evidence_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "fact_type": str(item.get("fact_type") or ""),
        "section_hint": str(item.get("section_hint") or ""),
        "claim": str(item.get("claim") or "").strip(),
        "quote": str(item.get("quote") or "").strip(),
        "importance": str(item.get("importance") or ""),
        "confidence": float(item.get("confidence") or 0.0),
    }


def _valid_score(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return 0.0 <= float(value) <= 1.0


def _strip_code_fence(text: str) -> str:
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


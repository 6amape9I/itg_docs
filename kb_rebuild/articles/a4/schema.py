from __future__ import annotations

import json
import re
from typing import Any

from kb_rebuild.articles.a4.models import ARTICLE_STATUSES
from kb_rebuild.articles.a4.validation import validate_article_response


A4_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["batch_id", "articles"],
    "properties": {
        "batch_id": {"type": "string"},
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "task_id",
                    "tag_id",
                    "article_status",
                    "title",
                    "summary",
                    "content",
                    "used_fact_group_ids",
                    "unused_fact_group_ids",
                    "needs_review_before_publication",
                    "review_reasons",
                    "confidence",
                    "reason",
                ],
                "properties": {
                    "task_id": {"type": "string"},
                    "tag_id": {"type": "string"},
                    "article_status": {"type": "string", "enum": sorted(ARTICLE_STATUSES)},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "content": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["time", "version", "blocks"],
                        "properties": {
                            "time": {"type": "integer"},
                            "version": {"type": "string"},
                            "blocks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["id", "type", "data", "metadata"],
                                    "properties": {
                                        "id": {"type": "string"},
                                        "type": {"type": "string", "enum": ["header", "paragraph", "list", "table"]},
                                        "data": {
                                            "type": "object",
                                            "additionalProperties": True,
                                            "properties": {
                                                "text": {"type": "string"},
                                                "level": {"type": "integer"},
                                                "style": {"type": "string"},
                                                "items": {"type": "array", "items": {"type": "string"}},
                                                "content": {
                                                    "type": "array",
                                                    "items": {"type": "array", "items": {"type": "string"}},
                                                },
                                            },
                                        },
                                        "metadata": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "required": ["source_fact_group_ids"],
                                            "properties": {
                                                "source_fact_group_ids": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                }
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "used_fact_group_ids": {"type": "array", "items": {"type": "string"}},
                    "unused_fact_group_ids": {"type": "array", "items": {"type": "string"}},
                    "needs_review_before_publication": {"type": "boolean"},
                    "review_reasons": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
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

    articles = parsed.get("articles")
    if not isinstance(articles, list):
        return None, errors + ["articles must be a list"]

    tasks_by_id = {str(task.get("task_id") or ""): task for task in batch.get("tasks", [])}
    expected_task_ids = set(tasks_by_id)
    seen_task_ids: set[str] = set()
    normalized_articles: list[dict[str, Any]] = []

    for index, article in enumerate(articles):
        if not isinstance(article, dict):
            errors.append(f"articles[{index}] must be an object")
            continue
        task_id = str(article.get("task_id") or "")
        if task_id not in expected_task_ids:
            errors.append(f"unknown task_id: {task_id}")
            continue
        if task_id in seen_task_ids:
            errors.append(f"duplicate task_id: {task_id}")
            continue
        seen_task_ids.add(task_id)
        normalized, item_errors = validate_article_response(article, tasks_by_id[task_id])
        if item_errors:
            errors.extend(f"{task_id}: {error}" for error in item_errors)
            continue
        if normalized is not None:
            normalized["task_id"] = task_id
            normalized_articles.append(normalized)

    missing = sorted(expected_task_ids - seen_task_ids)
    if missing:
        errors.append("missing task_id articles: " + ", ".join(missing[:20]))
    if errors:
        return None, errors
    return {"batch_id": expected_batch_id, "articles": normalized_articles}, []


def _strip_code_fence(text: str) -> str:
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text

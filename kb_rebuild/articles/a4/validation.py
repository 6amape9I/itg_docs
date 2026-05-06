from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from kb_rebuild.articles.a4.models import ARTICLE_STATUSES


CONTENT_BLOCK_TYPES = {"header", "paragraph", "list", "table"}


def validate_article_response(article: dict[str, Any], task: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    expected_tag_id = str(task.get("tag_id") or "")
    if str(article.get("tag_id") or "") != expected_tag_id:
        errors.append("tag_id mismatch")

    status = str(article.get("article_status") or "")
    if status not in ARTICLE_STATUSES:
        errors.append(f"invalid article_status: {status}")
    if str(task.get("a4_strategy") or "") == "compile_with_review_flag" and status != "compiled_with_review_flag":
        errors.append("compile_with_review_flag requires article_status=compiled_with_review_flag")

    title = str(article.get("title") or "").strip()
    if not title:
        errors.append("title must be non-empty")
    canonical_title = str(task.get("canonical_tag_ru") or "").strip()
    if title and canonical_title and not _title_is_close(title, canonical_title):
        errors.append("title must match canonical_tag_ru or be close")
    summary = str(article.get("summary") or "").strip()
    if not summary:
        errors.append("summary must be non-empty")

    confidence = article.get("confidence")
    if not _valid_score(confidence):
        errors.append("confidence must be in [0,1]")

    task_review = bool(task.get("needs_review_before_publication"))
    response_review = bool(article.get("needs_review_before_publication"))
    if task_review and not response_review:
        errors.append("needs_review_before_publication must preserve true input flag")
    task_reasons = _string_list(task.get("review_reasons"))
    response_reasons = _string_list(article.get("review_reasons"))
    missing_reasons = sorted(set(task_reasons) - set(response_reasons))
    if missing_reasons:
        errors.append("review_reasons must preserve input reasons: " + ", ".join(missing_reasons[:20]))

    allowed_fact_ids = {str(item) for item in task.get("fact_group_ids", []) if str(item)}
    used_ids = _string_list(article.get("used_fact_group_ids"))
    unused_ids = _string_list(article.get("unused_fact_group_ids"))
    unknown_used = sorted(set(used_ids) - allowed_fact_ids)
    unknown_unused = sorted(set(unused_ids) - allowed_fact_ids)
    if unknown_used:
        errors.append("used_fact_group_ids contain unknown ids: " + ", ".join(unknown_used[:20]))
    if unknown_unused:
        errors.append("unused_fact_group_ids contain unknown ids: " + ", ".join(unknown_unused[:20]))

    content, content_errors = validate_editorjs_content(article.get("content"), allowed_fact_ids=allowed_fact_ids)
    errors.extend(content_errors)
    cited_ids = sorted(collect_editorjs_source_fact_group_ids(content or {}))
    missing_used = sorted(set(cited_ids) - set(used_ids))
    if missing_used:
        errors.append("used_fact_group_ids must include cited ids: " + ", ".join(missing_used[:20]))

    if errors:
        return None, errors

    normalized = {
        "task_id": str(article.get("task_id") or ""),
        "tag_id": expected_tag_id,
        "article_status": status,
        "title": title,
        "summary": summary,
        "content": content,
        "used_fact_group_ids": _unique_strings(used_ids),
        "unused_fact_group_ids": _unique_strings(unused_ids),
        "needs_review_before_publication": response_review,
        "review_reasons": _unique_strings(response_reasons),
        "confidence": float(confidence or 0.0),
        "reason": str(article.get("reason") or "").strip(),
    }
    return normalized, []


def validate_editorjs_content(value: Any, *, allowed_fact_ids: set[str]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return None, ["content must be an object"]
    blocks = value.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return None, ["content.blocks must be a non-empty list"]

    normalized_blocks: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            errors.append(f"content.blocks[{index}] must be an object")
            continue
        block_type = str(block.get("type") or "")
        if block_type not in CONTENT_BLOCK_TYPES:
            errors.append(f"content.blocks[{index}] has unsupported type: {block_type}")
            continue
        block_id = str(block.get("id") or f"block_{index + 1:03d}").strip()
        if not block_id:
            errors.append(f"content.blocks[{index}].id must be non-empty")
        data = block.get("data")
        if not isinstance(data, dict):
            errors.append(f"content.blocks[{index}].data must be an object")
            continue
        metadata = block.get("metadata")
        if not isinstance(metadata, dict):
            errors.append(f"content.blocks[{index}].metadata must be an object")
            continue
        source_ids = _string_list(metadata.get("source_fact_group_ids"))
        unknown_source_ids = sorted(set(source_ids) - allowed_fact_ids)
        if unknown_source_ids:
            errors.append(f"content.blocks[{index}] cites unknown fact ids: " + ", ".join(unknown_source_ids[:20]))
        if index == 0 and block_type != "header":
            errors.append("content.blocks[0] must be header")
        if block_type != "header" and not source_ids:
            errors.append(f"content.blocks[{index}] must cite source_fact_group_ids")
        errors.extend(f"content.blocks[{index}]: {error}" for error in _validate_block_data(block_type, data))
        normalized_blocks.append(
            {
                "id": block_id,
                "type": block_type,
                "data": data,
                "metadata": {"source_fact_group_ids": _unique_strings(source_ids)},
            }
        )

    if errors:
        return None, errors

    return {
        "time": int(value.get("time") or 0),
        "version": str(value.get("version") or "2.28.0"),
        "blocks": normalized_blocks,
    }, []


def collect_editorjs_source_fact_group_ids(content: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    blocks = content.get("blocks") if isinstance(content, dict) else []
    if not isinstance(blocks, list):
        return ids
    for block in blocks:
        if not isinstance(block, dict):
            continue
        metadata = block.get("metadata")
        if not isinstance(metadata, dict):
            continue
        ids.update(_string_list(metadata.get("source_fact_group_ids")))
    return ids


def article_quality_issues(article: dict[str, Any], task: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    core_ids = set(_string_list(task.get("core_fact_group_ids")))
    used_ids = set(_string_list(article.get("used_fact_group_ids")))
    used_core = used_ids.intersection(core_ids)
    if len(core_ids) >= 10 and len(used_core) / len(core_ids) < 0.2:
        issues.append(_issue(article, task, "low_core_fact_group_usage", f"used_core={len(used_core)} available_core={len(core_ids)}"))
    if core_ids and not used_core:
        issues.append(_issue(article, task, "no_core_fact_groups_used", f"core_available={len(core_ids)}"))
    return issues


def _validate_block_data(block_type: str, data: dict[str, Any]) -> list[str]:
    if block_type == "header":
        text = str(data.get("text") or "").strip()
        if not text:
            return ["header.text must be non-empty"]
        level = data.get("level", 2)
        if isinstance(level, bool) or not isinstance(level, int) or level < 1 or level > 4:
            return ["header.level must be an integer from 1 to 4"]
        return []
    if block_type == "paragraph":
        return [] if str(data.get("text") or "").strip() else ["paragraph.text must be non-empty"]
    if block_type == "list":
        items = data.get("items")
        if not isinstance(items, list) or not items:
            return ["list.items must be a non-empty list"]
        if not any(_list_item_text(item) for item in items):
            return ["list.items must contain non-empty text"]
        return []
    if block_type == "table":
        content = data.get("content")
        if not isinstance(content, list) or not content:
            return ["table.content must be a non-empty list"]
        has_cell = False
        for row in content:
            if not isinstance(row, list):
                return ["table.content rows must be lists"]
            if any(str(cell or "").strip() for cell in row):
                has_cell = True
        if not has_cell:
            return ["table.content must contain non-empty cells"]
    return []


def _issue(article: dict[str, Any], task: dict[str, Any], issue_type: str, reason: str) -> dict[str, Any]:
    return {
        "task_id": article.get("task_id") or task.get("task_id") or "",
        "tag_id": article.get("tag_id") or task.get("tag_id") or "",
        "canonical_tag_ru": task.get("canonical_tag_ru") or article.get("title") or "",
        "entity_type": task.get("entity_type") or "",
        "issue_type": issue_type,
        "severity": "warning",
        "reason": reason,
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    stripped = str(value).strip()
    return [stripped] if stripped else []


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _valid_score(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return 0.0 <= float(value) <= 1.0


def _list_item_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("content") or value.get("text") or "").strip()
    return str(value or "").strip()


def _title_is_close(title: str, canonical: str) -> bool:
    left = _normalize_title(title)
    right = _normalize_title(canonical)
    if not left or not right:
        return True
    if left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.74


def _normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-zа-яё]+", " ", value.lower())).strip()

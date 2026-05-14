from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_EDITORJS_VERSION = "2.28.0"


def validate_editorjs_content(value: Any) -> tuple[dict[str, Any] | None, list[str]]:
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
        block_type = str(block.get("type") or "").strip()
        if not block_type:
            errors.append(f"content.blocks[{index}].type must be non-empty")
            continue
        data = block.get("data")
        if not isinstance(data, dict):
            errors.append(f"content.blocks[{index}].data must be an object")
            continue
        block_errors = _validate_block_data(block_type, data)
        errors.extend(f"content.blocks[{index}]: {error}" for error in block_errors)
        normalized_blocks.append(_normalize_block(block, block_type, data))

    if errors:
        return None, errors

    return {
        "time": _int_or_zero(value.get("time")),
        "version": str(value.get("version") or DEFAULT_EDITORJS_VERSION),
        "blocks": normalized_blocks,
    }, []


def safe_review_stub_content(canonical_tag_ru: str) -> dict[str, Any]:
    title = str(canonical_tag_ru or "Требуется проверка").strip() or "Требуется проверка"
    return {
        "time": 0,
        "version": DEFAULT_EDITORJS_VERSION,
        "blocks": [
            {"type": "header", "data": {"level": 2, "text": title}},
            {
                "type": "paragraph",
                "data": {
                    "text": (
                        "Страница создана как служебная review-заглушка. "
                        "Исходный контент не прошел проверку формата Editor.js."
                    )
                },
            },
        ],
    }


def content_blocks_count(content: dict[str, Any]) -> int:
    blocks = content.get("blocks")
    return len(blocks) if isinstance(blocks, list) else 0


def content_excerpt(content: dict[str, Any], *, max_chars: int = 260) -> str:
    chunks: list[str] = []
    blocks = content.get("blocks")
    if not isinstance(blocks, list):
        return ""
    for block in blocks:
        if not isinstance(block, dict):
            continue
        text = _block_text(str(block.get("type") or ""), block.get("data"))
        if text:
            chunks.append(text)
        if len(" ".join(chunks)) >= max_chars:
            break
    return " ".join(chunks)[:max_chars]


def _normalize_block(block: dict[str, Any], block_type: str, data: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(block)
    normalized["type"] = block_type
    normalized["data"] = deepcopy(data)
    return normalized


def _validate_block_data(block_type: str, data: dict[str, Any]) -> list[str]:
    if block_type == "header":
        if not str(data.get("text") or "").strip():
            return ["header.text must be non-empty"]
        return []
    if block_type == "paragraph":
        if not str(data.get("text") or "").strip():
            return ["paragraph.text must be non-empty"]
        return []
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


def _block_text(block_type: str, data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    if block_type in {"header", "paragraph"}:
        return str(data.get("text") or "").strip()
    if block_type == "list":
        items = data.get("items")
        if isinstance(items, list):
            return " ".join(text for item in items if (text := _list_item_text(item)))
    if block_type == "table":
        rows = data.get("content")
        if isinstance(rows, list):
            cells: list[str] = []
            for row in rows:
                if isinstance(row, list):
                    cells.extend(str(cell or "").strip() for cell in row if str(cell or "").strip())
            return " ".join(cells)
    return ""


def _list_item_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("content", "text"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _int_or_zero(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


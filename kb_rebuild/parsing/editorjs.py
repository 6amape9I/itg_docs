from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from kb_rebuild.schemas.parsed_documents import DocumentBlockRecord


TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
RECURSIVE_TEXT_KEYS = (
    "text",
    "caption",
    "title",
    "message",
    "items",
    "content",
    "data",
    "description",
)


@dataclass(frozen=True)
class EditorJSParseResult:
    parse_status: str
    parse_errors: list[str]
    clean_text: str
    blocks: list[DocumentBlockRecord]
    block_types: dict[str, int]
    block_parse_statuses: dict[str, int]
    empty_or_unhandled_blocks_count: int


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def hash_json(value: Any) -> str:
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        payload = repr(value)
    return content_sha256(payload)


def strip_html_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = WHITESPACE_RE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_plain_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = WHITESPACE_RE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_editorjs_content(raw_content: str, doc_id: str) -> EditorJSParseResult:
    raw_content = "" if raw_content is None else str(raw_content)
    if not raw_content.strip():
        return EditorJSParseResult(
            parse_status="empty",
            parse_errors=["empty_content"],
            clean_text="",
            blocks=[],
            block_types={},
            block_parse_statuses={},
            empty_or_unhandled_blocks_count=0,
        )

    parsed, errors = _load_editorjs_json(raw_content)
    if parsed is None:
        return EditorJSParseResult(
            parse_status="failed",
            parse_errors=errors,
            clean_text="",
            blocks=[],
            block_types={},
            block_parse_statuses={},
            empty_or_unhandled_blocks_count=0,
        )

    blocks_input, container_errors = _extract_blocks(parsed)
    errors.extend(container_errors)

    if not blocks_input:
        fallback_text = "\n".join(_extract_recursive_text(parsed))
        if fallback_text:
            synthetic_block = {"type": "unknown_document", "data": {"text": fallback_text}}
            blocks_input = [synthetic_block]
            errors.append("editorjs_blocks_missing_used_recursive_text")
        else:
            status = "partial" if errors else "empty"
            if not errors:
                errors.append("editorjs_blocks_empty")
            return EditorJSParseResult(
                parse_status=status,
                parse_errors=errors,
                clean_text="",
                blocks=[],
                block_types={},
                block_parse_statuses={},
                empty_or_unhandled_blocks_count=0,
            )

    parsed_blocks: list[DocumentBlockRecord] = []
    block_texts: list[str] = []
    block_types: Counter[str] = Counter()
    block_statuses: Counter[str] = Counter()
    empty_or_unhandled = 0

    for block_index, raw_block in enumerate(blocks_input):
        block = _parse_block(raw_block, doc_id=doc_id, block_index=block_index)
        parsed_blocks.append(block)
        block_types[block.block_type] += 1
        block_statuses[block.parse_status] += 1
        if block.parse_status == "empty_or_unhandled_block":
            empty_or_unhandled += 1
            errors.append(f"block_{block.block_id}_empty_or_unhandled:{block.block_type}")
        if block.text:
            block_texts.append(block.text)

    clean_text = "\n\n".join(block_texts).strip()
    if clean_text and errors:
        parse_status = "partial"
    elif clean_text:
        parse_status = "ok"
    elif parsed_blocks:
        parse_status = "empty"
    else:
        parse_status = "failed"

    return EditorJSParseResult(
        parse_status=parse_status,
        parse_errors=errors,
        clean_text=clean_text,
        blocks=parsed_blocks,
        block_types=dict(sorted(block_types.items())),
        block_parse_statuses=dict(sorted(block_statuses.items())),
        empty_or_unhandled_blocks_count=empty_or_unhandled,
    )


def _load_editorjs_json(raw_content: str) -> tuple[Any | None, list[str]]:
    errors: list[str] = []
    try:
        parsed: Any = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        return None, [f"invalid_json:{exc.msg}"]

    for _ in range(2):
        if isinstance(parsed, str) and parsed.strip().startswith(("{", "[")):
            try:
                parsed = json.loads(parsed)
            except json.JSONDecodeError as exc:
                errors.append(f"nested_json_string_invalid:{exc.msg}")
                break
        else:
            break
    return parsed, errors


def _extract_blocks(parsed: Any) -> tuple[list[Any], list[str]]:
    if isinstance(parsed, dict):
        blocks = parsed.get("blocks")
        if isinstance(blocks, list):
            return blocks, []
        if parsed.get("type") or parsed.get("data"):
            return [parsed], ["editorjs_container_missing_blocks_treated_as_single_block"]
        return [], ["editorjs_container_missing_blocks"]
    if isinstance(parsed, list):
        return parsed, ["editorjs_root_is_blocks_list"]
    return [], [f"editorjs_unexpected_root_type:{type(parsed).__name__}"]


def _parse_block(raw_block: Any, doc_id: str, block_index: int) -> DocumentBlockRecord:
    block_id = f"b_{block_index + 1:06d}"
    if isinstance(raw_block, dict):
        block_type = str(raw_block.get("type") or "unknown")
        data = raw_block.get("data")
        if not isinstance(data, dict):
            data = {}
        source_block_id = raw_block.get("id")
    else:
        block_type = "unknown"
        data = {}
        source_block_id = None

    text, metadata, handled_empty = _extract_block_text(block_type, data)
    if source_block_id:
        metadata["source_block_id"] = str(source_block_id)

    if text:
        parse_status = "ok"
    elif handled_empty:
        parse_status = "ok"
    else:
        parse_status = "empty_or_unhandled_block"

    return DocumentBlockRecord(
        doc_id=doc_id,
        block_id=block_id,
        block_index=block_index,
        block_type=block_type,
        text=text,
        text_length_chars=len(text),
        metadata=metadata,
        raw_block_hash=hash_json(raw_block),
        parse_status=parse_status,
    )


def _extract_block_text(block_type: str, data: dict[str, Any]) -> tuple[str, dict[str, Any], bool]:
    metadata: dict[str, Any] = {}

    if block_type == "paragraph":
        return strip_html_text(data.get("text")), metadata, False

    if block_type == "header":
        if "level" in data:
            metadata["level"] = data.get("level")
        return strip_html_text(data.get("text")), metadata, False

    if block_type == "list":
        if "style" in data:
            metadata["style"] = data.get("style")
        lines = _format_list_items(data.get("items"))
        return "\n".join(lines).strip(), metadata, False

    if block_type == "table":
        rows = _format_table(data.get("content"))
        return "\n".join(rows).strip(), metadata, False

    if block_type == "quote":
        parts = [strip_html_text(data.get("text")), strip_html_text(data.get("caption"))]
        return "\n".join(part for part in parts if part).strip(), metadata, False

    if block_type == "warning":
        parts = [strip_html_text(data.get("title")), strip_html_text(data.get("message"))]
        return "\n".join(part for part in parts if part).strip(), metadata, False

    if block_type == "checklist":
        lines = _format_checklist(data.get("items"))
        return "\n".join(lines).strip(), metadata, False

    if block_type == "delimiter":
        return "", metadata, True

    if block_type in {"image", "embed"}:
        for key in ("service", "source"):
            if key in data:
                metadata[key] = data.get(key)
        parts = [
            strip_html_text(data.get("caption")),
            strip_html_text(data.get("title")),
            strip_html_text(data.get("description")),
        ]
        return "\n".join(part for part in parts if part).strip(), metadata, True

    if block_type == "code":
        return normalize_plain_text(data.get("code") or data.get("text")), metadata, False

    if block_type == "raw":
        return normalize_plain_text(data.get("html") or data.get("text")), metadata, False

    recursive_parts = _extract_recursive_text(data)
    return "\n".join(recursive_parts).strip(), metadata, False


def _format_list_items(items: Any, depth: int = 0) -> list[str]:
    if not isinstance(items, list):
        return _extract_recursive_text(items)

    lines: list[str] = []
    prefix = "  " * depth + "- "
    for item in items:
        if isinstance(item, str):
            text = strip_html_text(item)
            if text:
                lines.append(prefix + text)
            continue

        if isinstance(item, dict):
            text = strip_html_text(
                item.get("content")
                or item.get("text")
                or item.get("title")
                or item.get("message")
            )
            if text:
                lines.append(prefix + text)
            nested = item.get("items")
            if isinstance(nested, list):
                lines.extend(_format_list_items(nested, depth=depth + 1))
            elif not text:
                lines.extend(_extract_recursive_text(item))
            continue

        text = strip_html_text(item)
        if text:
            lines.append(prefix + text)

    return lines


def _format_table(content: Any) -> list[str]:
    if not isinstance(content, list):
        return _extract_recursive_text(content)

    rows: list[str] = []
    for row in content:
        if isinstance(row, list):
            cells = [strip_html_text(cell) for cell in row]
            rows.append("\t".join(cell for cell in cells if cell))
        else:
            text = strip_html_text(row)
            if text:
                rows.append(text)
    return [row for row in rows if row]


def _format_checklist(items: Any) -> list[str]:
    if not isinstance(items, list):
        return _extract_recursive_text(items)

    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            marker = "[x]" if item.get("checked") else "[ ]"
            text = strip_html_text(item.get("text") or item.get("content"))
            if text:
                lines.append(f"{marker} {text}")
        else:
            text = strip_html_text(item)
            if text:
                lines.append(f"[ ] {text}")
    return lines


def _extract_recursive_text(value: Any) -> list[str]:
    parts: list[str] = []

    def walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, str):
            text = strip_html_text(node)
            if text:
                parts.append(text)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if isinstance(node, dict):
            for key in RECURSIVE_TEXT_KEYS:
                if key in node:
                    walk(node[key])
            return
        text = strip_html_text(node)
        if text:
            parts.append(text)

    walk(value)
    return _dedupe_preserve_order(parts)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

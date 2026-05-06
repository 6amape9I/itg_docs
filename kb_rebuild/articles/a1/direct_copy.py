from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kb_rebuild.articles.planning.loaders import bool_value, list_value


@dataclass(frozen=True)
class DirectCopyValidation:
    accepted: bool
    rejection_reasons: list[str]
    best_window: dict[str, Any] | None
    source_doc: dict[str, Any] | None
    source_blocks: list[dict[str, Any]]


def validate_direct_copy(
    plan: dict[str, Any],
    *,
    windows_by_id: dict[str, dict[str, Any]],
    docs_by_id: dict[str, dict[str, Any]],
    blocks_by_doc: dict[str, list[dict[str, Any]]],
) -> DirectCopyValidation:
    reasons: list[str] = []
    if str(plan.get("strategy") or "") != "direct_copy_candidate":
        reasons.append("strategy_not_direct_copy_candidate")
    if not bool_value(plan.get("article_candidate")):
        reasons.append("article_candidate_false")
    if bool_value(plan.get("needs_review_before_article")):
        reasons.append("needs_review_before_article")
    if int(plan.get("documents_count") or 0) != 1:
        reasons.append("documents_count_not_one")
    if int(plan.get("source_windows_count") or 0) < 1:
        reasons.append("source_windows_count_zero")
    if int(plan.get("competing_article_candidate_tags_in_doc") or 0) != 0:
        reasons.append("competing_article_candidate_tags_in_doc")

    windows = [windows_by_id[str(window_id)] for window_id in list_value(plan.get("source_window_ids")) if str(window_id) in windows_by_id]
    best_window = max(windows, key=lambda item: float(item.get("coverage_ratio_estimate") or 0.0), default=None)
    if best_window is None:
        reasons.append("source_window_missing")
    else:
        quality = str(best_window.get("window_quality") or "")
        if quality not in {"high", "medium"}:
            reasons.append("best_window_quality_low")
        coverage = float(best_window.get("coverage_ratio_estimate") or 0.0)
        match_method = str(best_window.get("match_method") or "")
        if coverage < 0.8 and match_method != "short_doc_fallback":
            reasons.append("coverage_below_threshold")

    source_doc_ids = [str(item) for item in list_value(plan.get("source_doc_ids")) if str(item)]
    doc_id = source_doc_ids[0] if source_doc_ids else ""
    source_doc = docs_by_id.get(doc_id)
    if source_doc is None:
        reasons.append("source_document_missing")
    source_blocks = [block for block in blocks_by_doc.get(doc_id, []) if str(block.get("text") or "").strip()]
    if not source_blocks:
        reasons.append("source_document_has_no_parsed_blocks")
    if source_doc is not None and int(source_doc.get("text_length_chars") or 0) <= 0:
        reasons.append("source_document_empty")

    return DirectCopyValidation(
        accepted=not reasons,
        rejection_reasons=sorted(set(reasons)),
        best_window=best_window,
        source_doc=source_doc,
        source_blocks=source_blocks,
    )


def source_blocks_to_editorjs(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    editor_blocks: list[dict[str, Any]] = []
    for block in blocks:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        block_type = str(block.get("block_type") or "")
        editor_block = _editorjs_block(block_type, text, block)
        editor_blocks.append(editor_block)
    return editor_blocks


def _editorjs_block(block_type: str, text: str, source_block: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "source_doc_id": str(source_block.get("doc_id") or ""),
        "source_block_id": str(source_block.get("block_id") or ""),
        "source_block_index": int(source_block.get("block_index") or 0),
        "source_block_type": block_type,
    }
    if block_type == "header":
        level = 2
        raw_metadata = source_block.get("metadata")
        if isinstance(raw_metadata, dict):
            try:
                level = int(raw_metadata.get("level") or 2)
            except (TypeError, ValueError):
                level = 2
        return {"type": "header", "data": {"text": text, "level": level}, "metadata": metadata}
    if block_type == "paragraph":
        return {"type": "paragraph", "data": {"text": text}, "metadata": metadata}
    if block_type == "list":
        items = _list_items(text)
        return {"type": "list", "data": {"style": _list_style(source_block), "items": items}, "metadata": metadata}
    if block_type == "table":
        return {"type": "table", "data": {"content": _table_rows(text)}, "metadata": metadata}
    return {"type": "paragraph", "data": {"text": text}, "metadata": metadata}


def _list_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        if stripped:
            items.append(stripped)
    return items or [text]


def _list_style(source_block: dict[str, Any]) -> str:
    metadata = source_block.get("metadata")
    if isinstance(metadata, dict) and str(metadata.get("style") or "") == "ordered":
        return "ordered"
    return "unordered"


def _table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "\t" in stripped:
            rows.append([cell.strip() for cell in stripped.split("\t")])
        elif "|" in stripped:
            rows.append([cell.strip() for cell in stripped.strip("|").split("|")])
        else:
            rows.append([stripped])
    return rows or [[text]]

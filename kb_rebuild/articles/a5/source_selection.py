from __future__ import annotations

from pathlib import Path
from typing import Any

from kb_rebuild.articles.a5.models import A1_EXPORT_STATUSES, A4_COMPILED_STATUSES


def select_article_source(
    status_row: dict[str, Any],
    *,
    a4_draft: dict[str, Any] | None,
    a3_input: dict[str, Any] | None,
    entity_article: dict[str, Any] | None,
    entity_path: Path | None,
) -> dict[str, Any]:
    if a4_draft and str(a4_draft.get("article_status") or "") in A4_COMPILED_STATUSES:
        return _from_a4(status_row, a4_draft, entity_path)

    a1_status = str(status_row.get("article_status") or "")
    if entity_article and a1_status in A1_EXPORT_STATUSES:
        return _from_a1(status_row, entity_article, entity_path, final_status=a1_status, source_stage="A1")

    if entity_article and a3_input and str(a3_input.get("a4_strategy") or "") == "insufficient_evidence_review":
        selected = _from_a1(
            status_row,
            entity_article,
            entity_path,
            final_status="insufficient_evidence_review",
            source_stage="A3",
        )
        selected["source_article_status"] = str(a3_input.get("article_status_from_a1") or a1_status or "unknown")
        selected["needs_review_before_publication"] = True
        selected["review_reasons"] = _unique_strings(
            selected["review_reasons"] + _string_list(a3_input.get("review_reasons")) + ["insufficient_evidence_review"]
        )
        return selected

    return {
        "tag_id": str(status_row.get("tag_id") or ""),
        "canonical_tag_ru": _first_text(status_row.get("canonical_tag_ru")),
        "canonical_tag_latin": _nullable_text(status_row.get("canonical_tag_latin")),
        "entity_type": _first_text(status_row.get("entity_type")) or "unknown",
        "article_status": "missing_article_source",
        "source_article_status": a1_status or "missing",
        "source_stage": "missing",
        "needs_review_before_publication": True,
        "review_reasons": _unique_strings(_status_review_reasons(status_row) + ["missing_article_source"]),
        "content_format": "editorjs",
        "content": None,
        "source_doc_ids": [],
        "source_documents_count": int(status_row.get("documents_count") or 0),
        "fact_group_ids": [],
        "used_fact_group_ids": [],
        "a1_entity_json_path": str(entity_path or status_row.get("article_file_path") or ""),
        "a4_draft_path": None,
        "selection_issue": "missing_article_source",
    }


def _from_a4(status_row: dict[str, Any], draft: dict[str, Any], entity_path: Path | None) -> dict[str, Any]:
    status = str(draft.get("article_status") or "")
    return {
        "tag_id": str(draft.get("tag_id") or status_row.get("tag_id") or ""),
        "canonical_tag_ru": _first_text(draft.get("canonical_tag_ru"), status_row.get("canonical_tag_ru")),
        "canonical_tag_latin": _nullable_text(draft.get("canonical_tag_latin"), status_row.get("canonical_tag_latin")),
        "entity_type": _first_text(draft.get("entity_type"), status_row.get("entity_type")) or "unknown",
        "article_status": status,
        "source_article_status": status,
        "source_stage": "A4",
        "needs_review_before_publication": bool(draft.get("needs_review_before_publication")),
        "review_reasons": _unique_strings(_string_list(draft.get("review_reasons"))),
        "content_format": str(draft.get("content_format") or "editorjs"),
        "content": draft.get("content"),
        "source_doc_ids": _string_list(draft.get("source_doc_ids")),
        "source_documents_count": int(draft.get("source_documents_count") or 0),
        "fact_group_ids": _unique_strings(_string_list(draft.get("fact_group_ids")) + _string_list(draft.get("used_fact_group_ids"))),
        "used_fact_group_ids": _unique_strings(_string_list(draft.get("used_fact_group_ids"))),
        "a1_entity_json_path": str(entity_path or status_row.get("article_file_path") or ""),
        "a4_draft_path": str(draft.get("article_file_path") or ""),
        "selection_issue": None,
    }


def _from_a1(
    status_row: dict[str, Any],
    entity_article: dict[str, Any],
    entity_path: Path | None,
    *,
    final_status: str,
    source_stage: str,
) -> dict[str, Any]:
    sources = entity_article.get("sources") if isinstance(entity_article.get("sources"), dict) else {}
    source_doc_ids = _string_list(sources.get("source_doc_ids"))
    return {
        "tag_id": str(entity_article.get("tag_id") or status_row.get("tag_id") or ""),
        "canonical_tag_ru": _first_text(entity_article.get("canonical_tag_ru"), status_row.get("canonical_tag_ru")),
        "canonical_tag_latin": _nullable_text(entity_article.get("canonical_tag_latin"), status_row.get("canonical_tag_latin")),
        "entity_type": _first_text(entity_article.get("entity_type"), status_row.get("entity_type")) or "unknown",
        "article_status": final_status,
        "source_article_status": str(entity_article.get("article_status") or status_row.get("article_status") or final_status),
        "source_stage": source_stage,
        "needs_review_before_publication": bool(
            entity_article.get("needs_review_before_publication") or status_row.get("needs_review_before_publication")
        ),
        "review_reasons": _unique_strings(_status_review_reasons(status_row) + _string_list(entity_article.get("review_reasons"))),
        "content_format": str(entity_article.get("content_format") or "editorjs"),
        "content": entity_article.get("content"),
        "source_doc_ids": source_doc_ids,
        "source_documents_count": int(entity_article.get("documents_count") or status_row.get("documents_count") or len(source_doc_ids)),
        "fact_group_ids": [],
        "used_fact_group_ids": [],
        "a1_entity_json_path": str(entity_path or status_row.get("article_file_path") or ""),
        "a4_draft_path": None,
        "selection_issue": None,
    }


def _status_review_reasons(status_row: dict[str, Any]) -> list[str]:
    return _unique_strings(_string_list(status_row.get("review_reasons")) + _string_list(status_row.get("publication_review_reasons")))


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _nullable_text(*values: Any) -> str | None:
    text = _first_text(*values)
    return text or None


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


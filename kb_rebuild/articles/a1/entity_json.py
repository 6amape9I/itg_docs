from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kb_rebuild.articles.a1.direct_copy import source_blocks_to_editorjs
from kb_rebuild.articles.a1.models import PENDING_STATUS_BY_STRATEGY
from kb_rebuild.articles.planning.loaders import bool_value, list_value


EDITORJS_VERSION = "2.28.0"


def article_status_for_strategy(
    plan: dict[str, Any],
    *,
    direct_copy_accepted: bool = False,
    direct_copy_rejected: bool = False,
) -> tuple[str, str]:
    strategy = str(plan.get("strategy") or "")
    if strategy == "stub_only":
        return "stub_only", "stub_only"
    if strategy in {"review_stub", "no_source_window_review"}:
        return "review_stub", "review_stub"
    if strategy == "direct_copy_candidate" and direct_copy_accepted:
        return "direct_copy_article", "direct_copy_candidate"
    if strategy == "direct_copy_candidate" and direct_copy_rejected:
        return "pending_single_doc_extract", "single_doc_extract"
    if strategy in PENDING_STATUS_BY_STRATEGY:
        return PENDING_STATUS_BY_STRATEGY[strategy], strategy
    return "failed_or_blocked", strategy


def build_entity_json(
    *,
    plan: dict[str, Any],
    article_status: str,
    source_strategy: str,
    entity_path: Path,
    content_blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    blocks = content_blocks if content_blocks is not None else _content_blocks(plan, article_status)
    return {
        "tag_id": str(plan.get("tag_id") or ""),
        "canonical_tag_ru": str(plan.get("canonical_tag_ru") or ""),
        "canonical_tag_latin": _nullable_string(plan.get("canonical_tag_latin")),
        "entity_type": str(plan.get("entity_type") or ""),
        "article_status": article_status,
        "source_strategy": source_strategy,
        "needs_review_before_article": bool_value(plan.get("needs_review_before_article")),
        "needs_review_before_publication": bool_value(plan.get("needs_review_before_publication")),
        "review_reasons": [str(item) for item in list_value(plan.get("review_reasons"))],
        "publication_review_reasons": [str(item) for item in list_value(plan.get("publication_review_reasons"))],
        "article_blocking_review_reasons": [str(item) for item in list_value(plan.get("article_blocking_review_reasons"))],
        "article_candidate": bool_value(plan.get("article_candidate")),
        "primary_role": str(plan.get("primary_role") or ""),
        "mentions_count": int(plan.get("mentions_count") or 0),
        "documents_count": int(plan.get("documents_count") or 0),
        "content_format": "editorjs",
        "content": {"time": 0, "version": EDITORJS_VERSION, "blocks": blocks},
        "sources": {
            "source_doc_ids": [str(item) for item in list_value(plan.get("source_doc_ids"))],
            "source_window_ids": [str(item) for item in list_value(plan.get("source_window_ids"))],
            "source_windows_count": int(plan.get("source_windows_count") or 0),
        },
        "provenance": {
            "created_from_stage": "A1",
            "normalization_source": "data/normalization/final",
            "planning_source": "data/articles/planning",
            "adjusted_plan_source": "data/articles/a1/tag_work_plan_adjusted.jsonl",
            "article_file_path": str(entity_path),
        },
    }


def direct_copy_entity_json(
    *,
    plan: dict[str, Any],
    entity_path: Path,
    source_blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    return build_entity_json(
        plan=plan,
        article_status="direct_copy_article",
        source_strategy="direct_copy_candidate",
        entity_path=entity_path,
        content_blocks=source_blocks_to_editorjs(source_blocks),
    )


def write_entity_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp_path.replace(path)


def entity_file_path(entities_out_dir: Path, plan: dict[str, Any]) -> Path:
    entity_type = str(plan.get("entity_type") or "unknown")
    tag_id = str(plan.get("tag_id") or "")
    return entities_out_dir / entity_type / f"{tag_id}.json"


def _content_blocks(plan: dict[str, Any], article_status: str) -> list[dict[str, Any]]:
    title = str(plan.get("canonical_tag_ru") or "")
    if article_status == "stub_only":
        return [
            {"type": "header", "data": {"text": title, "level": 2}},
            {
                "type": "paragraph",
                "data": {
                    "text": "Страница сущности создана как служебная карточка. Полноценная статья не сформирована, так как сущность не является самостоятельным article-candidate тегом."
                },
            },
        ]
    if article_status == "review_stub":
        return [
            {"type": "header", "data": {"text": title, "level": 2}},
            {"type": "paragraph", "data": {"text": "Страница требует проверки перед сборкой статьи."}},
        ]
    if article_status.startswith("pending_"):
        return [
            {"type": "header", "data": {"text": title, "level": 2}},
            {"type": "paragraph", "data": {"text": "Страница ожидает извлечения evidence из подготовленных source windows."}},
        ]
    return [{"type": "header", "data": {"text": title, "level": 2}}]


def _nullable_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None

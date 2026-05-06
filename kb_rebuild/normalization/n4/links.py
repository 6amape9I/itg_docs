from __future__ import annotations

from collections import defaultdict
from typing import Any

from kb_rebuild.normalization.n4.aliases import alias_index
from kb_rebuild.normalization.text import normalize_basic_text


def build_document_links(
    *,
    mentions: list[dict[str, Any]],
    mention_to_auto_cluster: dict[str, str],
    auto_cluster_to_tag_id: dict[str, str],
    tags_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    links: list[dict[str, Any]] = []
    missing_mentions: list[dict[str, Any]] = []
    for mention in mentions:
        mention_id = str(mention.get("mention_id") or "")
        auto_cluster_id = mention_to_auto_cluster.get(mention_id, "")
        tag_id = auto_cluster_to_tag_id.get(auto_cluster_id, "")
        tag = tags_by_id.get(tag_id, {})
        if not tag_id:
            missing_mentions.append(
                {
                    "mention_id": mention_id,
                    "doc_id": str(mention.get("doc_id") or ""),
                    "document_name": str(mention.get("document_name") or ""),
                    "entity_type": str(mention.get("entity_type") or ""),
                    "reason": "mention_id is not covered by any final tag",
                }
            )
        raw = mention.get("raw") if isinstance(mention.get("raw"), dict) else {}
        links.append(
            {
                "doc_id": str(mention.get("doc_id") or ""),
                "document_name": str(mention.get("document_name") or ""),
                "mention_id": mention_id,
                "raw_surface": str(raw.get("surface") or ""),
                "raw_canonical_candidate_ru": str(raw.get("canonical_candidate_ru") or ""),
                "raw_canonical_candidate_latin": str(raw.get("canonical_candidate_latin") or ""),
                "entity_type": str(mention.get("entity_type") or ""),
                "tag_role": str(mention.get("tag_role") or ""),
                "article_candidate": bool(mention.get("article_candidate")),
                "confidence": mention.get("confidence", ""),
                "tag_id": tag_id,
                "canonical_tag_ru": str(tag.get("canonical_tag_ru") or ""),
                "canonical_tag_latin": str(tag.get("canonical_tag_latin") or ""),
                "normalization_source": str(tag.get("normalization_source") or ""),
                "need_review": bool(tag.get("need_review", False)),
                "review_reasons": tag.get("review_reasons", []),
            }
        )
    return links, missing_mentions


def build_document_tags_by_doc(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    tags_by_doc: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for link in links:
        doc_id = str(link.get("doc_id") or "")
        if doc_id not in grouped:
            grouped[doc_id] = {
                "doc_id": doc_id,
                "document_name": str(link.get("document_name") or ""),
                "tags": [],
            }
        tag_id = str(link.get("tag_id") or "")
        if not tag_id:
            continue
        current = tags_by_doc[doc_id].get(tag_id)
        if current is None:
            tags_by_doc[doc_id][tag_id] = {
                "tag_id": tag_id,
                "canonical_tag_ru": str(link.get("canonical_tag_ru") or ""),
                "canonical_tag_latin": str(link.get("canonical_tag_latin") or ""),
                "entity_type": str(link.get("entity_type") or ""),
                "tag_role": str(link.get("tag_role") or ""),
                "article_candidate": bool(link.get("article_candidate")),
                "need_review": bool(link.get("need_review")),
            }
            continue
        current["article_candidate"] = bool(current.get("article_candidate")) or bool(link.get("article_candidate"))
        if link.get("tag_role") == "article_candidate":
            current["tag_role"] = "article_candidate"
    for doc_id, record in grouped.items():
        record["tags"] = sorted(
            tags_by_doc[doc_id].values(),
            key=lambda row: (row["entity_type"], row["canonical_tag_ru"], row["tag_id"]),
        )
    return [grouped[doc_id] for doc_id in sorted(grouped)]


def audit_coverage(
    *,
    mentions: list[dict[str, Any]],
    links: list[dict[str, Any]],
    canonical_rows: list[dict[str, Any]],
    alias_rows: list[dict[str, Any]],
    missing_mentions: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    tags_by_id = {str(row.get("tag_id") or ""): row for row in canonical_rows}
    index = alias_index(canonical_rows, alias_rows)
    links_to_missing_tag_id = sum(1 for link in links if str(link.get("tag_id") or "") not in tags_by_id)
    link_by_mention_id = {str(link.get("mention_id") or ""): link for link in links}
    missing_aliases: list[dict[str, Any]] = []
    for mention in mentions:
        mention_id = str(mention.get("mention_id") or "")
        link = link_by_mention_id.get(mention_id, {})
        expected_tag_id = str(link.get("tag_id") or "")
        for source_field, value in _mention_lookup_values(mention):
            norm = normalize_basic_text(value)
            if not norm:
                continue
            tag_ids = index.get((str(mention.get("entity_type") or ""), norm), set())
            if expected_tag_id and expected_tag_id in tag_ids:
                continue
            raw = mention.get("raw") if isinstance(mention.get("raw"), dict) else {}
            missing_aliases.append(
                {
                    "mention_id": mention_id,
                    "doc_id": str(mention.get("doc_id") or ""),
                    "document_name": str(mention.get("document_name") or ""),
                    "entity_type": str(mention.get("entity_type") or ""),
                    "missing_value": value,
                    "missing_value_norm": norm,
                    "source_field": source_field,
                    "raw_surface": str(raw.get("surface") or ""),
                    "raw_canonical_candidate_ru": str(raw.get("canonical_candidate_ru") or ""),
                    "raw_canonical_candidate_latin": str(raw.get("canonical_candidate_latin") or ""),
                    "expected_tag_id": expected_tag_id,
                    "reason": "value is absent from canonical+aliases index for expected tag_id",
                }
            )
    documents_with_mentions = len({str(mention.get("doc_id") or "") for mention in mentions if str(mention.get("doc_id") or "")})
    documents_with_normalized_tags = len({str(link.get("doc_id") or "") for link in links if str(link.get("tag_id") or "")})
    audit = {
        "mentions_total": len(mentions),
        "document_tag_links_total": len(links),
        "mentions_without_tag_id": len(missing_mentions),
        "links_to_missing_tag_id": links_to_missing_tag_id,
        "aliases_missing_for_original_mentions": len(missing_aliases),
        "documents_with_mentions": documents_with_mentions,
        "documents_with_normalized_tags": documents_with_normalized_tags,
        "all_mentions_have_tag_id": len(missing_mentions) == 0,
        "all_original_tag_names_recognized": len(missing_aliases) == 0,
        "passed": len(missing_mentions) == 0 and links_to_missing_tag_id == 0 and len(missing_aliases) == 0,
    }
    audit["quality"] = {
        "all_mentions_have_tag_id": audit["all_mentions_have_tag_id"],
        "all_original_tag_names_recognized": audit["all_original_tag_names_recognized"],
        "passed": audit["passed"],
    }
    return audit, missing_aliases


def _mention_lookup_values(mention: dict[str, Any]) -> list[tuple[str, str]]:
    raw = mention.get("raw") if isinstance(mention.get("raw"), dict) else {}
    normalized = mention.get("normalized") if isinstance(mention.get("normalized"), dict) else {}
    return [
        ("raw.surface", str(raw.get("surface") or "")),
        ("raw.canonical_candidate_ru", str(raw.get("canonical_candidate_ru") or "")),
        ("raw.canonical_candidate_latin", str(raw.get("canonical_candidate_latin") or "")),
        ("normalized.primary_norm", str(normalized.get("primary_norm") or "")),
        ("normalized.surface_norm", str(normalized.get("surface_norm") or "")),
        ("normalized.candidate_ru_norm", str(normalized.get("candidate_ru_norm") or "")),
        ("normalized.candidate_latin_norm", str(normalized.get("candidate_latin_norm") or "")),
    ]

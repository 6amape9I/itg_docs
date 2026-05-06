from __future__ import annotations

from dataclasses import replace
from typing import Any

from kb_rebuild.articles.planning.matching import METHOD_PRIORITY, QUALITY_PRIORITY
from kb_rebuild.articles.planning.models import A0Config, MatchHit, SourceWindowDraft


def build_windows_for_tag_doc(
    *,
    config: A0Config,
    tag: dict[str, Any],
    doc: dict[str, Any],
    blocks: list[dict[str, Any]],
    hits: list[MatchHit],
    mention_ids: list[str],
) -> list[SourceWindowDraft]:
    if not blocks or not hits:
        return []
    block_map = {int(block.get("block_index")): block for block in blocks if block.get("block_index") is not None}
    if not block_map:
        return []

    drafts: list[SourceWindowDraft] = []
    for hit in hits:
        indexes = _window_indexes(config, hit, block_map)
        draft = _draft_from_indexes(
            tag=tag,
            doc=doc,
            block_map=block_map,
            indexes=indexes,
            match_method=hit.method,
            window_quality=hit.quality,
            mention_ids=sorted(set(mention_ids) | set(hit.mention_ids)),
            matched_aliases=sorted(set(hit.matched_aliases)),
            needs_review=hit.needs_review,
            review_reasons=sorted(set(hit.review_reasons)),
        )
        if draft is not None:
            drafts.append(draft)

    return _merge_overlapping(drafts, block_map)


def _window_indexes(config: A0Config, hit: MatchHit, block_map: dict[int, dict[str, Any]]) -> list[int]:
    required = {index for index in hit.block_indexes if index in block_map}
    indexes = set(required)
    all_indexes = sorted(block_map)
    all_set = set(all_indexes)

    for index in required:
        for neighbor in range(index - config.max_neighbor_blocks, index + config.max_neighbor_blocks + 1):
            if neighbor in all_set:
                indexes.add(neighbor)
        previous_header = _previous_header(index, block_map)
        if previous_header is not None:
            indexes.add(previous_header)

    if hit.method == "short_doc_fallback":
        indexes = set(required)

    return _trim_to_char_limit(indexes, required, block_map, config.max_window_chars)


def _previous_header(index: int, block_map: dict[int, dict[str, Any]]) -> int | None:
    for candidate in sorted((item for item in block_map if item < index), reverse=True):
        if str(block_map[candidate].get("block_type") or "") == "header":
            return candidate
    return None


def _trim_to_char_limit(
    indexes: set[int],
    required: set[int],
    block_map: dict[int, dict[str, Any]],
    max_window_chars: int,
) -> list[int]:
    current = set(indexes)
    while _indexes_char_length(current, block_map) > max_window_chars:
        removable = sorted(current - required)
        if not removable:
            break
        current.remove(_farthest_index(removable, required))
    return sorted(current)


def _farthest_index(candidates: list[int], required: set[int]) -> int:
    if not required:
        return candidates[-1]
    return max(candidates, key=lambda index: (min(abs(index - req) for req in required), index))


def _indexes_char_length(indexes: set[int], block_map: dict[int, dict[str, Any]]) -> int:
    return sum(len(str(block_map[index].get("text") or "")) for index in indexes) + max(0, len(indexes) - 1) * 2


def _draft_from_indexes(
    *,
    tag: dict[str, Any],
    doc: dict[str, Any],
    block_map: dict[int, dict[str, Any]],
    indexes: list[int],
    match_method: str,
    window_quality: str,
    mention_ids: list[str],
    matched_aliases: list[str],
    needs_review: bool,
    review_reasons: list[str],
) -> SourceWindowDraft | None:
    selected = [block_map[index] for index in indexes if index in block_map]
    texts = [str(block.get("text") or "").strip() for block in selected if str(block.get("text") or "").strip()]
    window_text = "\n\n".join(texts).strip()
    if not window_text:
        return None
    document_char_length = int(doc.get("text_length_chars") or len(str(doc.get("clean_text") or "")) or len(window_text))
    coverage = min(1.0, len(window_text) / document_char_length) if document_char_length > 0 else 0.0
    return SourceWindowDraft(
        tag_id=str(tag.get("tag_id") or ""),
        canonical_tag_ru=str(tag.get("canonical_tag_ru") or ""),
        canonical_tag_latin=str(tag.get("canonical_tag_latin") or ""),
        entity_type=str(tag.get("entity_type") or ""),
        doc_id=str(doc.get("doc_id") or ""),
        document_name=str(doc.get("name") or ""),
        mention_ids=mention_ids,
        matched_aliases=matched_aliases,
        block_ids=[str(block.get("block_id") or "") for block in selected],
        block_indexes=[int(block.get("block_index")) for block in selected],
        heading_context=_heading_context(selected, block_map),
        window_text=window_text,
        window_char_length=len(window_text),
        match_method=match_method,
        window_quality=window_quality,
        needs_review=needs_review,
        review_reasons=review_reasons,
        document_char_length=document_char_length,
        coverage_ratio_estimate=round(coverage, 6),
    )


def _heading_context(selected: list[dict[str, Any]], block_map: dict[int, dict[str, Any]]) -> list[str]:
    context: list[str] = []
    selected_indexes = [int(block.get("block_index")) for block in selected if block.get("block_index") is not None]
    for index in selected_indexes:
        block = block_map[index]
        if str(block.get("block_type") or "") == "header":
            text = str(block.get("text") or "").strip()
            if text and text not in context:
                context.append(text)
    min_index = min(selected_indexes) if selected_indexes else None
    if min_index is not None:
        for candidate in sorted((item for item in block_map if item < min_index), reverse=True):
            block = block_map[candidate]
            if str(block.get("block_type") or "") == "header":
                text = str(block.get("text") or "").strip()
                if text and text not in context:
                    context.insert(0, text)
                break
    return context


def _merge_overlapping(
    drafts: list[SourceWindowDraft],
    block_map: dict[int, dict[str, Any]],
) -> list[SourceWindowDraft]:
    if not drafts:
        return []
    sorted_drafts = sorted(drafts, key=lambda draft: (min(draft.block_indexes), max(draft.block_indexes)))
    merged: list[SourceWindowDraft] = []
    current = sorted_drafts[0]
    current_indexes = set(current.block_indexes)

    for draft in sorted_drafts[1:]:
        draft_indexes = set(draft.block_indexes)
        overlaps = bool(current_indexes & draft_indexes)
        adjacent = max(current_indexes) + 1 >= min(draft_indexes) if current_indexes and draft_indexes else False
        if not overlaps and not adjacent:
            merged.append(current)
            current = draft
            current_indexes = set(current.block_indexes)
            continue
        current_indexes |= draft_indexes
        current = _merge_pair(current, draft, sorted(current_indexes), block_map)

    merged.append(current)
    return merged


def _merge_pair(
    left: SourceWindowDraft,
    right: SourceWindowDraft,
    indexes: list[int],
    block_map: dict[int, dict[str, Any]],
) -> SourceWindowDraft:
    selected = [block_map[index] for index in indexes if index in block_map]
    window_text = "\n\n".join(str(block.get("text") or "").strip() for block in selected if str(block.get("text") or "").strip())
    method = min((left.match_method, right.match_method), key=lambda item: METHOD_PRIORITY.get(item, 99))
    quality = min((left.window_quality, right.window_quality), key=lambda item: QUALITY_PRIORITY.get(item, 99))
    document_char_length = max(left.document_char_length, right.document_char_length)
    coverage = min(1.0, len(window_text) / document_char_length) if document_char_length > 0 else 0.0
    return replace(
        left,
        mention_ids=sorted(set(left.mention_ids) | set(right.mention_ids)),
        matched_aliases=sorted(set(left.matched_aliases) | set(right.matched_aliases)),
        block_ids=[str(block.get("block_id") or "") for block in selected],
        block_indexes=[int(block.get("block_index")) for block in selected],
        heading_context=_heading_context(selected, block_map),
        window_text=window_text,
        window_char_length=len(window_text),
        match_method=method,
        window_quality=quality,
        needs_review=left.needs_review or right.needs_review,
        review_reasons=sorted(set(left.review_reasons) | set(right.review_reasons)),
        document_char_length=document_char_length,
        coverage_ratio_estimate=round(coverage, 6),
    )

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from kb_rebuild.articles.planning.loaders import list_value
from kb_rebuild.articles.planning.models import A0Config, MatchHit
from kb_rebuild.normalization.text import normalize_basic_text


METHOD_PRIORITY = {
    "quote_match": 0,
    "alias_match": 1,
    "title_match": 2,
    "short_doc_fallback": 3,
    "mention_only_fallback": 4,
}

QUALITY_PRIORITY = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class AliasTerm:
    normalized: str
    display: str
    source: str
    is_canonical: bool = False

    @property
    def compact_length(self) -> int:
        return len(re.sub(r"\W+", "", self.normalized, flags=re.UNICODE))


def normalize_for_match(value: Any) -> str:
    return normalize_basic_text("" if value is None else str(value))


def build_alias_dictionary(
    canonical_tags: list[dict[str, Any]],
    aliases: list[dict[str, Any]],
    document_links: list[dict[str, Any]],
) -> dict[str, list[AliasTerm]]:
    terms: dict[str, dict[str, AliasTerm]] = defaultdict(dict)

    def add(tag_id: str, value: Any, source: str, *, is_canonical: bool = False) -> None:
        normalized = normalize_for_match(value)
        if not normalized:
            return
        existing = terms[tag_id].get(normalized)
        if existing is None or (is_canonical and not existing.is_canonical):
            terms[tag_id][normalized] = AliasTerm(
                normalized=normalized,
                display=str(value),
                source=source,
                is_canonical=is_canonical,
            )

    for row in canonical_tags:
        tag_id = str(row.get("tag_id") or "")
        if not tag_id:
            continue
        add(tag_id, row.get("canonical_tag_ru"), "canonical_tag_ru", is_canonical=True)
        add(tag_id, row.get("canonical_tag_latin"), "canonical_tag_latin", is_canonical=True)

    for row in aliases:
        tag_id = str(row.get("tag_id") or "")
        if not tag_id:
            continue
        add(tag_id, row.get("alias"), "tag_aliases.alias")
        add(tag_id, row.get("alias_latin"), "tag_aliases.alias_latin")

    for row in document_links:
        tag_id = str(row.get("tag_id") or "")
        if not tag_id:
            continue
        add(tag_id, row.get("raw_surface"), "document_link.raw_surface")
        add(tag_id, row.get("raw_canonical_candidate_ru"), "document_link.raw_canonical_candidate_ru")
        add(tag_id, row.get("raw_canonical_candidate_latin"), "document_link.raw_canonical_candidate_latin")

    return {
        tag_id: sorted(values.values(), key=lambda term: (not term.is_canonical, -len(term.normalized), term.normalized))
        for tag_id, values in terms.items()
    }


def build_quote_context(tag_mentions_normalized: list[dict[str, Any]]) -> dict[str, list[str]]:
    quotes_by_mention: dict[str, list[str]] = defaultdict(list)
    for row in tag_mentions_normalized:
        mention_id = str(row.get("mention_id") or "")
        if not mention_id:
            continue
        for quote in list_value(row.get("evidence_quotes")):
            quote_text = str(quote).strip()
            if quote_text:
                quotes_by_mention[mention_id].append(quote_text)
    return dict(quotes_by_mention)


def find_match_hits(
    *,
    config: A0Config,
    tag_id: str,
    aliases: list[AliasTerm],
    doc: dict[str, Any] | None,
    blocks: list[dict[str, Any]],
    mention_ids: list[str],
    quote_context: dict[str, list[str]],
    allow_short_document_fallback: bool,
) -> list[MatchHit]:
    nonempty_indexes = tuple(
        int(block.get("block_index"))
        for block in blocks
        if str(block.get("text") or "").strip() and block.get("block_index") is not None
    )
    if not nonempty_indexes:
        return []

    block_norms = {
        int(block.get("block_index")): normalize_for_match(block.get("text"))
        for block in blocks
        if block.get("block_index") is not None
    }
    hits: list[MatchHit] = []

    quote_hits = _quote_hits(block_norms, mention_ids, quote_context)
    hits.extend(quote_hits)

    alias_hits = _alias_hits(block_norms, aliases)
    hits.extend(alias_hits)

    if hits:
        return sorted(hits, key=_hit_sort_key)

    doc_length = int((doc or {}).get("text_length_chars") or 0)
    title_hit = _title_hit(
        doc,
        aliases,
        nonempty_indexes,
        use_all_blocks=doc_length <= config.short_document_char_limit and allow_short_document_fallback,
    )
    if title_hit is not None:
        return [title_hit]

    if doc_length <= config.short_document_char_limit and allow_short_document_fallback:
        return [
            MatchHit(
                method="short_doc_fallback",
                quality="medium",
                block_indexes=nonempty_indexes,
                mention_ids=tuple(mention_ids),
            )
        ]

    return [
        MatchHit(
            method="mention_only_fallback",
            quality="low",
            block_indexes=nonempty_indexes[:1],
            mention_ids=tuple(mention_ids),
            needs_review=True,
            review_reasons=("mention_only_fallback_no_quote_alias_or_title_match",),
        )
    ]


def title_matches_alias(document_name: str, aliases: list[AliasTerm]) -> bool:
    title_norm = normalize_for_match(document_name)
    if not title_norm:
        return False
    return any(_term_in_text(title_norm, alias.normalized, allow_short=True) for alias in aliases if alias.normalized)


def _quote_hits(
    block_norms: dict[int, str],
    mention_ids: list[str],
    quote_context: dict[str, list[str]],
) -> list[MatchHit]:
    hits: list[MatchHit] = []
    by_block: dict[int, set[str]] = defaultdict(set)
    for mention_id in mention_ids:
        for quote in quote_context.get(mention_id, []):
            quote_norm = normalize_for_match(quote)
            if len(quote_norm) < 8:
                continue
            for block_index, block_norm in block_norms.items():
                if quote_norm and quote_norm in block_norm:
                    by_block[block_index].add(mention_id)
    for block_index, matched_mentions in sorted(by_block.items()):
        hits.append(
            MatchHit(
                method="quote_match",
                quality="high",
                block_indexes=(block_index,),
                mention_ids=tuple(sorted(matched_mentions)),
            )
        )
    return hits


def _alias_hits(block_norms: dict[int, str], aliases: list[AliasTerm]) -> list[MatchHit]:
    hits: list[MatchHit] = []
    for block_index, block_norm in block_norms.items():
        matched: list[AliasTerm] = []
        for alias in aliases:
            if not _safe_alias_for_block(alias):
                continue
            if _term_in_text(block_norm, alias.normalized):
                matched.append(alias)
        if not matched:
            continue
        quality = "high" if any(alias.is_canonical or alias.compact_length >= 5 for alias in matched) else "medium"
        hits.append(
            MatchHit(
                method="alias_match",
                quality=quality,
                block_indexes=(block_index,),
                matched_aliases=tuple(alias.normalized for alias in matched[:10]),
            )
        )
    return hits


def _title_hit(
    doc: dict[str, Any] | None,
    aliases: list[AliasTerm],
    nonempty_indexes: tuple[int, ...],
    *,
    use_all_blocks: bool = False,
) -> MatchHit | None:
    document_name = str((doc or {}).get("name") or "")
    title_norm = normalize_for_match(document_name)
    if not title_norm:
        return None
    matched = [
        alias
        for alias in aliases
        if alias.normalized and _term_in_text(title_norm, alias.normalized, allow_short=True)
    ]
    if not matched:
        return None
    quality = "medium" if any(alias.is_canonical or alias.compact_length >= 5 for alias in matched) else "low"
    return MatchHit(
        method="title_match",
        quality=quality,
        block_indexes=nonempty_indexes if use_all_blocks else nonempty_indexes[:1],
        matched_aliases=tuple(alias.normalized for alias in matched[:10]),
        needs_review=quality == "low",
        review_reasons=() if quality == "medium" else ("title_match_short_or_ambiguous_alias",),
    )


def _safe_alias_for_block(alias: AliasTerm) -> bool:
    if not alias.normalized:
        return False
    if alias.compact_length < 3:
        return False
    return True


def _term_in_text(text_norm: str, term_norm: str, *, allow_short: bool = False) -> bool:
    if not text_norm or not term_norm:
        return False
    compact_length = len(re.sub(r"\W+", "", term_norm, flags=re.UNICODE))
    if compact_length < 3 and not allow_short:
        return False
    pattern = re.escape(term_norm)
    if term_norm[0].isalnum():
        pattern = rf"(?<!\w){pattern}"
    if term_norm[-1].isalnum():
        pattern = rf"{pattern}(?!\w)"
    return re.search(pattern, text_norm, flags=re.UNICODE) is not None


def _hit_sort_key(hit: MatchHit) -> tuple[int, int, int]:
    first_index = min(hit.block_indexes) if hit.block_indexes else 0
    return (METHOD_PRIORITY.get(hit.method, 99), QUALITY_PRIORITY.get(hit.quality, 99), first_index)

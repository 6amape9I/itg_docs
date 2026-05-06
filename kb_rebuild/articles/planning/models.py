from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


STAGE = "article_planning_a0"
STAGE_VERSION = "a0.0"

STRATEGIES = {
    "stub_only",
    "review_stub",
    "direct_copy_candidate",
    "single_doc_extract",
    "low_count_batch_extract",
    "multi_doc_map_reduce",
    "high_frequency_map_reduce",
    "no_source_window_review",
}

MATCH_METHODS = {
    "quote_match",
    "alias_match",
    "title_match",
    "short_doc_fallback",
    "mention_only_fallback",
}

WINDOW_QUALITIES = {"high", "medium", "low"}


@dataclass(frozen=True)
class A0Config:
    data_dir: Path = Path("data")
    normalization_final_dir: Path = Path("data/normalization/final")
    parsed_dir: Path = Path("data/parsed")
    normalization_dir: Path = Path("data/normalization")
    out_dir: Path = Path("data/articles/planning")
    max_neighbor_blocks: int = 2
    max_window_chars: int = 12000
    short_document_char_limit: int = 12000
    high_frequency_doc_threshold: int = 20
    low_count_doc_threshold: int = 3
    review_sample_size: int = 500
    overwrite: bool = True

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Path,
        *,
        normalization_final_dir: Path | None = None,
        parsed_dir: Path | None = None,
        normalization_dir: Path | None = None,
        out_dir: Path | None = None,
        max_neighbor_blocks: int = 2,
        max_window_chars: int = 12000,
        short_document_char_limit: int = 12000,
        high_frequency_doc_threshold: int = 20,
        low_count_doc_threshold: int = 3,
        review_sample_size: int = 500,
        overwrite: bool = True,
    ) -> "A0Config":
        norm_dir = normalization_dir or data_dir / "normalization"
        return cls(
            data_dir=data_dir,
            normalization_final_dir=normalization_final_dir or norm_dir / "final",
            parsed_dir=parsed_dir or data_dir / "parsed",
            normalization_dir=norm_dir,
            out_dir=out_dir or data_dir / "articles" / "planning",
            max_neighbor_blocks=max_neighbor_blocks,
            max_window_chars=max_window_chars,
            short_document_char_limit=short_document_char_limit,
            high_frequency_doc_threshold=high_frequency_doc_threshold,
            low_count_doc_threshold=low_count_doc_threshold,
            review_sample_size=review_sample_size,
            overwrite=overwrite,
        )


@dataclass
class PlanningInputs:
    canonical_tags: list[dict[str, Any]]
    aliases: list[dict[str, Any]]
    document_links: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    blocks: list[dict[str, Any]]
    tag_mentions_normalized: list[dict[str, Any]]
    tag_mentions_raw: list[dict[str, Any]]
    final_report: dict[str, Any]
    final_manifest: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MatchHit:
    method: str
    quality: str
    block_indexes: tuple[int, ...]
    matched_aliases: tuple[str, ...] = ()
    mention_ids: tuple[str, ...] = ()
    needs_review: bool = False
    review_reasons: tuple[str, ...] = ()


@dataclass
class SourceWindowDraft:
    tag_id: str
    canonical_tag_ru: str
    canonical_tag_latin: str
    entity_type: str
    doc_id: str
    document_name: str
    mention_ids: list[str]
    matched_aliases: list[str]
    block_ids: list[str]
    block_indexes: list[int]
    heading_context: list[str]
    window_text: str
    window_char_length: int
    match_method: str
    window_quality: str
    needs_review: bool
    review_reasons: list[str]
    document_char_length: int
    coverage_ratio_estimate: float

    def to_dict(self, window_id: str) -> dict[str, Any]:
        return {
            "window_id": window_id,
            "tag_id": self.tag_id,
            "canonical_tag_ru": self.canonical_tag_ru,
            "canonical_tag_latin": self.canonical_tag_latin,
            "entity_type": self.entity_type,
            "doc_id": self.doc_id,
            "document_name": self.document_name,
            "mention_ids": self.mention_ids,
            "matched_aliases": self.matched_aliases,
            "block_ids": self.block_ids,
            "block_indexes": self.block_indexes,
            "heading_context": self.heading_context,
            "window_text": self.window_text,
            "window_char_length": self.window_char_length,
            "match_method": self.match_method,
            "window_quality": self.window_quality,
            "needs_review": self.needs_review,
            "review_reasons": self.review_reasons,
            "document_char_length": self.document_char_length,
            "coverage_ratio_estimate": self.coverage_ratio_estimate,
        }

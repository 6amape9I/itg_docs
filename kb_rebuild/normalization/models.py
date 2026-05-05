from __future__ import annotations

from dataclasses import dataclass
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class TaggingRecord:
    line_number: int
    data: JsonDict


@dataclass(frozen=True)
class TagMention:
    mention_id: str
    doc_id: str
    document_name: str
    entity_index: int
    surface: str
    canonical_candidate_ru: str
    canonical_candidate_latin: str
    entity_type: str
    tag_role: str
    article_candidate: bool
    is_primary: bool
    confidence: float
    evidence_quotes: list[str]
    quote_validation_status: str
    quote_validation_details: list[Any]
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    source_file: str

    @property
    def raw_value(self) -> str:
        return self.canonical_candidate_ru.strip() or self.surface.strip()

    def to_dict(self) -> JsonDict:
        return {
            "mention_id": self.mention_id,
            "doc_id": self.doc_id,
            "document_name": self.document_name,
            "entity_index": self.entity_index,
            "surface": self.surface,
            "canonical_candidate_ru": self.canonical_candidate_ru,
            "canonical_candidate_latin": self.canonical_candidate_latin,
            "entity_type": self.entity_type,
            "tag_role": self.tag_role,
            "article_candidate": self.article_candidate,
            "is_primary": self.is_primary,
            "confidence": self.confidence,
            "evidence_quotes": self.evidence_quotes,
            "quote_validation_status": self.quote_validation_status,
            "quote_validation_details": self.quote_validation_details,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "source_file": self.source_file,
        }


@dataclass(frozen=True)
class NormalizedMention:
    mention_id: str
    doc_id: str
    document_name: str
    raw: JsonDict
    normalized: JsonDict
    entity_type: str
    tag_role: str
    article_candidate: bool
    is_primary: bool
    confidence: float
    evidence_quotes: list[str]
    quote_validation_status: str
    quote_validation_details: list[Any]
    normalization_flags: list[str]
    suspicious_flags: list[str]
    source_file: str

    @property
    def primary_norm(self) -> str:
        return str(self.normalized.get("primary_norm", ""))

    @property
    def raw_value(self) -> str:
        raw_candidate = str(self.raw.get("canonical_candidate_ru", "")).strip()
        return raw_candidate or str(self.raw.get("surface", "")).strip()

    def to_dict(self) -> JsonDict:
        return {
            "mention_id": self.mention_id,
            "doc_id": self.doc_id,
            "document_name": self.document_name,
            "raw": dict(self.raw),
            "normalized": dict(self.normalized),
            "entity_type": self.entity_type,
            "tag_role": self.tag_role,
            "article_candidate": self.article_candidate,
            "is_primary": self.is_primary,
            "confidence": self.confidence,
            "evidence_quotes": self.evidence_quotes,
            "quote_validation_status": self.quote_validation_status,
            "quote_validation_details": self.quote_validation_details,
            "normalization_flags": self.normalization_flags,
            "suspicious_flags": self.suspicious_flags,
            "source_file": self.source_file,
        }


@dataclass(frozen=True)
class AutoCluster:
    auto_cluster_id: str
    entity_type: str
    auto_cluster_key: str
    canonical_display_candidate: str
    canonical_latin_candidate: str
    aliases: list[str]
    normalized_aliases: list[str]
    mention_ids: list[str]
    documents_count: int
    mentions_count: int
    roles_count: dict[str, int]
    article_candidate_count: int
    context_only_count: int
    folder_candidate_count: int
    quote_not_found_count: int
    confidence_stats: JsonDict
    quote_status_count: dict[str, int]
    normalization_method: str
    review_required: bool
    review_reasons: list[str]

    def to_dict(self) -> JsonDict:
        return {
            "auto_cluster_id": self.auto_cluster_id,
            "entity_type": self.entity_type,
            "auto_cluster_key": self.auto_cluster_key,
            "canonical_display_candidate": self.canonical_display_candidate,
            "canonical_latin_candidate": self.canonical_latin_candidate,
            "aliases": self.aliases,
            "normalized_aliases": self.normalized_aliases,
            "mention_ids": self.mention_ids,
            "documents_count": self.documents_count,
            "mentions_count": self.mentions_count,
            "roles_count": self.roles_count,
            "article_candidate_count": self.article_candidate_count,
            "context_only_count": self.context_only_count,
            "folder_candidate_count": self.folder_candidate_count,
            "quote_not_found_count": self.quote_not_found_count,
            "confidence_stats": self.confidence_stats,
            "quote_status_count": self.quote_status_count,
            "normalization_method": self.normalization_method,
            "review_required": self.review_required,
            "review_reasons": self.review_reasons,
        }

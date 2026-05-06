from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


STAGE = "article_a1_entity_json_bootstrap"
STAGE_VERSION = "a1.0"

ARTICLE_STATUSES = {
    "stub_only",
    "review_stub",
    "direct_copy_article",
    "pending_single_doc_extract",
    "pending_low_count_batch_extract",
    "pending_multi_doc_map_reduce",
    "pending_high_frequency_map_reduce",
    "failed_or_blocked",
}

EXTRACTION_STRATEGIES = {
    "single_doc_extract",
    "low_count_batch_extract",
    "multi_doc_map_reduce",
    "high_frequency_map_reduce",
}

PENDING_STATUS_BY_STRATEGY = {
    "single_doc_extract": "pending_single_doc_extract",
    "low_count_batch_extract": "pending_low_count_batch_extract",
    "multi_doc_map_reduce": "pending_multi_doc_map_reduce",
    "high_frequency_map_reduce": "pending_high_frequency_map_reduce",
}

ARTICLE_BLOCKING_REVIEW_MARKERS = {
    "drug_policy_review",
    "drug_trade_name_active_substance_conflict",
    "merge_conflict",
    "entity_type_conflict",
    "rejected_constraint_conflict",
    "unresolved_review",
    "unresolved review",
    "empty_canonical_tag_ru",
    "canonical_empty",
    "unknown_node_id",
    "critical_merge_conflict",
}


@dataclass(frozen=True)
class A1Config:
    data_dir: Path = Path("data")
    articles_planning_dir: Path = Path("data/articles/planning")
    normalization_final_dir: Path = Path("data/normalization/final")
    parsed_dir: Path = Path("data/parsed")
    out_dir: Path = Path("data/articles/a1")
    entities_out_dir: Path = Path("data/articles/entities")
    review_sample_size: int = 500
    low_count_doc_threshold: int = 3
    high_frequency_doc_threshold: int = 20
    overwrite: bool = True

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Path,
        *,
        articles_planning_dir: Path | None = None,
        normalization_final_dir: Path | None = None,
        parsed_dir: Path | None = None,
        out_dir: Path | None = None,
        entities_out_dir: Path | None = None,
        review_sample_size: int = 500,
        low_count_doc_threshold: int = 3,
        high_frequency_doc_threshold: int = 20,
        overwrite: bool = True,
    ) -> "A1Config":
        return cls(
            data_dir=data_dir,
            articles_planning_dir=articles_planning_dir or data_dir / "articles" / "planning",
            normalization_final_dir=normalization_final_dir or data_dir / "normalization" / "final",
            parsed_dir=parsed_dir or data_dir / "parsed",
            out_dir=out_dir or data_dir / "articles" / "a1",
            entities_out_dir=entities_out_dir or data_dir / "articles" / "entities",
            review_sample_size=review_sample_size,
            low_count_doc_threshold=low_count_doc_threshold,
            high_frequency_doc_threshold=high_frequency_doc_threshold,
            overwrite=overwrite,
        )

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


STAGE = "article_a3_evidence_dedupe_fact_grouping"
STAGE_VERSION = "a3.0"

VALID_LAYER = "valid"
REVIEW_LAYER = "review"
REJECTED_LAYER = "rejected"
EVIDENCE_LAYERS = {VALID_LAYER, REVIEW_LAYER, REJECTED_LAYER}

USABLE_QUOTE_STATUSES = {"exact", "normalized_exact"}
REVIEW_QUOTE_STATUSES = {"fuzzy"}
REJECTED_QUOTE_STATUSES = {"not_found"}
QUOTE_STATUSES = USABLE_QUOTE_STATUSES | REVIEW_QUOTE_STATUSES | REJECTED_QUOTE_STATUSES

CORE_FACT_TYPES = {
    "definition",
    "description",
    "classification",
    "mechanism",
    "symptom",
    "diagnostics",
    "treatment",
    "indication",
    "usage_or_dosage",
    "procedure_step",
    "composition",
}

SUPPORTING_FACT_TYPES = {
    "other",
    "interpretation",
    "preparation",
    "prevention",
    "complication",
    "safety_warning",
    "side_effect",
    "contraindication",
    "cause_or_risk_factor",
}

A4_STRATEGIES = {
    "direct_copy_already_done",
    "compile_from_fact_groups",
    "compile_with_review_flag",
    "insufficient_evidence_review",
    "stub_only",
    "review_stub",
}


@dataclass(frozen=True)
class A3Config:
    data_dir: Path = Path("data")
    a2_dir: Path = Path("data/articles/a2/production_v1")
    a1_dir: Path = Path("data/articles/a1")
    normalization_final_dir: Path = Path("data/normalization/final")
    out_dir: Path = Path("data/articles/a3")
    min_confidence: float = 0.5
    allow_fuzzy_for_review: bool = True
    max_quotes_per_fact_group: int = 8
    max_fact_groups_per_tag: int = 200
    overwrite: bool = True

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Path,
        *,
        a2_dir: Path | None = None,
        a1_dir: Path | None = None,
        normalization_final_dir: Path | None = None,
        out_dir: Path | None = None,
        min_confidence: float = 0.5,
        allow_fuzzy_for_review: bool = True,
        max_quotes_per_fact_group: int = 8,
        max_fact_groups_per_tag: int = 200,
        overwrite: bool = True,
    ) -> "A3Config":
        return cls(
            data_dir=data_dir,
            a2_dir=a2_dir or data_dir / "articles" / "a2" / "production_v1",
            a1_dir=a1_dir or data_dir / "articles" / "a1",
            normalization_final_dir=normalization_final_dir or data_dir / "normalization" / "final",
            out_dir=out_dir or data_dir / "articles" / "a3",
            min_confidence=min_confidence,
            allow_fuzzy_for_review=allow_fuzzy_for_review,
            max_quotes_per_fact_group=max_quotes_per_fact_group,
            max_fact_groups_per_tag=max_fact_groups_per_tag,
            overwrite=overwrite,
        )


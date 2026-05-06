from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kb_rebuild.llm.models import GEMINI_3_FLASH_PREVIEW


STAGE = "article_a2_evidence_extraction"
STAGE_VERSION = "a2.0"
PROMPT_VERSION = "a2_evidence_extract_v1"
SCHEMA_VERSION = "a2_evidence_batch_v1"

DECISIONS = {
    "evidence_extracted",
    "no_relevant_information",
    "related_only",
    "needs_review",
    "invalid_or_unclear_source",
}

RELEVANCE_VALUES = {"direct", "related", "not_relevant", "unclear"}

FACT_TYPES = {
    "definition",
    "description",
    "classification",
    "mechanism",
    "cause_or_risk_factor",
    "symptom",
    "diagnostics",
    "treatment",
    "prevention",
    "complication",
    "indication",
    "contraindication",
    "side_effect",
    "usage_or_dosage",
    "procedure_step",
    "preparation",
    "interpretation",
    "composition",
    "safety_warning",
    "related_entity",
    "other",
}

IMPORTANCE_VALUES = {"high", "medium", "low"}
QUOTE_VALIDATION_STATUSES = {"exact", "normalized_exact", "fuzzy", "not_found"}
EXTRACTION_STRATEGIES = {
    "single_doc_extract",
    "low_count_batch_extract",
    "multi_doc_map_reduce",
    "high_frequency_map_reduce",
}
PRIORITIES = {"high", "medium", "low"}


@dataclass(frozen=True)
class A2Config:
    data_dir: Path = Path("data")
    a1_dir: Path = Path("data/articles/a1")
    planning_dir: Path = Path("data/articles/planning")
    normalization_final_dir: Path = Path("data/normalization/final")
    out_dir: Path = Path("data/articles/a2")
    provider: str = "gemini_direct"
    model: str = GEMINI_3_FLASH_PREVIEW
    structured_output_mode: str = "gemini_schema"
    limit: int | None = None
    task_filter: str = "all"
    strategy_filter: tuple[str, ...] = tuple(sorted(EXTRACTION_STRATEGIES))
    priority_filter: tuple[str, ...] = tuple(sorted(PRIORITIES))
    max_tasks_per_batch: int = 8
    batch_char_limit: int = 60000
    max_inflight: int = 8
    max_retries: int = 3
    max_output_tokens: int = 12000
    repair_max_output_tokens: int = 24000
    thinking_level: str | None = "minimal"
    max_cost_usd: float = 20.0
    retry_failures: bool = False
    resume: bool = True
    experiment_name: str | None = None
    temperature: float = 0.0

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Path,
        *,
        a1_dir: Path | None = None,
        planning_dir: Path | None = None,
        normalization_final_dir: Path | None = None,
        out_dir: Path | None = None,
        provider: str = "gemini_direct",
        model: str = GEMINI_3_FLASH_PREVIEW,
        structured_output_mode: str = "gemini_schema",
        limit: int | None = None,
        task_filter: str = "all",
        strategy_filter: tuple[str, ...] | None = None,
        priority_filter: tuple[str, ...] | None = None,
        max_tasks_per_batch: int = 8,
        batch_char_limit: int = 60000,
        max_inflight: int = 8,
        max_retries: int = 3,
        max_output_tokens: int = 12000,
        repair_max_output_tokens: int = 24000,
        thinking_level: str | None = "minimal",
        max_cost_usd: float = 20.0,
        retry_failures: bool = False,
        resume: bool = True,
        experiment_name: str | None = None,
    ) -> "A2Config":
        return cls(
            data_dir=data_dir,
            a1_dir=a1_dir or data_dir / "articles" / "a1",
            planning_dir=planning_dir or data_dir / "articles" / "planning",
            normalization_final_dir=normalization_final_dir or data_dir / "normalization" / "final",
            out_dir=out_dir or data_dir / "articles" / "a2",
            provider=provider,
            model=model,
            structured_output_mode=structured_output_mode,
            limit=limit,
            task_filter=task_filter,
            strategy_filter=strategy_filter or tuple(sorted(EXTRACTION_STRATEGIES)),
            priority_filter=priority_filter or tuple(sorted(PRIORITIES)),
            max_tasks_per_batch=max_tasks_per_batch,
            batch_char_limit=batch_char_limit,
            max_inflight=max_inflight,
            max_retries=max_retries,
            max_output_tokens=max_output_tokens,
            repair_max_output_tokens=repair_max_output_tokens,
            thinking_level=thinking_level,
            max_cost_usd=max_cost_usd,
            retry_failures=retry_failures,
            resume=resume,
            experiment_name=experiment_name,
        )


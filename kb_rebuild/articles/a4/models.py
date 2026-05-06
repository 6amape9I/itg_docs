from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kb_rebuild.llm.models import GEMINI_3_FLASH_PREVIEW


STAGE = "article_a4_article_compilation"
STAGE_VERSION = "a4.0"
PROMPT_VERSION = "a4_article_compile_v1"
SCHEMA_VERSION = "a4_article_draft_v1"

COMPILABLE_STRATEGIES = {"compile_from_fact_groups", "compile_with_review_flag"}
NON_COMPILABLE_STRATEGIES = {
    "direct_copy_already_done",
    "stub_only",
    "review_stub",
    "insufficient_evidence_review",
}
A4_STRATEGIES = COMPILABLE_STRATEGIES | NON_COMPILABLE_STRATEGIES
ARTICLE_STATUSES = {
    "compiled_article",
    "compiled_with_review_flag",
    "insufficient_evidence_review",
    "invalid_or_unclear",
}

ARTICLE_SECTIONS: dict[str, list[str]] = {
    "disease": [
        "Что это",
        "Причины и факторы риска",
        "Симптомы",
        "Диагностика",
        "Лечение",
        "Профилактика",
        "Осложнения",
        "Когда обращаться к врачу",
        "Связанные сведения",
    ],
    "drug_trade_name": [
        "Что это",
        "Показания",
        "Применение",
        "Противопоказания",
        "Побочные эффекты",
        "Особые указания",
        "Связанные сведения",
    ],
    "supplement": ["Что это", "Состав", "Для чего применяется", "Способ применения", "Предосторожности", "Связанные сведения"],
    "diagnostic_method": [
        "Что это",
        "Для чего применяется",
        "Как проводится",
        "Что показывает",
        "Подготовка",
        "Ограничения и особенности",
        "Связанные сведения",
    ],
    "procedure": ["Что это", "Когда применяется", "Порядок выполнения", "Подготовка", "Меры безопасности", "Ограничения"],
    "instruction": ["Что это", "Когда применяется", "Порядок выполнения", "Подготовка", "Меры безопасности", "Ограничения"],
    "microorganism": [
        "Что это",
        "Классификация",
        "Связанные заболевания",
        "Диагностика",
        "Лечение и профилактика",
        "Особенности",
    ],
}
GENERIC_SECTIONS = ["Что это", "Описание", "Значение", "Диагностика или применение", "Связанные сведения"]


@dataclass(frozen=True)
class A4Config:
    data_dir: Path = Path("data")
    a3_dir: Path = Path("data/articles/a3")
    a1_dir: Path = Path("data/articles/a1")
    entities_dir: Path = Path("data/articles/entities")
    normalization_final_dir: Path = Path("data/normalization/final")
    out_dir: Path = Path("data/articles/a4/experiments/smoke_200")
    provider: str = "gemini_direct"
    model: str = GEMINI_3_FLASH_PREVIEW
    structured_output_mode: str = "gemini_schema"
    limit: int | None = None
    strategy_filter: tuple[str, ...] = tuple(sorted(COMPILABLE_STRATEGIES))
    entity_type_filter: tuple[str, ...] | None = None
    priority_filter: tuple[str, ...] = ("high", "medium", "low")
    max_tags_per_batch: int = 2
    max_fact_groups_per_tag: int = 80
    max_quotes_per_tag: int = 120
    batch_char_limit: int = 70000
    max_inflight: int = 8
    max_retries: int = 3
    max_output_tokens: int = 16000
    repair_max_output_tokens: int = 32000
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
        a3_dir: Path | None = None,
        a1_dir: Path | None = None,
        entities_dir: Path | None = None,
        normalization_final_dir: Path | None = None,
        out_dir: Path | None = None,
        provider: str = "gemini_direct",
        model: str = GEMINI_3_FLASH_PREVIEW,
        structured_output_mode: str = "gemini_schema",
        limit: int | None = None,
        strategy_filter: tuple[str, ...] | None = None,
        entity_type_filter: tuple[str, ...] | None = None,
        priority_filter: tuple[str, ...] | None = None,
        max_tags_per_batch: int = 2,
        max_fact_groups_per_tag: int = 80,
        max_quotes_per_tag: int = 120,
        batch_char_limit: int = 70000,
        max_inflight: int = 8,
        max_retries: int = 3,
        max_output_tokens: int = 16000,
        repair_max_output_tokens: int = 32000,
        thinking_level: str | None = "minimal",
        max_cost_usd: float = 20.0,
        retry_failures: bool = False,
        resume: bool = True,
        experiment_name: str | None = None,
    ) -> "A4Config":
        return cls(
            data_dir=data_dir,
            a3_dir=a3_dir or data_dir / "articles" / "a3",
            a1_dir=a1_dir or data_dir / "articles" / "a1",
            entities_dir=entities_dir or data_dir / "articles" / "entities",
            normalization_final_dir=normalization_final_dir or data_dir / "normalization" / "final",
            out_dir=out_dir or data_dir / "articles" / "a4" / "experiments" / "smoke_200",
            provider=provider,
            model=model,
            structured_output_mode=structured_output_mode,
            limit=limit,
            strategy_filter=strategy_filter or tuple(sorted(COMPILABLE_STRATEGIES)),
            entity_type_filter=entity_type_filter,
            priority_filter=priority_filter or ("high", "medium", "low"),
            max_tags_per_batch=max_tags_per_batch,
            max_fact_groups_per_tag=max_fact_groups_per_tag,
            max_quotes_per_tag=max_quotes_per_tag,
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


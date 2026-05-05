from __future__ import annotations

from dataclasses import dataclass


OPENROUTER_DEEPSEEK_FLASH = "deepseek/deepseek-v4-flash"
OPENROUTER_DEEPSEEK_PRO = "deepseek/deepseek-v4-pro"
OPENROUTER_GEMINI_FLASH_TAGGING_MODEL = "google/gemini-3-flash-preview"
OPENROUTER_GEMINI_FLASH_LITE_FALLBACK = "google/gemini-3.1-flash-lite-preview"

GEMINI_3_FLASH_PREVIEW = "gemini-3-flash-preview"
GEMINI_3_FLASH_LATEST = "gemini-3-flash-latest"
GEMINI_FLASH_LATEST = "gemini-flash-latest"
GEMINI_3_PRO_PREVIEW = "gemini-3-pro-preview"
GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
GEMINI_2_5_PRO = "gemini-2.5-pro"
GEMINI_2_0_FLASH = "gemini-2.0-flash"

PRIMARY_TAGGING_MODEL = GEMINI_3_FLASH_PREVIEW
NORMALIZATION_MODEL = GEMINI_3_PRO_PREVIEW
FALLBACK_TAGGING_MODEL = GEMINI_2_5_FLASH_LITE
GEMINI_FLASH_TAGGING_MODEL = GEMINI_3_FLASH_PREVIEW
GEMINI_FLASH_MODEL = GEMINI_FLASH_TAGGING_MODEL


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_million_tokens: float
    output_usd_per_million_tokens: float


MODEL_PRICING: dict[str, ModelPricing] = {
    OPENROUTER_DEEPSEEK_FLASH: ModelPricing(
        input_usd_per_million_tokens=0.14,
        output_usd_per_million_tokens=0.28,
    ),
    OPENROUTER_DEEPSEEK_PRO: ModelPricing(
        input_usd_per_million_tokens=0.435,
        output_usd_per_million_tokens=0.87,
    ),
    OPENROUTER_GEMINI_FLASH_LITE_FALLBACK: ModelPricing(
        input_usd_per_million_tokens=0.25,
        output_usd_per_million_tokens=1.50,
    ),
    OPENROUTER_GEMINI_FLASH_TAGGING_MODEL: ModelPricing(
        input_usd_per_million_tokens=0.50,
        output_usd_per_million_tokens=3.00,
    ),
    GEMINI_3_FLASH_PREVIEW: ModelPricing(
        input_usd_per_million_tokens=0.50,
        output_usd_per_million_tokens=3.00,
    ),
    GEMINI_3_FLASH_LATEST: ModelPricing(
        input_usd_per_million_tokens=0.50,
        output_usd_per_million_tokens=3.00,
    ),
    GEMINI_FLASH_LATEST: ModelPricing(
        input_usd_per_million_tokens=0.50,
        output_usd_per_million_tokens=3.00,
    ),
    GEMINI_3_PRO_PREVIEW: ModelPricing(
        input_usd_per_million_tokens=2.00,
        output_usd_per_million_tokens=12.00,
    ),
}


MODEL_PRESETS: dict[str, str] = {
    "deepseek-flash": OPENROUTER_DEEPSEEK_FLASH,
    "gemini-flash": GEMINI_FLASH_TAGGING_MODEL,
    "openrouter-gemini-flash": OPENROUTER_GEMINI_FLASH_TAGGING_MODEL,
}


MODEL_ROLE_MAPPING: dict[str, str] = {
    "TAGGING_PRIMARY": GEMINI_3_FLASH_PREVIEW,
    "EVIDENCE_EXTRACTION_PRIMARY": GEMINI_3_FLASH_PREVIEW,
    "TAG_NORMALIZATION_PRIMARY": GEMINI_3_PRO_PREVIEW,
    "ARTICLE_COMPILATION_COMPLEX": GEMINI_3_PRO_PREVIEW,
    "ARTICLE_COMPILATION_SIMPLE": GEMINI_3_FLASH_PREVIEW,
    "FOLDER_HIERARCHY_PRIMARY": GEMINI_3_FLASH_PREVIEW,
    "QA_AUDIT_PRIMARY": GEMINI_3_FLASH_PREVIEW,
    "QA_AUDIT_HARD": GEMINI_3_PRO_PREVIEW,
}


def model_from_preset(preset: str | None, explicit_model: str) -> str:
    if not preset:
        return explicit_model
    if preset not in MODEL_PRESETS:
        known = ", ".join(sorted(MODEL_PRESETS))
        raise ValueError(f"unknown model preset: {preset}; known: {known}")
    return MODEL_PRESETS[preset]


def model_from_role(model_role: str | None, explicit_model: str) -> str:
    if not model_role:
        return explicit_model
    if model_role not in MODEL_ROLE_MAPPING:
        known = ", ".join(sorted(MODEL_ROLE_MAPPING))
        raise ValueError(f"unknown model role: {model_role}; known: {known}")
    return MODEL_ROLE_MAPPING[model_role]


def validate_model_id(model_id: str) -> None:
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("model id must be a non-empty string")
    normalized = model_id.strip().lower()
    if normalized == "latest" or normalized.endswith(":latest") or normalized.endswith("/latest"):
        raise ValueError(f"latest model aliases are forbidden: {model_id}")
    if model_id not in MODEL_PRICING:
        known = ", ".join(sorted(MODEL_PRICING))
        raise ValueError(f"model has no configured pricing and cannot be budget-limited: {model_id}; known: {known}")


def validate_direct_gemini_model_id(model_id: str) -> None:
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("Gemini model id must be a non-empty string")
    normalized = model_id.strip().lower()
    if normalized == "latest" or normalized.endswith(":latest") or normalized.endswith("/latest"):
        raise ValueError(f"latest model aliases are forbidden: {model_id}")
    if model_id.startswith("models/") or "/" in model_id:
        raise ValueError(f"direct Gemini model id must not use provider prefixes: {model_id}")
    validate_model_id(model_id)


def estimate_tokens_from_chars(chars_count: int) -> int:
    if chars_count <= 0:
        return 0
    return max(1, (chars_count + 3) // 4)


def estimate_request_cost_usd(model_id: str, input_chars: int, max_output_tokens: int) -> float:
    validate_model_id(model_id)
    pricing = MODEL_PRICING[model_id]
    input_tokens = estimate_tokens_from_chars(input_chars)
    return calculate_cost_usd(
        model_id=model_id,
        prompt_tokens=input_tokens,
        completion_tokens=max_output_tokens,
        reasoning_tokens=0,
    )


def calculate_cost_usd(
    model_id: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> float:
    validate_model_id(model_id)
    pricing = MODEL_PRICING[model_id]
    input_cost = (max(prompt_tokens, 0) / 1_000_000) * pricing.input_usd_per_million_tokens
    output_token_count = max(completion_tokens, 0) + max(reasoning_tokens, 0)
    output_cost = (output_token_count / 1_000_000) * pricing.output_usd_per_million_tokens
    return round(input_cost + output_cost, 8)

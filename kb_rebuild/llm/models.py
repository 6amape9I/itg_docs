from __future__ import annotations

from dataclasses import dataclass


PRIMARY_TAGGING_MODEL = "deepseek/deepseek-v4-flash"
NORMALIZATION_MODEL = "deepseek/deepseek-v4-pro"
FALLBACK_TAGGING_MODEL = "google/gemini-3.1-flash-lite-preview"
GEMINI_FLASH_TAGGING_MODEL = "google/gemini-3-flash-preview"
GEMINI_FLASH_MODEL = GEMINI_FLASH_TAGGING_MODEL


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_million_tokens: float
    output_usd_per_million_tokens: float


MODEL_PRICING: dict[str, ModelPricing] = {
    PRIMARY_TAGGING_MODEL: ModelPricing(
        input_usd_per_million_tokens=0.14,
        output_usd_per_million_tokens=0.28,
    ),
    NORMALIZATION_MODEL: ModelPricing(
        input_usd_per_million_tokens=0.435,
        output_usd_per_million_tokens=0.87,
    ),
    FALLBACK_TAGGING_MODEL: ModelPricing(
        input_usd_per_million_tokens=0.25,
        output_usd_per_million_tokens=1.50,
    ),
    GEMINI_FLASH_TAGGING_MODEL: ModelPricing(
        input_usd_per_million_tokens=0.50,
        output_usd_per_million_tokens=3.00,
    ),
}


MODEL_PRESETS: dict[str, str] = {
    "deepseek-flash": PRIMARY_TAGGING_MODEL,
    "gemini-flash": GEMINI_FLASH_TAGGING_MODEL,
}


def model_from_preset(preset: str | None, explicit_model: str) -> str:
    if not preset:
        return explicit_model
    if preset not in MODEL_PRESETS:
        known = ", ".join(sorted(MODEL_PRESETS))
        raise ValueError(f"unknown model preset: {preset}; known: {known}")
    return MODEL_PRESETS[preset]


def validate_model_id(model_id: str) -> None:
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("model id must be a non-empty string")
    normalized = model_id.strip().lower()
    if normalized == "latest" or normalized.endswith(":latest") or normalized.endswith("/latest"):
        raise ValueError(f"latest model aliases are forbidden: {model_id}")
    if model_id not in MODEL_PRICING:
        known = ", ".join(sorted(MODEL_PRICING))
        raise ValueError(f"model has no configured pricing and cannot be budget-limited: {model_id}; known: {known}")


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

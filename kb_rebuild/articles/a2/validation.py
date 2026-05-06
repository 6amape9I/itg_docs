from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class QuoteValidationResult:
    status: str
    reason: str = ""
    review_required: bool = False


def validate_quote(quote: str, window_text: str) -> QuoteValidationResult:
    raw_quote = str(quote or "").strip()
    text = str(window_text or "")
    if not raw_quote:
        return QuoteValidationResult("not_found", "empty_quote", True)
    if _has_ellipsis(raw_quote):
        return QuoteValidationResult("not_found", "ellipsis_or_stitched_quote", True)
    if raw_quote in text:
        return QuoteValidationResult("exact")

    normalized_quote = normalize_for_quote(raw_quote)
    normalized_text = normalize_for_quote(text)
    if normalized_quote and normalized_quote in normalized_text:
        return QuoteValidationResult("normalized_exact")

    if len(normalized_quote) >= 32 and _fuzzy_contiguous_match(normalized_quote, normalized_text):
        return QuoteValidationResult("fuzzy", "contiguous_fuzzy_match", True)
    return QuoteValidationResult("not_found", "quote_not_found", True)


def normalize_for_quote(value: str) -> str:
    normalized = value.replace("\u00a0", " ").replace("ё", "е").replace("Ё", "Е").lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _has_ellipsis(value: str) -> bool:
    return "..." in value or "…" in value


def _fuzzy_contiguous_match(quote: str, text: str) -> bool:
    if not quote or not text or len(quote) > len(text):
        return False
    if len(quote) > 500:
        return False
    window_size = len(quote)
    best = 0.0
    step = max(1, window_size // 12)
    for start in range(0, len(text) - window_size + 1, step):
        candidate = text[start : start + window_size]
        ratio = SequenceMatcher(None, quote, candidate).ratio()
        if ratio > best:
            best = ratio
        if ratio >= 0.94:
            return True
    return best >= 0.96

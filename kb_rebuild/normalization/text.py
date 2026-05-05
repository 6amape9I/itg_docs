from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Any


DASH_CHARS = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
OUTER_QUOTES = "\"'«»“”„‟‘’‚‛`"
GREEK_LETTERS = {
    "α": "альфа",
    "Α": "альфа",
    "β": "бета",
    "Β": "бета",
    "γ": "гамма",
    "Γ": "гамма",
    "δ": "дельта",
    "Δ": "дельта",
}
SPECIFICITY_MODIFIERS = {
    "острый",
    "острая",
    "острое",
    "острые",
    "хронический",
    "хроническая",
    "хроническое",
    "хронические",
    "врожденный",
    "врожденная",
    "врожденное",
    "врожденные",
    "приобретенный",
    "приобретенная",
    "приобретенное",
    "приобретенные",
    "первичный",
    "первичная",
    "первичное",
    "первичные",
    "вторичный",
    "вторичная",
    "вторичное",
    "вторичные",
    "идиопатический",
    "идиопатическая",
    "идиопатическое",
    "идиопатические",
    "аутоиммунный",
    "аутоиммунная",
    "аутоиммунное",
    "аутоиммунные",
    "наследственный",
    "наследственная",
    "наследственное",
    "наследственные",
    "метастатический",
    "метастатическая",
    "метастатическое",
    "метастатические",
}

DOSAGE_RE = re.compile(
    r"(?iu)(?:\b\d+(?:[,.]\d+)?\s*(?:мг|мкг|мл|г|%|шт|штук)\b|(?:№|n)\s*\d+\b|\b\d+\s*%)"
)
PACKAGING_RE = re.compile(
    r"(?iu)(?:\b(?:таблетки|таблетка|капсулы|капсула|ампулы|флакон|флаконы|"
    r"пакетики|саше|пастилки|суппозитории|шт|штук)\b|(?:№|n)\s*\d+\b)"
)
CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)
LATIN_RE = re.compile(r"[a-z]", re.IGNORECASE)


@dataclass(frozen=True)
class ProductNormalization:
    value: str
    changed: bool
    too_short: bool


def normalize_basic_text(value: str | None) -> str:
    text = "" if value is None else str(value)
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00a0", " ")
    for source, target in GREEK_LETTERS.items():
        text = text.replace(source, target)
    for dash in DASH_CHARS:
        text = text.replace(dash, "-")

    text = text.strip()
    text = _strip_outer_quotes(text)
    text = _strip_outer_brackets(text)
    text = text.lower().replace("ё", "е")
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"[\s\.,:;]+$", "", text).strip()
    text = _strip_outer_quotes(text)
    text = _strip_outer_brackets(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_latin_text(value: str | None) -> str:
    return normalize_basic_text(value)


def normalize_greek_letters(value: str | None) -> str:
    text = "" if value is None else str(value)
    for source, target in GREEK_LETTERS.items():
        text = text.replace(source, target)
    return text


def normalize_drug_trade_name(value: str | None) -> str:
    return normalize_product_name(value, "drug_trade_name").value


def normalize_supplement_name(value: str | None) -> str:
    return normalize_product_name(value, "supplement").value


def normalize_product_name(value: str | None, entity_type: str) -> ProductNormalization:
    basic = normalize_basic_text(value)
    cleaned = basic
    cleaned = re.sub(r"[(),;:]+", " ", cleaned)
    cleaned = DOSAGE_RE.sub(" ", cleaned)

    phrases = [
        "биологически активная добавка",
        "для наружного применения",
        "для приема внутрь",
        "покрытые оболочкой",
        "пленочной оболочкой",
        "кишечнорастворимые",
    ]
    for phrase in phrases:
        cleaned = re.sub(rf"(?iu)(?<!\w){re.escape(phrase)}(?!\w)", " ", cleaned)

    form_terms = {
        "таблетки",
        "таблетка",
        "капсулы",
        "капсула",
        "гель",
        "мазь",
        "крем",
        "раствор",
        "сироп",
        "спрей",
        "капли",
        "порошок",
        "саше",
        "суспензия",
        "ампулы",
        "флакон",
        "флаконы",
        "пакетики",
        "пастилки",
        "суппозитории",
        "мг",
        "мкг",
        "мл",
        "г",
        "шт",
        "штук",
        "n",
    }
    if entity_type == "supplement":
        form_terms.update({"бад"})
    terms_re = "|".join(re.escape(term) for term in sorted(form_terms, key=len, reverse=True))
    cleaned = re.sub(rf"(?iu)\b(?:{terms_re})\b", " ", cleaned)
    cleaned = cleaned.replace("№", " ")
    cleaned = cleaned.replace("%", " ")
    cleaned = re.sub(r"\s*-\s*", "-", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    cleaned = normalize_basic_text(cleaned)

    compact = re.sub(r"[\W_]+", "", cleaned, flags=re.UNICODE)
    too_short = bool(cleaned) and len(compact) < 3
    if not cleaned or too_short:
        return ProductNormalization(value=basic, changed=False, too_short=True)
    return ProductNormalization(value=cleaned, changed=cleaned != basic, too_short=False)


def normalize_drug_class(value: str | None) -> str:
    normalized = normalize_basic_text(value)
    normalized = normalized.replace("бета лактамные", "бета-лактамные")
    if normalized == "бета-лактамы":
        return "бета-лактамные антибиотики"
    return normalized


def normalize_microorganism_text(value: str | None) -> str:
    normalized = normalize_basic_text(value)
    normalized = re.sub(r"\b([a-z])\.\s*", r"\1 ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def diagnostic_abbreviation_candidate(value: str | None) -> str:
    normalized = normalize_basic_text(value)
    mapping = {
        "иммуноферментный анализ": "ифа",
        "enzyme-linked immunosorbent assay": "elisa",
        "полимеразная цепная реакция": "пцр",
    }
    return mapping.get(normalized, "")


def has_specificity_modifier(value: str | None) -> bool:
    normalized = normalize_basic_text(value)
    tokens = set(re.findall(r"[\w-]+", normalized, flags=re.UNICODE))
    return bool(tokens & SPECIFICITY_MODIFIERS)


def contains_dosage(value: str | None) -> bool:
    return bool(DOSAGE_RE.search(normalize_basic_text(value)))


def contains_packaging(value: str | None) -> bool:
    return bool(PACKAGING_RE.search(normalize_basic_text(value)))


def quote_has_issue(
    quote_validation_status: str,
    quote_validation_details: list[Any],
    evidence_quotes: list[str],
) -> bool:
    status = quote_validation_status.lower()
    if "not_found" in status:
        return True
    if not evidence_quotes or any(not str(quote).strip() for quote in evidence_quotes):
        return True
    if any("..." in str(quote) or "…" in str(quote) for quote in evidence_quotes):
        return True
    return _details_contain_not_found(quote_validation_details)


def detect_suspicious_flags(
    *,
    surface: str,
    canonical_candidate_ru: str,
    primary_norm: str,
    entity_type: str,
    tag_role: str,
    confidence: float,
    quote_validation_status: str,
    quote_validation_details: list[Any],
    evidence_quotes: list[str],
    document_name: str = "",
    product_name_norm: str = "",
    product_too_short: bool = False,
) -> list[str]:
    flags: list[str] = []
    raw_primary = canonical_candidate_ru.strip() or surface.strip()
    compact_primary = re.sub(r"[\W_]+", "", primary_norm, flags=re.UNICODE)

    if not surface.strip():
        flags.append("empty_surface")
    if not canonical_candidate_ru.strip():
        flags.append("empty_canonical_candidate_ru")
    if primary_norm and len(compact_primary) <= 3:
        flags.extend(["very_short_alias", "possible_abbreviation"])
    if contains_dosage(raw_primary):
        flags.append("contains_dosage")
    if contains_packaging(raw_primary):
        flags.append("contains_packaging")
    if entity_type in {"drug_trade_name", "supplement"} and contains_dosage(raw_primary):
        flags.append("possible_trade_name_with_dosage")
    if entity_type == "disease" and has_specificity_modifier(raw_primary):
        flags.extend(["contains_specificity_modifier", "has_specificity_modifier", "possible_parent_child_term"])
    if quote_has_issue(quote_validation_status, quote_validation_details, evidence_quotes):
        flags.append("quote_not_found")
    if confidence < 0.75:
        flags.append("low_confidence")
    if tag_role == "context_only":
        flags.append("context_only")
    if tag_role == "folder_candidate":
        flags.append("folder_candidate")
    if is_latin_only(raw_primary):
        flags.append("latin_only")
    if has_mixed_cyrillic_latin(raw_primary):
        flags.append("mixed_cyrillic_latin")
    if not evidence_quotes and document_name and normalize_basic_text(document_name) == primary_norm:
        flags.append("possible_name_only_entity")
    if product_too_short:
        flags.append("product_norm_too_short")
    if entity_type == "microorganism" and is_possible_genus_level_entity(raw_primary):
        flags.append("possible_genus_level_entity")
    if entity_type == "diagnostic_method" and diagnostic_abbreviation_candidate(raw_primary):
        flags.append("abbreviation_candidate")
    if product_name_norm and product_name_norm != primary_norm:
        flags.append("product_name_cleanup_applied")

    return sorted(set(flags))


def normalization_flags_for_values(*values: str) -> list[str]:
    flags: set[str] = set()
    for value in values:
        raw = "" if value is None else str(value)
        stripped = raw.strip()
        normalized = normalize_basic_text(raw)
        if raw != stripped:
            flags.add("trim")
        if stripped.lower() != stripped:
            flags.add("lowercase")
        if "ё" in raw or "Ё" in raw:
            flags.add("yo_to_e")
        if any(ch in raw for ch in DASH_CHARS):
            flags.add("dash_to_hyphen")
        if any(ch in raw for ch in GREEK_LETTERS):
            flags.add("greek_letters")
        if html.unescape(raw) != raw:
            flags.add("html_unescape")
        if unicodedata.normalize("NFKC", raw) != raw:
            flags.add("unicode_nfkc")
        if re.search(r"\s{2,}", raw):
            flags.add("collapse_whitespace")
        if stripped and stripped[0] in OUTER_QUOTES or stripped and stripped[-1] in OUTER_QUOTES:
            flags.add("strip_outer_quotes")
        if re.search(r"[\.,:;]\s*$", stripped):
            flags.add("strip_trailing_punctuation")
        if normalized != stripped.lower().replace("ё", "е"):
            flags.add("safe_string_cleanup")
    return sorted(flags)


def is_latin_only(value: str | None) -> bool:
    text = normalize_basic_text(value)
    return bool(text and LATIN_RE.search(text) and not CYRILLIC_RE.search(text))


def has_mixed_cyrillic_latin(value: str | None) -> bool:
    text = normalize_basic_text(value)
    return bool(CYRILLIC_RE.search(text) and LATIN_RE.search(text))


def is_possible_genus_level_entity(value: str | None) -> bool:
    normalized = normalize_microorganism_text(value)
    if not normalized or " " in normalized or "-" in normalized:
        return False
    return bool(re.fullmatch(r"[a-z]+", normalized)) and len(normalized) >= 4


def quote_issue_type(
    quote_validation_status: str,
    quote_validation_details: list[Any],
    evidence_quotes: list[str],
) -> str:
    if "not_found" in quote_validation_status.lower() or _details_contain_not_found(quote_validation_details):
        return "quote_not_found"
    if not evidence_quotes or any(not str(quote).strip() for quote in evidence_quotes):
        return "empty_quote"
    if any("..." in str(quote) or "…" in str(quote) for quote in evidence_quotes):
        return "truncated_quote"
    return "quote_issue"


def _strip_outer_quotes(value: str) -> str:
    text = value.strip()
    while len(text) >= 2 and text[0] in OUTER_QUOTES and text[-1] in OUTER_QUOTES:
        text = text[1:-1].strip()
    while text and text[0] in OUTER_QUOTES:
        text = text[1:].strip()
    while text and text[-1] in OUTER_QUOTES:
        text = text[:-1].strip()
    return text


def _strip_outer_brackets(value: str) -> str:
    pairs = {"(": ")", "[": "]", "{": "}"}
    text = value.strip()
    changed = True
    while changed and len(text) >= 2:
        changed = False
        closing = pairs.get(text[0])
        if closing and text[-1] == closing:
            inner = text[1:-1].strip()
            if inner:
                text = inner
                changed = True
    return text


def _details_contain_not_found(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_details_contain_not_found(item) for item in value.values())
    if isinstance(value, list):
        return any(_details_contain_not_found(item) for item in value)
    return "not_found" in str(value).lower()

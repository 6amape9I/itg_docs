from __future__ import annotations

import re

from kb_rebuild.normalization.n2.features import tokens
from kb_rebuild.normalization.n2.models import CandidateNode
from kb_rebuild.normalization.text import normalize_basic_text


DIAGNOSTIC_BASES = {
    "мрт",
    "магнитно-резонансная томография",
    "кт",
    "компьютерная томография",
    "мскт",
    "узи",
    "ультразвуковое исследование",
    "рентгенография",
    "рентгенологическое исследование",
    "биопсия",
    "анализ",
    "анализ крови",
    "анализ мочи",
    "генетическое тестирование",
    "секвенирование",
}
DIAGNOSTIC_MODIFIERS = {
    "орбиты",
    "гипофиза",
    "головного мозга",
    "позвоночника",
    "молочных желез",
    "органов грудной клетки",
    "брюшной полости",
    "малого таза",
    "сердца",
    "печени",
    "почки",
    "почек",
    "кожи",
    "зубов",
    "стопы",
    "кисти",
    "сустава",
    "тазобедренного сустава",
    "сетчатки",
    "глаза",
    "легких",
    "лёгких",
}
DISEASE_HEADS = {
    "герминогенная опухоль",
    "опухоль",
    "рак",
    "карцинома",
    "саркома",
    "полип",
    "киста",
    "абсцесс",
    "стеноз",
    "порок",
    "дефект",
    "недостаточность",
    "лейкоз",
    "лимфома",
}
DISEASE_LOCATIONS = {
    "яичка",
    "яичек",
    "яичника",
    "яичников",
    "матки",
    "шейки матки",
    "носа",
    "легкого",
    "легких",
    "лёгкого",
    "лёгких",
    "печени",
    "почки",
    "почек",
    "желудка",
    "кишечника",
    "толстой кишки",
    "тонкой кишки",
    "молочной железы",
    "молочных желез",
    "головного мозга",
    "мозга",
    "спинного мозга",
    "кожи",
    "глаза",
    "сетчатки",
    "орбиты",
    "сердца",
    "костей",
    "сустава",
    "позвоночника",
    "поджелудочной железы",
    "щитовидной железы",
    "надпочечника",
    "надпочечников",
    "желчного пузыря",
}
PROCEDURE_PREFIXES = ("вакцинация против", "профилактика против", "иммунизация против")
ROMAN_TO_INT = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5"}
LETTER_MAP = {"a": "a", "b": "b", "c": "c", "а": "a", "в": "b", "с": "c"}


def scope_conflict_reasons(left: CandidateNode, right: CandidateNode) -> list[str]:
    if left.entity_type != right.entity_type:
        return []
    left_label = normalize_basic_text(left.normalized_label)
    right_label = normalize_basic_text(right.normalized_label)
    if not left_label or not right_label or left_label == right_label:
        return []
    if left.entity_type == "diagnostic_method":
        return _diagnostic_scope_conflicts(left_label, right_label)
    if left.entity_type == "procedure":
        return _procedure_scope_conflicts(left_label, right_label)
    if left.entity_type == "disease":
        return _disease_scope_conflicts(left_label, right_label)
    if left.entity_type == "drug_class":
        return _drug_class_scope_conflicts(left_label, right_label)
    return []


def extract_subtype_markers(label: str) -> set[str]:
    normalized = normalize_basic_text(label)
    markers: set[str] = set()
    for match in re.findall(r"\b(?:тип|type|подтип)\b\s*([0-9]+|[abcавс]|i{1,3}|iv|v)\b", normalized):
        marker = _normalize_type_marker(match)
        if marker:
            markers.add(f"type_{marker}")
    for match in re.findall(r"\bтипа\s+([0-9]+|[abcавс]|i{1,3}|iv|v)\b", normalized):
        marker = _normalize_type_marker(match)
        if marker:
            markers.add(f"type_{marker}")
    for match in re.findall(r"\b([0-9]+)(?:-?го)?\s+типа\b", normalized):
        markers.add(f"type_{match}")
    for match in re.findall(r"\b([0-9]+)\s+множественных\s+типов\b", normalized):
        markers.add(f"type_{match}")
    for match in re.findall(r"\b(i{1,3}|iv|v)\s+типа\b", normalized):
        marker = _normalize_type_marker(match)
        if marker:
            markers.add(f"type_{marker}")
    for match in re.findall(r"\b(?:комплекс|комплекса)\s*([0-9]+|i{1,3}|iv|v)\b", normalized):
        marker = _normalize_complex_marker(match)
        if marker:
            markers.add(f"complex_{marker}")
    markers.update(extract_cellular_markers(normalized))
    return markers


def extract_cellular_markers(label: str) -> set[str]:
    normalized = normalize_basic_text(label)
    markers: set[str] = set()
    if re.search(r"\b(?:b|в)-?клеточн", normalized):
        markers.add("b_cell")
    if re.search(r"\b(?:t|т)-?клеточн", normalized):
        markers.add("t_cell")
    if re.search(r"\bnk-?клеточн", normalized):
        markers.add("nk_cell")
    if "миелоид" in normalized:
        markers.add("myeloid")
    if "лимфоид" in normalized:
        markers.add("lymphoid")
    if "лимфобласт" in normalized:
        markers.add("lymphoblastic")
    if "миелобласт" in normalized:
        markers.add("myeloblastic")
    return markers


def extract_complex_markers(label: str) -> set[str]:
    return {marker for marker in extract_subtype_markers(label) if marker.startswith("complex_")}


def extract_location_markers(label: str) -> set[str]:
    return _matched_phrases(normalize_basic_text(label), DISEASE_LOCATIONS)


def extract_disease_heads(label: str) -> set[str]:
    normalized = normalize_basic_text(label)
    return {head for head in DISEASE_HEADS if head in normalized}


def cellular_conflict(markers: set[str]) -> bool:
    return bool(
        {"b_cell", "t_cell"} <= markers
        or {"myeloid", "lymphoid"} <= markers
        or {"myeloblastic", "lymphoblastic"} <= markers
    )


def _diagnostic_scope_conflicts(left: str, right: str) -> list[str]:
    reasons: set[str] = set()
    left_bases = _diagnostic_bases(left)
    right_bases = _diagnostic_bases(right)
    left_modifiers = _matched_phrases(left, DIAGNOSTIC_MODIFIERS)
    right_modifiers = _matched_phrases(right, DIAGNOSTIC_MODIFIERS)
    if left_bases and right_bases and _diagnostic_bases_overlap(left_bases, right_bases):
        if left_modifiers != right_modifiers and (left_modifiers or right_modifiers):
            reasons.add("diagnostic_method_scope_conflict")
        if _is_base_label(left) != _is_base_label(right):
            reasons.add("diagnostic_method_parent_child_scope")
    return sorted(reasons)


def _procedure_scope_conflicts(left: str, right: str) -> list[str]:
    left_object = _object_after_prefix(left, PROCEDURE_PREFIXES)
    right_object = _object_after_prefix(right, PROCEDURE_PREFIXES)
    if left_object and right_object and left_object != right_object:
        return ["procedure_object_scope_conflict"]
    if _operation_object(left) and _operation_object(right) and _operation_object(left) != _operation_object(right):
        return ["procedure_object_scope_conflict"]
    return []


def _disease_scope_conflicts(left: str, right: str) -> list[str]:
    left_head = _disease_head(left)
    right_head = _disease_head(right)
    if not left_head or left_head != right_head:
        return []
    left_locations = _matched_phrases(left, DISEASE_LOCATIONS)
    right_locations = _matched_phrases(right, DISEASE_LOCATIONS)
    reasons: set[str] = set()
    if left_locations and right_locations and left_locations != right_locations:
        reasons.add("disease_location_conflict")
    if bool(left_locations) != bool(right_locations):
        reasons.add("disease_parent_child_scope")
    return sorted(reasons)


def _drug_class_scope_conflicts(left: str, right: str) -> list[str]:
    left_tokens = set(tokens(left))
    right_tokens = set(tokens(right))
    if left_tokens and right_tokens and (left_tokens < right_tokens or right_tokens < left_tokens):
        return ["drug_class_parent_child_scope"]
    broad_terms = {"антибиотики", "нпвс", "нестероидные противовоспалительные средства"}
    if left in broad_terms or right in broad_terms:
        return ["drug_class_parent_child_scope"]
    return []


def _diagnostic_bases(label: str) -> set[str]:
    bases: set[str] = set()
    for base in sorted(DIAGNOSTIC_BASES, key=len, reverse=True):
        if label == base or label.startswith(f"{base} ") or re.search(rf"\b{re.escape(base)}\b", label):
            bases.add(base)
    return bases


def _diagnostic_bases_overlap(left: set[str], right: set[str]) -> bool:
    return any(_same_diagnostic_base(left_base, right_base) for left_base in left for right_base in right)


def _same_diagnostic_base(left: str, right: str) -> bool:
    groups = [
        {"мрт", "магнитно-резонансная томография"},
        {"кт", "компьютерная томография", "мскт"},
        {"узи", "ультразвуковое исследование"},
        {"рентгенография", "рентгенологическое исследование"},
    ]
    if left == right:
        return True
    return any(left in group and right in group for group in groups)


def _is_base_label(label: str) -> bool:
    return label in DIAGNOSTIC_BASES


def _object_after_prefix(label: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if label.startswith(f"{prefix} "):
            return label[len(prefix) :].strip()
    return ""


def _operation_object(label: str) -> str:
    match = re.match(r"^(?:операция на|трансплантация|пересадка)\s+(.+)$", label)
    return match.group(1).strip() if match else ""


def _disease_head(label: str) -> str:
    for head in sorted(DISEASE_HEADS, key=len, reverse=True):
        if head in label:
            return head
    return ""


def _matched_phrases(label: str, phrases: set[str]) -> set[str]:
    return {phrase for phrase in phrases if phrase in label}


def _normalize_type_marker(value: str) -> str:
    normalized = normalize_basic_text(value)
    if normalized in ROMAN_TO_INT:
        return ROMAN_TO_INT[normalized]
    if normalized in LETTER_MAP:
        return LETTER_MAP[normalized]
    if normalized.isdigit():
        return normalized
    return ""


def _normalize_complex_marker(value: str) -> str:
    normalized = normalize_basic_text(value)
    if normalized in ROMAN_TO_INT:
        return normalized
    if normalized.isdigit():
        reverse = {number: roman for roman, number in ROMAN_TO_INT.items()}
        return reverse.get(normalized, normalized)
    return ""

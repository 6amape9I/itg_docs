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
    "узи",
    "ультразвуковое исследование",
    "рентгенография",
    "биопсия",
}
DIAGNOSTIC_MODIFIERS = {
    "головного мозга",
    "гипофиза",
    "позвоночника",
    "молочных желез",
    "кожи",
    "почки",
    "печени",
    "легких",
    "лёгких",
    "органов грудной клетки",
    "зубов",
    "стопы",
    "кисти",
    "сустава",
    "тазобедренного сустава",
    "сердца",
    "глаза",
    "сетчатки",
}
DISEASE_HEADS = {"полип", "рак", "абсцесс", "киста", "опухоль", "порок", "стеноз"}
DISEASE_LOCATIONS = {
    "матки",
    "носа",
    "шейки матки",
    "молочной железы",
    "желудка",
    "печени",
    "легкого",
    "лёгкого",
    "легких",
    "лёгких",
    "глаза",
    "почки",
    "кожи",
    "желчного пузыря",
}
PROCEDURE_PREFIXES = ("вакцинация против", "профилактика против", "иммунизация против")


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


def _diagnostic_scope_conflicts(left: str, right: str) -> list[str]:
    reasons: set[str] = set()
    left_base = _diagnostic_base(left)
    right_base = _diagnostic_base(right)
    left_modifiers = _matched_phrases(left, DIAGNOSTIC_MODIFIERS)
    right_modifiers = _matched_phrases(right, DIAGNOSTIC_MODIFIERS)
    if left_base and right_base and _same_diagnostic_base(left_base, right_base):
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


def _diagnostic_base(label: str) -> str:
    for base in sorted(DIAGNOSTIC_BASES, key=len, reverse=True):
        if label == base or label.startswith(f"{base} "):
            return base
    return ""


def _same_diagnostic_base(left: str, right: str) -> bool:
    groups = [
        {"мрт", "магнитно-резонансная томография"},
        {"кт", "компьютерная томография"},
        {"узи", "ультразвуковое исследование"},
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
    match = re.match(r"^(?:операция на|трансплантация)\s+(.+)$", label)
    return match.group(1).strip() if match else ""


def _disease_head(label: str) -> str:
    label_tokens = tokens(label)
    for head in DISEASE_HEADS:
        if head in label_tokens:
            return head
    return ""


def _matched_phrases(label: str, phrases: set[str]) -> set[str]:
    return {phrase for phrase in phrases if phrase in label}

from __future__ import annotations

from kb_rebuild.normalization.n2.features import has_strong_reason, short_alias, tokens
from kb_rebuild.normalization.n2.models import CandidateNode
from kb_rebuild.normalization.n2.scope_conflict import scope_conflict_reasons
from kb_rebuild.normalization.text import is_latin_only, normalize_basic_text


def blocking_reasons(left: CandidateNode, right: CandidateNode, candidate_reasons: list[str]) -> list[str]:
    reasons: set[str] = set()
    if left.entity_type != right.entity_type:
        reasons.add("different_entity_type")
        return sorted(reasons)

    if left.entity_type == "disease" and _disease_subtype_conflict(left, right):
        reasons.add("disease_subtype_conflict")

    if left.entity_type == "microorganism" and _taxonomic_level_conflict(left.normalized_label, right.normalized_label):
        reasons.add("taxonomic_level_conflict")

    scope_reasons = scope_conflict_reasons(left, right)
    reasons.update(scope_reasons)

    if _parent_child_suspect(left, right) and not _product_variant_exception(left, right, candidate_reasons):
        reasons.add("parent_child_suspect")
        if left.entity_type in {"disease", "drug_class", "organ_or_body_system", "diagnostic_method", "procedure"}:
            reasons.add("parent_child_blocked")

    if short_alias(left.normalized_label) and short_alias(right.normalized_label) and not has_strong_reason(candidate_reasons):
        reasons.add("short_alias_ambiguous")

    return sorted(reasons)


def risk_reasons(left: CandidateNode, right: CandidateNode) -> list[str]:
    reasons: set[str] = set()
    if left.entity_type == "drug_trade_name" and {"latin_only"} & (set(left.risk_flags) | set(right.risk_flags)):
        reasons.add("possible_brand_substance_conflict")
    reasons.update(scope_conflict_reasons(left, right))
    if _parent_child_suspect(left, right) and not _same_product_variant(left, right):
        reasons.add("parent_child_suspect")
    return sorted(reasons)


def _disease_subtype_conflict(left: CandidateNode, right: CandidateNode) -> bool:
    left_sig = left.subtype_signature or "none"
    right_sig = right.subtype_signature or "none"
    return left_sig != right_sig and (left_sig != "none" or right_sig != "none")


def _taxonomic_level_conflict(left_label: str, right_label: str) -> bool:
    left_tokens = tokens(left_label)
    right_tokens = tokens(right_label)
    if len(left_tokens) == 1 and len(right_tokens) == 2 and left_tokens[0] == right_tokens[0]:
        return is_latin_only(left_tokens[0]) and is_latin_only(" ".join(right_tokens))
    if len(right_tokens) == 1 and len(left_tokens) == 2 and right_tokens[0] == left_tokens[0]:
        return is_latin_only(right_tokens[0]) and is_latin_only(" ".join(left_tokens))
    return False


def _product_variant_exception(left: CandidateNode, right: CandidateNode, candidate_reasons: list[str]) -> bool:
    return "product_variant_match" in candidate_reasons and _same_product_variant(left, right)


def _same_product_variant(left: CandidateNode, right: CandidateNode) -> bool:
    return bool(
        left.entity_type in {"drug_trade_name", "supplement"}
        and left.product_key
        and left.product_key == right.product_key
    )


def _parent_child_suspect(left: CandidateNode, right: CandidateNode) -> bool:
    left_label = normalize_basic_text(left.normalized_label)
    right_label = normalize_basic_text(right.normalized_label)
    if not left_label or not right_label or left_label == right_label:
        return False
    left_tokens = tokens(left_label)
    right_tokens = tokens(right_label)
    if not left_tokens or not right_tokens:
        return False
    left_set = set(left_tokens)
    right_set = set(right_tokens)
    if left_set < right_set or right_set < left_set:
        return True
    return left_label in right_label or right_label in left_label

from __future__ import annotations

import re
from difflib import SequenceMatcher

from kb_rebuild.normalization.n2.models import CandidateNode, PairFeatures
from kb_rebuild.normalization.text import normalize_basic_text


STRONG_REASONS = {
    "shared_latin_candidate",
    "abbreviation_match",
    "parenthetical_alias_match",
    "product_variant_match",
    "exact_normalized_match",
}


def score_pair_features(left: CandidateNode, right: CandidateNode) -> PairFeatures:
    reasons: set[str] = set()
    risks: set[str] = set()
    metrics: dict[str, float | int | str | list[str]] = {}
    score = 0.0

    left_labels = _all_norm_labels(left)
    right_labels = _all_norm_labels(right)
    if left_labels & right_labels:
        reasons.add("exact_normalized_match")
        score += 0.80

    if _shared_latin_candidate(left, right):
        reasons.add("shared_latin_candidate")
        score += 0.45

    if abbreviation_match(left, right):
        reasons.add("abbreviation_match")
        score += 0.45

    if parenthetical_alias_match(left, right):
        reasons.add("parenthetical_alias_match")
        score += 0.40

    if product_variant_match(left, right):
        reasons.add("product_variant_match")
        score += 0.45

    token_similarity = token_jaccard(left.normalized_label, right.normalized_label)
    sequence_similarity = SequenceMatcher(None, left.normalized_label, right.normalized_label).ratio()
    metrics["token_similarity"] = round(token_similarity, 6)
    metrics["sequence_similarity"] = round(sequence_similarity, 6)
    if token_similarity >= 0.75:
        reasons.add("high_token_similarity")
        score += 0.25
    if sequence_similarity >= 0.88:
        reasons.add("high_sequence_similarity")
        score += 0.20
    elif sequence_similarity >= 0.78:
        reasons.add("moderate_sequence_similarity")
        score += 0.12

    doc_overlap = len({doc["doc_id"] for doc in left.documents} & {doc["doc_id"] for doc in right.documents})
    if doc_overlap:
        reasons.add("same_document_cooccurrence")
        overlap_score = min(0.15, 0.05 + doc_overlap * 0.02)
        metrics["same_document_overlap"] = doc_overlap
        score += overlap_score

    if left.context_only_count == left.mentions_count and right.context_only_count == right.mentions_count:
        risks.add("both_context_only")
        score -= 0.15
    if "quote_not_found" in left.risk_flags or "quote_not_found" in right.risk_flags:
        risks.add("quote_issue")
        score -= 0.10
    if "low_confidence" in left.risk_flags or "low_confidence" in right.risk_flags:
        risks.add("low_confidence")
        score -= 0.15
    if disease_modifier_mismatch(left, right):
        risks.add("disease_modifier_mismatch")
        score -= 0.30

    score = max(0.0, min(1.0, score))
    metrics["left_abbreviations"] = sorted(abbreviations_for_node(left))
    metrics["right_abbreviations"] = sorted(abbreviations_for_node(right))
    return PairFeatures(
        score=round(score, 6),
        candidate_reasons=sorted(reasons),
        risk_reasons=sorted(risks),
        blocking_reasons=[],
        metrics=metrics,
    )


def abbreviation_match(left: CandidateNode, right: CandidateNode) -> bool:
    left_labels = _all_norm_labels(left)
    right_labels = _all_norm_labels(right)
    return bool((abbreviations_for_node(left) & right_labels) or (abbreviations_for_node(right) & left_labels))


def parenthetical_alias_match(left: CandidateNode, right: CandidateNode) -> bool:
    left_parenthetical = parenthetical_aliases(left)
    right_parenthetical = parenthetical_aliases(right)
    return bool((left_parenthetical & _all_norm_labels(right)) or (right_parenthetical & _all_norm_labels(left)))


def product_variant_match(left: CandidateNode, right: CandidateNode) -> bool:
    if left.entity_type not in {"drug_trade_name", "supplement"}:
        return False
    return bool(left.product_key and left.product_key == right.product_key)


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(tokens(left))
    right_tokens = set(tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def tokens(value: str) -> list[str]:
    return re.findall(r"[\w]+", normalize_basic_text(value), flags=re.UNICODE)


def acronym(value: str) -> str:
    stopwords = {"и", "или", "с", "со", "по", "для", "на", "of", "and", "the", "with"}
    parts = [token for token in tokens(value) if token not in stopwords]
    if len(parts) < 2:
        return ""
    return "".join(part[0] for part in parts if part)


def disease_modifier_mismatch(left: CandidateNode, right: CandidateNode) -> bool:
    if left.entity_type != "disease":
        return False
    modifier_flags = {"has_specificity_modifier", "contains_specificity_modifier"}
    return bool((set(left.risk_flags) ^ set(right.risk_flags)) & modifier_flags)


def short_alias(value: str) -> bool:
    compact = re.sub(r"[\W_]+", "", normalize_basic_text(value), flags=re.UNICODE)
    return bool(compact and len(compact) <= 4)


def has_strong_reason(reasons: list[str]) -> bool:
    return bool(set(reasons) & STRONG_REASONS)


def _shared_latin_candidate(left: CandidateNode, right: CandidateNode) -> bool:
    left_latin = normalize_basic_text(left.latin_label)
    right_latin = normalize_basic_text(right.latin_label)
    if left_latin and right_latin and left_latin == right_latin:
        return True
    if left_latin and left_latin in _all_norm_labels(right):
        return True
    if right_latin and right_latin in _all_norm_labels(left):
        return True
    return False


def abbreviations_for_node(node: CandidateNode) -> set[str]:
    known = {
        "иммуноферментный анализ": "ифа",
        "enzyme-linked immunosorbent assay": "elisa",
        "полимеразная цепная реакция": "пцр",
        "магнитно-резонансная томография": "мрт",
        "компьютерная томография": "кт",
        "ультразвуковое исследование": "узи",
        "вирус папилломы человека": "впч",
    }
    result: set[str] = set()
    for label in _all_norm_labels(node):
        if label in known:
            result.add(known[label])
        generated = acronym(label)
        if generated and len(generated) <= 6:
            result.add(generated)
    return result


def parenthetical_aliases(node: CandidateNode) -> set[str]:
    aliases: set[str] = set()
    for value in [node.label, *node.aliases]:
        for match in re.findall(r"\(([^)]+)\)", value):
            normalized = normalize_basic_text(match)
            if normalized:
                aliases.add(normalized)
    return aliases


def _all_norm_labels(node: CandidateNode) -> set[str]:
    labels = {node.normalized_label}
    labels.update(normalize_basic_text(alias) for alias in node.aliases)
    labels.update(node.normalized_aliases)
    labels.discard("")
    return labels

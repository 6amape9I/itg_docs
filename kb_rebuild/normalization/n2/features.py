from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher

from kb_rebuild.normalization.n2.models import CandidateNode, PairFeatures
from kb_rebuild.normalization.text import normalize_basic_text


AMBIGUOUS_ABBREVIATIONS = {"кт", "мрт", "узи", "пцр", "ифа", "экг", "ээг", "мскт", "окт"}
KNOWN_ABBREVIATIONS = {
    "иммуноферментный анализ": "ифа",
    "enzyme-linked immunosorbent assay": "elisa",
    "полимеразная цепная реакция": "пцр",
    "магнитно-резонансная томография": "мрт",
    "компьютерная томография": "кт",
    "ультразвуковое исследование": "узи",
    "электрокардиография": "экг",
    "электрокардиограмма": "экг",
    "электроэнцефалография": "ээг",
    "вирус папилломы человека": "впч",
}
GENERIC_ALIASES_BY_TYPE = {
    "diagnostic_method": {
        "магнитно-резонансная томография",
        "мрт",
        "компьютерная томография",
        "кт",
        "ультразвуковое исследование",
        "узи",
        "биопсия",
        "рентгенография",
        "анализ крови",
        "анализ мочи",
        "генетическое тестирование",
    },
    "procedure": {
        "вакцинация",
        "вакцинация против",
        "трансплантация",
        "операция",
        "терапия",
    },
    "disease": {"полип", "опухоль", "рак", "синдром", "болезнь", "порок", "дефект"},
}
STRONG_CLEAN_REASONS = {
    "primary_label_exact_match",
    "canonical_alias_exact_match",
    "explicit_parenthetical_alias_match",
    "explicit_alias_exact_match",
    "shared_latin_candidate_non_short",
    "product_variant_match",
    "known_safe_abbreviation_match",
    "high_sequence_similarity_without_scope_conflict",
}


def score_pair_features(left: CandidateNode, right: CandidateNode) -> PairFeatures:
    reasons: set[str] = set()
    clean_reasons: set[str] = set()
    weak_reasons: set[str] = set()
    risks: set[str] = set()
    metrics: dict[str, float | int | str | list[str] | bool] = {}
    score = 0.0

    exact = exact_match_details(left, right)
    if exact["matched"]:
        reasons.add("exact_normalized_match")
        metrics["exact_match_type"] = exact["match_type"]
        metrics["generic_aliases_matched"] = sorted(exact["generic_aliases"])
        if exact["match_type"] == "primary_label_exact_match":
            clean_reasons.add("primary_label_exact_match")
            score += 0.80
        elif exact["match_type"] == "canonical_alias_exact_match":
            clean_reasons.add("canonical_alias_exact_match")
            score += 0.65
        else:
            weak_reasons.add("generic_alias_exact_match")
            risks.add("generic_alias_conflict")
            score += 0.18

    if _shared_latin_candidate(left, right):
        reasons.add("shared_latin_candidate")
        if not short_alias(left.latin_label) and not short_alias(right.latin_label):
            clean_reasons.add("shared_latin_candidate_non_short")
            score += 0.45
        else:
            weak_reasons.add("shared_latin_candidate_short")
            score += 0.15

    abbreviation = abbreviation_match_details(left, right)
    if abbreviation["matched"]:
        reasons.add("abbreviation_match")
        metrics["abbreviation_source"] = sorted(abbreviation["sources"])
        metrics["abbreviations_matched"] = sorted(abbreviation["abbreviations"])
        if abbreviation["ambiguous"]:
            risks.add("ambiguous_abbreviation")
            weak_reasons.add("ambiguous_abbreviation_match")
            score += 0.12
        elif abbreviation["clean"]:
            clean_reasons.add("known_safe_abbreviation_match")
            score += 0.45
        else:
            weak_reasons.add("generated_acronym_match")
            score += 0.10

    if parenthetical_alias_match(left, right):
        reasons.add("parenthetical_alias_match")
        clean_reasons.add("explicit_parenthetical_alias_match")
        score += 0.40

    if product_variant_match(left, right):
        reasons.add("product_variant_match")
        clean_reasons.add("product_variant_match")
        score += 0.45

    token_similarity = token_jaccard(left.normalized_label, right.normalized_label)
    sequence_similarity = SequenceMatcher(None, left.normalized_label, right.normalized_label).ratio()
    metrics["token_similarity"] = round(token_similarity, 6)
    metrics["sequence_similarity"] = round(sequence_similarity, 6)
    if token_similarity >= 0.75:
        reasons.add("high_token_similarity")
        weak_reasons.add("high_token_similarity")
        score += 0.25
    if sequence_similarity >= 0.92 and not _generic_label_pair(left, right):
        reasons.add("high_sequence_similarity")
        clean_reasons.add("high_sequence_similarity_without_scope_conflict")
        score += 0.20
    elif sequence_similarity >= 0.88:
        reasons.add("high_sequence_similarity")
        weak_reasons.add("high_sequence_similarity")
        score += 0.20
    elif sequence_similarity >= 0.78:
        reasons.add("moderate_sequence_similarity")
        weak_reasons.add("moderate_sequence_similarity")
        score += 0.12

    doc_overlap = len({doc["doc_id"] for doc in left.documents} & {doc["doc_id"] for doc in right.documents})
    if doc_overlap:
        reasons.add("same_document_cooccurrence")
        weak_reasons.add("same_document_cooccurrence")
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
        clean_candidate_reasons=sorted(clean_reasons),
        weak_candidate_reasons=sorted(weak_reasons),
        risk_reasons=sorted(risks),
        blocking_reasons=[],
        metrics=metrics,
    )


def exact_match_details(left: CandidateNode, right: CandidateNode) -> dict[str, object]:
    left_primary = normalize_basic_text(left.normalized_label)
    right_primary = normalize_basic_text(right.normalized_label)
    left_labels = _all_norm_labels(left)
    right_labels = _all_norm_labels(right)
    matched = left_labels & right_labels
    generic = {
        label
        for label in matched
        if is_generic_alias(left.entity_type, label) or is_generic_alias(right.entity_type, label)
    }
    if left_primary and left_primary == right_primary:
        return {"matched": True, "match_type": "primary_label_exact_match", "generic_aliases": generic}
    if not matched:
        return {"matched": False, "match_type": "", "generic_aliases": set()}
    non_generic = matched - generic
    if non_generic:
        return {"matched": True, "match_type": "canonical_alias_exact_match", "generic_aliases": generic}
    return {"matched": True, "match_type": "generic_alias_exact_match", "generic_aliases": generic}


def abbreviation_match(left: CandidateNode, right: CandidateNode) -> bool:
    return bool(abbreviation_match_details(left, right)["matched"])


def abbreviation_match_details(left: CandidateNode, right: CandidateNode) -> dict[str, object]:
    left_abbreviations = abbreviations_for_node_with_sources(left)
    right_abbreviations = abbreviations_for_node_with_sources(right)
    left_labels = _all_norm_labels(left)
    right_labels = _all_norm_labels(right)
    matched_sources: set[str] = set()
    matched_abbreviations: set[str] = set()

    for abbreviation, sources in left_abbreviations.items():
        if abbreviation in right_labels:
            matched_abbreviations.add(abbreviation)
            matched_sources.update(sources)
            matched_sources.update(_label_sources_for_abbreviation(right, abbreviation))
    for abbreviation, sources in right_abbreviations.items():
        if abbreviation in left_labels:
            matched_abbreviations.add(abbreviation)
            matched_sources.update(sources)
            matched_sources.update(_label_sources_for_abbreviation(left, abbreviation))
    for abbreviation in set(left_abbreviations) & set(right_abbreviations):
        matched_abbreviations.add(abbreviation)
        matched_sources.update(left_abbreviations[abbreviation])
        matched_sources.update(right_abbreviations[abbreviation])

    if not matched_abbreviations:
        return {"matched": False, "sources": set(), "abbreviations": set(), "clean": False, "ambiguous": False}

    strong_sources = {"explicit_parenthetical", "explicit_alias", "known_dictionary"}
    clean = bool(matched_sources & strong_sources) and not (
        matched_abbreviations & AMBIGUOUS_ABBREVIATIONS and matched_sources <= {"generated_acronym", "known_dictionary"}
    )
    ambiguous = bool(matched_abbreviations & AMBIGUOUS_ABBREVIATIONS) and not clean
    return {
        "matched": True,
        "sources": matched_sources,
        "abbreviations": matched_abbreviations,
        "clean": clean,
        "ambiguous": ambiguous,
    }


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
    return bool(set(reasons) & STRONG_CLEAN_REASONS)


def has_clean_reason(reasons: list[str]) -> bool:
    return bool(set(reasons) & STRONG_CLEAN_REASONS)


def is_generic_alias(entity_type: str, value: str) -> bool:
    return normalize_basic_text(value) in GENERIC_ALIASES_BY_TYPE.get(entity_type, set())


def abbreviations_for_node(node: CandidateNode) -> set[str]:
    return set(abbreviations_for_node_with_sources(node))


def abbreviations_for_node_with_sources(node: CandidateNode) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for alias in parenthetical_aliases(node):
        if alias:
            result[alias].add("explicit_parenthetical")
    for label in _all_norm_labels(node):
        if label in KNOWN_ABBREVIATIONS:
            result[KNOWN_ABBREVIATIONS[label]].add("known_dictionary")
        if short_alias(label):
            result[label].add("explicit_alias")
        generated = acronym(label)
        if generated and len(generated) <= 6:
            result[generated].add("generated_acronym")
    return {key: set(value) for key, value in result.items()}


def parenthetical_aliases(node: CandidateNode) -> set[str]:
    aliases: set[str] = set()
    for value in [node.label, *node.aliases]:
        for match in re.findall(r"\(([^)]+)\)", value):
            normalized = normalize_basic_text(match)
            if normalized:
                aliases.add(normalized)
    return aliases


def generic_aliases_for_node(node: CandidateNode) -> set[str]:
    return {label for label in _all_norm_labels(node) if is_generic_alias(node.entity_type, label)}


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


def _label_sources_for_abbreviation(node: CandidateNode, abbreviation: str) -> set[str]:
    sources: set[str] = set()
    if abbreviation in parenthetical_aliases(node):
        sources.add("explicit_parenthetical")
    for label in _all_norm_labels(node):
        if label == abbreviation and short_alias(label):
            sources.add("explicit_alias")
    return sources


def _all_norm_labels(node: CandidateNode) -> set[str]:
    labels = {node.normalized_label}
    labels.update(normalize_basic_text(alias) for alias in node.aliases)
    labels.update(node.normalized_aliases)
    labels.discard("")
    return labels


def _generic_label_pair(left: CandidateNode, right: CandidateNode) -> bool:
    return bool(generic_aliases_for_node(left) or generic_aliases_for_node(right))

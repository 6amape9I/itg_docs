from __future__ import annotations

import re
from typing import Any

from kb_rebuild.normalization.n2.scope_conflict import (
    extract_disease_heads,
    extract_location_markers,
    scope_conflict_reasons,
)
from kb_rebuild.normalization.n2.models import CandidateNode
from kb_rebuild.normalization.text import normalize_basic_text


KNOWN_BAD_ACCEPTED_LABEL_SETS = (
    ("Вирус гепатита A", "Вирус гепатита B"),
    ("Стрептококк группы A", "Стрептококки группы B"),
    ("Жевательный кальций RBC", "Железо RBC"),
    ("Аллергические реакции", "Аллергический ринит", "Лекарственная аллергия"),
    ("Андрогенетическая алопеция у женщин", "Апластическая анемия"),
    ("Мегалобластная анемия", "Мерцательная аритмия"),
    ("Гемолитическая анемия", "Гемофилия A"),
    ("Стеноз гортани", "Стеноз пищевода"),
    ("Лазерная коагуляция сетчатки", "Лазерная коагуляция шейки матки"),
    ("Цистэктомия печени", "Цистэктомия яичника"),
)


def build_quality_diagnostics(
    *,
    accepted_clusters: list[dict[str, Any]],
    split_groups: list[dict[str, Any]],
    known_bad_matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    bad_matches = known_bad_matches if known_bad_matches is not None else find_known_bad_accepted_clusters(accepted_clusters)
    diagnostics = {
        "accepted_clusters_with_single_node": sum(1 for cluster in accepted_clusters if len(cluster.get("node_ids", [])) < 2),
        "accepted_clusters_with_empty_canonical": sum(
            1 for cluster in accepted_clusters if not str(cluster.get("canonical_tag_ru", "")).strip()
        ),
        "split_groups_with_uncovered_nodes": sum(1 for group in split_groups if _split_has_uncovered_nodes(group)),
        "known_bad_accepted_clusters": len(bad_matches),
        "passed": True,
        "known_bad_matches": bad_matches,
    }
    diagnostics["passed"] = all(
        value == 0
        for key, value in diagnostics.items()
        if key not in {"passed", "known_bad_matches"}
    )
    return diagnostics


def find_known_bad_accepted_clusters(accepted_clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    known_sets = [
        {
            "display": " + ".join(labels),
            "normalized": {normalize_basic_text(label) for label in labels},
        }
        for labels in KNOWN_BAD_ACCEPTED_LABEL_SETS
    ]
    for cluster in accepted_clusters:
        labels = [str(label) for label in cluster.get("labels", [])]
        normalized = {normalize_basic_text(label) for label in labels}
        reasons: list[str] = []
        for known in known_sets:
            if known["normalized"] <= normalized:
                reasons.append(f"known_bad_set:{known['display']}")
        if _hepatitis_variant_conflict(labels):
            reasons.append("hepatitis_variant_conflict")
        if _streptococcus_group_conflict(labels):
            reasons.append("streptococcus_group_conflict")
        if _rbc_supplement_conflict(labels):
            reasons.append("rbc_supplement_conflict")
        if _disease_location_conflict(str(cluster.get("entity_type", "")), labels):
            reasons.append("disease_location_conflict")
        if _procedure_or_diagnostic_scope_conflict(str(cluster.get("entity_type", "")), labels):
            reasons.append("procedure_or_diagnostic_scope_conflict")
        for reason in reasons:
            matches.append(
                {
                    "n3_cluster_id": str(cluster.get("n3_cluster_id", "")),
                    "source_candidate_group_id": str(cluster.get("source_candidate_group_id", "")),
                    "labels": " | ".join(labels),
                    "reason": reason,
                }
            )
    return matches


def _split_has_uncovered_nodes(group: dict[str, Any]) -> bool:
    input_ids = set(str(node_id) for node_id in group.get("input_node_ids", []))
    subcluster_ids = {
        str(node_id)
        for subcluster in group.get("subclusters", [])
        if isinstance(subcluster, dict)
        for node_id in subcluster.get("node_ids", [])
    }
    rejected_ids = {
        str(item.get("node_id", ""))
        for item in group.get("rejected_labels", [])
        if isinstance(item, dict)
    }
    return bool(input_ids - subcluster_ids - rejected_ids)


def _hepatitis_variant_conflict(labels: list[str]) -> bool:
    markers = set()
    for label in labels:
        normalized = normalize_basic_text(label)
        if "гепатит" not in normalized and "hepatitis" not in normalized:
            continue
        tokens = normalized.split()
        for index, token in enumerate(tokens):
            if not (token.startswith("гепатит") or token == "hepatitis"):
                continue
            if index + 1 >= len(tokens):
                continue
            marker = _hepatitis_marker(tokens[index + 1])
            if marker:
                markers.add(marker)
    return len(markers) > 1


def _streptococcus_group_conflict(labels: list[str]) -> bool:
    markers = set()
    for label in labels:
        normalized = normalize_basic_text(label)
        if "стрептокок" not in normalized and "streptococc" not in normalized:
            continue
        markers.update(re.findall(r"\bгрупп[а-я]*\s*([abав])\b", normalized))
    return len({_latin_letter(marker) for marker in markers}) > 1


def _rbc_supplement_conflict(labels: list[str]) -> bool:
    bases = {_rbc_product_base(label) for label in labels if _has_rbc_marker(label)}
    bases.discard("")
    return len(bases) > 1


def _disease_location_conflict(entity_type: str, labels: list[str]) -> bool:
    if entity_type != "disease":
        return False
    heads = {head for label in labels for head in extract_disease_heads(label)}
    locations = {location for label in labels for location in extract_location_markers(label)}
    return bool(heads and len(locations) > 1)


def _procedure_or_diagnostic_scope_conflict(entity_type: str, labels: list[str]) -> bool:
    if entity_type not in {"procedure", "diagnostic_method"}:
        return False
    nodes = [
        CandidateNode(
            node_id=f"q_{index}",
            auto_cluster_id="",
            entity_type=entity_type,
            label=label,
            normalized_label=normalize_basic_text(label),
            latin_label="",
            aliases=[label],
            normalized_aliases=[normalize_basic_text(label)],
            mention_ids=[],
            documents=[],
            mentions_count=0,
            documents_count=0,
            article_candidate_count=0,
            context_only_count=0,
            folder_candidate_count=0,
            risk_flags=[],
            routing_flags=[],
            cluster_status="",
            merge_allowed=False,
            subtype_signature="none",
            product_key="",
        )
        for index, label in enumerate(labels)
    ]
    for left_index, left in enumerate(nodes):
        for right in nodes[left_index + 1 :]:
            if scope_conflict_reasons(left, right):
                return True
    return False


def _latin_letter(value: str) -> str:
    mapping = {"а": "a", "в": "b", "с": "c", "д": "d", "е": "e"}
    normalized = normalize_basic_text(value)
    return mapping.get(normalized, normalized)


def _hepatitis_marker(value: str) -> str:
    normalized = normalize_basic_text(value)
    aliases = {
        "a": "a",
        "а": "a",
        "b": "b",
        "в": "b",
        "c": "c",
        "с": "c",
        "d": "d",
        "д": "d",
        "delta": "d",
        "дельта": "d",
        "e": "e",
        "е": "e",
    }
    return aliases.get(normalized, "")


def _has_rbc_marker(label: str) -> bool:
    return bool(re.search(r"(?<![a-zа-я0-9])rbc(?![a-zа-я0-9])", normalize_basic_text(label)))


def _rbc_product_base(label: str) -> str:
    normalized = normalize_basic_text(label)
    without_marker = re.sub(r"(?<![a-zа-я0-9])rbc(?![a-zа-я0-9])", " ", normalized)
    return re.sub(r"[^a-zа-я0-9]+", "", without_marker)

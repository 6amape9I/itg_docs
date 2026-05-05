from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from kb_rebuild.normalization.n2.models import CandidateGroup, CandidateNode, CandidatePair
from kb_rebuild.normalization.text import normalize_basic_text


KNOWN_BAD_N3_EXAMPLES = (
    ("Детская герминогенная опухоль яичка", "Детская герминогенная опухоль яичника"),
    ("Дефицит кофактора молибдена тип A", "Дефицит кофактора молибдена тип B"),
    ("Дефицит кофактора молибдена тип A", "Дефицит кофактора молибдена тип C"),
    ("Катаракта 2 множественных типов", "Катаракта 3 множественных типов"),
    ("Детский В-клеточный острый лимфобластный лейкоз", "Детский Т-клеточный острый лимфобластный лейкоз"),
    ("Врожденный гипотиреоз", "Герпетический энцефалит"),
    ("Анемия хронических заболеваний", "Желудочковые аритмии"),
    ("Рентгенография позвоночника", "Рентгенологическое исследование"),
    ("КТ и МРТ орбиты", "Магнитно-резонансная томография"),
)
REVIEW_GROUP_STATUSES = {
    "blocked_review",
    "hub_parent_child_suspect",
    "ambiguous_abbreviation",
    "generic_alias_conflict",
    "subtype_conflict",
    "location_scope_conflict",
    "quality_score_rejected",
}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp_path.replace(path)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    count = 0
    with tmp_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})
            count += 1
    tmp_path.replace(path)
    return count


def build_candidate_groups_csv_rows(groups: list[CandidateGroup]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in groups:
        rows.append(
            {
                "candidate_group_id": group.candidate_group_id,
                "entity_type": group.entity_type,
                "group_priority": group.group_priority,
                "candidate_group_status": group.candidate_group_status,
                "n3_ready": group.n3_ready,
                "group_score": group.group_score,
                "hard_alias_reason": group.hard_alias_reason,
                "score_gate_passed": group.score_gate_passed,
                "group_labels": " | ".join(group.group_labels),
                "node_ids": "; ".join(group.node_ids),
                "mentions_count": group.mentions_count,
                "documents_count": group.documents_count,
                "article_candidate_count": group.article_candidate_count,
                "context_only_count": group.context_only_count,
                "candidate_reasons": "; ".join(group.candidate_reasons),
                "clean_candidate_reasons": "; ".join(group.clean_candidate_reasons),
                "weak_candidate_reasons": "; ".join(group.weak_candidate_reasons),
                "group_risk_flags": "; ".join(group.group_risk_flags),
                "exclusion_reasons": "; ".join(group.exclusion_reasons),
                "subtype_markers": "; ".join(group.subtype_markers),
                "location_markers": "; ".join(group.location_markers),
                "cellular_markers": "; ".join(group.cellular_markers),
                "complex_markers": "; ".join(group.complex_markers),
                "quality_gate_flags": "; ".join(group.quality_gate_flags),
                "hub_node_ids": "; ".join(group.hub_node_ids),
                "generic_aliases_matched": "; ".join(group.generic_aliases_matched),
                "ambiguous_abbreviations": "; ".join(group.ambiguous_abbreviations),
                "scope_conflict_reasons": "; ".join(group.scope_conflict_reasons),
                "requires_llm_validation": group.requires_llm_validation,
                "recommended_for_n3": group.recommended_for_n3,
                "sample_documents": group.sample_documents,
            }
        )
    return rows


def build_singleton_fast_path_rows(singletons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in singletons:
        recommended = bool(row.get("recommended_fast_path"))
        rows.append(
            {
                **row,
                "fast_path_reason": "single_article_candidate_with_valid_quote" if recommended else "",
                "expected_downstream_action": (
                    "single_document_article_generation_without_multi_doc_extraction" if recommended else "review_or_regular_pipeline"
                ),
            }
        )
    return rows


def build_report(
    *,
    created_at: str,
    source_manifest_path: Path,
    nodes: list[CandidateNode],
    candidate_pairs: list[CandidatePair],
    blocked_pairs: list[CandidatePair],
    rejected_pairs: list[CandidatePair],
    groups: list[CandidateGroup],
    singleton_fast_path_rows: list[dict[str, Any]],
    warnings: list[str],
    known_bad_matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    all_pairs = [*candidate_pairs, *blocked_pairs, *rejected_pairs]
    priority_counts = Counter(group.group_priority for group in groups)
    status_counts = Counter(group.candidate_group_status for group in groups)
    quality_gate = build_quality_gate(groups, known_bad_matches=known_bad_matches)
    return {
        "stage": "normalization_n2_candidate_generation",
        "stage_version": "n2.2",
        "created_at": created_at,
        "source_stage": "normalization_n1",
        "source_stage_version": "n1.1",
        "source_normalization_manifest": str(source_manifest_path),
        "counts": {
            "nodes_total": len(nodes),
            "candidate_pairs_total": len(candidate_pairs),
            "high_priority_pairs": sum(1 for pair in candidate_pairs if pair.pair_status == "high_priority_candidate"),
            "blocked_pairs": len(blocked_pairs),
            "n3_ready_pairs": sum(1 for pair in all_pairs if pair.n3_pair_ready),
            "low_confidence_candidate_pairs": sum(1 for pair in candidate_pairs if pair.pair_status == "low_confidence_candidate"),
            "rejected_low_score_pairs": len(rejected_pairs),
            "candidate_groups_total": len(groups),
            "high_priority_groups": priority_counts.get("high", 0),
            "medium_priority_groups": priority_counts.get("medium", 0),
            "low_priority_groups": priority_counts.get("low", 0),
            "n3_candidate_groups": sum(1 for group in groups if group.n3_ready),
            "blocked_review_groups": sum(
                1
                for group in groups
                if group.candidate_group_status in REVIEW_GROUP_STATUSES
            ),
            "ambiguous_abbreviation_groups": status_counts.get("ambiguous_abbreviation", 0),
            "generic_alias_conflict_groups": status_counts.get("generic_alias_conflict", 0),
            "hub_parent_child_suspect_groups": status_counts.get("hub_parent_child_suspect", 0),
            "subtype_conflict_groups": status_counts.get("subtype_conflict", 0),
            "location_scope_conflict_groups": status_counts.get("location_scope_conflict", 0),
            "quality_score_rejected_groups": status_counts.get("quality_score_rejected", 0),
            "known_bad_n3_matches": len(known_bad_matches or []),
            "singleton_fast_path_candidates": sum(1 for row in singleton_fast_path_rows if row.get("recommended_fast_path")),
        },
        "counts_by_entity_type": _counts_by_entity_type(nodes, candidate_pairs, blocked_pairs, rejected_pairs, groups),
        "candidate_reason_counts": dict(
            Counter(reason for pair in all_pairs for reason in pair.candidate_reasons).most_common()
        ),
        "clean_candidate_reason_counts": dict(
            Counter(reason for pair in all_pairs for reason in pair.clean_candidate_reasons).most_common()
        ),
        "weak_candidate_reason_counts": dict(
            Counter(reason for pair in all_pairs for reason in pair.weak_candidate_reasons).most_common()
        ),
        "blocking_reason_counts": dict(Counter(reason for pair in blocked_pairs for reason in pair.blocking_reasons).most_common()),
        "group_risk_flag_counts": dict(Counter(flag for group in groups for flag in group.group_risk_flags).most_common()),
        "group_status_counts": dict(status_counts.most_common()),
        "exclusion_reason_counts": dict(
            Counter(reason for group in groups for reason in group.exclusion_reasons).most_common()
        ),
        "quality_gate": quality_gate,
        "warnings": warnings,
    }


def build_group_quality_diagnostics(
    groups: list[CandidateGroup],
    known_bad_matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    n3_groups = [group for group in groups if group.n3_ready]
    node_counts = Counter(node_id for group in n3_groups for node_id in group.node_ids)
    return {
        "quality_gate": build_quality_gate(groups, known_bad_matches=known_bad_matches),
        "group_status_counts": dict(Counter(group.candidate_group_status for group in groups).most_common()),
        "group_priority_counts": dict(Counter(group.group_priority for group in groups).most_common()),
        "exclusion_reason_counts": dict(
            Counter(reason for group in groups for reason in group.exclusion_reasons).most_common()
        ),
        "quality_gate_flag_counts": dict(Counter(flag for group in groups for flag in group.quality_gate_flags).most_common()),
        "known_bad_n3_matches": known_bad_matches or [],
        "top_n3_hub_nodes": [
            {"node_id": node_id, "n3_group_count": count}
            for node_id, count in node_counts.most_common(25)
        ],
    }


def build_quality_gate(
    groups: list[CandidateGroup],
    known_bad_matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    n3_groups = [group for group in groups if group.n3_ready]
    node_counts = Counter(node_id for group in n3_groups for node_id in group.node_ids)
    matches = known_bad_matches if known_bad_matches is not None else find_known_bad_n3_matches(groups)
    gate = {
        "n3_candidate_groups_total": len(n3_groups),
        "n3_groups_with_score_below_0_72_without_hard_alias_reason": sum(
            1
            for group in n3_groups
            if (group.group_score < 0.72 and not group.hard_alias_reason)
            or "score_below_n3_threshold_without_hard_alias_reason" in group.quality_gate_flags
        ),
        "n3_disease_groups_with_multiple_type_values": sum(
            1
            for group in n3_groups
            if group.entity_type == "disease" and "different_subtype_values_inside_group" in group.quality_gate_flags
        ),
        "n3_disease_groups_with_base_vs_subtype_conflict": sum(
            1 for group in n3_groups if group.entity_type == "disease" and "base_vs_subtype_conflict" in group.quality_gate_flags
        ),
        "n3_groups_with_disease_location_conflict": sum(
            1
            for group in n3_groups
            if "disease_location_conflict" in group.quality_gate_flags
            or "disease_location_conflict" in group.scope_conflict_reasons
            or "disease_location_conflict" in group.group_risk_flags
        ),
        "n3_groups_with_cellular_subtype_conflict": sum(
            1 for group in n3_groups if "cellular_subtype_conflict" in group.quality_gate_flags
        ),
        "n3_groups_with_complex_subtype_conflict": sum(
            1 for group in n3_groups if "complex_subtype_conflict" in group.quality_gate_flags
        ),
        "n3_groups_with_disease_modifier_mismatch": sum(
            1
            for group in n3_groups
            if "disease_modifier_mismatch" in group.quality_gate_flags
        ),
        "n3_groups_with_quality_risk_without_hard_alias_reason": sum(
            1 for group in n3_groups if "quality_risk_without_hard_alias_reason" in group.quality_gate_flags
        ),
        "n3_groups_matching_known_bad_examples": len(matches),
        "nodes_in_more_than_5_n3_groups": sum(1 for count in node_counts.values() if count > 5),
    }
    gate["passed"] = all(value == 0 for key, value in gate.items() if key != "n3_candidate_groups_total")
    return gate


def find_known_bad_n3_matches(groups: list[CandidateGroup]) -> list[dict[str, Any]]:
    examples = [
        {
            "display": " | ".join(example),
            "normalized": {normalize_basic_text(label) for label in example},
        }
        for example in KNOWN_BAD_N3_EXAMPLES
    ]
    matches: list[dict[str, Any]] = []
    for group in groups:
        if not group.n3_ready:
            continue
        group_label_norms = {normalize_basic_text(label) for label in group.group_labels}
        for example in examples:
            if example["normalized"] <= group_label_norms:
                matches.append(
                    {
                        "candidate_group_id": group.candidate_group_id,
                        "matched_bad_example": example["display"],
                        "group_labels": " | ".join(group.group_labels),
                        "reason": "known_bad_n3_pattern",
                    }
                )
    return matches


def _counts_by_entity_type(
    nodes: list[CandidateNode],
    candidate_pairs: list[CandidatePair],
    blocked_pairs: list[CandidatePair],
    rejected_pairs: list[CandidatePair],
    groups: list[CandidateGroup],
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for node in nodes:
        result[node.entity_type]["nodes"] += 1
    for pair in candidate_pairs:
        result[pair.entity_type]["candidate_pairs"] += 1
    for pair in blocked_pairs:
        result[pair.entity_type]["blocked_pairs"] += 1
    for pair in rejected_pairs:
        result[pair.entity_type]["rejected_pairs"] += 1
    for group in groups:
        result[group.entity_type]["candidate_groups"] += 1
    return {entity_type: dict(counts) for entity_type, counts in sorted(result.items())}


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value

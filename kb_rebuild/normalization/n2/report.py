from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from kb_rebuild.normalization.n2.models import CandidateGroup, CandidateNode, CandidatePair


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
                "group_score": group.group_score,
                "group_labels": " | ".join(group.group_labels),
                "node_ids": "; ".join(group.node_ids),
                "mentions_count": group.mentions_count,
                "documents_count": group.documents_count,
                "article_candidate_count": group.article_candidate_count,
                "context_only_count": group.context_only_count,
                "candidate_reasons": "; ".join(group.candidate_reasons),
                "group_risk_flags": "; ".join(group.group_risk_flags),
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
) -> dict[str, Any]:
    all_pairs = [*candidate_pairs, *blocked_pairs, *rejected_pairs]
    priority_counts = Counter(group.group_priority for group in groups)
    return {
        "stage": "normalization_n2_candidate_generation",
        "created_at": created_at,
        "source_stage": "normalization_n1",
        "source_stage_version": "n1.1",
        "source_normalization_manifest": str(source_manifest_path),
        "counts": {
            "nodes_total": len(nodes),
            "candidate_pairs_total": len(candidate_pairs),
            "high_priority_pairs": sum(1 for pair in candidate_pairs if pair.pair_status == "high_priority_candidate"),
            "blocked_pairs": len(blocked_pairs),
            "rejected_low_score_pairs": len(rejected_pairs),
            "candidate_groups_total": len(groups),
            "high_priority_groups": priority_counts.get("high", 0),
            "medium_priority_groups": priority_counts.get("medium", 0),
            "low_priority_groups": priority_counts.get("low", 0),
            "blocked_review_groups": priority_counts.get("blocked_review", 0),
            "singleton_fast_path_candidates": sum(1 for row in singleton_fast_path_rows if row.get("recommended_fast_path")),
        },
        "counts_by_entity_type": _counts_by_entity_type(nodes, candidate_pairs, blocked_pairs, rejected_pairs, groups),
        "candidate_reason_counts": dict(
            Counter(reason for pair in all_pairs for reason in pair.candidate_reasons).most_common()
        ),
        "blocking_reason_counts": dict(Counter(reason for pair in blocked_pairs for reason in pair.blocking_reasons).most_common()),
        "group_risk_flag_counts": dict(Counter(flag for group in groups for flag in group.group_risk_flags).most_common()),
        "warnings": warnings,
    }


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

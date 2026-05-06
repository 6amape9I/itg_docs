from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from kb_rebuild.normalization.n3.models import N3Decision
from kb_rebuild.normalization.n3.quality import build_quality_diagnostics


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


def partition_decisions(
    decisions: list[N3Decision],
    *,
    accepted_confidence_threshold: float = 0.8,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    accepted_clusters: list[dict[str, Any]] = []
    rejected_groups: list[dict[str, Any]] = []
    split_groups: list[dict[str, Any]] = []
    review_groups: list[dict[str, Any]] = []
    next_cluster_index = 1

    for decision in decisions:
        record = decision.to_dict()
        if decision.decision == "accept_same_entity" and decision.confidence >= accepted_confidence_threshold:
            accepted_clusters.append(
                _accepted_cluster(
                    cluster_index=next_cluster_index,
                    decision=decision,
                    labels=decision.input_group_labels,
                    node_ids=decision.input_node_ids,
                    canonical_tag_ru=decision.canonical_tag_ru,
                    canonical_tag_latin=decision.canonical_tag_latin,
                    confidence=decision.confidence,
                    reason=decision.reason,
                    from_split=False,
                )
            )
            next_cluster_index += 1
        elif decision.decision == "accept_same_entity":
            review = dict(record)
            review["review_reason"] = "low_confidence_accept"
            review_groups.append(review)
        elif decision.decision == "reject_distinct_entities":
            rejected_groups.append(record)
        elif decision.decision == "split_into_subclusters":
            split_groups.append(record)
            for subcluster in decision.subclusters:
                if (
                    subcluster.decision == "same_entity"
                    and len(subcluster.node_ids) >= 2
                    and subcluster.confidence >= accepted_confidence_threshold
                ):
                    accepted_clusters.append(
                        _accepted_cluster(
                            cluster_index=next_cluster_index,
                            decision=decision,
                            labels=subcluster.labels,
                            node_ids=subcluster.node_ids,
                            canonical_tag_ru=subcluster.canonical_tag_ru,
                            canonical_tag_latin=subcluster.canonical_tag_latin,
                            confidence=subcluster.confidence,
                            reason=subcluster.reason,
                            from_split=True,
                        )
                    )
                    next_cluster_index += 1
        else:
            review_groups.append(record)
    return accepted_clusters, rejected_groups, split_groups, review_groups


def build_report(
    *,
    created_at: str,
    n2_manifest_path: Path,
    n3_candidate_groups_path: Path,
    decisions: list[N3Decision],
    accepted_clusters: list[dict[str, Any]],
    rejected_groups: list[dict[str, Any]],
    split_groups: list[dict[str, Any]],
    review_groups: list[dict[str, Any]],
    validation_failures: list[dict[str, Any]],
    known_bad_matches: list[dict[str, Any]],
    estimated_cost_usd: float,
    requests: int,
    cache_hits: int,
    cache_misses: int,
    warnings: list[str],
) -> dict[str, Any]:
    decision_counts = Counter(decision.decision for decision in decisions)
    by_entity_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for decision in decisions:
        by_entity_type[decision.entity_type][decision.decision] += 1
        by_entity_type[decision.entity_type]["groups"] += 1
    quality = build_quality_diagnostics(
        accepted_clusters=accepted_clusters,
        split_groups=split_groups,
        known_bad_matches=known_bad_matches,
    )
    return {
        "stage": "normalization_n3_llm_validation",
        "stage_version": "n3.0",
        "created_at": created_at,
        "input": {
            "n3_candidate_groups": str(n3_candidate_groups_path),
            "n2_manifest": str(n2_manifest_path),
        },
        "counts": {
            "groups_total": len(decisions),
            "groups_processed": len(decisions),
            "accepted_same_entity": decision_counts.get("accept_same_entity", 0),
            "rejected_distinct_entities": decision_counts.get("reject_distinct_entities", 0),
            "split_into_subclusters": decision_counts.get("split_into_subclusters", 0),
            "needs_web_or_human_review": decision_counts.get("needs_web_or_human_review", 0),
            "invalid_llm_responses": len(validation_failures),
            "accepted_clusters_total": len(accepted_clusters),
            "accepted_clusters_from_split": sum(1 for cluster in accepted_clusters if cluster.get("from_split")),
            "review_groups_total": len(review_groups),
        },
        "by_entity_type": {key: dict(value) for key, value in sorted(by_entity_type.items())},
        "cost": {
            "estimated_cost_usd": round(estimated_cost_usd, 8),
            "requests": requests,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
        },
        "quality": {
            key: value for key, value in quality.items() if key != "known_bad_matches"
        },
        "warnings": warnings,
    }


def decision_csv_rows(decisions: list[N3Decision]) -> list[dict[str, Any]]:
    rows = []
    for decision in decisions:
        rows.append(
            {
                "candidate_group_id": decision.candidate_group_id,
                "entity_type": decision.entity_type,
                "decision": decision.decision,
                "confidence": decision.confidence,
                "canonical_tag_ru": decision.canonical_tag_ru,
                "canonical_tag_latin": decision.canonical_tag_latin,
                "input_group_labels": " | ".join(decision.input_group_labels),
                "input_node_ids": "; ".join(decision.input_node_ids),
                "requires_human_review": decision.requires_human_review,
                "risk_flags": "; ".join(decision.risk_flags),
                "reason": decision.reason,
                "model": decision.model,
                "estimated_cost_usd": decision.estimated_cost_usd,
                "cache_key": decision.cache_key,
                "from_cache": decision.from_cache,
            }
        )
    return rows


def accepted_cluster_csv_rows(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "n3_cluster_id": cluster.get("n3_cluster_id", ""),
            "source_candidate_group_id": cluster.get("source_candidate_group_id", ""),
            "entity_type": cluster.get("entity_type", ""),
            "canonical_tag_ru": cluster.get("canonical_tag_ru", ""),
            "canonical_tag_latin": cluster.get("canonical_tag_latin", ""),
            "labels": " | ".join(cluster.get("labels", [])),
            "node_ids": "; ".join(cluster.get("node_ids", [])),
            "confidence": cluster.get("confidence", 0.0),
            "decision_source": cluster.get("decision_source", ""),
            "reason": cluster.get("reason", ""),
        }
        for cluster in clusters
    ]


def group_csv_rows(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "candidate_group_id": group.get("candidate_group_id", ""),
            "entity_type": group.get("entity_type", ""),
            "decision": group.get("decision", ""),
            "confidence": group.get("confidence", 0.0),
            "input_group_labels": " | ".join(group.get("input_group_labels", [])),
            "input_node_ids": "; ".join(group.get("input_node_ids", [])),
            "requires_human_review": group.get("requires_human_review", False),
            "risk_flags": "; ".join(group.get("risk_flags", [])),
            "reason": group.get("reason", ""),
        }
        for group in groups
    ]


def _accepted_cluster(
    *,
    cluster_index: int,
    decision: N3Decision,
    labels: list[str],
    node_ids: list[str],
    canonical_tag_ru: str,
    canonical_tag_latin: str,
    confidence: float,
    reason: str,
    from_split: bool,
) -> dict[str, Any]:
    return {
        "n3_cluster_id": f"n3c_{cluster_index:06d}",
        "source_candidate_group_id": decision.candidate_group_id,
        "entity_type": decision.entity_type,
        "canonical_tag_ru": canonical_tag_ru,
        "canonical_tag_latin": canonical_tag_latin,
        "labels": labels,
        "node_ids": node_ids,
        "confidence": confidence,
        "decision_source": "llm_n3",
        "reason": reason,
        "from_split": from_split,
    }


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from kb_rebuild.normalization.auto_cluster import build_auto_cluster_key
from kb_rebuild.normalization.models import AutoCluster, NormalizedMention, TagMention


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


def build_report(
    *,
    created_at: str,
    input_paths: dict[str, str],
    mentions: list[NormalizedMention],
    clusters: list[AutoCluster],
    failed_documents_count: int,
    invalid_records_count: int,
    warnings: list[str],
    min_mentions_for_report: int,
) -> dict[str, Any]:
    raw_values = [mention.raw_value for mention in mentions if mention.raw_value]
    normalized_values = [mention.primary_norm for mention in mentions if mention.primary_norm]
    entity_type_counts = Counter(mention.entity_type for mention in mentions)
    tag_role_counts = Counter(mention.tag_role for mention in mentions)
    quote_status_counts = Counter(mention.quote_validation_status for mention in mentions)
    article_candidate_counts = Counter(str(mention.article_candidate).lower() for mention in mentions)

    return {
        "stage": "normalization_n1",
        "created_at": created_at,
        "input": input_paths,
        "counts": {
            "documents_with_tags": len({mention.doc_id for mention in mentions}),
            "failed_documents": failed_documents_count,
            "mentions_total": len(mentions),
            "unique_raw_values": len(set(raw_values)),
            "unique_normalized_values": len(set(normalized_values)),
            "auto_clusters_total": len(clusters),
            "auto_clusters_review_required": sum(1 for cluster in clusters if cluster.review_required),
            "suspicious_mentions": sum(1 for mention in mentions if mention.suspicious_flags),
            "quote_issue_mentions": sum(1 for mention in mentions if "quote_not_found" in mention.suspicious_flags),
            "invalid_tagging_records": invalid_records_count,
        },
        "entity_type_counts": dict(sorted(entity_type_counts.items())),
        "tag_role_counts": dict(sorted(tag_role_counts.items())),
        "article_candidate_counts": {
            "true": article_candidate_counts.get("true", 0),
            "false": article_candidate_counts.get("false", 0),
        },
        "quote_status_counts": dict(sorted(quote_status_counts.items())),
        "top_entity_types": _counter_rows(entity_type_counts, min_count=min_mentions_for_report, limit=20),
        "top_raw_tags": _counter_rows(Counter(raw_values), min_count=min_mentions_for_report, limit=50),
        "top_normalized_tags": _counter_rows(Counter(normalized_values), min_count=min_mentions_for_report, limit=50),
        "warnings": warnings,
    }


def build_tags_raw_rows(mentions: list[NormalizedMention], min_mentions: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, bool], list[NormalizedMention]] = defaultdict(list)
    for mention in mentions:
        key = (
            mention.raw_value,
            mention.primary_norm,
            mention.entity_type,
            mention.tag_role,
            mention.article_candidate,
        )
        grouped[key].append(mention)

    rows: list[dict[str, Any]] = []
    for (raw_value, normalized_value, entity_type, tag_role, article_candidate), group in grouped.items():
        if len(group) < min_mentions:
            continue
        rows.append(
            {
                "raw_value": raw_value,
                "normalized_value": normalized_value,
                "entity_type": entity_type,
                "tag_role": tag_role,
                "article_candidate": article_candidate,
                "mentions_count": len(group),
                "documents_count": len({mention.doc_id for mention in group}),
                "avg_confidence": _avg(mention.confidence for mention in group),
                "quote_not_found_count": sum(1 for mention in group if "quote_not_found" in mention.suspicious_flags),
                "examples": " | ".join(
                    _first_unique((mention.document_name for mention in group if mention.document_name), 3)
                ),
            }
        )
    return sorted(rows, key=lambda row: (-int(row["mentions_count"]), str(row["entity_type"]), str(row["raw_value"])))


def build_auto_cluster_csv_rows(clusters: list[AutoCluster]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cluster in clusters:
        rows.append(
            {
                "auto_cluster_id": cluster.auto_cluster_id,
                "entity_type": cluster.entity_type,
                "canonical_display_candidate": cluster.canonical_display_candidate,
                "canonical_latin_candidate": cluster.canonical_latin_candidate,
                "aliases": "; ".join(cluster.aliases),
                "normalized_aliases": "; ".join(cluster.normalized_aliases),
                "mentions_count": cluster.mentions_count,
                "documents_count": cluster.documents_count,
                "article_candidate_count": cluster.article_candidate_count,
                "folder_candidate_count": cluster.folder_candidate_count,
                "context_only_count": cluster.context_only_count,
                "avg_confidence": cluster.confidence_stats.get("avg", 0.0),
                "quote_not_found_count": cluster.quote_not_found_count,
                "review_required": cluster.review_required,
                "review_reasons": "; ".join(cluster.review_reasons),
            }
        )
    return rows


def build_type_role_stats_rows(mentions: list[NormalizedMention]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, bool], list[NormalizedMention]] = defaultdict(list)
    for mention in mentions:
        grouped[(mention.entity_type, mention.tag_role, mention.article_candidate)].append(mention)
    rows: list[dict[str, Any]] = []
    for (entity_type, tag_role, article_candidate), group in grouped.items():
        rows.append(
            {
                "entity_type": entity_type,
                "tag_role": tag_role,
                "article_candidate": article_candidate,
                "mentions_count": len(group),
                "documents_count": len({mention.doc_id for mention in group}),
                "unique_normalized_count": len({mention.primary_norm for mention in group if mention.primary_norm}),
            }
        )
    return sorted(rows, key=lambda row: (-int(row["mentions_count"]), str(row["entity_type"]), str(row["tag_role"])))


def build_top_aliases_by_type_rows(mentions: list[NormalizedMention]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[NormalizedMention]] = defaultdict(list)
    for mention in mentions:
        grouped[(mention.entity_type, mention.raw_value, mention.primary_norm)].append(mention)
    rows = [
        {
            "entity_type": entity_type,
            "raw_value": raw_value,
            "normalized_value": normalized_value,
            "mentions_count": len(group),
            "documents_count": len({mention.doc_id for mention in group}),
        }
        for (entity_type, raw_value, normalized_value), group in grouped.items()
    ]
    return sorted(rows, key=lambda row: (str(row["entity_type"]), -int(row["mentions_count"]), str(row["raw_value"])))


def build_top_canonical_candidates_rows(mentions: list[NormalizedMention]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[NormalizedMention]] = defaultdict(list)
    for mention in mentions:
        candidate = str(mention.raw.get("canonical_candidate_ru", "")).strip()
        if not candidate:
            continue
        grouped[(mention.entity_type, candidate, mention.primary_norm)].append(mention)
    rows = [
        {
            "entity_type": entity_type,
            "canonical_candidate_ru": candidate,
            "normalized_value": normalized_value,
            "mentions_count": len(group),
            "documents_count": len({mention.doc_id for mention in group}),
        }
        for (entity_type, candidate, normalized_value), group in grouped.items()
    ]
    return sorted(rows, key=lambda row: (str(row["entity_type"]), -int(row["mentions_count"]), str(row["canonical_candidate_ru"])))


def attach_auto_cluster_keys(mentions: list[NormalizedMention]) -> list[NormalizedMention]:
    # N1 keeps the auto-cluster key in cluster artifacts; this helper is kept for reports that need it later.
    for mention in mentions:
        build_auto_cluster_key(mention)
    return mentions


def _counter_rows(counter: Counter[str], *, min_count: int, limit: int) -> list[dict[str, Any]]:
    rows = [
        {"value": value, "count": count}
        for value, count in counter.most_common()
        if count >= min_count and value
    ]
    return rows[:limit]


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _avg(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return round(sum(items) / len(items), 6)


def _first_unique(values: Iterable[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result

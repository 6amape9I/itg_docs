from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from kb_rebuild.normalization.n4.models import FinalComponent
from kb_rebuild.normalization.text import normalize_basic_text


def build_component_alias_candidates(
    component: FinalComponent,
    clusters_by_id: dict[str, dict[str, Any]],
    mentions: list[dict[str, Any]],
    canonical_ru: str,
    canonical_latin: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    _add_candidate(candidates, canonical_ru, "n3_canonical" if component.edges else "n4_generated", canonical_latin=canonical_latin)
    if canonical_latin:
        _add_candidate(candidates, canonical_latin, "n3_canonical", alias_latin=canonical_latin)

    for edge in component.edges:
        for label in edge.labels:
            _add_candidate(candidates, label, "n3_label")
        _add_candidate(candidates, edge.canonical_tag_ru, "n3_canonical", canonical_latin=edge.canonical_tag_latin)
        if edge.canonical_tag_latin:
            _add_candidate(candidates, edge.canonical_tag_latin, "n3_canonical", alias_latin=edge.canonical_tag_latin)

    for cluster_id in component.auto_cluster_ids:
        cluster = clusters_by_id[cluster_id]
        _add_candidate(candidates, str(cluster.get("canonical_display_candidate") or ""), "n1_auto_cluster_alias")
        if cluster.get("canonical_latin_candidate"):
            _add_candidate(
                candidates,
                str(cluster.get("canonical_latin_candidate") or ""),
                "n1_canonical_candidate_latin",
                alias_latin=str(cluster.get("canonical_latin_candidate") or ""),
            )
        for alias in _list(cluster.get("aliases")):
            _add_candidate(candidates, str(alias), "n1_auto_cluster_alias")
        for alias in _list(cluster.get("normalized_aliases")):
            _add_candidate(candidates, str(alias), "n1_auto_cluster_alias")

    for mention in mentions:
        raw = mention.get("raw") if isinstance(mention.get("raw"), dict) else {}
        normalized = mention.get("normalized") if isinstance(mention.get("normalized"), dict) else {}
        _add_candidate(candidates, str(raw.get("surface") or ""), "n1_surface")
        _add_candidate(candidates, str(raw.get("canonical_candidate_ru") or ""), "n1_canonical_candidate_ru")
        _add_candidate(
            candidates,
            str(raw.get("canonical_candidate_latin") or ""),
            "n1_canonical_candidate_latin",
            alias_latin=str(raw.get("canonical_candidate_latin") or ""),
        )
        _add_candidate(candidates, str(normalized.get("display_candidate_ru") or ""), "n1_canonical_candidate_ru")
        _add_candidate(
            candidates,
            str(normalized.get("display_candidate_latin") or ""),
            "n1_canonical_candidate_latin",
            alias_latin=str(normalized.get("display_candidate_latin") or ""),
        )
        for key in ("surface_norm", "candidate_ru_norm", "candidate_latin_norm", "primary_norm"):
            _add_candidate(candidates, str(normalized.get(key) or ""), "n4_generated")

    return _dedupe_alias_candidates(candidates)


def build_alias_records(
    *,
    tag_id: str,
    entity_type: str,
    candidates: list[dict[str, Any]],
    mention_norm_counts: dict[str, dict[str, int]],
    blocked_norms: set[str] | None = None,
    need_review: bool = False,
    review_reasons: list[str] | None = None,
) -> list[dict[str, Any]]:
    blocked_norms = blocked_norms or set()
    review_reasons = review_reasons or []
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        alias = str(candidate["alias"])
        alias_norm = normalize_basic_text(alias)
        if not alias_norm:
            continue
        alias_id = "al_" + hashlib.sha256(f"{tag_id}\n{entity_type}\n{alias_norm}".encode("utf-8")).hexdigest()[:16]
        mention_counts = mention_norm_counts.get(alias_norm, {})
        alias_status = "blocked_active_substance_candidate" if alias_norm in blocked_norms else "active"
        alias_review_reasons = list(review_reasons) if alias_status != "active" else []
        rows.append(
            {
                "alias_id": alias_id,
                "tag_id": tag_id,
                "alias": alias,
                "alias_norm": alias_norm,
                "alias_latin": str(candidate.get("alias_latin") or ""),
                "entity_type": entity_type,
                "alias_source": str(candidate.get("alias_source") or "n4_generated"),
                "alias_status": alias_status,
                "mention_count": int(mention_counts.get("mention_count", 0)),
                "document_count": int(mention_counts.get("document_count", 0)),
                "confidence": "",
                "need_review": bool(need_review or alias_status != "active"),
                "review_reasons": alias_review_reasons,
                "n1_surface": candidate.get("alias_source") == "n1_surface",
                "n1_canonical_candidate_ru": candidate.get("alias_source") == "n1_canonical_candidate_ru",
                "n1_canonical_candidate_latin": candidate.get("alias_source") == "n1_canonical_candidate_latin",
                "n1_auto_cluster_alias": candidate.get("alias_source") == "n1_auto_cluster_alias",
                "n3_label": candidate.get("alias_source") == "n3_label",
                "n3_canonical": candidate.get("alias_source") == "n3_canonical",
                "n4_generated": candidate.get("alias_source") == "n4_generated",
                "active": alias_status == "active",
                "needs_review": bool(need_review or alias_status != "active"),
                "blocked_active_substance_candidate": alias_status == "blocked_active_substance_candidate",
                "conflict_alias": False,
            }
        )
    return rows


def alias_index(
    canonical_rows: list[dict[str, Any]],
    alias_rows: list[dict[str, Any]],
) -> dict[tuple[str, str], set[str]]:
    index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in canonical_rows:
        entity_type = str(row.get("entity_type") or "")
        tag_id = str(row.get("tag_id") or "")
        for value in (row.get("canonical_tag_ru"), row.get("canonical_tag_latin")):
            norm = normalize_basic_text(str(value or ""))
            if norm:
                index[(entity_type, norm)].add(tag_id)
    for row in alias_rows:
        entity_type = str(row.get("entity_type") or "")
        tag_id = str(row.get("tag_id") or "")
        if row.get("alias_status") == "blocked_active_substance_candidate":
            continue
        for value in (row.get("alias"), row.get("alias_latin")):
            norm = normalize_basic_text(str(value or ""))
            if norm:
                index[(entity_type, norm)].add(tag_id)
    return index


def find_alias_conflicts(alias_rows: list[dict[str, Any]], canonical_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = alias_index(canonical_rows, alias_rows)
    conflicts: list[dict[str, Any]] = []
    for (entity_type, alias_norm), tag_ids in sorted(index.items()):
        if len(tag_ids) <= 1:
            continue
        conflicts.append(
            {
                "entity_type": entity_type,
                "alias_norm": alias_norm,
                "tag_ids": sorted(tag_ids),
                "conflict_type": "alias_maps_to_multiple_tags",
                "need_review": True,
            }
        )
    return conflicts


def mark_alias_conflicts(alias_rows: list[dict[str, Any]], conflicts: list[dict[str, Any]]) -> None:
    conflict_keys = {(row["entity_type"], row["alias_norm"]) for row in conflicts}
    for row in alias_rows:
        key = (str(row.get("entity_type") or ""), str(row.get("alias_norm") or ""))
        if key in conflict_keys:
            row["conflict_alias"] = True
            row["need_review"] = True
            row["needs_review"] = True
            reasons = row.get("review_reasons")
            if not isinstance(reasons, list):
                reasons = []
            if "alias_conflict" not in reasons:
                reasons.append("alias_conflict")
            row["review_reasons"] = reasons


def _add_candidate(
    rows: list[dict[str, Any]],
    alias: str,
    alias_source: str,
    *,
    alias_latin: str = "",
    canonical_latin: str = "",
) -> None:
    alias = str(alias or "").strip()
    if not alias:
        return
    rows.append(
        {
            "alias": alias,
            "alias_source": alias_source,
            "alias_latin": alias_latin or canonical_latin or "",
        }
    )


def _dedupe_alias_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {
        "n3_canonical": 0,
        "n1_canonical_candidate_ru": 1,
        "n1_surface": 2,
        "n1_auto_cluster_alias": 3,
        "n3_label": 4,
        "n1_canonical_candidate_latin": 5,
        "n4_generated": 6,
    }
    by_norm: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        norm = normalize_basic_text(str(candidate.get("alias") or ""))
        if not norm:
            continue
        current = by_norm.get(norm)
        if current is None:
            by_norm[norm] = dict(candidate)
            continue
        current_score = priority.get(str(current.get("alias_source")), 99)
        new_score = priority.get(str(candidate.get("alias_source")), 99)
        if (new_score, len(str(candidate.get("alias") or ""))) < (current_score, len(str(current.get("alias") or ""))):
            by_norm[norm] = dict(candidate)
    return [by_norm[norm] for norm in sorted(by_norm)]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from kb_rebuild.normalization.n4.models import FinalComponent
from kb_rebuild.normalization.text import normalize_basic_text, normalize_product_name


def canonical_tag_id(entity_type: str, canonical_ru: str, canonical_latin: str, alias_norms: list[str]) -> str:
    payload = "\n".join(
        [
            entity_type,
            normalize_basic_text(canonical_ru),
            normalize_basic_text(canonical_latin),
            *sorted(set(alias_norms)),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]
    return f"{entity_type}_{digest}"


def choose_canonical(
    component: FinalComponent,
    clusters_by_id: dict[str, dict[str, Any]],
    mention_records: list[dict[str, Any]] | None = None,
) -> tuple[str, str, list[str]]:
    review_reasons: list[str] = []
    n3_ru_candidates: list[tuple[float, str]] = [
        (edge.confidence, edge.canonical_tag_ru)
        for edge in component.edges
        if edge.canonical_tag_ru.strip()
    ]
    n3_latin_candidates: list[tuple[float, str]] = [
        (edge.confidence, edge.canonical_tag_latin)
        for edge in component.edges
        if edge.canonical_tag_latin.strip()
    ]

    canonical_ru = _best_n3_candidate(n3_ru_candidates)
    if _has_conflicting_values([value for _, value in n3_ru_candidates]):
        review_reasons.append("n3_canonical_ru_conflict")

    if not canonical_ru:
        canonical_ru = _best_cluster_display(component, clusters_by_id)

    if component.entity_type in {"drug_trade_name", "supplement"}:
        canonical_ru = _clean_product_canonical(component.entity_type, canonical_ru, component, clusters_by_id)

    if not canonical_ru and mention_records:
        canonical_ru = _best_mention_display(mention_records)
    if not canonical_ru:
        canonical_ru = component.auto_cluster_ids[0]
        review_reasons.append("empty_canonical_tag_ru_fallback")

    canonical_latin = _best_n3_candidate(n3_latin_candidates)
    if _has_conflicting_values([value for _, value in n3_latin_candidates]):
        review_reasons.append("n3_canonical_latin_conflict")
    if not canonical_latin:
        canonical_latin = _best_cluster_latin(component, clusters_by_id)
    if not canonical_latin and mention_records:
        canonical_latin = _best_mention_latin(mention_records)

    return canonical_ru, canonical_latin, review_reasons


def component_stats(
    component: FinalComponent,
    clusters_by_id: dict[str, dict[str, Any]],
    mentions: list[dict[str, Any]],
) -> dict[str, Any]:
    doc_ids = {str(mention.get("doc_id") or "") for mention in mentions if str(mention.get("doc_id") or "")}
    tag_roles = Counter(str(mention.get("tag_role") or "") for mention in mentions if str(mention.get("tag_role") or ""))
    article_candidate = any(bool(mention.get("article_candidate")) for mention in mentions)
    context_only = all("context_only" in _list(cluster.get("routing_flags")) for cluster in _component_clusters(component, clusters_by_id))
    folder_candidate = any(int(cluster.get("folder_candidate_count") or 0) > 0 for cluster in _component_clusters(component, clusters_by_id))
    confidences = [float(mention.get("confidence") or 0.0) for mention in mentions if mention.get("confidence") is not None]
    primary_role = _primary_role(tag_roles)
    return {
        "mentions_count": len(mentions) if mentions else sum(int(cluster.get("mentions_count") or 0) for cluster in _component_clusters(component, clusters_by_id)),
        "documents_count": len(doc_ids) if doc_ids else sum(int(cluster.get("documents_count") or 0) for cluster in _component_clusters(component, clusters_by_id)),
        "article_candidate_count": sum(int(cluster.get("article_candidate_count") or 0) for cluster in _component_clusters(component, clusters_by_id)),
        "context_only_count": sum(int(cluster.get("context_only_count") or 0) for cluster in _component_clusters(component, clusters_by_id)),
        "folder_candidate_count": sum(int(cluster.get("folder_candidate_count") or 0) for cluster in _component_clusters(component, clusters_by_id)),
        "article_candidate": article_candidate,
        "context_only": context_only,
        "folder_candidate": folder_candidate,
        "primary_role": primary_role,
        "confidence": round(sum(confidences) / len(confidences), 6) if confidences else _cluster_confidence(component, clusters_by_id),
    }


def _best_n3_candidate(candidates: list[tuple[float, str]]) -> str:
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: (-item[0], normalize_basic_text(item[1]), item[1]))[0][1].strip()


def _best_cluster_display(component: FinalComponent, clusters_by_id: dict[str, dict[str, Any]]) -> str:
    candidates: list[tuple[int, int, int, str]] = []
    for cluster in _component_clusters(component, clusters_by_id):
        value = str(cluster.get("canonical_display_candidate") or "").strip()
        if value:
            candidates.append(
                (
                    int(cluster.get("article_candidate_count") or 0),
                    int(cluster.get("mentions_count") or 0),
                    int(cluster.get("documents_count") or 0),
                    value,
                )
            )
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: (-item[0], -item[1], -item[2], normalize_basic_text(item[3]), item[3]))[0][3]


def _best_cluster_latin(component: FinalComponent, clusters_by_id: dict[str, dict[str, Any]]) -> str:
    candidates: list[tuple[int, int, str]] = []
    for cluster in _component_clusters(component, clusters_by_id):
        value = str(cluster.get("canonical_latin_candidate") or "").strip()
        if value:
            candidates.append((int(cluster.get("mentions_count") or 0), int(cluster.get("documents_count") or 0), value))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: (-item[0], item[2].lower(), item[2]))[0][2]


def _best_mention_display(mentions: list[dict[str, Any]]) -> str:
    values = []
    for mention in mentions:
        values.extend(
            [
                _nested(mention, "normalized", "display_candidate_ru"),
                _nested(mention, "raw", "canonical_candidate_ru"),
                _nested(mention, "raw", "surface"),
            ]
        )
    return _most_common_display(values)


def _best_mention_latin(mentions: list[dict[str, Any]]) -> str:
    values = []
    for mention in mentions:
        values.extend(
            [
                _nested(mention, "normalized", "display_candidate_latin"),
                _nested(mention, "raw", "canonical_candidate_latin"),
            ]
        )
    return _most_common_display(values)


def _clean_product_canonical(
    entity_type: str,
    canonical_ru: str,
    component: FinalComponent,
    clusters_by_id: dict[str, dict[str, Any]],
) -> str:
    product = normalize_product_name(canonical_ru, entity_type)
    if not product.changed:
        return canonical_ru
    product_norm = product.value
    for cluster in _component_clusters(component, clusters_by_id):
        values = [str(cluster.get("canonical_display_candidate") or ""), *[str(alias) for alias in _list(cluster.get("aliases"))]]
        for value in values:
            if normalize_product_name(value, entity_type).value == product_norm and normalize_basic_text(value) == product_norm:
                return value.strip()
    return product_norm[:1].upper() + product_norm[1:] if product_norm else canonical_ru


def _has_conflicting_values(values: list[str]) -> bool:
    norms = {normalize_basic_text(value) for value in values if normalize_basic_text(value)}
    return len(norms) > 1


def _component_clusters(component: FinalComponent, clusters_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [clusters_by_id[cluster_id] for cluster_id in component.auto_cluster_ids if cluster_id in clusters_by_id]


def _cluster_confidence(component: FinalComponent, clusters_by_id: dict[str, dict[str, Any]]) -> float:
    values = []
    for cluster in _component_clusters(component, clusters_by_id):
        stats = cluster.get("confidence_stats")
        if isinstance(stats, dict) and stats.get("avg") is not None:
            values.append(float(stats.get("avg") or 0.0))
    return round(sum(values) / len(values), 6) if values else 0.0


def _primary_role(counter: Counter[str]) -> str:
    if not counter:
        return ""
    if counter.get("article_candidate"):
        return "article_candidate"
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _most_common_display(values: list[str]) -> str:
    cleaned = [value.strip() for value in values if value and value.strip()]
    if not cleaned:
        return ""
    counts = Counter(cleaned)
    return sorted(counts, key=lambda value: (-counts[value], normalize_basic_text(value), value))[0]


def _nested(record: dict[str, Any], *path: str) -> str:
    value: Any = record
    for key in path:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return str(value or "")


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Any

from kb_rebuild.normalization.n2.blocking import blocking_reasons, risk_reasons
from kb_rebuild.normalization.n2.features import (
    abbreviations_for_node,
    has_clean_reason,
    has_strong_reason,
    parenthetical_aliases,
    score_pair_features,
    token_jaccard,
    tokens,
)
from kb_rebuild.normalization.n2.models import CandidateNode, CandidatePair
from kb_rebuild.normalization.text import normalize_basic_text, subtype_signature


BUCKET_MAX_SIZE = 250
STRONG_BUCKET_MAX_SIZE = 1000
PRODUCT_VARIANT_RISK_FLAGS = {
    "possible_numeric_dosage_variant",
    "contains_dosage",
    "possible_trade_name_with_dosage",
    "contains_packaging",
}


def build_candidate_nodes(
    clusters: list[dict[str, Any]],
    normalized_mentions: list[dict[str, Any]],
) -> list[CandidateNode]:
    mentions_by_id = {str(mention.get("mention_id", "")): mention for mention in normalized_mentions}
    nodes: list[CandidateNode] = []
    next_node_index = 1
    for cluster in clusters:
        base_node = _node_from_cluster(
            node_index=next_node_index,
            cluster=cluster,
            mentions_by_id=mentions_by_id,
            label_override=None,
        )
        nodes.append(base_node)
        next_node_index += 1
        for alias in _product_variant_aliases(cluster, base_node.normalized_label):
            nodes.append(
                _node_from_cluster(
                    node_index=next_node_index,
                    cluster=cluster,
                    mentions_by_id=mentions_by_id,
                    label_override=alias,
                )
            )
            next_node_index += 1
    return nodes


def _node_from_cluster(
    *,
    node_index: int,
    cluster: dict[str, Any],
    mentions_by_id: dict[str, dict[str, Any]],
    label_override: str | None,
) -> CandidateNode:
    entity_type = str(cluster.get("entity_type", ""))
    cluster_aliases = [str(alias) for alias in cluster.get("aliases", []) if str(alias).strip()]
    label = label_override or str(cluster.get("canonical_display_candidate") or "")
    if not label and cluster_aliases:
        label = cluster_aliases[0]

    normalized_label = normalize_basic_text(label)
    if label_override:
        aliases = [label]
        normalized_aliases = [normalized_label] if normalized_label else []
        mention_ids = _mention_ids_for_label(cluster, mentions_by_id, normalized_label)
        risk_flags = sorted({str(flag) for flag in cluster.get("risk_flags", [])} | {"product_variant_alias_node"})
        cluster_status = "product_variant_alias"
        merge_allowed = False
    else:
        normalized_aliases = [str(alias) for alias in cluster.get("normalized_aliases", []) if str(alias).strip()]
        if not normalized_label and normalized_aliases:
            normalized_label = normalized_aliases[0]
        aliases = cluster_aliases
        mention_ids = [str(mention_id) for mention_id in cluster.get("mention_ids", [])]
        risk_flags = [str(flag) for flag in cluster.get("risk_flags", [])]
        cluster_status = str(cluster.get("cluster_status", ""))
        merge_allowed = bool(cluster.get("merge_allowed", False))

    documents = _documents_for_mention_ids(mention_ids, mentions_by_id)
    product_key = ""
    if entity_type in {"drug_trade_name", "supplement"}:
        product_key = _key_payload(str(cluster.get("auto_cluster_key", "")), entity_type)

    return CandidateNode(
        node_id=f"n_{node_index:06d}",
        auto_cluster_id=str(cluster.get("auto_cluster_id", "")),
        entity_type=entity_type,
        label=label,
        normalized_label=normalized_label,
        latin_label=normalize_basic_text(str(cluster.get("canonical_latin_candidate", ""))),
        aliases=aliases,
        normalized_aliases=normalized_aliases,
        mention_ids=mention_ids,
        documents=documents,
        mentions_count=_mention_count(cluster, mention_ids, label_override=label_override),
        documents_count=_document_count(cluster, documents, label_override=label_override),
        article_candidate_count=_role_count(
            cluster,
            mentions_by_id,
            mention_ids,
            "article_candidate",
            label_override=label_override,
        ),
        context_only_count=_role_count(
            cluster,
            mentions_by_id,
            mention_ids,
            "context_only",
            label_override=label_override,
        ),
        folder_candidate_count=_role_count(
            cluster,
            mentions_by_id,
            mention_ids,
            "folder_candidate",
            label_override=label_override,
        ),
        risk_flags=risk_flags,
        routing_flags=[str(flag) for flag in cluster.get("routing_flags", [])],
        cluster_status=cluster_status,
        merge_allowed=merge_allowed,
        subtype_signature=subtype_signature(label) if entity_type == "disease" else "none",
        product_key=product_key,
    )


def _product_variant_aliases(cluster: dict[str, Any], base_normalized_label: str) -> list[str]:
    entity_type = str(cluster.get("entity_type", ""))
    if entity_type not in {"drug_trade_name", "supplement"}:
        return []
    risk_flags = {str(flag) for flag in cluster.get("risk_flags", [])}
    aliases = [str(alias).strip() for alias in cluster.get("aliases", []) if str(alias).strip()]
    normalized_aliases = {normalize_basic_text(alias) for alias in aliases}
    normalized_aliases.update(str(alias) for alias in cluster.get("normalized_aliases", []) if str(alias).strip())
    normalized_aliases.discard("")
    has_variant_signal = bool(risk_flags & PRODUCT_VARIANT_RISK_FLAGS) or any(
        normalized and normalized != base_normalized_label for normalized in normalized_aliases
    )
    if not has_variant_signal:
        return []
    result: list[str] = []
    seen: set[str] = {base_normalized_label}
    for text in aliases:
        normalized = normalize_basic_text(text)
        if not text or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(text)
        if len(result) >= 20:
            break
    return result


def generate_candidate_pairs(
    nodes: list[CandidateNode],
    *,
    min_score: float,
    high_priority_score: float,
    max_pairs_per_type: int,
    warnings: list[str],
) -> tuple[list[CandidatePair], list[CandidatePair], list[CandidatePair]]:
    candidate_pairs: list[CandidatePair] = []
    blocked_pairs: list[CandidatePair] = []
    rejected_pairs: list[CandidatePair] = []
    next_pair_index = 1

    for entity_type, type_nodes in sorted(_group_by_type(nodes).items()):
        pair_keys = _candidate_pair_keys_for_type(type_nodes, warnings=warnings, entity_type=entity_type)
        evaluated: list[CandidatePair] = []
        for left_index, right_index in sorted(pair_keys):
            pair = _evaluate_pair(
                pair_index=next_pair_index,
                left=type_nodes[left_index],
                right=type_nodes[right_index],
                min_score=min_score,
                high_priority_score=high_priority_score,
            )
            next_pair_index += 1
            evaluated.append(pair)

        if len(evaluated) > max_pairs_per_type:
            warnings.append(
                f"{entity_type}: generated pairs {len(evaluated)} exceeded max_pairs_per_type={max_pairs_per_type}; kept strongest"
            )
            evaluated = sorted(evaluated, key=_pair_sort_key)[:max_pairs_per_type]

        for pair in evaluated:
            if pair.pair_status in {"candidate", "high_priority_candidate", "low_confidence_candidate"}:
                candidate_pairs.append(pair)
            elif pair.pair_status == "blocked":
                blocked_pairs.append(pair)
            else:
                rejected_pairs.append(pair)

    return candidate_pairs, blocked_pairs, rejected_pairs


def _candidate_pair_keys_for_type(
    nodes: list[CandidateNode],
    *,
    warnings: list[str],
    entity_type: str,
) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()

    def add_bucket(bucket_name: str, bucket_nodes: list[int], *, strong: bool = False) -> None:
        max_size = STRONG_BUCKET_MAX_SIZE if strong else BUCKET_MAX_SIZE
        unique_nodes = sorted(set(bucket_nodes))
        if len(unique_nodes) < 2:
            return
        if len(unique_nodes) > max_size:
            warnings.append(f"{entity_type}: skipped {bucket_name} bucket with {len(unique_nodes)} nodes")
            return
        for left, right in combinations(unique_nodes, 2):
            pairs.add((left, right))

    indexes: dict[str, dict[str, list[int]]] = {
        "latin": defaultdict(list),
        "product": defaultdict(list),
        "abbreviation": defaultdict(list),
        "parenthetical": defaultdict(list),
        "first_token": defaultdict(list),
        "prefix": defaultdict(list),
        "token_signature": defaultdict(list),
    }
    labels_to_nodes: dict[str, list[int]] = defaultdict(list)

    for index, node in enumerate(nodes):
        if node.latin_label:
            indexes["latin"][node.latin_label].append(index)
        if node.product_key:
            indexes["product"][node.product_key].append(index)
        labels_to_nodes[node.normalized_label].append(index)
        for alias in node.normalized_aliases:
            labels_to_nodes[alias].append(index)
        node_tokens = tokens(node.normalized_label)
        if node_tokens:
            indexes["first_token"][node_tokens[0]].append(index)
            indexes["prefix"][node.normalized_label[:8]].append(index)
            indexes["token_signature"][" ".join(sorted(set(node_tokens))[:4])].append(index)
        for abbreviation in abbreviations_for_node(node):
            indexes["abbreviation"][abbreviation].append(index)
        for parenthetical in parenthetical_aliases(node):
            indexes["parenthetical"][parenthetical].append(index)

    for bucket_name in ("latin", "product"):
        for key, bucket in indexes[bucket_name].items():
            add_bucket(f"{bucket_name}:{key}", bucket, strong=True)
    for key, abbreviation_nodes in indexes["abbreviation"].items():
        add_bucket(f"abbreviation:{key}", list(abbreviation_nodes) + labels_to_nodes.get(key, []), strong=True)
    for key, parenthetical_nodes in indexes["parenthetical"].items():
        add_bucket(f"parenthetical:{key}", list(parenthetical_nodes) + labels_to_nodes.get(key, []), strong=True)
    for bucket_name in ("first_token", "prefix", "token_signature"):
        for key, bucket in indexes[bucket_name].items():
            add_bucket(f"{bucket_name}:{key}", bucket)

    return pairs


def _evaluate_pair(
    *,
    pair_index: int,
    left: CandidateNode,
    right: CandidateNode,
    min_score: float,
    high_priority_score: float,
) -> CandidatePair:
    features = score_pair_features(left, right)
    blocking = blocking_reasons(left, right, features.candidate_reasons)
    risks = sorted(set(features.risk_reasons) | set(risk_reasons(left, right)))
    score = features.score
    if "parent_child_suspect" in risks:
        score = max(0.0, round(score - 0.30, 6))
    if "short_alias_ambiguous" in blocking:
        score = max(0.0, round(score - 0.25, 6))

    if blocking:
        status = "blocked"
    elif "ambiguous_abbreviation" in risks or "generic_alias_conflict" in risks:
        status = "low_confidence_candidate"
    elif score >= high_priority_score or has_strong_reason(features.clean_candidate_reasons):
        status = "high_priority_candidate"
    elif score >= min_score and has_clean_reason(features.clean_candidate_reasons):
        status = "candidate"
    elif score >= min_score:
        status = "low_confidence_candidate"
    else:
        status = "rejected_low_score"

    metrics = dict(features.metrics)
    metrics["token_jaccard"] = round(token_jaccard(left.normalized_label, right.normalized_label), 6)
    scope_reasons = [reason for reason in blocking if "scope" in reason]
    abbreviation_source = [str(source) for source in metrics.get("abbreviation_source", [])]
    generic_alias_match = bool(metrics.get("generic_aliases_matched"))
    n3_pair_ready = _n3_pair_ready(
        status=status,
        clean_reasons=features.clean_candidate_reasons,
        risks=risks,
        blocking=blocking,
        generic_alias_match=generic_alias_match,
    )
    return CandidatePair(
        pair_id=f"p_{pair_index:09d}",
        left_node_id=left.node_id,
        right_node_id=right.node_id,
        entity_type=left.entity_type,
        left_label=left.label,
        right_label=right.label,
        score=score,
        pair_status=status,
        candidate_reasons=features.candidate_reasons,
        clean_candidate_reasons=features.clean_candidate_reasons,
        weak_candidate_reasons=features.weak_candidate_reasons,
        risk_reasons=risks,
        blocking_reasons=blocking,
        candidate_quality="n3_ready" if n3_pair_ready else status,
        scope_conflict_reasons=scope_reasons,
        abbreviation_source=abbreviation_source,
        generic_alias_match=generic_alias_match,
        n3_pair_ready=n3_pair_ready,
        metrics=metrics,
    )


def _n3_pair_ready(
    *,
    status: str,
    clean_reasons: list[str],
    risks: list[str],
    blocking: list[str],
    generic_alias_match: bool,
) -> bool:
    if status not in {"candidate", "high_priority_candidate"}:
        return False
    disallowed = {
        "both_context_only",
        "parent_child_suspect",
        "generic_alias_conflict",
        "ambiguous_abbreviation",
    }
    if blocking or set(risks) & disallowed or generic_alias_match:
        return False
    return has_clean_reason(clean_reasons)


def _group_by_type(nodes: list[CandidateNode]) -> dict[str, list[CandidateNode]]:
    grouped: dict[str, list[CandidateNode]] = defaultdict(list)
    for node in nodes:
        grouped[node.entity_type].append(node)
    return grouped


def _mention_ids_for_label(
    cluster: dict[str, Any],
    mentions_by_id: dict[str, dict[str, Any]],
    normalized_label: str,
) -> list[str]:
    fallback = [str(mention_id) for mention_id in cluster.get("mention_ids", [])]
    matched: list[str] = []
    for mention_id in fallback:
        mention = mentions_by_id.get(mention_id, {})
        if normalized_label and normalized_label in _mention_normalized_values(mention):
            matched.append(mention_id)
    return matched or fallback


def _mention_normalized_values(mention: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    normalized = mention.get("normalized", {})
    raw = mention.get("raw", {})
    if isinstance(normalized, dict):
        values.update(normalize_basic_text(value) for value in normalized.values() if isinstance(value, str))
    if isinstance(raw, dict):
        values.update(normalize_basic_text(value) for value in raw.values() if isinstance(value, str))
    values.discard("")
    return values


def _documents_for_mention_ids(
    mention_ids: list[str],
    mentions_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for mention_id in mention_ids:
        mention = mentions_by_id.get(mention_id, {})
        doc_id = str(mention.get("doc_id", ""))
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        result.append({"doc_id": doc_id, "document_name": str(mention.get("document_name", ""))})
        if len(result) >= 20:
            break
    return result


def _mention_count(cluster: dict[str, Any], mention_ids: list[str], *, label_override: str | None) -> int:
    if label_override:
        return len(mention_ids)
    return int(cluster.get("mentions_count", 0) or len(mention_ids))


def _document_count(
    cluster: dict[str, Any],
    documents: list[dict[str, str]],
    *,
    label_override: str | None,
) -> int:
    if label_override:
        return len(documents)
    return int(cluster.get("documents_count", 0) or len(documents))


def _role_count(
    cluster: dict[str, Any],
    mentions_by_id: dict[str, dict[str, Any]],
    mention_ids: list[str],
    role: str,
    *,
    label_override: str | None,
) -> int:
    if not label_override:
        return int(cluster.get(f"{role}_count", 0) or 0)
    return sum(1 for mention_id in mention_ids if _mention_has_role(mentions_by_id.get(mention_id, {}), role))


def _mention_has_role(mention: dict[str, Any], role: str) -> bool:
    routing_flags = {str(flag) for flag in mention.get("routing_flags", [])}
    tag_role = str(mention.get("tag_role", ""))
    if role == "article_candidate":
        return bool(mention.get("article_candidate")) or tag_role == "article_candidate" or role in routing_flags
    if role == "context_only":
        return tag_role == "context_only" or role in routing_flags
    if role == "folder_candidate":
        return tag_role == "folder_candidate" or role in routing_flags
    return False


def _key_payload(auto_cluster_key: str, entity_type: str) -> str:
    prefix = f"{entity_type}::"
    if auto_cluster_key.startswith(prefix):
        return auto_cluster_key[len(prefix) :]
    return ""


def _pair_sort_key(pair: CandidatePair) -> tuple[int, float, str]:
    status_rank = {
        "high_priority_candidate": 0,
        "candidate": 1,
        "low_confidence_candidate": 2,
        "blocked": 3,
        "rejected_low_score": 4,
    }.get(pair.pair_status, 9)
    return (status_rank, -pair.score, pair.pair_id)

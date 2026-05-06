from __future__ import annotations

import json
import re
from typing import Any

from kb_rebuild.normalization.n3.models import (
    GROUP_DECISIONS,
    SCHEMA_VERSION,
    SUBCLUSTER_DECISIONS,
    N3InputGroup,
    N3RejectedLabel,
    N3Subcluster,
)


N3_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidate_group_id": {"type": "string"},
        "decision": {"type": "string", "enum": sorted(GROUP_DECISIONS)},
        "confidence": {"type": "number"},
        "canonical_tag_ru": {"type": "string"},
        "canonical_tag_latin": {"type": "string"},
        "entity_type": {"type": "string"},
        "subclusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "subcluster_id": {"type": "string"},
                    "decision": {"type": "string", "enum": sorted(SUBCLUSTER_DECISIONS)},
                    "canonical_tag_ru": {"type": "string"},
                    "canonical_tag_latin": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "node_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "subcluster_id",
                    "decision",
                    "canonical_tag_ru",
                    "canonical_tag_latin",
                    "labels",
                    "node_ids",
                    "confidence",
                    "reason",
                ],
            },
        },
        "rejected_labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "node_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["label", "node_id", "reason"],
            },
        },
        "reason": {"type": "string"},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "requires_human_review": {"type": "boolean"},
    },
    "required": [
        "candidate_group_id",
        "decision",
        "confidence",
        "canonical_tag_ru",
        "canonical_tag_latin",
        "entity_type",
        "subclusters",
        "rejected_labels",
        "reason",
        "risk_flags",
        "requires_human_review",
    ],
    "schema_version": SCHEMA_VERSION,
}


def parse_decision_json(content: str) -> tuple[dict[str, Any] | None, list[str]]:
    stripped = content.strip()
    if not stripped:
        return None, ["empty LLM response"]
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        stripped = fence_match.group(1).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON: {exc}"]
    if not isinstance(parsed, dict):
        return None, ["LLM response must be a JSON object"]
    return parsed, []


def validate_decision_response(raw: dict[str, Any], group: N3InputGroup) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    required = N3_RESPONSE_SCHEMA["required"]
    for key in required:
        if key not in raw:
            errors.append(f"missing required field: {key}")
    if errors:
        return None, errors

    candidate_group_id = str(raw.get("candidate_group_id", ""))
    decision = str(raw.get("decision", ""))
    entity_type = str(raw.get("entity_type", ""))
    confidence = _float_or_none(raw.get("confidence"))
    if candidate_group_id != group.candidate_group_id:
        errors.append(f"candidate_group_id mismatch: {candidate_group_id} != {group.candidate_group_id}")
    if decision not in GROUP_DECISIONS:
        errors.append(f"unknown decision: {decision}")
    if entity_type != group.entity_type:
        errors.append(f"entity_type mismatch: {entity_type} != {group.entity_type}")
    if confidence is None or not 0.0 <= confidence <= 1.0:
        errors.append("confidence must be a number in [0, 1]")

    subclusters_raw = raw.get("subclusters")
    rejected_raw = raw.get("rejected_labels")
    risk_flags_raw = raw.get("risk_flags")
    if not isinstance(subclusters_raw, list):
        errors.append("subclusters must be an array")
        subclusters_raw = []
    if not isinstance(rejected_raw, list):
        errors.append("rejected_labels must be an array")
        rejected_raw = []
    if not isinstance(risk_flags_raw, list):
        errors.append("risk_flags must be an array")
        risk_flags_raw = []

    subclusters: list[N3Subcluster] = []
    for index, value in enumerate(subclusters_raw):
        if not isinstance(value, dict):
            errors.append(f"subclusters[{index}] must be an object")
            continue
        subcluster = N3Subcluster.from_dict(value)
        subclusters.append(subcluster)
        _validate_subcluster(subcluster, group, index, errors)

    rejected_labels: list[N3RejectedLabel] = []
    for index, value in enumerate(rejected_raw):
        if not isinstance(value, dict):
            errors.append(f"rejected_labels[{index}] must be an object")
            continue
        rejected = N3RejectedLabel.from_dict(value)
        rejected_labels.append(rejected)
        if rejected.node_id not in set(group.node_ids):
            errors.append(f"rejected_labels[{index}] unknown node_id: {rejected.node_id}")
        if rejected.label and rejected.label not in set(group.group_labels):
            errors.append(f"rejected_labels[{index}] unknown label: {rejected.label}")

    covered_by_subclusters: list[str] = [node_id for item in subclusters for node_id in item.node_ids]
    duplicates = sorted({node_id for node_id in covered_by_subclusters if covered_by_subclusters.count(node_id) > 1})
    if duplicates:
        errors.append(f"subclusters overlap by node_id: {duplicates}")
    input_node_ids = set(group.node_ids)
    covered = set(covered_by_subclusters)
    rejected_node_ids = {item.node_id for item in rejected_labels if item.node_id}

    if decision == "accept_same_entity":
        if len(subclusters) != 1:
            errors.append("accept_same_entity requires exactly one subcluster")
        if covered != input_node_ids:
            errors.append("accept_same_entity subcluster must cover all input node_ids")
        if rejected_labels:
            errors.append("accept_same_entity must not reject labels")
        if not str(raw.get("canonical_tag_ru", "")).strip():
            errors.append("accept_same_entity requires canonical_tag_ru")
        if subclusters and subclusters[0].decision != "same_entity":
            errors.append("accept_same_entity subcluster decision must be same_entity")
    elif decision == "split_into_subclusters":
        uncovered = input_node_ids - covered - rejected_node_ids
        if uncovered:
            errors.append(f"split_into_subclusters has uncovered node_ids: {sorted(uncovered)}")
        if not any(item.decision == "same_entity" and len(item.node_ids) >= 2 for item in subclusters):
            errors.append("split_into_subclusters must contain at least one useful same_entity subcluster")
    elif decision == "reject_distinct_entities":
        if any(item.decision == "same_entity" for item in subclusters):
            errors.append("reject_distinct_entities must not include same_entity subclusters")
    elif decision == "needs_web_or_human_review":
        if any(item.decision == "same_entity" for item in subclusters):
            errors.append("needs_web_or_human_review must not include final same_entity subclusters")

    if errors:
        return None, errors

    normalized = {
        "candidate_group_id": candidate_group_id,
        "decision": decision,
        "confidence": float(confidence or 0.0),
        "canonical_tag_ru": str(raw.get("canonical_tag_ru", "")),
        "canonical_tag_latin": str(raw.get("canonical_tag_latin", "")),
        "entity_type": entity_type,
        "subclusters": [item.to_dict() for item in subclusters],
        "rejected_labels": [item.to_dict() for item in rejected_labels],
        "reason": str(raw.get("reason", "")),
        "risk_flags": [str(flag) for flag in risk_flags_raw],
        "requires_human_review": bool(raw.get("requires_human_review", False)),
    }
    return normalized, []


def invalid_response_review_decision(group: N3InputGroup, errors: list[str]) -> dict[str, Any]:
    return {
        "candidate_group_id": group.candidate_group_id,
        "decision": "needs_web_or_human_review",
        "confidence": 0.0,
        "canonical_tag_ru": "",
        "canonical_tag_latin": "",
        "entity_type": group.entity_type,
        "subclusters": [],
        "rejected_labels": [
            {"label": label, "node_id": node_id, "reason": "invalid_llm_response"}
            for label, node_id in zip(group.group_labels, group.node_ids)
        ],
        "reason": "needs_human_review_due_to_invalid_llm_response: " + "; ".join(errors[:10]),
        "risk_flags": ["invalid_llm_response", "schema_validation_failed"],
        "requires_human_review": True,
    }


def _validate_subcluster(subcluster: N3Subcluster, group: N3InputGroup, index: int, errors: list[str]) -> None:
    if subcluster.decision not in SUBCLUSTER_DECISIONS:
        errors.append(f"subclusters[{index}] unknown decision: {subcluster.decision}")
    if not 0.0 <= subcluster.confidence <= 1.0:
        errors.append(f"subclusters[{index}] confidence must be in [0, 1]")
    for node_id in subcluster.node_ids:
        if node_id not in set(group.node_ids):
            errors.append(f"subclusters[{index}] unknown node_id: {node_id}")
    for label in subcluster.labels:
        if label not in set(group.group_labels):
            errors.append(f"subclusters[{index}] unknown label: {label}")
    if subcluster.decision == "same_entity" and len(subcluster.node_ids) >= 2 and not subcluster.canonical_tag_ru.strip():
        errors.append(f"subclusters[{index}] same_entity requires canonical_tag_ru")


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


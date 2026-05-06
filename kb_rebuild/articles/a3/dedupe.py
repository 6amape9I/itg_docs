from __future__ import annotations

import re
import unicodedata
from typing import Any


DASH_CHARS = "\u2010\u2011\u2012\u2013\u2014\u2212"
TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё%.,+-]+", re.UNICODE)
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?", re.UNICODE)


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\u00a0", " ").replace("ё", "е").replace("Ё", "е")
    for char in DASH_CHARS:
        text = text.replace(char, "-")
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(" \t\r\n.,;:!?()[]{}\"'")
    return text


def token_set(value: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(normalize_text(value)) if token}


def numeric_tokens(value: str) -> set[str]:
    return {match.group(0).replace(",", ".") for match in NUMBER_RE.finditer(normalize_text(value))}


def exact_dedupe_key(item: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(item.get("tag_id") or ""),
        str(item.get("fact_type") or ""),
        normalize_text(str(item.get("claim") or "")),
        normalize_text(str(item.get("quote") or "")),
        str(item.get("doc_id") or ""),
        str(item.get("window_id") or ""),
    )


def dedupe_evidence(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    for item in items:
        key = exact_dedupe_key(item)
        evidence_id = str(item.get("evidence_item_id") or "")
        if key not in seen:
            row = dict(item)
            row["original_evidence_item_ids"] = _provenance_ids(item)
            row["duplicate_evidence_item_ids"] = []
            row["normalized_claim"] = key[2]
            row["normalized_quote"] = key[3]
            seen[key] = row
            continue
        target = seen[key]
        target["original_evidence_item_ids"] = sorted(set(_provenance_ids(target) + _provenance_ids(item)))
        target["duplicate_evidence_item_ids"] = sorted(set(_list_value(target.get("duplicate_evidence_item_ids")) + [evidence_id]))
        duplicates.append(
            {
                "duplicate_evidence_item_id": evidence_id,
                "kept_evidence_item_id": target.get("evidence_item_id"),
                "tag_id": item.get("tag_id"),
                "fact_type": item.get("fact_type"),
                "doc_id": item.get("doc_id"),
                "window_id": item.get("window_id"),
                "normalized_claim": key[2],
                "normalized_quote": key[3],
            }
        )
    return list(seen.values()), duplicates


def _provenance_ids(item: dict[str, Any]) -> list[str]:
    ids = _list_value(item.get("original_evidence_item_ids"))
    evidence_id = str(item.get("evidence_item_id") or "")
    if evidence_id:
        ids.append(evidence_id)
    return sorted(set(ids))


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value:
        return [str(value)]
    return []


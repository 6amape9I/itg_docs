from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kb_rebuild.io.jsonl import read_jsonl
from kb_rebuild.parsing.documents import configure_csv_field_size_limit
from kb_rebuild.schemas.parsed_documents import ALLOWED_DOCUMENT_PARSE_STATUSES


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def validate_parsed_artifacts(
    data_dir: Path,
    input_path: Path | None = None,
    expected_docs: int | None = None,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict[str, Any] = {}

    parsed_path = data_dir / "parsed" / "parsed_documents.jsonl"
    blocks_path = data_dir / "parsed" / "document_blocks.jsonl"

    documents = _safe_read_jsonl(parsed_path, errors)
    blocks = _safe_read_jsonl(blocks_path, errors)
    if errors:
        return ValidationResult(ok=False, errors=errors, warnings=warnings, stats=stats)

    stats["documents_count"] = len(documents)
    stats["blocks_count"] = len(blocks)

    doc_ids: set[str] = set()
    block_counts_by_doc: Counter[str] = Counter()
    block_ids_by_doc: dict[str, set[str]] = defaultdict(set)

    for index, document in enumerate(documents, start=1):
        doc_id = document.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id:
            errors.append(f"document #{index}: missing or invalid doc_id")
            continue
        if doc_id in doc_ids:
            errors.append(f"duplicate doc_id: {doc_id}")
        doc_ids.add(doc_id)

        _require_field(document, "name", str, f"document {doc_id}", errors)
        _require_field(document, "content_hash", str, f"document {doc_id}", errors)
        _require_field(document, "clean_text", str, f"document {doc_id}", errors)
        parse_status = document.get("parse_status")
        if parse_status not in ALLOWED_DOCUMENT_PARSE_STATUSES:
            errors.append(f"document {doc_id}: invalid parse_status {parse_status!r}")
        if "blocks_count" in document and not isinstance(document["blocks_count"], int):
            errors.append(f"document {doc_id}: blocks_count must be int")

    for index, block in enumerate(blocks, start=1):
        doc_id = block.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id:
            errors.append(f"block #{index}: missing or invalid doc_id")
            continue
        if doc_id not in doc_ids:
            errors.append(f"block #{index}: references unknown doc_id {doc_id}")

        block_id = block.get("block_id")
        if not isinstance(block_id, str) or not block_id:
            errors.append(f"block #{index}: missing or invalid block_id")
        elif block_id in block_ids_by_doc[doc_id]:
            errors.append(f"document {doc_id}: duplicate block_id {block_id}")
        else:
            block_ids_by_doc[doc_id].add(block_id)

        _require_field(block, "block_index", int, f"block {doc_id}/{block_id}", errors)
        _require_field(block, "block_type", str, f"block {doc_id}/{block_id}", errors)
        _require_field(block, "text", str, f"block {doc_id}/{block_id}", errors)
        _require_field(block, "parse_status", str, f"block {doc_id}/{block_id}", errors)
        block_counts_by_doc[doc_id] += 1

    for document in documents:
        doc_id = document.get("doc_id")
        if not isinstance(doc_id, str):
            continue
        expected_blocks = document.get("blocks_count")
        if isinstance(expected_blocks, int) and block_counts_by_doc[doc_id] != expected_blocks:
            errors.append(
                f"document {doc_id}: blocks_count={expected_blocks}, "
                f"but document_blocks has {block_counts_by_doc[doc_id]}"
            )

    if expected_docs is not None and len(documents) != expected_docs:
        errors.append(f"expected {expected_docs} parsed documents, found {len(documents)}")

    if input_path is not None:
        if not input_path.exists():
            warnings.append(f"input CSV not found for source count check: {input_path}")
        else:
            source_count = _count_csv_rows(input_path)
            stats["source_documents_count"] = source_count
            if expected_docs is None and len(documents) != source_count:
                errors.append(f"source CSV has {source_count} rows, parsed artifact has {len(documents)}")

    return ValidationResult(ok=not errors, errors=errors, warnings=warnings, stats=stats)


def _safe_read_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        errors.append(f"missing artifact: {path}")
        return []
    try:
        return read_jsonl(path)
    except ValueError as exc:
        errors.append(str(exc))
        return []


def _require_field(
    record: dict[str, Any],
    field_name: str,
    expected_type: type,
    context: str,
    errors: list[str],
) -> None:
    value = record.get(field_name)
    if not isinstance(value, expected_type):
        errors.append(f"{context}: field {field_name} must be {expected_type.__name__}")


def _count_csv_rows(input_path: Path) -> int:
    configure_csv_field_size_limit()
    with input_path.open("r", encoding="utf-8-sig", newline="") as fh:
        return sum(1 for _ in csv.DictReader(fh))

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

from kb_rebuild.parsing.editorjs import content_sha256, parse_editorjs_content
from kb_rebuild.schemas.parsed_documents import DocumentBlockRecord, ParsedDocumentRecord


REQUIRED_COLUMNS = {"name", "description", "content"}


def configure_csv_field_size_limit() -> None:
    field_size_limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(field_size_limit)
            return
        except OverflowError:
            field_size_limit = field_size_limit // 10


def generate_doc_id(row_index: int, content: str, existing_ids: set[str] | None = None) -> tuple[str, bool]:
    content_hash = content_sha256(content)
    base_doc_id = f"doc_{row_index:06d}_{content_hash[:8]}"
    if existing_ids is None or base_doc_id not in existing_ids:
        return base_doc_id, False

    suffix = 2
    while f"{base_doc_id}_dup{suffix}" in existing_ids:
        suffix += 1
    return f"{base_doc_id}_dup{suffix}", True


def parse_csv_documents(input_path: Path, limit: int | None = None) -> tuple[
    list[ParsedDocumentRecord],
    list[DocumentBlockRecord],
    int,
    list[dict[str, Any]],
]:
    documents: list[ParsedDocumentRecord] = []
    blocks: list[DocumentBlockRecord] = []
    duplicate_doc_ids = 0
    errors: list[dict[str, Any]] = []
    seen_doc_ids: set[str] = set()

    configure_csv_field_size_limit()
    with input_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_COLUMNS - fieldnames)
        if missing_columns:
            raise ValueError(f"CSV is missing required columns: {', '.join(missing_columns)}")

        for row_index, row in enumerate(reader, start=1):
            if limit is not None and len(documents) >= limit:
                break
            document, document_blocks, duplicate = parse_document_row(row, row_index, seen_doc_ids)
            seen_doc_ids.add(document.doc_id)
            duplicate_doc_ids += int(duplicate)
            documents.append(document)
            blocks.extend(document_blocks)

            for parse_error in document.parse_errors:
                if parse_error == "empty_content":
                    continue
                errors.append(
                    {
                        "doc_id": document.doc_id,
                        "row_index": row_index,
                        "parse_status": document.parse_status,
                        "error": parse_error,
                    }
                )

    return documents, blocks, duplicate_doc_ids, errors


def parse_document_row(
    row: dict[str, Any],
    row_index: int,
    existing_doc_ids: set[str] | None = None,
) -> tuple[ParsedDocumentRecord, list[DocumentBlockRecord], bool]:
    raw_content = "" if row.get("content") is None else str(row.get("content"))
    doc_id, duplicate = generate_doc_id(row_index, raw_content, existing_doc_ids)
    content_hash = content_sha256(raw_content)
    parsed = parse_editorjs_content(raw_content, doc_id=doc_id)

    record = ParsedDocumentRecord(
        doc_id=doc_id,
        row_index=row_index,
        name="" if row.get("name") is None else str(row.get("name")),
        description="" if row.get("description") is None else str(row.get("description")),
        content_hash=content_hash,
        parse_status=parsed.parse_status,
        parse_errors=parsed.parse_errors,
        clean_text=parsed.clean_text,
        text_length_chars=len(parsed.clean_text),
        blocks_count=len(parsed.blocks),
        non_empty_blocks_count=sum(1 for block in parsed.blocks if block.text),
        block_types=parsed.block_types,
        block_parse_statuses=parsed.block_parse_statuses,
        empty_or_unhandled_blocks_count=parsed.empty_or_unhandled_blocks_count,
    )
    return record, parsed.blocks, duplicate

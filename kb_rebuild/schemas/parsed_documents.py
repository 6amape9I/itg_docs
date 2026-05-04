from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ALLOWED_DOCUMENT_PARSE_STATUSES = {"ok", "partial", "failed", "empty"}


@dataclass(frozen=True)
class DocumentBlockRecord:
    doc_id: str
    block_id: str
    block_index: int
    block_type: str
    text: str
    text_length_chars: int
    metadata: dict[str, Any]
    raw_block_hash: str
    parse_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParsedDocumentRecord:
    doc_id: str
    row_index: int
    name: str
    description: str
    content_hash: str
    parse_status: str
    parse_errors: list[str]
    clean_text: str
    text_length_chars: int
    blocks_count: int
    non_empty_blocks_count: int
    block_types: dict[str, int]
    block_parse_statuses: dict[str, int] = field(default_factory=dict)
    empty_or_unhandled_blocks_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

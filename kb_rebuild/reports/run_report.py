from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from kb_rebuild.schemas.parsed_documents import ParsedDocumentRecord


@dataclass
class RunReport:
    stage: str = "parse"
    documents_total: int = 0
    documents_parsed_ok: int = 0
    documents_parse_partial: int = 0
    documents_parse_failed: int = 0
    documents_empty: int = 0
    blocks_total: int = 0
    block_types: dict[str, int] = field(default_factory=dict)
    duplicate_doc_ids: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    input_file: str = ""
    output_dir: str = ""
    limit: int | None = None

    @classmethod
    def from_documents(
        cls,
        documents: list[ParsedDocumentRecord],
        duplicate_doc_ids: int,
        errors: list[dict[str, Any]],
        input_file: Path,
        output_dir: Path,
        limit: int | None,
    ) -> "RunReport":
        status_counts = Counter(doc.parse_status for doc in documents)
        block_types: Counter[str] = Counter()
        blocks_total = 0
        for doc in documents:
            block_types.update(doc.block_types)
            blocks_total += doc.blocks_count

        return cls(
            documents_total=len(documents),
            documents_parsed_ok=status_counts.get("ok", 0),
            documents_parse_partial=status_counts.get("partial", 0),
            documents_parse_failed=status_counts.get("failed", 0),
            documents_empty=status_counts.get("empty", 0),
            blocks_total=blocks_total,
            block_types=dict(sorted(block_types.items())),
            duplicate_doc_ids=duplicate_doc_ids,
            errors=errors,
            input_file=str(input_file),
            output_dir=str(output_dir),
            limit=limit,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_run_report(path: Path, report: RunReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)

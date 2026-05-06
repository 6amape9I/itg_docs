from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from kb_rebuild.articles.planning.models import A0Config, PlanningInputs
from kb_rebuild.io.jsonl import read_jsonl
from kb_rebuild.parsing.documents import configure_csv_field_size_limit


def load_planning_inputs(config: A0Config) -> PlanningInputs:
    warnings: list[str] = []
    _validate_config(config)
    paths = _input_paths(config)
    _validate_required_paths(paths)

    final_report = _read_json(paths["final_report"])
    if not bool(final_report.get("quality", {}).get("passed")):
        raise ValueError("A0 refuses to run unless final_normalization_report.quality.passed=true")

    canonical_tags = read_csv_dicts(paths["tags_canonical"])
    aliases = read_csv_dicts(paths["tag_aliases"])
    document_links = read_jsonl(paths["document_links"])
    expected_links = int(final_report.get("counts", {}).get("document_tag_links_total") or 0)
    if expected_links != len(document_links):
        raise ValueError(
            "final_normalization_report.counts.document_tag_links_total "
            f"({expected_links}) != document_tag_links_normalized.jsonl rows ({len(document_links)})"
        )

    final_manifest = _read_optional_json(paths["final_manifest"])
    tag_mentions_normalized: list[dict[str, Any]] = []
    if paths["tag_mentions_normalized"].exists():
        tag_mentions_normalized = read_jsonl(paths["tag_mentions_normalized"])
    else:
        warnings.append(f"optional tag_mentions_normalized missing: {paths['tag_mentions_normalized']}")

    tag_mentions_raw: list[dict[str, Any]] = []
    if paths["tag_mentions_raw"].exists():
        tag_mentions_raw = read_jsonl(paths["tag_mentions_raw"])
    else:
        warnings.append(f"optional tag_mentions_raw missing: {paths['tag_mentions_raw']}")

    return PlanningInputs(
        canonical_tags=canonical_tags,
        aliases=aliases,
        document_links=document_links,
        documents=read_jsonl(paths["parsed_documents"]),
        blocks=read_jsonl(paths["document_blocks"]),
        tag_mentions_normalized=tag_mentions_normalized,
        tag_mentions_raw=tag_mentions_raw,
        final_report=final_report,
        final_manifest=final_manifest,
        warnings=warnings,
    )


def read_csv_dicts(path: Path) -> list[dict[str, Any]]:
    configure_csv_field_size_limit()
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [dict(row) for row in reader]


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [text]
    if isinstance(parsed, list):
        return parsed
    return [parsed]


def _validate_config(config: A0Config) -> None:
    if config.max_neighbor_blocks < 0:
        raise ValueError("max_neighbor_blocks must be >= 0")
    if config.max_window_chars <= 0:
        raise ValueError("max_window_chars must be > 0")
    if config.short_document_char_limit <= 0:
        raise ValueError("short_document_char_limit must be > 0")
    if config.low_count_doc_threshold < 1:
        raise ValueError("low_count_doc_threshold must be >= 1")
    if config.high_frequency_doc_threshold <= config.low_count_doc_threshold:
        raise ValueError("high_frequency_doc_threshold must be > low_count_doc_threshold")
    if config.review_sample_size < 0:
        raise ValueError("review_sample_size must be >= 0")


def _input_paths(config: A0Config) -> dict[str, Path]:
    return {
        "tags_canonical": config.normalization_final_dir / "tags_canonical.csv",
        "tag_aliases": config.normalization_final_dir / "tag_aliases.csv",
        "document_links": config.normalization_final_dir / "document_tag_links_normalized.jsonl",
        "document_tags_by_doc": config.normalization_final_dir / "document_tags_normalized_by_doc.jsonl",
        "final_report": config.normalization_final_dir / "final_normalization_report.json",
        "final_manifest": config.normalization_final_dir / "final_normalization_manifest.json",
        "parsed_documents": config.parsed_dir / "parsed_documents.jsonl",
        "document_blocks": config.parsed_dir / "document_blocks.jsonl",
        "tag_mentions_normalized": config.normalization_dir / "tag_mentions_normalized.jsonl",
        "tag_mentions_raw": config.normalization_dir / "tag_mentions_raw.jsonl",
    }


def _validate_required_paths(paths: dict[str, Path]) -> None:
    required = (
        "tags_canonical",
        "tag_aliases",
        "document_links",
        "document_tags_by_doc",
        "final_report",
        "parsed_documents",
        "document_blocks",
    )
    for name in required:
        path = paths[name]
        if not path.exists():
            raise FileNotFoundError(f"missing A0 input {name}: {path}")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path)

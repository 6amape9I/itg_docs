from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from kb_rebuild.articles.a5.report import write_json


MAX_FILENAME_BASE_BYTES = 180


def prepare_output_dir(out_dir: Path, *, overwrite: bool, known_files: list[Path]) -> None:
    for_n8n = out_dir / "for_n8n"
    for_docs = out_dir / "for_docs"
    if overwrite:
        for path in (for_n8n, for_docs):
            if path.exists():
                shutil.rmtree(path)
        for path in known_files:
            if path.exists():
                path.unlink()
    else:
        existing = [path for path in (for_n8n, for_docs, *known_files) if path.exists()]
        if existing:
            raise ValueError("A5 output already exists; pass --overwrite or choose another --out: " + ", ".join(str(path) for path in existing[:10]))
    for_n8n.mkdir(parents=True, exist_ok=True)
    for_docs.mkdir(parents=True, exist_ok=True)


def write_article_exports(article: dict[str, Any], companion: dict[str, Any], *, n8n_path: Path, docs_path: Path, quotes_path: Path) -> None:
    write_json(n8n_path, article)
    write_json(docs_path, article)
    write_json(quotes_path, companion)


def json_file_is_valid(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8") as fh:
            json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False
    return True


def export_filename_base(article: dict[str, Any]) -> str:
    entity_type = safe_filename_part(article.get("entity_type"), fallback="unknown")
    canonical_name = _canonical_filename_source(article)
    canonical_part = safe_filename_part(canonical_name, fallback=str(article.get("tag_id") or "untitled"))
    base = f"{entity_type}_{canonical_part}"
    if base.endswith("_quotes"):
        base = f"{base}_article"
    return trim_filename_base(base)


def unique_export_filename_base(article: dict[str, Any], used_bases: set[str]) -> str:
    base = export_filename_base(article)
    if base not in used_bases:
        used_bases.add(base)
        return base

    tag_id_part = safe_filename_part(article.get("tag_id"), fallback="tag")
    suffix = f"_{tag_id_part}"
    candidate = _with_suffix(base, suffix)
    counter = 2
    while candidate in used_bases:
        candidate = _with_suffix(base, f"{suffix}_{counter}")
        counter += 1
    used_bases.add(candidate)
    return candidate


def safe_filename_part(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip() or fallback
    text = re.sub(r"[\x00-\x1f\x7f/\\:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"_+", "_", text)
    text = text.strip(" ._")
    if not text:
        text = fallback
    return text


def trim_filename_base(value: str, *, max_bytes: int = MAX_FILENAME_BASE_BYTES) -> str:
    text = value.strip(" ._") or "untitled"
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    trimmed = encoded[:max_bytes].decode("utf-8", errors="ignore").strip(" ._")
    return trimmed or "untitled"


def _canonical_filename_source(article: dict[str, Any]) -> str:
    canonical_ru = str(article.get("canonical_tag_ru") or "").strip()
    if canonical_ru:
        return canonical_ru
    canonical_latin = str(article.get("canonical_tag_latin") or "").strip()
    if canonical_latin:
        return canonical_latin
    return str(article.get("tag_id") or "").strip()


def _with_suffix(base: str, suffix: str) -> str:
    max_base_bytes = MAX_FILENAME_BASE_BYTES - len(suffix.encode("utf-8"))
    return f"{trim_filename_base(base, max_bytes=max_base_bytes)}{suffix}"

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


STAGE = "article_a5_final_export_assembly"
STAGE_VERSION = "a5.0"

A4_COMPILED_STATUSES = {"compiled_article", "compiled_with_review_flag"}
A1_EXPORT_STATUSES = {"direct_copy_article", "stub_only", "review_stub"}
EMPTY_QUOTES_STATUSES = {
    "stub_only",
    "review_stub",
    "insufficient_evidence_review",
    "export_repair_stub",
    "missing_article_source",
}
VALID_QUOTE_STATUSES = {"exact", "normalized_exact"}


@dataclass(frozen=True)
class A5Config:
    data_dir: Path = Path("data")
    a1_dir: Path = Path("data/articles/a1")
    a3_dir: Path = Path("data/articles/a3")
    a4_dir: Path = Path("data/articles/a4/production_v1")
    entities_dir: Path = Path("data/articles/entities")
    normalization_final_dir: Path = Path("data/normalization/final")
    out_dir: Path = Path("data/articles/final_exports")
    overwrite: bool = False

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Path,
        *,
        a1_dir: Path | None = None,
        a3_dir: Path | None = None,
        a4_dir: Path | None = None,
        entities_dir: Path | None = None,
        normalization_final_dir: Path | None = None,
        out_dir: Path | None = None,
        overwrite: bool = False,
    ) -> "A5Config":
        return cls(
            data_dir=data_dir,
            a1_dir=a1_dir or data_dir / "articles" / "a1",
            a3_dir=a3_dir or data_dir / "articles" / "a3",
            a4_dir=a4_dir or data_dir / "articles" / "a4" / "production_v1",
            entities_dir=entities_dir or data_dir / "articles" / "entities",
            normalization_final_dir=normalization_final_dir or data_dir / "normalization" / "final",
            out_dir=out_dir or data_dir / "articles" / "final_exports",
            overwrite=overwrite,
        )


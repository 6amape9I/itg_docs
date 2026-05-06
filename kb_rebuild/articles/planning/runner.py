from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from kb_rebuild.articles.planning.loaders import bool_value, list_value, load_planning_inputs
from kb_rebuild.articles.planning.matching import (
    build_alias_dictionary,
    build_quote_context,
    find_match_hits,
)
from kb_rebuild.articles.planning.models import A0Config, STRATEGIES
from kb_rebuild.articles.planning.report import (
    HIGH_FREQUENCY_FIELDS,
    SOURCE_WINDOW_QUALITY_FIELDS,
    STRATEGY_SUMMARY_FIELDS,
    TAG_WORK_PLAN_CSV_FIELDS,
    build_manifest,
    build_report,
    source_window_quality_rows,
    strategy_summary_rows,
    utc_now,
    write_csv,
    write_json,
)
from kb_rebuild.articles.planning.strategy import select_strategy
from kb_rebuild.articles.planning.windows import build_windows_for_tag_doc
from kb_rebuild.io.jsonl import write_jsonl


OUTPUT_FILENAMES = {
    "tag_source_index_jsonl": "tag_source_index.jsonl",
    "tag_work_plan_jsonl": "tag_work_plan.jsonl",
    "source_block_windows_jsonl": "source_block_windows.jsonl",
    "direct_copy_candidates_jsonl": "direct_copy_candidates.jsonl",
    "singleton_candidates_jsonl": "singleton_candidates.jsonl",
    "stub_only_tags_jsonl": "stub_only_tags.jsonl",
    "review_stub_tags_jsonl": "review_stub_tags.jsonl",
    "no_source_window_tags_jsonl": "no_source_window_tags.jsonl",
    "article_planning_report_json": "article_planning_report.json",
    "article_planning_manifest_json": "article_planning_manifest.json",
    "tag_work_plan_csv": "tag_work_plan.csv",
    "strategy_summary_by_entity_type_csv": "strategy_summary_by_entity_type.csv",
    "high_frequency_tags_csv": "high_frequency_tags.csv",
    "source_window_quality_report_csv": "source_window_quality_report.csv",
}


def run_article_planning_a0(config: A0Config) -> dict[str, Any]:
    return ArticlePlanningA0Runner(config).run()


class ArticlePlanningA0Runner:
    def __init__(self, config: A0Config) -> None:
        self.config = config
        self.outputs = {name: config.out_dir / filename for name, filename in OUTPUT_FILENAMES.items()}
        self.inputs = {
            "tags_canonical_csv": config.normalization_final_dir / "tags_canonical.csv",
            "tag_aliases_csv": config.normalization_final_dir / "tag_aliases.csv",
            "document_tag_links_normalized_jsonl": config.normalization_final_dir / "document_tag_links_normalized.jsonl",
            "document_tags_normalized_by_doc_jsonl": config.normalization_final_dir / "document_tags_normalized_by_doc.jsonl",
            "final_normalization_report_json": config.normalization_final_dir / "final_normalization_report.json",
            "final_normalization_manifest_json": config.normalization_final_dir / "final_normalization_manifest.json",
            "parsed_documents_jsonl": config.parsed_dir / "parsed_documents.jsonl",
            "document_blocks_jsonl": config.parsed_dir / "document_blocks.jsonl",
            "tag_mentions_normalized_jsonl": config.normalization_dir / "tag_mentions_normalized.jsonl",
            "tag_mentions_raw_jsonl": config.normalization_dir / "tag_mentions_raw.jsonl",
        }

    def run(self) -> dict[str, Any]:
        created_at = utc_now()
        self._validate_outputs()
        loaded = load_planning_inputs(self.config)

        tags_by_id = {str(row.get("tag_id") or ""): row for row in loaded.canonical_tags}
        aliases_by_tag = build_alias_dictionary(loaded.canonical_tags, loaded.aliases, loaded.document_links)
        links_by_tag = _links_by_tag(loaded.document_links)
        links_by_tag_doc = _links_by_tag_doc(loaded.document_links)
        docs_by_id = {str(row.get("doc_id") or ""): row for row in loaded.documents}
        blocks_by_doc = _blocks_by_doc(loaded.blocks)
        article_candidate_tags_by_doc = _article_candidate_tags_by_doc(loaded.document_links)
        quote_context = build_quote_context(loaded.tag_mentions_normalized)

        source_index = [
            _source_index_row(tag, links_by_tag.get(str(tag.get("tag_id") or ""), []), aliases_by_tag.get(str(tag.get("tag_id") or ""), []))
            for tag in loaded.canonical_tags
        ]
        source_index_by_tag = {str(row.get("tag_id") or ""): row for row in source_index}

        window_records: list[dict[str, Any]] = []
        window_id_counter = 1
        for source_row in source_index:
            tag_id = str(source_row.get("tag_id") or "")
            tag = tags_by_id.get(tag_id, {})
            aliases = aliases_by_tag.get(tag_id, [])
            for doc_id in source_row.get("source_doc_ids", []):
                doc = docs_by_id.get(str(doc_id))
                blocks = blocks_by_doc.get(str(doc_id), [])
                if doc is None or not blocks:
                    continue
                tag_doc_links = links_by_tag_doc.get((tag_id, str(doc_id)), [])
                mention_ids = [str(link.get("mention_id") or "") for link in tag_doc_links if str(link.get("mention_id") or "")]
                allow_short = tag_id in article_candidate_tags_by_doc.get(str(doc_id), set()) and len(article_candidate_tags_by_doc.get(str(doc_id), set())) == 1
                hits = find_match_hits(
                    config=self.config,
                    tag_id=tag_id,
                    aliases=aliases,
                    doc=doc,
                    blocks=blocks,
                    mention_ids=mention_ids,
                    quote_context=quote_context,
                    allow_short_document_fallback=allow_short,
                )
                drafts = build_windows_for_tag_doc(
                    config=self.config,
                    tag=tag,
                    doc=doc,
                    blocks=blocks,
                    hits=hits,
                    mention_ids=mention_ids,
                )
                for draft in drafts:
                    window_records.append(draft.to_dict(f"win_{window_id_counter:09d}"))
                    window_id_counter += 1

        windows_by_tag = _windows_by_tag(window_records)
        work_plans = [
            _work_plan_row(
                config=self.config,
                source_row=source_row,
                windows=windows_by_tag.get(str(source_row.get("tag_id") or ""), []),
                aliases=aliases_by_tag.get(str(source_row.get("tag_id") or ""), []),
                doc_by_id=docs_by_id,
                article_candidate_tags_by_doc=article_candidate_tags_by_doc,
            )
            for source_row in source_index
        ]

        self._validate_quality(source_index, work_plans, window_records, docs_by_id, tags_by_id)
        report = build_report(
            created_at=created_at,
            source_index=source_index,
            work_plans=work_plans,
            windows=window_records,
            warnings=loaded.warnings,
        )
        manifest = build_manifest(created_at=created_at, config=self.config, inputs=self.inputs, outputs=self.outputs)
        self._write_outputs(source_index, work_plans, window_records, report, manifest)
        return report

    def _validate_outputs(self) -> None:
        if self.config.overwrite:
            return
        existing = [path for path in self.outputs.values() if path.exists()]
        if existing:
            raise FileExistsError(f"A0 output exists and --no-overwrite was set: {existing[0]}")

    def _validate_quality(
        self,
        source_index: list[dict[str, Any]],
        work_plans: list[dict[str, Any]],
        windows: list[dict[str, Any]],
        docs_by_id: dict[str, dict[str, Any]],
        tags_by_id: dict[str, dict[str, Any]],
    ) -> None:
        source_tag_ids = {str(row.get("tag_id") or "") for row in source_index}
        work_tag_ids = {str(row.get("tag_id") or "") for row in work_plans}
        if source_tag_ids != work_tag_ids:
            raise ValueError("missing tag_id in work_plan")
        for window in windows:
            if str(window.get("tag_id") or "") not in tags_by_id:
                raise ValueError(f"source window references missing tag_id: {window.get('window_id')}")
            if str(window.get("doc_id") or "") not in docs_by_id:
                raise ValueError(f"source window references missing doc_id: {window.get('window_id')}")
            if not str(window.get("window_text") or "").strip():
                raise ValueError(f"source window has empty window_text: {window.get('window_id')}")
        for plan in work_plans:
            strategy = str(plan.get("strategy") or "")
            if strategy not in STRATEGIES:
                raise ValueError(f"unknown strategy for {plan.get('tag_id')}: {strategy}")
            if strategy == "direct_copy_candidate" and int(plan.get("documents_count") or 0) != 1:
                raise ValueError(f"direct_copy_candidate has documents_count != 1: {plan.get('tag_id')}")
            if strategy == "stub_only" and bool_value(plan.get("article_candidate")):
                raise ValueError(f"stub_only has article_candidate=true: {plan.get('tag_id')}")

    def _write_outputs(
        self,
        source_index: list[dict[str, Any]],
        work_plans: list[dict[str, Any]],
        windows: list[dict[str, Any]],
        report: dict[str, Any],
        manifest: dict[str, Any],
    ) -> None:
        write_jsonl(self.outputs["tag_source_index_jsonl"], source_index)
        write_jsonl(self.outputs["source_block_windows_jsonl"], windows)
        write_jsonl(self.outputs["tag_work_plan_jsonl"], work_plans)
        write_jsonl(self.outputs["direct_copy_candidates_jsonl"], _direct_copy_candidates(work_plans, windows))
        write_jsonl(self.outputs["singleton_candidates_jsonl"], _singleton_candidates(work_plans))
        write_jsonl(self.outputs["stub_only_tags_jsonl"], (plan for plan in work_plans if plan.get("strategy") == "stub_only"))
        write_jsonl(
            self.outputs["review_stub_tags_jsonl"],
            (plan for plan in work_plans if plan.get("strategy") in {"review_stub", "no_source_window_review"}),
        )
        write_jsonl(
            self.outputs["no_source_window_tags_jsonl"],
            (
                plan
                for plan in work_plans
                if int(plan.get("mentions_count") or 0) > 0 and int(plan.get("source_windows_count") or 0) == 0
            ),
        )
        write_json(self.outputs["article_planning_report_json"], report)
        write_json(self.outputs["article_planning_manifest_json"], manifest)
        write_csv(self.outputs["tag_work_plan_csv"], TAG_WORK_PLAN_CSV_FIELDS, work_plans)
        write_csv(self.outputs["strategy_summary_by_entity_type_csv"], STRATEGY_SUMMARY_FIELDS, strategy_summary_rows(work_plans))
        write_csv(self.outputs["high_frequency_tags_csv"], HIGH_FREQUENCY_FIELDS, _high_frequency_tags(work_plans, self.config))
        write_csv(self.outputs["source_window_quality_report_csv"], SOURCE_WINDOW_QUALITY_FIELDS, source_window_quality_rows(windows))


def _links_by_tag(links: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link in links:
        grouped[str(link.get("tag_id") or "")].append(link)
    return dict(grouped)


def _links_by_tag_doc(links: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for link in links:
        grouped[(str(link.get("tag_id") or ""), str(link.get("doc_id") or ""))].append(link)
    return dict(grouped)


def _blocks_by_doc(blocks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for block in blocks:
        grouped[str(block.get("doc_id") or "")].append(block)
    return {doc_id: sorted(items, key=lambda block: int(block.get("block_index") or 0)) for doc_id, items in grouped.items()}


def _article_candidate_tags_by_doc(links: list[dict[str, Any]]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for link in links:
        if bool_value(link.get("article_candidate")):
            grouped[str(link.get("doc_id") or "")].add(str(link.get("tag_id") or ""))
    return dict(grouped)


def _source_index_row(tag: dict[str, Any], links: list[dict[str, Any]], aliases: list[Any]) -> dict[str, Any]:
    source_doc_ids = _dedupe(str(link.get("doc_id") or "") for link in links if str(link.get("doc_id") or ""))
    doc_name_by_id = {
        str(link.get("doc_id") or ""): str(link.get("document_name") or "")
        for link in links
        if str(link.get("doc_id") or "")
    }
    return {
        "tag_id": str(tag.get("tag_id") or ""),
        "canonical_tag_ru": str(tag.get("canonical_tag_ru") or ""),
        "canonical_tag_latin": str(tag.get("canonical_tag_latin") or ""),
        "entity_type": str(tag.get("entity_type") or ""),
        "article_candidate": bool_value(tag.get("article_candidate")),
        "need_review": bool_value(tag.get("need_review") if "need_review" in tag else tag.get("needs_review")),
        "primary_role": str(tag.get("primary_role") or ""),
        "mentions_count": len(links),
        "documents_count": len(source_doc_ids),
        "aliases": _dedupe(alias.display for alias in aliases if alias.display),
        "source_doc_ids": source_doc_ids,
        "source_doc_names": [doc_name_by_id.get(doc_id, "") for doc_id in source_doc_ids],
        "review_reasons": [str(item) for item in list_value(tag.get("review_reasons"))],
        "source_mentions": [
            {
                "mention_id": str(link.get("mention_id") or ""),
                "doc_id": str(link.get("doc_id") or ""),
                "document_name": str(link.get("document_name") or ""),
                "raw_surface": str(link.get("raw_surface") or ""),
                "tag_role": str(link.get("tag_role") or ""),
                "confidence": _float_value(link.get("confidence")),
            }
            for link in links
        ],
    }


def _work_plan_row(
    *,
    config: A0Config,
    source_row: dict[str, Any],
    windows: list[dict[str, Any]],
    aliases: list[Any],
    doc_by_id: dict[str, dict[str, Any]],
    article_candidate_tags_by_doc: dict[str, set[str]],
) -> dict[str, Any]:
    decision = select_strategy(
        config=config,
        source_index=source_row,
        windows=windows,
        aliases=aliases,
        doc_by_id=doc_by_id,
        article_candidate_tags_by_doc=article_candidate_tags_by_doc,
    )
    high_quality = sum(1 for window in windows if window.get("window_quality") == "high")
    low_quality = sum(1 for window in windows if window.get("window_quality") == "low")
    medium_quality = sum(1 for window in windows if window.get("window_quality") == "medium")
    source_doc_ids = list(source_row.get("source_doc_ids", []))
    competing_count = None
    if len(source_doc_ids) == 1:
        doc_id = str(source_doc_ids[0])
        competing_count = max(0, len(article_candidate_tags_by_doc.get(doc_id, set()) - {str(source_row.get("tag_id") or "")}))
    return {
        "tag_id": source_row["tag_id"],
        "canonical_tag_ru": source_row["canonical_tag_ru"],
        "canonical_tag_latin": source_row["canonical_tag_latin"],
        "entity_type": source_row["entity_type"],
        "article_candidate": source_row["article_candidate"],
        "need_review": source_row["need_review"],
        "primary_role": source_row["primary_role"],
        "mentions_count": source_row["mentions_count"],
        "documents_count": source_row["documents_count"],
        "source_windows_count": len(windows),
        "high_quality_windows_count": high_quality,
        "medium_quality_windows_count": medium_quality,
        "low_quality_windows_count": low_quality,
        "strategy": decision.strategy,
        "strategy_reasons": decision.strategy_reasons,
        "estimated_llm_extraction_tasks": decision.estimated_llm_extraction_tasks,
        "estimated_article_compilation_tasks": decision.estimated_article_compilation_tasks,
        "can_create_stub_without_llm": decision.can_create_stub_without_llm,
        "can_direct_copy": decision.can_direct_copy,
        "needs_review_before_article": decision.needs_review_before_article,
        "source_window_ids": [str(window.get("window_id") or "") for window in windows],
        "source_doc_ids": source_doc_ids,
        "source_doc_names": source_row.get("source_doc_names", []),
        "competing_article_candidate_tags_in_doc": competing_count,
        "review_reasons": source_row.get("review_reasons", []),
    }


def _windows_by_tag(windows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for window in windows:
        grouped[str(window.get("tag_id") or "")].append(window)
    return dict(grouped)


def _direct_copy_candidates(work_plans: list[dict[str, Any]], windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    windows_by_id = {str(window.get("window_id") or ""): window for window in windows}
    rows: list[dict[str, Any]] = []
    for plan in work_plans:
        if plan.get("strategy") != "direct_copy_candidate":
            continue
        source_window_ids = [str(item) for item in plan.get("source_window_ids", [])]
        candidate_windows = [windows_by_id[item] for item in source_window_ids if item in windows_by_id]
        best_coverage = max((float(window.get("coverage_ratio_estimate") or 0.0) for window in candidate_windows), default=0.0)
        doc_id = str((plan.get("source_doc_ids") or [""])[0])
        document_name = str(candidate_windows[0].get("document_name") or "") if candidate_windows else ""
        rows.append(
            {
                "tag_id": plan.get("tag_id"),
                "canonical_tag_ru": plan.get("canonical_tag_ru"),
                "doc_id": doc_id,
                "document_name": document_name,
                "reason": plan.get("strategy_reasons"),
                "source_window_ids": source_window_ids,
                "coverage_ratio_estimate": best_coverage,
            }
        )
    return rows


def _singleton_candidates(work_plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for plan in work_plans:
        if int(plan.get("documents_count") or 0) != 1:
            continue
        source_doc_ids = list(plan.get("source_doc_ids") or [])
        source_doc_names = list(plan.get("source_doc_names") or [])
        rows.append(
            {
                "tag_id": plan.get("tag_id"),
                "canonical_tag_ru": plan.get("canonical_tag_ru"),
                "entity_type": plan.get("entity_type"),
                "strategy": plan.get("strategy"),
                "doc_id": str(source_doc_ids[0]) if source_doc_ids else "",
                "document_name": str(source_doc_names[0]) if source_doc_names else "",
                "article_candidate": plan.get("article_candidate"),
                "need_review": plan.get("need_review"),
                "source_windows_count": plan.get("source_windows_count"),
                "competing_article_candidate_tags_in_doc": plan.get("competing_article_candidate_tags_in_doc"),
            }
        )
    return rows


def _high_frequency_tags(work_plans: list[dict[str, Any]], config: A0Config) -> list[dict[str, Any]]:
    return [
        {
            "tag_id": plan.get("tag_id"),
            "canonical_tag_ru": plan.get("canonical_tag_ru"),
            "entity_type": plan.get("entity_type"),
            "documents_count": plan.get("documents_count"),
            "mentions_count": plan.get("mentions_count"),
            "source_windows_count": plan.get("source_windows_count"),
            "strategy": plan.get("strategy"),
        }
        for plan in work_plans
        if int(plan.get("documents_count") or 0) > config.high_frequency_doc_threshold
    ]


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

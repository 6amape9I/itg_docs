from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kb_rebuild.articles.planning.loaders import bool_value, list_value
from kb_rebuild.articles.planning.matching import AliasTerm, title_matches_alias
from kb_rebuild.articles.planning.models import A0Config


CRITICAL_REVIEW_MARKERS = (
    "alias_conflict",
    "drug_policy_review",
    "merge_conflict",
    "unresolved_review",
    "unresolved review",
)


@dataclass(frozen=True)
class StrategyDecision:
    strategy: str
    strategy_reasons: list[str]
    estimated_llm_extraction_tasks: int
    estimated_article_compilation_tasks: int
    can_create_stub_without_llm: bool
    can_direct_copy: bool
    needs_review_before_article: bool


def select_strategy(
    *,
    config: A0Config,
    source_index: dict[str, Any],
    windows: list[dict[str, Any]],
    aliases: list[AliasTerm],
    doc_by_id: dict[str, dict[str, Any]],
    article_candidate_tags_by_doc: dict[str, set[str]],
) -> StrategyDecision:
    article_candidate = bool_value(source_index.get("article_candidate"))
    need_review = bool_value(source_index.get("need_review"))
    primary_role = str(source_index.get("primary_role") or "")
    mentions_count = int(source_index.get("mentions_count") or 0)
    documents_count = int(source_index.get("documents_count") or 0)
    source_windows_count = len(windows)
    review_reasons = [str(item) for item in list_value(source_index.get("review_reasons"))]
    critical_review = _has_critical_review(review_reasons)
    low_quality_windows = sum(1 for window in windows if window.get("window_quality") == "low")
    review_before_article = bool(need_review or low_quality_windows)

    if need_review and (critical_review or not article_candidate):
        return _decision(
            "review_stub",
            ["need_review", "critical_review_reason" if critical_review else "non_article_candidate_review"],
            needs_review_before_article=True,
        )

    if not article_candidate and primary_role in {"context_only", "folder_candidate"} and not need_review:
        return _decision("stub_only", ["not_article_candidate", primary_role])

    if mentions_count > 0 and source_windows_count == 0:
        return _decision(
            "no_source_window_review",
            ["has_mentions", "source_windows_count_zero"],
            needs_review_before_article=True,
        )

    if article_candidate and mentions_count == 0:
        return _decision(
            "review_stub",
            ["article_candidate", "mentions_count_zero"],
            needs_review_before_article=True,
        )

    if article_candidate:
        if documents_count == 1:
            if _can_direct_copy(
                source_index=source_index,
                windows=windows,
                aliases=aliases,
                doc_by_id=doc_by_id,
                article_candidate_tags_by_doc=article_candidate_tags_by_doc,
            ):
                return _decision(
                    "direct_copy_candidate",
                    [
                        "article_candidate",
                        "single_document",
                        "no_review",
                        "no_competing_article_candidate_tags",
                        "title_matches_alias",
                        "window_covers_most_document_or_short_fallback",
                    ],
                    can_direct_copy=True,
                    needs_review_before_article=False,
                )
            if source_windows_count > 0:
                return _decision(
                    "single_doc_extract",
                    ["article_candidate", "single_document", "not_direct_copy_candidate"],
                    extraction_tasks=source_windows_count,
                    compilation_tasks=1,
                    needs_review_before_article=review_before_article,
                )
        if 2 <= documents_count <= config.low_count_doc_threshold:
            return _decision(
                "low_count_batch_extract",
                ["article_candidate", "documents_count_within_low_threshold"],
                extraction_tasks=source_windows_count,
                compilation_tasks=1,
                needs_review_before_article=review_before_article,
            )
        if documents_count > config.high_frequency_doc_threshold:
            return _decision(
                "high_frequency_map_reduce",
                ["article_candidate", "documents_count_gt_high_frequency_threshold"],
                extraction_tasks=source_windows_count,
                compilation_tasks=1,
                needs_review_before_article=review_before_article,
            )
        if documents_count > config.low_count_doc_threshold:
            return _decision(
                "multi_doc_map_reduce",
                ["article_candidate", "documents_count_gt_low_count_threshold"],
                extraction_tasks=source_windows_count,
                compilation_tasks=1,
                needs_review_before_article=review_before_article,
            )

    if need_review:
        return _decision("review_stub", ["need_review"], needs_review_before_article=True)
    return _decision("stub_only", ["fallback_non_article_candidate"])


def _can_direct_copy(
    *,
    source_index: dict[str, Any],
    windows: list[dict[str, Any]],
    aliases: list[AliasTerm],
    doc_by_id: dict[str, dict[str, Any]],
    article_candidate_tags_by_doc: dict[str, set[str]],
) -> bool:
    if bool_value(source_index.get("need_review")):
        return False
    if len(windows) == 0:
        return False
    source_doc_ids = list_value(source_index.get("source_doc_ids"))
    if len(source_doc_ids) != 1:
        return False
    doc_id = str(source_doc_ids[0])
    doc = doc_by_id.get(doc_id)
    if not doc:
        return False
    competing_tags = article_candidate_tags_by_doc.get(doc_id, set()) - {str(source_index.get("tag_id") or "")}
    if competing_tags:
        return False
    if not title_matches_alias(str(doc.get("name") or ""), aliases):
        return False
    max_coverage = max(float(window.get("coverage_ratio_estimate") or 0.0) for window in windows)
    has_short_fallback = any(window.get("match_method") == "short_doc_fallback" for window in windows)
    return bool(has_short_fallback or max_coverage >= 0.8)


def _decision(
    strategy: str,
    reasons: list[str],
    *,
    extraction_tasks: int = 0,
    compilation_tasks: int = 0,
    can_direct_copy: bool = False,
    needs_review_before_article: bool = False,
) -> StrategyDecision:
    return StrategyDecision(
        strategy=strategy,
        strategy_reasons=reasons,
        estimated_llm_extraction_tasks=extraction_tasks,
        estimated_article_compilation_tasks=compilation_tasks,
        can_create_stub_without_llm=strategy in {"stub_only", "review_stub", "no_source_window_review"},
        can_direct_copy=can_direct_copy,
        needs_review_before_article=needs_review_before_article,
    )


def _has_critical_review(review_reasons: list[str]) -> bool:
    for reason in review_reasons:
        normalized = reason.lower()
        if any(marker in normalized for marker in CRITICAL_REVIEW_MARKERS):
            return True
    return False

from __future__ import annotations

from typing import Any

from kb_rebuild.articles.a5.models import A4_COMPILED_STATUSES, VALID_QUOTE_STATUSES


QUESTION_TEMPLATES = {
    "definition": "Что такое {tag}?",
    "description": "Что известно о {tag}?",
    "classification": "Как классифицируется {tag}?",
    "mechanism": "Каков механизм или принцип действия для {tag}?",
    "cause_or_risk_factor": "Какие причины или факторы риска связаны с {tag}?",
    "symptom": "Какие симптомы описаны для {tag}?",
    "diagnostics": "Как диагностируют или оценивают {tag}?",
    "treatment": "Какие подходы к лечению описаны для {tag}?",
    "prevention": "Какие меры профилактики описаны для {tag}?",
    "complication": "Какие осложнения связаны с {tag}?",
    "indication": "Для чего применяется {tag}?",
    "contraindication": "Какие противопоказания описаны для {tag}?",
    "side_effect": "Какие побочные эффекты описаны для {tag}?",
    "usage_or_dosage": "Как применяется {tag}?",
    "procedure_step": "Какие этапы выполнения описаны для {tag}?",
    "preparation": "Какая подготовка описана для {tag}?",
    "interpretation": "Как интерпретируются результаты, связанные с {tag}?",
    "composition": "Каков состав или компоненты {tag}?",
    "safety_warning": "Какие меры безопасности описаны для {tag}?",
    "other": "Что сказано о {tag}?",
}


def build_companion_quotes(
    article: dict[str, Any],
    *,
    fact_groups_by_id: dict[str, dict[str, Any]],
    source_fact_groups_path: str,
    source_article_path: str,
) -> dict[str, Any]:
    status = str(article.get("article_status") or "")
    if status in A4_COMPILED_STATUSES:
        return _compiled_companion(
            article,
            fact_groups_by_id=fact_groups_by_id,
            source_fact_groups_path=source_fact_groups_path,
            source_article_path=source_article_path,
        )
    if status == "direct_copy_article":
        questions_status = "pending_fact_extraction_or_manual"
        quotes_status = "direct_copy_no_fact_groups"
    else:
        questions_status = "not_applicable_or_pending"
        quotes_status = "no_usable_evidence"
    return _base_companion(
        article,
        questions_generation_status=questions_status,
        quotes_source_status=quotes_status,
        questions=[],
        quotes=[],
        source_fact_groups_path=source_fact_groups_path,
        source_article_path=source_article_path,
    )


def _compiled_companion(
    article: dict[str, Any],
    *,
    fact_groups_by_id: dict[str, dict[str, Any]],
    source_fact_groups_path: str,
    source_article_path: str,
) -> dict[str, Any]:
    sources = article.get("sources") if isinstance(article.get("sources"), dict) else {}
    used_fact_group_ids = _unique_strings(_string_list(sources.get("used_fact_group_ids")) + _string_list(article.get("used_fact_group_ids")))
    quotes: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    canonical = str(article.get("canonical_tag_ru") or "").strip() or str(article.get("tag_id") or "")
    tag_id = str(article.get("tag_id") or "")

    for fact_group_id in used_fact_group_ids:
        fact_group = fact_groups_by_id.get(fact_group_id)
        if not _valid_fact_group(fact_group):
            continue
        quote_index = len(quotes) + 1
        fact_type = str(fact_group.get("fact_type") or "other").strip() or "other"
        quote_status = str(fact_group.get("representative_quote_validation_status") or "").strip()
        needs_review = bool(fact_group.get("needs_review_before_publication"))
        quote = {
            "quote_id": f"quote_{tag_id}_{quote_index:03d}",
            "fact_group_id": fact_group_id,
            "fact_type": fact_type,
            "claim": str(fact_group.get("representative_claim") or "").strip(),
            "quote": str(fact_group.get("representative_quote") or "").strip(),
            "source_doc_ids": _string_list(fact_group.get("source_doc_ids")),
            "source_window_ids": _string_list(fact_group.get("source_window_ids")),
            "quote_validation_status": quote_status,
            "used_in_article": True,
            "needs_review": needs_review,
        }
        question_text = _question_text(canonical, fact_type, fact_group, seen_questions)
        question = {
            "question_id": f"q_{tag_id}_{quote_index:03d}",
            "question": question_text,
            "answer_quote": quote["quote"],
            "fact_group_id": fact_group_id,
            "fact_type": fact_type,
            "source_doc_ids": quote["source_doc_ids"],
            "quote_validation_status": quote_status,
            "needs_review": needs_review,
        }
        seen_questions.add(question_text)
        quotes.append(quote)
        questions.append(question)

    quotes_status = "from_a3_fact_groups" if quotes else "empty_or_unavailable"
    questions_status = "deterministic_draft" if questions else "not_applicable_or_pending"
    return _base_companion(
        article,
        questions_generation_status=questions_status,
        quotes_source_status=quotes_status,
        questions=questions,
        quotes=quotes,
        source_fact_groups_path=source_fact_groups_path,
        source_article_path=source_article_path,
    )


def _base_companion(
    article: dict[str, Any],
    *,
    questions_generation_status: str,
    quotes_source_status: str,
    questions: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    source_fact_groups_path: str,
    source_article_path: str,
) -> dict[str, Any]:
    return {
        "tag_id": str(article.get("tag_id") or ""),
        "canonical_tag_ru": str(article.get("canonical_tag_ru") or ""),
        "canonical_tag_latin": article.get("canonical_tag_latin"),
        "entity_type": str(article.get("entity_type") or ""),
        "article_status": str(article.get("article_status") or ""),
        "needs_review_before_publication": bool(article.get("needs_review_before_publication")),
        "review_reasons": _string_list(article.get("review_reasons")),
        "questions_generation_status": questions_generation_status,
        "quotes_source_status": quotes_source_status,
        "questions": questions,
        "quotes": quotes,
        "provenance": {
            "source_fact_groups": source_fact_groups_path,
            "source_article": source_article_path,
        },
    }


def _valid_fact_group(fact_group: dict[str, Any] | None) -> bool:
    if not fact_group:
        return False
    if not bool(fact_group.get("usable_for_a4")):
        return False
    if str(fact_group.get("representative_quote_validation_status") or "") not in VALID_QUOTE_STATUSES:
        return False
    return bool(str(fact_group.get("representative_quote") or "").strip())


def _question_text(canonical: str, fact_type: str, fact_group: dict[str, Any], seen: set[str]) -> str:
    template = QUESTION_TEMPLATES.get(fact_type, QUESTION_TEMPLATES["other"])
    question = template.format(tag=canonical)
    if question not in seen:
        return question
    section = str(fact_group.get("section_hint") or "").strip()
    if section:
        question = f"Что сказано о {canonical} в разделе «{section}»?"
        if question not in seen:
            return question
    question = f"Что сказано о {canonical} по теме «{fact_type}»?"
    if question not in seen:
        return question
    return f"{question} ({fact_group.get('fact_group_id') or len(seen) + 1})"


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    stripped = str(value).strip()
    return [stripped] if stripped else []


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

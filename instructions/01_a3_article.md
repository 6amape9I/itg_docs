# A3. Evidence Dedupe & Fact Grouping

## 0. Контекст

A2 production завершён и принят как evidence extraction stage.

A2 обработал всю очередь из A1:

```text
tasks_requested = 34 995
tasks_processed = 34 995
tasks_failed = 0
evidence_items_total = 72 843
evidence_items_valid_quotes = 69 280
evidence_items_quote_not_found = 3 563
quote_not_found_share = 0.048913
quality.passed = true

A2 работал в production mode:

provider = gemini_direct
model = gemini-3-flash-preview
experiment_name = production_v1
limit = null
max_inflight = 16
max_tasks_per_batch = 8
batch_char_limit = 60000
max_output_tokens = 12000
repair_max_output_tokens = 24000

Главные A2 outputs:

data/articles/a2/production_v1/evidence_items.jsonl
data/articles/a2/production_v1/evidence_task_results.jsonl
data/articles/a2/production_v1/quote_validation_issues.jsonl
data/articles/a2/production_v1/a2_report.json
data/articles/a2/production_v1/a2_manifest.json

A3 должен взять 72 843 сырых evidence items и подготовить компактные, безопасные fact groups для будущей сборки статей на A4.

A3 не должен писать статьи. A3 не должен вызывать LLM.

1. Главная цель A3

A3 должен превратить сырые evidence items в проверенный слой фактов:

raw evidence_items → filtered evidence → deduplicated fact_groups → tag_fact_group_index

Главный output для A4:

data/articles/a3/fact_groups.jsonl
data/articles/a3/tag_fact_group_index.jsonl
data/articles/a3/a4_compilation_input.jsonl

A4 должен получать не 72k сырых items, а компактные fact groups по каждому tag_id.

2. Не цели A3

На A3 запрещено:

вызывать LLM;
делать web search;
писать финальные статьи;
компилировать Editor.js articles;
изменять A2 outputs;
изменять A1 entity JSON;
изменять A0/A1/N1/N2/N3/N4 outputs;
добавлять внешние медицинские знания;
создавать новые медицинские утверждения;
строить folders;
строить knowledge graph.

A3 — deterministic data processing stage.

3. Входные файлы A3

Обязательные:

data/articles/a2/production_v1/evidence_items.jsonl
data/articles/a2/production_v1/evidence_task_results.jsonl
data/articles/a2/production_v1/quote_validation_issues.jsonl
data/articles/a2/production_v1/a2_report.json
data/articles/a2/production_v1/a2_manifest.json

data/articles/a1/article_status_index.jsonl
data/articles/a1/tag_work_plan_adjusted.jsonl
data/articles/a1/a1_report.json
data/articles/a1/a1_manifest.json

data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv

Опциональные, но полезные:

data/articles/a1/publication_review_queue.jsonl
data/articles/a1/hard_review_queue.jsonl
data/articles/a1/direct_copy_articles.jsonl
data/articles/a1/pending_extraction_articles.jsonl
data/articles/a2/production_v1/manual_qa_sample.csv

A3 runner должен отказаться запускаться, если:

A2 report stage != article_a2_evidence_extraction
A2 quality.passed != true
A2 tasks_failed > 0
A2 evidence_items_total = 0
A2 quote_not_found_share > 0.05
A1 quality.passed != true

Если quote_not_found_share <= 0.05, A3 может работать, но обязан вынести not_found evidence в rejected/review слой.

4. Выходные файлы A3

Создать директорию:

data/articles/a3/

Обязательные outputs:

data/articles/a3/evidence_items_valid.jsonl
data/articles/a3/evidence_items_review.jsonl
data/articles/a3/evidence_items_rejected.jsonl

data/articles/a3/evidence_deduped.jsonl
data/articles/a3/fact_groups.jsonl
data/articles/a3/tag_fact_group_index.jsonl
data/articles/a3/a4_compilation_input.jsonl

data/articles/a3/tags_without_usable_evidence.jsonl
data/articles/a3/tag_evidence_coverage.jsonl

data/articles/a3/fact_groups.csv
data/articles/a3/tag_evidence_coverage.csv
data/articles/a3/rejected_evidence_summary.csv
data/articles/a3/review_evidence_summary.csv

data/articles/a3/a3_report.json
data/articles/a3/a3_manifest.json

Дополнительные QA outputs:

data/articles/a3/manual_qa_fact_groups_sample.csv
data/articles/a3/high_volume_tags.csv
data/articles/a3/duplicate_evidence_diagnostics.csv
data/articles/a3/quote_status_by_entity_type.csv
5. Рекомендуемая структура кода

Создать пакет:

kb_rebuild/articles/a3/

Файлы:

kb_rebuild/articles/a3/__init__.py
kb_rebuild/articles/a3/models.py
kb_rebuild/articles/a3/filtering.py
kb_rebuild/articles/a3/dedupe.py
kb_rebuild/articles/a3/grouping.py
kb_rebuild/articles/a3/coverage.py
kb_rebuild/articles/a3/report.py
kb_rebuild/articles/a3/runner.py

Назначение:

models.py    — constants/enums/dataclasses
filtering.py — valid/review/rejected evidence classification
dedupe.py    — exact and near-duplicate detection
grouping.py  — deterministic fact group building
coverage.py  — per-tag coverage and A4 readiness
report.py    — reports/CSV/JSON writers
runner.py    — orchestration

Добавить CLI:

python -m kb_rebuild article-a3-group-evidence --data data

Флаги:

--a2-dir data/articles/a2/production_v1
--a1-dir data/articles/a1
--normalization-final-dir data/normalization/final
--out data/articles/a3
--min-confidence 0.5
--allow-fuzzy-for-review
--max-quotes-per-fact-group 8
--max-fact-groups-per-tag 200
--no-overwrite

По умолчанию:

LLM disabled
web disabled
fuzzy evidence not usable for A4 without review
quote_not_found rejected
6. Evidence classification

A3 должен классифицировать каждый evidence item в один из слоёв:

valid
review
rejected
6.1 Valid evidence

Evidence item считается valid, если:

quote_validation_status in {exact, normalized_exact}
relevance = direct
fact_type != related_entity
claim is non-empty
quote is non-empty
confidence >= min_confidence

needs_review_before_publication=true НЕ запрещает valid evidence, но этот флаг должен сохраняться в fact group.

То есть evidence может быть:

usable_for_a4 = true
needs_review_before_publication = true
6.2 Review evidence

Evidence item идёт в review, если:

quote_validation_status = fuzzy
needs_review_before_publication = true
relevance in {related, unclear}
fact_type = related_entity
confidence < min_confidence
window_quality = low
review_reasons not empty

Review evidence не должна теряться. Она может использоваться A4 только для секции “Связанные сущности” или после ручной проверки.

6.3 Rejected evidence

Evidence item идёт в rejected, если:

quote_validation_status = not_found
quote contains ... or …
quote is stitched/non-contiguous
quote empty
claim empty
relevance = not_relevant
task_id/tag_id mismatch if detected

Rejected evidence не должно попадать в fact_groups как usable evidence.

7. Quote status policy

A3 должен строго соблюдать:

exact → usable
normalized_exact → usable
fuzzy → review only
not_found → rejected

fuzzy можно хранить в fact group metadata, но:

usable_for_a4 = false

если в группе нет хотя бы одного exact/normalized_exact item.

not_found не использовать для A4 compilation.

8. Deduplication

A3 должен дедуплицировать evidence items до группировки.

8.1 Exact duplicate key

Удалять/схлопывать exact duplicate evidence по ключу:

tag_id
fact_type
normalized_claim
normalized_quote
doc_id
window_id

Сохранять provenance всех исходных evidence_item_id.

8.2 Quote duplicate key

Если у одного tag_id + fact_type одинаковая normalized quote, но claim слегка отличается, считать это одним evidence group candidate.

8.3 Claim duplicate key

Если у одного tag_id + fact_type одинаковый normalized claim, но quotes разные, это не duplicate, а multi-source support.

Оно должно стать одним fact group с несколькими evidence items.

8.4 Normalization

Для claim/quote normalization:

lowercase
ё → е
unicode normalize
collapse whitespace
strip punctuation at ends
replace non-breaking spaces
normalize dash variants

Не удалять медицинские числа, типы, дозировки, проценты и латинские обозначения.

9. Fact grouping

A3 должен группировать evidence items внутри:

tag_id + fact_type

Не группировать разные tag_id.

Не группировать разные fact_type, кроме редких технических случаев, которые должны идти в review.

9.1 Grouping rules

Создать fact group, если items имеют:

same normalized claim
or same normalized quote
or high deterministic claim similarity

Для high deterministic similarity использовать стандартную библиотеку Python:

difflib.SequenceMatcher
token Jaccard

Рекомендуемые пороги:

claim_sequence_similarity >= 0.88
or token_jaccard >= 0.82

Но если fact_type разный — не группировать.

9.2 No semantic overmerge

Не объединять claims, если они отличаются по:

числам;
дозировкам;
процентам;
типам;
стадиям;
локализациям;
противоположному смыслу;
разным объектам процедуры;
разным препаратам;
разным заболеваниям.

Если похожесть высокая, но есть числовой конфликт:

review group

а не обычный fact group.

9.3 Stable fact_group_id

Создать deterministic id:

fg_{hash12}

Hash от:

tag_id
fact_type
primary_claim_norm
representative_quote_norm
sorted evidence_item_ids
10. Fact group schema

fact_groups.jsonl: одна строка = одна fact group.

Формат:

{
  "fact_group_id": "fg_abcdef123456",

  "tag_id": "...",
  "canonical_tag_ru": "...",
  "canonical_tag_latin": null,
  "entity_type": "disease",

  "fact_type": "definition",
  "section_hint": "Что это",

  "representative_claim": "...",
  "representative_quote": "...",
  "representative_quote_validation_status": "exact",

  "importance": "high",
  "confidence": 0.92,

  "evidence_item_ids": [],
  "source_task_ids": [],
  "source_doc_ids": [],
  "source_window_ids": [],

  "evidence_items_count": 3,
  "source_documents_count": 2,
  "valid_evidence_count": 3,
  "review_evidence_count": 0,
  "rejected_evidence_count": 0,

  "quote_status_counts": {
    "exact": 2,
    "normalized_exact": 1,
    "fuzzy": 0,
    "not_found": 0
  },

  "needs_review_before_publication": false,
  "review_reasons": [],

  "usable_for_a4": true,
  "a4_usage": "core_fact",
  "created_from_stage": "a3.0"
}
11. Choosing representative claim and quote

Representative claim:

Prefer item with importance=high.
Prefer highest confidence.
Prefer quote_validation_status=exact over normalized_exact.
Prefer shorter, clearer claim if confidence tie.
Do not synthesize a new claim.

Representative quote:

Prefer exact.
Then normalized_exact.
Do not use fuzzy as representative if exact/normalized exists.
Never use not_found.

A3 must not generate new medical claims. It only selects one existing claim.

12. A4 usage categories

Each fact group must have a4_usage:

core_fact
supporting_fact
related_only
review_only
not_usable

Rules:

core_fact
usable_for_a4=true
fact_type in {definition, description, classification, mechanism, symptom, diagnostics, treatment, indication, usage_or_dosage, procedure_step, composition}
importance in {high, medium}
valid_evidence_count >= 1
supporting_fact
usable_for_a4=true
importance=low
or fact_type in {other, interpretation, preparation, prevention, complication, safety_warning, side_effect, contraindication}
related_only
fact_type=related_entity
or relevance=related
review_only
only fuzzy evidence
publication review required
source window low quality
not_usable
only not_found/rejected evidence

Only core_fact and supporting_fact should be used by default in A4 article compilation.

13. Tag fact group index

Create:

tag_fact_group_index.jsonl

One row per tag_id from A1 article_status_index.

Format:

{
  "tag_id": "...",
  "canonical_tag_ru": "...",
  "canonical_tag_latin": null,
  "entity_type": "disease",

  "article_status": "pending_single_doc_extract",
  "article_candidate": true,

  "evidence_items_total": 12,
  "valid_evidence_items": 10,
  "review_evidence_items": 1,
  "rejected_evidence_items": 1,

  "fact_groups_total": 5,
  "core_fact_groups": 3,
  "supporting_fact_groups": 2,
  "review_only_fact_groups": 0,

  "source_documents_count": 2,
  "fact_types": ["definition", "symptom", "diagnostics"],

  "ready_for_a4": true,
  "a4_strategy": "compile_from_fact_groups",
  "needs_review_before_publication": false,
  "review_reasons": []
}
14. A4 compilation input

Create:

a4_compilation_input.jsonl

One row per tag that is ready for A4 or needs explicit stub/review handling.

Format:

{
  "tag_id": "...",
  "canonical_tag_ru": "...",
  "entity_type": "disease",
  "article_status_from_a1": "pending_single_doc_extract",

  "a4_strategy": "compile_from_fact_groups",
  "ready_for_a4": true,

  "fact_group_ids": [],
  "core_fact_group_ids": [],
  "supporting_fact_group_ids": [],
  "review_only_fact_group_ids": [],

  "source_documents_count": 2,
  "usable_fact_groups_count": 5,

  "needs_review_before_publication": false,
  "review_reasons": []
}

A4 strategies:

direct_copy_already_done
compile_from_fact_groups
compile_with_review_flag
insufficient_evidence_review
stub_only
review_stub
14.1 direct_copy_article

For A1 direct_copy_article:

ready_for_a4 = false
a4_strategy = direct_copy_already_done

No evidence extraction needed.

14.2 stub_only / review_stub

For A1 stub_only:

ready_for_a4 = false
a4_strategy = stub_only

For A1 review_stub:

ready_for_a4 = false
a4_strategy = review_stub
14.3 pending extraction with usable groups

If tag has core/supporting fact groups:

ready_for_a4 = true
a4_strategy = compile_from_fact_groups

If it has usable groups but needs_review_before_publication=true:

a4_strategy = compile_with_review_flag
14.4 pending extraction with no usable groups

If tag has A2 tasks but no usable evidence:

ready_for_a4 = false
a4_strategy = insufficient_evidence_review

Record in:

tags_without_usable_evidence.jsonl
15. Coverage and diagnostics

Create:

tag_evidence_coverage.jsonl
tag_evidence_coverage.csv

Coverage must include all 22 513 final tags from A1 status index.

Expected categories:

direct_copy_article
stub_only
review_stub
pending_with_usable_evidence
pending_without_usable_evidence

A3 must report:

final_tags_total
tags_with_a2_tasks
tags_with_evidence_items
tags_with_valid_evidence
tags_without_usable_evidence
direct_copy_tags
stub_only_tags
review_stub_tags
ready_for_a4_tags
16. Handling review-heavy evidence

A2 has many tasks_review, mostly because A1 propagated publication review flags.

A3 should not discard valid evidence just because status=review.

If an item has exact/normalized quote and direct relevance:

it can be valid evidence
but fact group gets needs_review_before_publication=true

So review status from A2 is not the same as rejected evidence.

17. Handling quote_not_found

A3 must move all quote_validation_status=not_found evidence to:

evidence_items_rejected.jsonl

Also summarize:

rejected_evidence_summary.csv

Fields:

entity_type
fact_type
reason
items_count
tags_count
documents_count

Do not include not_found items in usable fact groups.

18. Handling fuzzy quotes

A3 must move fuzzy quote items to:

evidence_items_review.jsonl

unless the same fact group has exact/normalized evidence.

If a fact group contains both exact and fuzzy items:

usable_for_a4=true
review_evidence_count includes fuzzy
needs_review_before_publication=true
review_reasons includes fuzzy_quote_evidence_present

If a fact group contains only fuzzy items:

usable_for_a4=false
a4_usage=review_only
19. Manual QA sample

Create:

manual_qa_fact_groups_sample.csv

Fields:

fact_group_id
tag_id
canonical_tag_ru
entity_type
fact_type
representative_claim
representative_quote
quote_status
source_documents_count
evidence_items_count
usable_for_a4
a4_usage
needs_review_before_publication
review_reasons

Include:

20 high-confidence valid fact groups
20 groups with multiple source documents
20 review-only groups
20 tags_without_usable_evidence
all fact groups from top 10 high-volume tags if feasible
20. Reports

Create:

a3_report.json

Structure:

{
  "stage": "article_a3_evidence_dedupe_fact_grouping",
  "stage_version": "a3.0",
  "created_at": "...",

  "input": {
    "a2_evidence_items": "data/articles/a2/production_v1/evidence_items.jsonl",
    "a2_task_results": "data/articles/a2/production_v1/evidence_task_results.jsonl",
    "a1_status_index": "data/articles/a1/article_status_index.jsonl"
  },

  "counts": {
    "final_tags_total": 0,
    "a2_evidence_items_total": 0,

    "valid_evidence_items": 0,
    "review_evidence_items": 0,
    "rejected_evidence_items": 0,

    "deduped_evidence_items": 0,
    "exact_duplicate_items_removed": 0,

    "fact_groups_total": 0,
    "usable_fact_groups": 0,
    "review_only_fact_groups": 0,

    "tags_with_a2_tasks": 0,
    "tags_with_evidence_items": 0,
    "tags_with_valid_evidence": 0,
    "tags_without_usable_evidence": 0,

    "ready_for_a4_tags": 0,
    "compile_with_review_flag_tags": 0,
    "direct_copy_already_done_tags": 0,
    "stub_only_tags": 0,
    "review_stub_tags": 0
  },

  "by_entity_type": {},
  "by_fact_type": {},
  "quote_validation": {},

  "quality": {
    "all_evidence_items_accounted_for": true,
    "no_not_found_in_usable_fact_groups": true,
    "all_fact_groups_have_tag_id": true,
    "all_a4_ready_tags_have_fact_groups": true,
    "tag_fact_group_index_complete": true,
    "passed": true
  },

  "warnings": []
}

Manifest:

a3_manifest.json

Should include all inputs, outputs, config, stage_version.

21. Quality gates

A3 passes if:

all A2 evidence items are in exactly one of valid/review/rejected
no evidence_item_id lost
no duplicate evidence_item_id in final outputs
no quote_validation_status=not_found in usable fact groups
no fuzzy-only fact group is marked usable_for_a4
all fact_groups have tag_id/canonical/entity_type
tag_fact_group_index contains all A1 tag_ids
a4_compilation_input contains all A1 tag_ids or all non-direct/stub tags with explicit strategy
ready_for_a4 tags have at least one usable fact group
quality.passed=true

If any of these fail, A3 must exit non-zero or write quality.passed=false.

22. Tests

Add tests:

tests/test_article_a3_filtering.py
tests/test_article_a3_dedupe.py
tests/test_article_a3_grouping.py
tests/test_article_a3_coverage.py
tests/test_article_a3_runner.py
tests/test_article_a3_report.py
22.1 Filtering tests
exact quote + direct relevance → valid.
normalized_exact quote → valid.
fuzzy quote → review.
not_found quote → rejected.
related_entity fact_type → review/related_only.
needs_review_before_publication with exact quote remains valid but review flag preserved.
22.2 Dedupe tests
exact duplicate evidence removed.
same quote with different claim grouped.
same claim with different quotes grouped as multi-source support.
different numeric values are not merged.
different dosages are not merged.
different disease types are not merged.
22.3 Grouping tests
groups only inside same tag_id + fact_type.
representative claim selected from existing claim.
representative quote never uses not_found.
fuzzy-only group is review_only.
group with exact+fuzzy remains usable but review flagged.
22.4 Coverage tests
tag_fact_group_index includes all A1 tags.
pending tag without usable evidence goes to insufficient_evidence_review.
direct_copy_article goes to direct_copy_already_done.
stub_only/review_stub preserved.
22.5 Runner tests
creates all required outputs.
refuses bad A2 quality.
refuses quote_not_found_share > 0.05.
report counts consistent.
quality gate fails if evidence item is unaccounted.

Run:

.venv/bin/python -m unittest discover -s tests

Compile:

.venv/bin/python -m py_compile \
  kb_rebuild/articles/a3/models.py \
  kb_rebuild/articles/a3/filtering.py \
  kb_rebuild/articles/a3/dedupe.py \
  kb_rebuild/articles/a3/grouping.py \
  kb_rebuild/articles/a3/coverage.py \
  kb_rebuild/articles/a3/report.py \
  kb_rebuild/articles/a3/runner.py \
  kb_rebuild/cli.py
23. CLI command

Run A3:

.venv/bin/python -m kb_rebuild article-a3-group-evidence \
  --data data \
  --a2-dir data/articles/a2/production_v1 \
  --a1-dir data/articles/a1 \
  --normalization-final-dir data/normalization/final \
  --out data/articles/a3 \
  --min-confidence 0.5 \
  --max-quotes-per-fact-group 8 \
  --max-fact-groups-per-tag 200
24. Feedback after A3

Create:

docs/article_a3_feedback.md

Feedback must include:

1. Что сделано.
2. Какие файлы изменены.
3. Какие команды запускались.
4. Сколько tests passed.
5. A2 evidence items total.
6. Valid/review/rejected evidence counts.
7. Exact duplicates removed.
8. Fact groups total.
9. Usable fact groups.
10. Review-only fact groups.
11. Tags with valid evidence.
12. Tags without usable evidence.
13. Ready-for-A4 tags.
14. Direct-copy/stub/review-stub counts.
15. Quote status distribution after filtering.
16. Examples of good fact groups.
17. Examples of rejected not_found evidence.
18. Examples of review-only fuzzy evidence.
19. High-volume tags.
20. Risks.
21. What to pass to A4.

Required line:

Главный output для A4:
data/articles/a3/a4_compilation_input.jsonl
data/articles/a3/fact_groups.jsonl
data/articles/a3/tag_fact_group_index.jsonl
25. Agent behavior

Before coding, create:

docs/article_a3_plan.md

Plan must include:

what was understood;
inputs;
outputs;
filtering rules;
dedupe rules;
fact grouping rules;
coverage strategy;
quality gates;
tests;
risks;
checklist.

Agent must reread this instruction at:

after_plan
after_filtering
after_dedupe
after_grouping
after_coverage
after_tests
before_production_run
before_feedback

Feedback must include:

ТЗ перечитано на этапах: after_plan, after_filtering, after_dedupe, after_grouping, after_coverage, after_tests, before_production_run, before_feedback

If context is lost, reread:

instructions/current_a3_instruction.md
docs/article_a2_feedback.md
data/articles/a2/production_v1/a2_report.json
data/articles/a2/production_v1/a2_manifest.json
data/articles/a1/a1_report.json
data/articles/a1/article_status_index.jsonl
26. Главное напоминание

A3 не пишет статьи.

A3 должен защитить A4 от шума:

not_found quotes → rejected
fuzzy-only → review_only
exact/normalized direct evidence → usable
duplicates → grouped
all tags → indexed

Главный результат A3:

clean, compact, citation-safe fact groups for article compilation.

Итог: подозрительных блокеров нет. A3 можно отдавать агенту.
# A4. Article Compilation from Fact Groups

## 0. Контекст

A3 завершён и принят как deterministic evidence grouping stage.

A3 подготовил главный вход для A4:

```text
data/articles/a3/a4_compilation_input.jsonl
data/articles/a3/fact_groups.jsonl
data/articles/a3/tag_fact_group_index.jsonl

По A3 report:

final_tags_total = 22 513
a2_evidence_items_total = 72 843

valid_evidence_items = 66 114
review_evidence_items = 3 166
rejected_evidence_items = 3 563

fact_groups_total = 67 950
usable_fact_groups = 64 305
review_only_fact_groups = 1 701

ready_for_a4_tags = 9 748
compile_with_review_flag_tags = 6 787
direct_copy_already_done_tags = 6 806
stub_only_tags = 3 839
review_stub_tags = 2 017
tags_without_usable_evidence = 103

quality.passed = true
no_not_found_in_usable_fact_groups = true
no_fuzzy_only_fact_group_marked_usable = true
all_a4_ready_tags_have_fact_groups = true

A4 должен скомпилировать статьи из fact groups.

Важно:

A4 НЕ должен запускать production.

На этом этапе агент должен реализовать A4, прогнать deterministic tests, затем выполнить только smoke-прогоны:

smoke_50
smoke_200

Production будет запускаться только после отдельного одобрения архитектора.

1. Главная цель A4

A4 должен превратить подготовленные A3 fact groups в article JSON в формате Editor.js.

Цель A4:

tag_id + fact_groups → article draft JSON

A4 должен создавать статьи только для тегов со стратегиями:

compile_from_fact_groups
compile_with_review_flag

Для остальных стратегий A4 должен сохранять статус без LLM-компиляции:

direct_copy_already_done
stub_only
review_stub
insufficient_evidence_review
2. Не цели A4

На A4 запрещено:

запускать production без отдельного одобрения архитектора;
изменять A1 entity JSON в production;
изменять A0/A1/A2/A3/N1/N2/N3/N4 artifacts;
добавлять внешние медицинские знания;
делать web search по умолчанию;
делать citation/question generation;
строить папки;
строить knowledge graph;
переписывать direct-copy articles;
компилировать review_stub и insufficient_evidence_review как обычные статьи.

A4 пишет article drafts в отдельный output folder.

3. Входные файлы A4

Обязательные:

data/articles/a3/a4_compilation_input.jsonl
data/articles/a3/fact_groups.jsonl
data/articles/a3/tag_fact_group_index.jsonl
data/articles/a3/a3_report.json
data/articles/a3/a3_manifest.json

data/articles/a1/article_status_index.jsonl
data/articles/a1/a1_report.json
data/articles/a1/a1_manifest.json

data/articles/entities/
data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv

Опциональные, но полезные:

data/articles/a3/high_volume_tags.csv
data/articles/a3/manual_qa_fact_groups_sample.csv
data/articles/a3/tags_without_usable_evidence.jsonl
data/articles/a3/tag_evidence_coverage.jsonl

A4 runner должен отказаться запускаться, если:

A3 report stage != article_a3_evidence_dedupe_fact_grouping
A3 quality.passed != true
A3 ready_for_a4_tags = 0
A1 quality.passed != true
a4_compilation_input.jsonl отсутствует
fact_groups.jsonl отсутствует
4. Выходные файлы A4

Для smoke-прогонов outputs должны лежать только в experiment folders:

data/articles/a4/experiments/smoke_50/
data/articles/a4/experiments/smoke_200/

Production output folder должен быть предусмотрен, но не запускаться:

data/articles/a4/production_v1/

Обязательные outputs для каждого A4 run:

article_compilation_tasks.jsonl
article_compilation_batches.jsonl
article_drafts.jsonl
article_status_updates.jsonl

compiled_articles/{entity_type}/{tag_id}.json

article_compilation_failures.jsonl
article_compilation_review.jsonl
invalid_llm_responses.jsonl
article_quality_issues.jsonl

article_drafts.csv
batch_report.csv
manual_qa_articles_sample.csv

a4_report.json
a4_manifest.json
article_quality_diagnostics.json
cost_latency_report.json

Для smoke 50/200 дополнительно:

smoke_50_report.json
smoke_200_report.json
5. Рекомендуемая структура кода

Создать пакет:

kb_rebuild/articles/a4/

Файлы:

kb_rebuild/articles/a4/__init__.py
kb_rebuild/articles/a4/models.py
kb_rebuild/articles/a4/task_builder.py
kb_rebuild/articles/a4/prompt.py
kb_rebuild/articles/a4/schema.py
kb_rebuild/articles/a4/validation.py
kb_rebuild/articles/a4/runner.py
kb_rebuild/articles/a4/report.py
kb_rebuild/articles/a4/prompts/article_compile_v1.md

Назначение:

models.py       — constants/enums/dataclasses
task_builder.py — build compilation tasks from A3 input
prompt.py       — prompt builder
schema.py       — structured output schema and local validation
validation.py   — Editor.js validation, citation/evidence coverage checks
runner.py       — LLM orchestration, cache/resume/retry, smoke runs
report.py       — reports, CSV writers, QA samples

Добавить CLI:

python -m kb_rebuild article-a4-compile --data data

Флаги:

--a3-dir data/articles/a3
--a1-dir data/articles/a1
--entities-dir data/articles/entities
--normalization-final-dir data/normalization/final
--out data/articles/a4/experiments/smoke_200

--provider gemini_direct
--model gemini-3-flash-preview
--structured-output-mode gemini_schema

--limit 200
--strategy-filter compile_from_fact_groups,compile_with_review_flag
--entity-type-filter all
--priority-filter high,medium,low

--max-tags-per-batch 2
--max-fact-groups-per-tag 80
--max-quotes-per-tag 120
--batch-char-limit 70000

--max-inflight 8
--max-retries 3
--max-output-tokens 16000
--repair-max-output-tokens 32000
--thinking-level minimal
--max-cost-usd 20

--experiment-name smoke_200
--no-resume
6. Production prohibition

Агенту запрещено запускать production.

Запрещены команды без --limit:

article-a4-compile ... --out data/articles/a4/production_v1
article-a4-compile ... --limit отсутствует
article-a4-compile ... --limit 4000

Агент может реализовать production-ready CLI, но запускать только:

--limit 50
--limit 200

Production будет запущен отдельно после проверки архитектором.

7. LLM operational policy

Разрешены:

smoke 50
smoke 200

Запрещено:

тест на 4000
production без разрешения

Smoke defaults:

smoke_50:
  max_inflight = 4
  max_tags_per_batch = 1 или 2
  max_output_tokens = 16000
  repair_max_output_tokens = 32000
  max_cost_usd = 10

smoke_200:
  max_inflight = 8
  max_tags_per_batch = 2
  max_output_tokens = 16000
  repair_max_output_tokens = 32000
  max_cost_usd = 20

Будущий production, не запускать сейчас:

max_inflight минимум 16
лучше 32–64 при стабильности
batching обязательно
cache/resume/retry обязательно
structured output обязательно
не ставить жёсткий max_output_tokens
8. Compilation task builder

A4 должен построить tasks из:

a4_compilation_input.jsonl
fact_groups.jsonl

Только для:

a4_strategy in {compile_from_fact_groups, compile_with_review_flag}
ready_for_a4 = true

Не создавать LLM tasks для:

direct_copy_already_done
stub_only
review_stub
insufficient_evidence_review
8.1 Task schema

article_compilation_tasks.jsonl:

{
  "task_id": "a4task_000000001",
  "tag_id": "...",
  "canonical_tag_ru": "...",
  "canonical_tag_latin": null,
  "entity_type": "disease",

  "a4_strategy": "compile_from_fact_groups",
  "article_status_from_a1": "pending_single_doc_extract",

  "needs_review_before_publication": false,
  "review_reasons": [],

  "fact_group_ids": [],
  "core_fact_group_ids": [],
  "supporting_fact_group_ids": [],

  "fact_groups": [
    {
      "fact_group_id": "...",
      "fact_type": "definition",
      "section_hint": "Что это",
      "representative_claim": "...",
      "representative_quote": "...",
      "source_doc_ids": [],
      "source_documents_count": 1,
      "confidence": 0.93,
      "importance": "high",
      "a4_usage": "core_fact"
    }
  ],

  "source_documents_count": 2,
  "usable_fact_groups_count": 5,

  "priority": "high",
  "estimated_input_chars": 12000,
  "recommended_max_output_tokens": 16000
}
9. Fact group selection for task

A4 не должен отправлять в prompt слишком много fact groups по high-volume tags.

Использовать A3 a4_compilation_input.fact_group_ids, но дополнительно ограничить:

--max-fact-groups-per-tag default 80
--max-quotes-per-tag default 120
9.1 Ranking fact groups

Сортировать fact groups по приоритету:

a4_usage=core_fact
importance=high
fact_type=definition
fact_type=description
exact quote over normalized_exact
higher confidence
multi-source support
supporting fact
shorter claim/quote if tie
9.2 Section balance

Не позволять одному fact_type полностью забить prompt.

Рекомендуемый soft cap per fact_type:

definition: 8
description: 8
classification: 8
mechanism: 8
symptom: 12
diagnostics: 12
treatment: 12
usage_or_dosage: 12
indication: 12
contraindication: 8
side_effect: 8
procedure_step: 15
composition: 10
other/supporting: 10

Если fact groups больше лимита:

сохранить excluded_fact_group_ids в task metadata
10. Entity-type-specific article templates

A4 prompt должен использовать разные структуры статьи по entity_type.

10.1 disease

Разделы:

Что это
Причины и факторы риска
Симптомы
Диагностика
Лечение
Профилактика
Осложнения
Когда обращаться к врачу
Связанные сведения

Использовать раздел только если есть evidence.

10.2 drug_trade_name

Важно: сущность лекарства = торговое название.

Разделы:

Что это
Показания
Применение
Противопоказания
Побочные эффекты
Особые указания
Связанные сведения

Не превращать торговое название в статью о действующем веществе, если fact groups этого не подтверждают.

10.3 supplement

Разделы:

Что это
Состав
Для чего применяется
Способ применения
Предосторожности
Связанные сведения

Не объединять разные продукты одной линейки.

10.4 diagnostic_method

Разделы:

Что это
Для чего применяется
Как проводится
Что показывает
Подготовка
Ограничения и особенности
Связанные сведения
10.5 procedure / instruction

Разделы:

Что это
Когда применяется
Порядок выполнения
Подготовка
Меры безопасности
Ограничения
10.6 microorganism

Разделы:

Что это
Классификация
Связанные заболевания
Диагностика
Лечение и профилактика
Особенности
10.7 biological_substance / medical_concept / symptom / device / other

Использовать generic template:

Что это
Описание
Значение
Диагностика или применение
Связанные сведения
11. Prompt requirements

Создать:

kb_rebuild/articles/a4/prompts/article_compile_v1.md

Prompt на русском.

Ключевые правила:

Ты пишешь статью только по предоставленным fact_groups.
Не добавляй внешние знания.
Не используй web.
Не придумывай факты.
Не добавляй медицинских рекомендаций сверх источников.
Если разделу не хватает facts, не заполняй его общими знаниями.
Каждое содержательное утверждение должно быть основано на fact_group.
Не используй rejected/review_only evidence.
Сохраняй осторожный стиль.

Prompt должен требовать:

strict JSON
Editor.js compatible content
source_fact_group_ids per block
article_status
review flags
12. Structured output schema

LLM должна вернуть JSON:

{
  "task_id": "a4task_000000001",
  "tag_id": "...",
  "article_status": "compiled_article",
  "title": "Каноническое название",
  "summary": "Краткое описание по источникам.",
  "content": {
    "time": 0,
    "version": "2.28.0",
    "blocks": [
      {
        "id": "block_001",
        "type": "header",
        "data": {
          "text": "Что это",
          "level": 2
        },
        "metadata": {
          "source_fact_group_ids": []
        }
      },
      {
        "id": "block_002",
        "type": "paragraph",
        "data": {
          "text": "..."
        },
        "metadata": {
          "source_fact_group_ids": ["fg_..."]
        }
      }
    ]
  },
  "used_fact_group_ids": [],
  "unused_fact_group_ids": [],
  "needs_review_before_publication": false,
  "review_reasons": [],
  "confidence": 0.9,
  "reason": ""
}
12.1 Allowed article_status
compiled_article
compiled_with_review_flag
insufficient_evidence_review
invalid_or_unclear

For A4 smoke tasks, expected:

compiled_article
compiled_with_review_flag
13. Local validation

A4 must validate each LLM response.

Checks:

task_id matches input
tag_id matches input
article_status in enum
content is valid Editor.js object
blocks is non-empty list
first block is header or title block
no empty header text
paragraph/list/table blocks have non-empty content
used_fact_group_ids exist in task
each non-header content block has source_fact_group_ids
source_fact_group_ids exist in task
no unknown fact_group_id
article title matches canonical_tag_ru or is close
summary does not contain unsupported claims
needs_review_before_publication preserved if input had it
review_reasons preserved/extended

If validation fails:

repair retry with validation errors;
if still invalid, split batch or single-task retry;
if still invalid, write to article_compilation_failures.jsonl.
14. Evidence support validation

A4 cannot perfectly fact-check generated prose, but must enforce support metadata.

Rules:

Every paragraph/list/table block must have at least one source_fact_group_id.
Header blocks may have empty source ids.
No block may cite fact_group_id not present in task.
If input needs_review_before_publication=true, output must also true.
If output uses less than 20% of available core facts and tag has many core facts, add quality warning.

A4 must not use review_only_fact_group_ids by default.

15. Batch strategy

Article compilation is heavier than extraction.

Default batch:

max_tags_per_batch = 2
batch_char_limit = 70000

For large tags:

if one tag task exceeds batch_char_limit / 2
batch it alone

If invalid responses happen:

repair
then split batch
then single-task
16. Cache/resume

Use LLM cache.

Cache key includes:

stage = article_a4_compilation
provider
model
prompt_version
schema_version
task_id/tag_id
input_hash of fact groups
generation params

Resume should skip successfully compiled tasks.

17. Smoke selection

A4 must support --limit.

For smoke runs, selection should be representative, not just first N.

17.1 Smoke 50 selection

Include:

at least 20 compile_from_fact_groups
at least 20 compile_with_review_flag
mix of disease, drug_trade_name, diagnostic_method, procedure, microorganism, supplement, biological_substance
some single_doc, low_count, multi_doc, high_frequency source histories if available
at least 5 high-volume tags if they fit limit
17.2 Smoke 200 selection

Broader version of smoke 50:

balanced by entity_type
balanced by a4_strategy
include high-volume tags
include publication-review tags
include short/simple tags
include long/multi-source tags

Do not select:

direct_copy_already_done
stub_only
review_stub
insufficient_evidence_review

unless explicitly requested by a separate QA flag.

18. Output article draft schema

Each compiled article file:

compiled_articles/{entity_type}/{tag_id}.json

Schema:

{
  "tag_id": "...",
  "canonical_tag_ru": "...",
  "canonical_tag_latin": null,
  "entity_type": "disease",

  "article_status": "compiled_article",
  "source_stage": "A4",
  "a4_strategy": "compile_from_fact_groups",

  "needs_review_before_publication": false,
  "review_reasons": [],

  "content_format": "editorjs",
  "content": {},

  "used_fact_group_ids": [],
  "unused_fact_group_ids": [],

  "sources": {
    "fact_group_ids": [],
    "source_doc_ids": [],
    "source_documents_count": 0
  },

  "provenance": {
    "a3_input": "data/articles/a3/a4_compilation_input.jsonl",
    "model": "gemini-3-flash-preview",
    "provider": "gemini_direct",
    "prompt_version": "a4_article_compile_v1",
    "schema_version": "a4_article_draft_v1"
  }
}
19. Reports

Create:

a4_report.json

Structure:

{
  "stage": "article_a4_article_compilation",
  "stage_version": "a4.0",
  "created_at": "...",

  "input": {
    "a3_manifest": "data/articles/a3/a3_manifest.json",
    "a4_compilation_input": "data/articles/a3/a4_compilation_input.jsonl"
  },

  "counts": {
    "tasks_requested": 0,
    "tasks_processed": 0,
    "compiled_articles": 0,
    "compiled_with_review_flag": 0,
    "failed_tasks": 0,
    "review_tasks": 0,
    "batches_total": 0,
    "batches_success": 0,
    "batches_failed": 0
  },

  "by_entity_type": {},
  "by_a4_strategy": {},

  "llm": {
    "provider": "gemini_direct",
    "model": "gemini-3-flash-preview",
    "requests": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "invalid_json_count": 0,
    "schema_validation_failures": 0,
    "estimated_cost_usd": 0,
    "avg_latency_ms": 0
  },

  "quality": {
    "all_processed_tasks_have_result": true,
    "all_compiled_articles_have_editorjs": true,
    "all_content_blocks_have_source_fact_group_ids": true,
    "no_unknown_fact_group_ids_used": true,
    "review_flags_preserved": true,
    "passed": true
  },

  "stop_reason": null,
  "warnings": []
}

Manifest:

a4_manifest.json

Must include all inputs, outputs, config, model, prompt/schema versions.

20. Manual QA sample

Create:

manual_qa_articles_sample.csv

Fields:

tag_id
canonical_tag_ru
entity_type
a4_strategy
article_status
needs_review_before_publication
title
summary
blocks_count
used_fact_groups_count
source_documents_count
article_file_path
qa_excerpt
quality_warnings

Include all smoke articles if smoke <= 200.

21. Quality gates

A4 smoke passes if:

tasks_failed = 0
invalid_json_count = 0 or recovered
all compiled article files exist
all content is valid Editor.js
no unknown fact_group_ids used
review flags preserved
manual QA sample created
quality.passed = true

Smoke should fail if:

LLM adds unsupported sections with no source_fact_group_ids
blocks cite unknown fact_group_ids
compiled article has empty content
review flag lost
too many schema failures
22. Tests

Add tests:

tests/test_article_a4_task_builder.py
tests/test_article_a4_schema.py
tests/test_article_a4_validation.py
tests/test_article_a4_runner.py
tests/test_article_a4_report.py
22.1 Task builder tests
builds tasks only for compile_from_fact_groups and compile_with_review_flag;
skips direct_copy_already_done, stub_only, review_stub, insufficient_evidence_review;
respects max fact groups per tag;
keeps core facts before supporting facts;
preserves review flags.
22.2 Schema tests
valid compiled article response passes;
unknown task_id fails;
unknown fact_group_id fails;
missing Editor.js blocks fails;
content block without source_fact_group_ids fails;
review flag lost fails.
22.3 Validation tests
valid Editor.js article passes;
paragraph without sources fails;
header without sources allowed;
unsupported fact group id fails;
empty title/header fails.
22.4 Runner tests
fake Gemini client compiles valid article;
invalid response triggers repair;
unrepaired invalid response goes to failures;
cache hit skips LLM;
resume skips completed tasks;
smoke limit respected;
production without explicit approval flag is refused.
22.5 Report tests
report counts consistent;
manifest has stage_version a4.0;
quality fails on missing article file;
manual QA sample generated.

Run:

.venv/bin/python -m unittest discover -s tests

Compile:

.venv/bin/python -m py_compile \
  kb_rebuild/articles/a4/models.py \
  kb_rebuild/articles/a4/task_builder.py \
  kb_rebuild/articles/a4/prompt.py \
  kb_rebuild/articles/a4/schema.py \
  kb_rebuild/articles/a4/validation.py \
  kb_rebuild/articles/a4/runner.py \
  kb_rebuild/articles/a4/report.py \
  kb_rebuild/cli.py
23. Smoke commands
23.1 Smoke 50

Allowed:

.venv/bin/python -m kb_rebuild article-a4-compile \
  --data data \
  --a3-dir data/articles/a3 \
  --a1-dir data/articles/a1 \
  --entities-dir data/articles/entities \
  --normalization-final-dir data/normalization/final \
  --out data/articles/a4/experiments/smoke_50 \
  --provider gemini_direct \
  --model gemini-3-flash-preview \
  --structured-output-mode gemini_schema \
  --limit 50 \
  --max-tags-per-batch 1 \
  --max-fact-groups-per-tag 80 \
  --max-quotes-per-tag 120 \
  --batch-char-limit 70000 \
  --max-inflight 4 \
  --max-retries 3 \
  --max-output-tokens 16000 \
  --repair-max-output-tokens 32000 \
  --thinking-level minimal \
  --max-cost-usd 10 \
  --experiment-name smoke_50 \
  --no-resume
23.2 Smoke 200

Allowed only after smoke 50 passes:

.venv/bin/python -m kb_rebuild article-a4-compile \
  --data data \
  --a3-dir data/articles/a3 \
  --a1-dir data/articles/a1 \
  --entities-dir data/articles/entities \
  --normalization-final-dir data/normalization/final \
  --out data/articles/a4/experiments/smoke_200 \
  --provider gemini_direct \
  --model gemini-3-flash-preview \
  --structured-output-mode gemini_schema \
  --limit 200 \
  --max-tags-per-batch 2 \
  --max-fact-groups-per-tag 80 \
  --max-quotes-per-tag 120 \
  --batch-char-limit 70000 \
  --max-inflight 8 \
  --max-retries 3 \
  --max-output-tokens 16000 \
  --repair-max-output-tokens 32000 \
  --thinking-level minimal \
  --max-cost-usd 20 \
  --experiment-name smoke_200
24. Production command — do not run

Production command may be documented but must not be executed by the agent.

Future production command, not allowed now:

.venv/bin/python -m kb_rebuild article-a4-compile \
  --data data \
  --a3-dir data/articles/a3 \
  --a1-dir data/articles/a1 \
  --entities-dir data/articles/entities \
  --normalization-final-dir data/normalization/final \
  --out data/articles/a4/production_v1 \
  --provider gemini_direct \
  --model gemini-3-flash-preview \
  --structured-output-mode gemini_schema \
  --max-tags-per-batch 2 \
  --max-fact-groups-per-tag 80 \
  --max-quotes-per-tag 120 \
  --batch-char-limit 70000 \
  --max-inflight 16 \
  --max-retries 3 \
  --max-output-tokens 16000 \
  --repair-max-output-tokens 32000 \
  --thinking-level minimal \
  --max-cost-usd 150 \
  --retry-failures \
  --experiment-name production_v1

Agent must not run this.

If production is accidentally run, agent must stop, report it, and not continue.

25. Feedback after A4 implementation

Create:

docs/article_a4_feedback.md

Feedback must include:

1. Что сделано.
2. Какие файлы изменены.
3. Какие команды запускались.
4. Tests passed.
5. Smoke 50 result.
6. Smoke 200 result.
7. Production run: must say NOT RUN.
8. Tasks processed.
9. Compiled articles.
10. Compiled with review flag.
11. Failed tasks.
12. Invalid JSON / schema failures / retries.
13. Cost and latency.
14. Examples of compiled articles.
15. Examples of review-flag articles.
16. Examples of failures, if any.
17. Quality diagnostics.
18. Manual QA sample path.
19. Risks.
20. What needs architect approval before production.

Required line:

Production A4 не запускался. Для production требуется отдельное одобрение архитектора.
26. Agent behavior

Before coding, create:

docs/article_a4_plan.md

Plan must include:

what was understood;
inputs;
outputs;
task builder design;
prompt/schema design;
validation rules;
smoke selection strategy;
tests;
explicit statement that production will not be run;
risks;
checklist.

Agent must reread this instruction at:

after_plan
after_task_builder
after_schema
after_validation
after_runner
after_tests
before_smoke_50
before_smoke_200
before_feedback

Feedback must include:

ТЗ перечитано на этапах: after_plan, after_task_builder, after_schema, after_validation, after_runner, after_tests, before_smoke_50, before_smoke_200, before_feedback

If context is lost, reread:

instructions/current_a4_instruction.md
docs/article_a3_feedback.md
data/articles/a3/a3_report.json
data/articles/a3/a3_manifest.json
data/articles/a3/a4_compilation_input.jsonl
data/articles/a3/fact_groups.jsonl
data/articles/a1/article_status_index.jsonl
27. Главное напоминание

A4 smoke is for validating the compiler, prompt, schema, and quality gates.

A4 must not run production yet.

Correct behavior:

compile_from_fact_groups → smoke compile article
compile_with_review_flag → smoke compile article with review flag preserved
direct_copy_already_done → skip LLM
stub_only → skip LLM
review_stub → skip LLM
insufficient_evidence_review → skip LLM

Главный результат smoke A4:

data/articles/a4/experiments/smoke_50/
data/articles/a4/experiments/smoke_200/

Production will be approved separately after architect QA.
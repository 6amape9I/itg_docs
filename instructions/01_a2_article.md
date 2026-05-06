# A2. Evidence Extraction from Source Windows

## 0. Контекст

A1 завершён и принят как bootstrap-этап.

A1 создал:

```text
data/articles/a1/tag_work_plan_adjusted.jsonl
data/articles/a1/article_status_index.jsonl
data/articles/a1/a2_extraction_task_queue.jsonl
data/articles/a1/publication_review_queue.jsonl
data/articles/a1/hard_review_queue.jsonl
data/articles/entities/{entity_type}/{tag_id}.json

По A1 report:

final_tags_total = 22513
entity_json_files_created = 22513
article_status_index_rows = 22513
a0_review_stub_original = 3349
a0_1_rerouted_from_review_stub = 1332
review_stub_articles = 2017
direct_copy_article = 6806
direct_copy_rejected = 0
pending_single_doc_extract = 7025
pending_low_count_batch_extract = 1779
pending_multi_doc_map_reduce = 940
pending_high_frequency_map_reduce = 107
a2_extraction_tasks_total = 34995
publication_review_queue_total = 9325
hard_review_queue_total = 2017
quality.passed = true

A2 должен взять очередь:

data/articles/a1/a2_extraction_task_queue.jsonl

и извлечь evidence/facts из source_window для конкретного tag_id.

A2 НЕ пишет финальную статью. A2 только извлекает факты и цитаты, которые потом будут дедуплицированы и использованы в A3/A4.

1. Главная цель A2

Для каждого extraction task из A1 получить структурированный evidence result:

task_id + tag_id + source window → evidence_items

A2 должен создать:

data/articles/a2/evidence_task_results.jsonl
data/articles/a2/evidence_items.jsonl
data/articles/a2/no_evidence_tasks.jsonl
data/articles/a2/review_tasks.jsonl
data/articles/a2/failed_tasks.jsonl
data/articles/a2/a2_report.json
data/articles/a2/a2_manifest.json

Главный output для A3:

data/articles/a2/evidence_items.jsonl
2. Что A2 не делает

На A2 запрещено:

создавать финальные статьи;
компилировать Editor.js articles;
изменять entity JSON из A1;
изменять A0/A1/N1/N2/N3/N4 artifacts;
делать web search по умолчанию;
добавлять внешние медицинские знания;
делать citation/question generation;
строить папки;
строить граф знаний.

A2 может вызывать LLM только для evidence extraction по подготовленным source windows.

3. Операционная политика LLM

В проекте уже есть Gemini keys.

Разрешены smoke/benchmark LLM-тесты:

50 элементов
200 элементов

Запрещено:

тестовый запуск на 4000 элементов

Production LLM run должен быть эффективным:

batch processing обязательно;
structured output обязательно;
cache/resume/retry обязательно;
cost/latency/error report обязательно;
на smoke max_inflight = 4–8;
на production max_inflight минимум 16;
лучше 32–64, если нет 429/ошибок;
max_output_tokens не должен быть слишком жёстким;
repair retries должны иметь больший output limit.

Важно: после N3 мы уже видели, что слишком низкий max_output_tokens приводит к MAX_TOKENS и truncated JSON. Поэтому A2 должен сразу использовать мягкие лимиты.

Рекомендуемые production defaults:

model = gemini-3-flash-preview
provider = gemini_direct
structured_output_mode = gemini_schema
temperature = 0
thinking_level = minimal
max_inflight = 16
max_tasks_per_batch = 8
batch_char_limit = 60000
max_output_tokens = 12000
repair_max_output_tokens = 24000
max_retries = 3

Если после первых 500–1000 tasks ошибок нет, production можно перезапустить/продолжить с:

max_inflight = 32

и затем, если всё стабильно:

max_inflight = 64
4. Входные файлы A2

Обязательные:

data/articles/a1/a2_extraction_task_queue.jsonl
data/articles/a1/article_status_index.jsonl
data/articles/a1/tag_work_plan_adjusted.jsonl
data/articles/a1/a1_report.json
data/articles/a1/a1_manifest.json
data/articles/planning/source_block_windows.jsonl
data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv

Опциональные, но полезные:

data/articles/a1/publication_review_queue.jsonl
data/articles/a1/hard_review_queue.jsonl
data/articles/a1/direct_copy_articles.jsonl
data/articles/a1/pending_extraction_articles.jsonl

A2 должен отказаться запускаться, если:

A1 report stage != article_a1_entity_json_bootstrap
A1 quality.passed != true
a2_extraction_task_queue.jsonl отсутствует
article_status_index.jsonl отсутствует
5. Выходные файлы A2

Создать директорию:

data/articles/a2/

Обязательные outputs:

data/articles/a2/evidence_extraction_batches.jsonl
data/articles/a2/evidence_task_results.jsonl
data/articles/a2/evidence_items.jsonl
data/articles/a2/no_evidence_tasks.jsonl
data/articles/a2/review_tasks.jsonl
data/articles/a2/failed_tasks.jsonl
data/articles/a2/invalid_llm_responses.jsonl
data/articles/a2/quote_validation_issues.jsonl

data/articles/a2/evidence_items.csv
data/articles/a2/task_results.csv
data/articles/a2/batch_report.csv

data/articles/a2/a2_report.json
data/articles/a2/a2_manifest.json

Cache:

data/articles/a2/llm_cache/

Дополнительные outputs:

data/articles/a2/smoke_50_report.json
data/articles/a2/smoke_200_report.json
data/articles/a2/evidence_quality_diagnostics.json
data/articles/a2/cost_latency_report.json
6. Рекомендуемая структура кода

Создать пакет:

kb_rebuild/articles/a2/

Файлы:

kb_rebuild/articles/a2/__init__.py
kb_rebuild/articles/a2/models.py
kb_rebuild/articles/a2/prompt.py
kb_rebuild/articles/a2/schema.py
kb_rebuild/articles/a2/batch_builder.py
kb_rebuild/articles/a2/validation.py
kb_rebuild/articles/a2/runner.py
kb_rebuild/articles/a2/report.py

Назначение:

models.py        — dataclasses/constants/enums
prompt.py        — prompt builder for batch extraction
schema.py        — Gemini response schema + local validation
batch_builder.py — grouping tasks into batches
validation.py    — quote validation and response validation
runner.py        — LLM orchestration, cache, retry, resume
report.py        — reports and CSV/JSON writers

Добавить CLI:

python -m kb_rebuild article-a2-extract --data data

Флаги:

--a1-dir data/articles/a1
--planning-dir data/articles/planning
--out data/articles/a2
--provider gemini_direct
--model gemini-3-flash-preview
--structured-output-mode gemini_schema
--limit 200
--task-filter all
--strategy-filter single_doc_extract,low_count_batch_extract,multi_doc_map_reduce,high_frequency_map_reduce
--priority-filter high,medium,low
--max-tasks-per-batch 8
--batch-char-limit 60000
--max-inflight 8
--max-retries 3
--max-output-tokens 12000
--repair-max-output-tokens 24000
--thinking-level minimal
--max-cost-usd 20
--retry-failures
--no-resume
--experiment-name smoke_200
7. Batch builder

A2 должен батчить tasks.

Одна LLM request должна содержать несколько независимых extraction tasks.

7.1 Batch grouping

Группировать по:

entity_type
source_strategy
priority
batch_group_key

Не смешивать в одном batch слишком разные entity types, если это ухудшает prompt.

Рекомендуемый batch key:

{entity_type}:{source_strategy}:{priority}
7.2 Batch limits

Соблюдать:

max_tasks_per_batch
batch_char_limit
max_output_tokens

Default:

max_tasks_per_batch = 8
batch_char_limit = 60000
max_output_tokens = 12000

Если batch response invalid:

retry repair;
если снова invalid, split batch на половины;
если одна task всё ещё invalid, записать task в failed_tasks.jsonl или review_tasks.jsonl.
7.3 Batch output

Создать:

evidence_extraction_batches.jsonl

Формат:

{
  "batch_id": "a2batch_000001",
  "task_ids": ["a2task_000000001"],
  "entity_type": "disease",
  "source_strategy": "single_doc_extract",
  "priority": "high",
  "tasks_count": 8,
  "input_chars": 42312,
  "batch_group_key": "disease:single_doc_extract:high"
}
8. Prompt requirements

Создать prompt:

kb_rebuild/articles/a2/prompts/evidence_extract_v1.md

Prompt на русском.

Смысл:

Ты извлекаешь только информацию, относящуюся к указанной сущности tag_id.
Не пиши статью.
Не добавляй внешние знания.
Не делай медицинских рекомендаций от себя.
Каждый claim должен быть подтверждён дословной цитатой из window_text.
Если в окне нет полезной информации о сущности — верни no_relevant_information.
Если информация относится к другой сущности — не извлекай её.
Если сущность упомянута только вскользь без полезного факта — no_relevant_information или related_only.

В prompt обязательно добавить:

Цитата должна быть непрерывной подстрокой из window_text.
Не используй многоточия.
Не склеивай фрагменты из разных мест.
Не обобщай за пределы цитаты.
Не переносить факты о связанных сущностях на целевую сущность.
9. Input format для LLM

Batch prompt должен передавать:

{
  "batch_id": "a2batch_000001",
  "tasks": [
    {
      "task_id": "a2task_000000001",
      "tag_id": "...",
      "canonical_tag_ru": "...",
      "canonical_tag_latin": null,
      "entity_type": "disease",
      "source_strategy": "single_doc_extract",
      "doc_id": "...",
      "document_name": "...",
      "window_id": "...",
      "heading_context": [],
      "window_text": "...",
      "window_quality": "high",
      "match_method": "quote_match"
    }
  ]
}

Do not pass full documents unless the task window is already full-document by direct planning.

10. Structured output schema

LLM должна вернуть строгий JSON:

{
  "batch_id": "a2batch_000001",
  "task_results": [
    {
      "task_id": "a2task_000000001",
      "tag_id": "...",
      "decision": "evidence_extracted",
      "relevance": "direct",
      "confidence": 0.92,
      "evidence_items": [
        {
          "fact_type": "definition",
          "section_hint": "Что это",
          "claim": "Краткая формулировка факта своими словами, строго по цитате.",
          "quote": "Дословная цитата из window_text",
          "importance": "high",
          "confidence": 0.91
        }
      ],
      "reason": ""
    }
  ]
}
10.1 Decision enum
evidence_extracted
no_relevant_information
related_only
needs_review
invalid_or_unclear_source
10.2 Relevance enum
direct
related
not_relevant
unclear
10.3 fact_type enum

Общие:

definition
description
classification
mechanism
cause_or_risk_factor
symptom
diagnostics
treatment
prevention
complication
indication
contraindication
side_effect
usage_or_dosage
procedure_step
preparation
interpretation
composition
safety_warning
related_entity
other

Не все типы подходят всем entity types. Модель должна выбирать наиболее близкий.

11. Local validation

После LLM ответа код должен проверить:

batch_id совпадает;
каждый task_id известен;
нет пропущенных task_id без результата;
decision в enum;
relevance в enum;
confidence в [0,1];
evidence_items список;
fact_type в enum;
importance в enum;
quote непустая для evidence_extracted;
quote является подстрокой window_text или проходит normalized/fuzzy quote validation;
claim непустой;
claim не слишком длинный;
task_id/tag_id совпадает с input.

Если quote не найден:

quote_validation_status = not_found

и item записать в:

quote_validation_issues.jsonl

Но task не должен полностью падать, если есть другие валидные evidence items.

Если все quotes invalid:

decision = needs_review

или task result goes to review.

12. Quote validation

Для каждого evidence item:

quote_validation_status:
  exact
  normalized_exact
  fuzzy
  not_found

Для accepted evidence желательно:

exact или normalized_exact

fuzzy допустим, но item получает review flag.

not_found не должен использоваться в article compilation без ручной проверки.

13. Evidence item output

evidence_items.jsonl — одна строка = один evidence item.

Формат:

{
  "evidence_item_id": "ev_000000001",
  "task_id": "a2task_000000001",
  "batch_id": "a2batch_000001",

  "tag_id": "...",
  "canonical_tag_ru": "...",
  "canonical_tag_latin": null,
  "entity_type": "disease",

  "doc_id": "...",
  "document_name": "...",
  "window_id": "...",
  "block_ids": [],
  "block_indexes": [],
  "heading_context": [],

  "fact_type": "definition",
  "section_hint": "Что это",
  "claim": "...",
  "quote": "...",
  "quote_validation_status": "exact",

  "importance": "high",
  "confidence": 0.92,
  "relevance": "direct",

  "source_strategy": "single_doc_extract",
  "window_quality": "high",
  "match_method": "quote_match",

  "needs_review_before_publication": false,
  "review_reasons": [],

  "model": "gemini-3-flash-preview",
  "provider": "gemini_direct",
  "prompt_version": "a2_evidence_extract_v1",
  "schema_version": "a2_evidence_batch_v1",
  "created_at": "..."
}
14. Task result output

evidence_task_results.jsonl — одна строка = один task.

Формат:

{
  "task_id": "a2task_000000001",
  "tag_id": "...",
  "decision": "evidence_extracted",
  "relevance": "direct",
  "evidence_items_count": 3,
  "valid_quote_items_count": 3,
  "invalid_quote_items_count": 0,
  "confidence": 0.92,
  "batch_id": "a2batch_000001",
  "status": "success",
  "reason": ""
}

Для no_relevant_information:

{
  "decision": "no_relevant_information",
  "evidence_items_count": 0,
  "status": "no_evidence"
}
15. Review tasks

Записывать task в review_tasks.jsonl, если:

decision = needs_review
decision = invalid_or_unclear_source
all evidence quotes are not_found
window_quality = low
relevance = related или unclear
LLM response partially invalid
publication_review flag exists

Важно: publication-review task может иметь валидные evidence items, но всё равно должен быть отмечен для review-before-publication.

16. Failed tasks

Записывать в failed_tasks.jsonl, если:

LLM request failed after retries;
schema invalid after retries/splits;
unknown task_id in response and cannot repair;
budget exceeded before processing task;
input task malformed.

Failed task не должен ломать весь run.

17. Cache/resume

A2 должен поддерживать:

cache
resume
retry-failures
experiment-name

Cache key должен включать:

stage = article_a2_evidence_extraction
provider
model
prompt_version
schema_version
batch_id or task_ids
input_hash of tasks/window_text
generation params

Если batch split/retry происходит, cache key должен отличаться.

18. Cost and budget

A2 должен считать:

requests
tasks_processed
tasks_per_request
input tokens/chars
output tokens
estimated_cost_usd
cost_per_task
cost_per_evidence_item
latency
docs/tasks per hour

Если модель возвращает usage metadata — использовать её.

Если usage нет — оценивать по char-to-token approximation и помечать:

usage_source = estimated

Budget:

--max-cost-usd

Если budget исчерпан, runner должен:

завершиться gracefully;
записать stop_reason = max_cost_reached;
сохранить processed results;
позволить resume.
19. Smoke tests and production commands
19.1 Deterministic unit tests

Обязательны перед LLM:

.venv/bin/python -m unittest discover -s tests

Compile:

.venv/bin/python -m py_compile \
  kb_rebuild/articles/a2/models.py \
  kb_rebuild/articles/a2/prompt.py \
  kb_rebuild/articles/a2/schema.py \
  kb_rebuild/articles/a2/batch_builder.py \
  kb_rebuild/articles/a2/validation.py \
  kb_rebuild/articles/a2/runner.py \
  kb_rebuild/articles/a2/report.py \
  kb_rebuild/cli.py
19.2 Smoke 50

Разрешён:

.venv/bin/python -m kb_rebuild article-a2-extract \
  --data data \
  --a1-dir data/articles/a1 \
  --planning-dir data/articles/planning \
  --out data/articles/a2/experiments/smoke_50 \
  --provider gemini_direct \
  --model gemini-3-flash-preview \
  --structured-output-mode gemini_schema \
  --limit 50 \
  --max-tasks-per-batch 5 \
  --batch-char-limit 40000 \
  --max-inflight 4 \
  --max-retries 3 \
  --max-output-tokens 12000 \
  --repair-max-output-tokens 24000 \
  --thinking-level minimal \
  --max-cost-usd 5 \
  --experiment-name smoke_50
19.3 Smoke 200

Разрешён, если smoke 50 нормальный:

.venv/bin/python -m kb_rebuild article-a2-extract \
  --data data \
  --a1-dir data/articles/a1 \
  --planning-dir data/articles/planning \
  --out data/articles/a2/experiments/smoke_200 \
  --provider gemini_direct \
  --model gemini-3-flash-preview \
  --structured-output-mode gemini_schema \
  --limit 200 \
  --max-tasks-per-batch 8 \
  --batch-char-limit 60000 \
  --max-inflight 8 \
  --max-retries 3 \
  --max-output-tokens 12000 \
  --repair-max-output-tokens 24000 \
  --thinking-level minimal \
  --max-cost-usd 10 \
  --experiment-name smoke_200
19.4 Запрещённый тест

Не запускать:

--limit 4000

как тест.

19.5 Production command

Не запускать production без отдельного разрешения архитектора.

После разрешения:

.venv/bin/python -m kb_rebuild article-a2-extract \
  --data data \
  --a1-dir data/articles/a1 \
  --planning-dir data/articles/planning \
  --out data/articles/a2/production \
  --provider gemini_direct \
  --model gemini-3-flash-preview \
  --structured-output-mode gemini_schema \
  --max-tasks-per-batch 8 \
  --batch-char-limit 60000 \
  --max-inflight 16 \
  --max-retries 3 \
  --max-output-tokens 12000 \
  --repair-max-output-tokens 24000 \
  --thinking-level minimal \
  --max-cost-usd 100 \
  --retry-failures \
  --experiment-name production_v1

Если первые 500–1000 tasks идут без 429/invalid JSON/quote issues explosion, можно продолжить с:

--max-inflight 32

Если стабильно:

--max-inflight 64
20. A2 report

Создать:

data/articles/a2/a2_report.json

Структура:

{
  "stage": "article_a2_evidence_extraction",
  "stage_version": "a2.0",
  "created_at": "...",

  "input": {
    "a2_task_queue": "data/articles/a1/a2_extraction_task_queue.jsonl",
    "a1_manifest": "data/articles/a1/a1_manifest.json"
  },

  "counts": {
    "tasks_requested": 0,
    "tasks_processed": 0,
    "tasks_success": 0,
    "tasks_no_evidence": 0,
    "tasks_review": 0,
    "tasks_failed": 0,

    "batches_total": 0,
    "batches_success": 0,
    "batches_failed": 0,
    "batch_splits": 0,

    "evidence_items_total": 0,
    "evidence_items_valid_quotes": 0,
    "evidence_items_quote_not_found": 0
  },

  "by_entity_type": {},
  "by_source_strategy": {},
  "by_fact_type": {},

  "quote_validation": {
    "exact": 0,
    "normalized_exact": 0,
    "fuzzy": 0,
    "not_found": 0
  },

  "llm": {
    "provider": "gemini_direct",
    "model": "gemini-3-flash-preview",
    "requests": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "invalid_json_count": 0,
    "schema_validation_failures": 0,
    "http_status_counts": {},
    "estimated_cost_usd": 0,
    "avg_latency_ms": 0
  },

  "quality": {
    "all_processed_tasks_have_result": true,
    "no_unknown_task_ids": true,
    "quote_not_found_share": 0.0,
    "passed": true
  },

  "stop_reason": null,
  "warnings": []
}
21. A2 manifest

Создать:

data/articles/a2/a2_manifest.json

Содержимое:

{
  "stage": "article_a2_evidence_extraction",
  "stage_version": "a2.0",
  "created_at": "...",
  "source_a1_manifest": "data/articles/a1/a1_manifest.json",
  "inputs": {},
  "outputs": {},
  "provider": "gemini_direct",
  "model": "gemini-3-flash-preview",
  "prompt_version": "a2_evidence_extract_v1",
  "schema_version": "a2_evidence_batch_v1",
  "config": {}
}
22. Quality gates

Smoke 50/200 считается успешным, если:

invalid_json_count = 0 или очень низкий и recovered by retry;
tasks_failed = 0 или объяснимо;
no_unknown_task_ids = true;
quote_not_found_share <= 0.05 желательно;
evidence_items_total > 0;
no catastrophic hallucination in manual sample.

Production quality gate:

all_processed_tasks_have_result = true
no_unknown_task_ids = true
tasks_failed share <= 1%
quote_not_found_share <= 5%
invalid_json_count recovered by retry/split

Если quote_not_found_share > 5%, не переходить к A3 без анализа.

23. Manual QA sample

После smoke 50 и smoke 200 агент должен создать:

data/articles/a2/experiments/{experiment}/manual_qa_sample.csv

Поля:

task_id
tag_id
canonical_tag_ru
entity_type
document_name
window_text_excerpt
decision
fact_type
claim
quote
quote_validation_status
confidence
review_flag

Включить:

10 successful evidence items
5 no_evidence tasks
5 review tasks if available
all quote_not_found items if count <= 20
24. Tests

Добавить:

tests/test_article_a2_batch_builder.py
tests/test_article_a2_schema.py
tests/test_article_a2_validation.py
tests/test_article_a2_runner.py
tests/test_article_a2_report.py
24.1 Batch builder tests
groups tasks by entity_type/source_strategy/priority;
respects max_tasks_per_batch;
respects batch_char_limit;
creates deterministic batch ids;
does not drop tasks.
24.2 Schema tests
valid batch response passes;
unknown task_id fails;
missing task result fails or goes repair;
invalid decision fails;
invalid fact_type fails;
evidence_extracted without quote fails.
24.3 Quote validation tests
exact quote passes;
normalized quote passes;
stitched quote fails;
ellipsis quote fails;
quote from different window fails.
24.4 Runner tests
fake Gemini client returns valid response;
cache hit skips LLM;
invalid response triggers repair;
unrepaired invalid response goes failed/review;
batch split works;
budget stop is graceful;
resume skips completed tasks.
24.5 Report tests
counts consistent;
every processed task has result;
quote validation counts correct;
manifest has stage_version a2.0.
25. Feedback после A2

Создать:

docs/article_a2_feedback.md

Feedback должен содержать:

1. Что сделано.
2. Какие файлы изменены.
3. Какие команды запускались.
4. Сколько tests passed.
5. Smoke 50 result.
6. Smoke 200 result.
7. Production run запускался или нет.
8. Tasks processed.
9. Evidence items created.
10. No-evidence tasks.
11. Review tasks.
12. Failed tasks.
13. Quote validation stats.
14. Invalid JSON / retries / batch splits.
15. Cost and latency.
16. Примеры хороших evidence items.
17. Примеры no_evidence.
18. Примеры review/quote issues.
19. Что не сделано.
20. Риски.
21. Что передать в A3.

Обязательно указать:

Главный output для A3:
data/articles/a2/evidence_items.jsonl
data/articles/a2/evidence_task_results.jsonl
26. Поведение агента

Перед началом создать план:

docs/article_a2_plan.md

План должен содержать:

что понял;
какие inputs использует;
какие files изменит;
какие outputs создаст;
как будет строить batches;
какую schema реализует;
как будет валидировать quotes;
как будет делать cache/resume/retry;
какие smoke tests запустит;
какие production команды НЕ будет запускать без разрешения;
риски;
чеклист.

Агент обязан перечитать ТЗ:

after_plan
after_batch_builder
after_schema
after_validation_logic
after_runner
after_tests
before_smoke_50
before_smoke_200
before_feedback

В feedback добавить строку:

ТЗ перечитано на этапах: after_plan, after_batch_builder, after_schema, after_validation_logic, after_runner, after_tests, before_smoke_50, before_smoke_200, before_feedback

Если память агента очищена, сначала перечитать:

instructions/current_a2_instruction.md
docs/article_a1_feedback.md
data/articles/a1/a1_report.json
data/articles/a1/a1_manifest.json
data/articles/a1/a2_extraction_task_queue.jsonl
data/articles/a1/article_status_index.jsonl
27. Главное напоминание

A2 не должен писать статьи.

A2 должен извлечь проверяемые evidence items из source windows.

Правильное поведение:

нет фактов о tag_id → no_relevant_information;
есть только связанные сущности → related_only/review;
есть факт о tag_id → evidence_extracted with exact quote;
сомнение → needs_review;
quote не найдена → не считать evidence надёжным.

Главный результат A2:

data/articles/a2/evidence_items.jsonl
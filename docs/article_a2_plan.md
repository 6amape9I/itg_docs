# Article A2 Plan

## Что понял

A2 должен извлечь структурированные evidence items из уже подготовленных A1 source windows:

```text
data/articles/a1/a2_extraction_task_queue.jsonl
```

A2 не пишет статьи, не компилирует Editor.js, не меняет entity JSON из A1 и не меняет A0/A1/N* artifacts. Единственная LLM-задача этапа: batch extraction фактов и дословных цитат из `window_text` для конкретного `tag_id`.

Production run запрещен без отдельного разрешения архитектора. В рамках этого этапа после deterministic checks можно запускать smoke 50, а smoke 200 только если smoke 50 не выявит blocking-проблем.

## Inputs

Обязательные:

```text
data/articles/a1/a2_extraction_task_queue.jsonl
data/articles/a1/article_status_index.jsonl
data/articles/a1/tag_work_plan_adjusted.jsonl
data/articles/a1/a1_report.json
data/articles/a1/a1_manifest.json
data/articles/planning/source_block_windows.jsonl
data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv
```

Полезные для review/report:

```text
data/articles/a1/publication_review_queue.jsonl
data/articles/a1/hard_review_queue.jsonl
data/articles/a1/direct_copy_articles.jsonl
data/articles/a1/pending_extraction_articles.jsonl
```

Runner должен отказаться запускаться, если A1 report не `article_a1_entity_json_bootstrap` или `quality.passed != true`, либо отсутствуют task queue/status index.

## Files изменю

Создам:

```text
kb_rebuild/articles/a2/__init__.py
kb_rebuild/articles/a2/models.py
kb_rebuild/articles/a2/prompt.py
kb_rebuild/articles/a2/schema.py
kb_rebuild/articles/a2/batch_builder.py
kb_rebuild/articles/a2/validation.py
kb_rebuild/articles/a2/report.py
kb_rebuild/articles/a2/runner.py
kb_rebuild/articles/a2/prompts/evidence_extract_v1.md
```

Изменю:

```text
kb_rebuild/cli.py
```

Tests:

```text
tests/test_article_a2_batch_builder.py
tests/test_article_a2_schema.py
tests/test_article_a2_validation.py
tests/test_article_a2_runner.py
tests/test_article_a2_report.py
```

Docs:

```text
docs/article_a2_plan.md
docs/article_a2_feedback.md
```

## Outputs

Run output directory:

```text
data/articles/a2/
data/articles/a2/experiments/smoke_50/
data/articles/a2/experiments/smoke_200/
```

Обязательные artifacts:

```text
evidence_extraction_batches.jsonl
evidence_task_results.jsonl
evidence_items.jsonl
no_evidence_tasks.jsonl
review_tasks.jsonl
failed_tasks.jsonl
invalid_llm_responses.jsonl
quote_validation_issues.jsonl
evidence_items.csv
task_results.csv
batch_report.csv
a2_report.json
a2_manifest.json
llm_cache/
manual_qa_sample.csv
evidence_quality_diagnostics.json
cost_latency_report.json
```

Главный output для A3:

```text
data/articles/a2/evidence_items.jsonl
data/articles/a2/evidence_task_results.jsonl
```

## Batch builder

Batch grouping:

- group key: `{entity_type}:{source_strategy}:{priority}`;
- не смешивать entity type/source strategy/priority внутри batch;
- соблюдать `max_tasks_per_batch`;
- соблюдать `batch_char_limit` по сумме `window_text` и базового prompt payload;
- создавать стабильные `a2batch_000001` ids;
- не терять tasks.

## Schema

Реализую локальную schema для ответа:

- `batch_id`;
- `task_results[]`;
- `decision`: `evidence_extracted`, `no_relevant_information`, `related_only`, `needs_review`, `invalid_or_unclear_source`;
- `relevance`: `direct`, `related`, `not_relevant`, `unclear`;
- `evidence_items[]` с `fact_type`, `section_hint`, `claim`, `quote`, `importance`, `confidence`.

Gemini schema будет строиться через существующий `schema_for_gemini`.

## Quote validation

Для каждого evidence item:

- exact substring;
- normalized exact;
- fuzzy только как accepted-with-review flag;
- ellipsis/stitched quote fail;
- not_found записывается в `quote_validation_issues.jsonl`.

Если все quotes invalid, task уходит в review. `not_found` не должен считаться надежным evidence для A3/A4 без ручной проверки.

## Cache/resume/retry

Cache key включает:

- stage;
- provider/model;
- prompt/schema version;
- batch_id или task_ids;
- input hash с tasks/window_text;
- generation params.

Runner:

- пишет cache в `llm_cache/`;
- resume пропускает completed task_ids;
- `--retry-failures` возвращает failed/review failure tasks в обработку;
- invalid response вызывает repair retry с `repair_max_output_tokens`;
- unrepaired batch split на половины;
- single-task unrepaired failure не ломает run;
- budget stop graceful, с `stop_reason=max_cost_reached`.

## Smoke tests

Сначала deterministic:

```text
.venv/bin/python -m py_compile ...
.venv/bin/python -m unittest discover -s tests
```

Затем:

- smoke 50: разрешен;
- smoke 200: только если smoke 50 не покажет blocking-проблемы;
- production command не запускаю без отдельного разрешения.

## Риски

- LLM может вернуть валидный JSON с плохими цитатами; quote validator должен быть строгим.
- Publication-review flags не блокируют extraction, но должны переноситься в `review_tasks.jsonl` и evidence item review flags.
- `quote_not_found_share > 5%` блокирует переход к A3 без анализа.
- Queue большая: production требует batching, resume, cache и controlled max_inflight.
- Сетевой/API smoke может быть заблокирован sandbox или отсутствием ключей; это не должно ломать deterministic artifacts.

## Чеклист

- [x] Прочитать `instructions/01_a2_article.md`.
- [x] Прочитать `docs/article_a1_feedback.md`.
- [x] Прочитать `data/articles/a1/a1_report.json`.
- [x] Прочитать `data/articles/a1/a1_manifest.json`.
- [x] Посмотреть sample `data/articles/a1/a2_extraction_task_queue.jsonl`.
- [x] Создать этот план.
- [x] Перечитать ТЗ на checkpoint `after_plan`.
- [x] Реализовать batch builder.
- [x] Перечитать ТЗ на checkpoint `after_batch_builder`.
- [x] Реализовать schema.
- [x] Перечитать ТЗ на checkpoint `after_schema`.
- [x] Реализовать quote validation.
- [x] Перечитать ТЗ на checkpoint `after_validation_logic`.
- [x] Реализовать runner/cache/resume/retry/report/CLI.
- [x] Перечитать ТЗ на checkpoint `after_runner`.
- [x] Добавить tests.
- [x] Запустить compile check и full tests.
- [x] Перечитать ТЗ на checkpoint `after_tests`.
- [x] Перечитать ТЗ на checkpoint `before_smoke_50`.
- [x] Запустить smoke 50 или зафиксировать blocker.
- [x] Перечитать ТЗ на checkpoint `before_smoke_200`.
- [x] Запустить smoke 200 после успешного smoke 50.
- [x] Перечитать ТЗ на checkpoint `before_feedback`.
- [x] Создать `docs/article_a2_feedback.md`.

ТЗ перечитывается на этапах: after_plan, after_batch_builder, after_schema, after_validation_logic, after_runner, after_tests, before_smoke_50, before_smoke_200, before_feedback.

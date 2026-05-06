# Article A2 Feedback

ТЗ перечитано на этапах: after_plan, after_batch_builder, after_schema, after_validation_logic, after_runner, after_tests, before_smoke_50, before_smoke_200, before_feedback

## 1. Что сделано

- Реализован A2 `Evidence Extraction from Source Windows`.
- Добавлены batch builder, prompt, schema, quote validation, runner, cache/resume/retry/split, reports и CLI.
- A2 читает `data/articles/a1/a2_extraction_task_queue.jsonl` и не меняет A1 entity JSON.
- Добавлены smoke outputs для `smoke_50` и `smoke_200`.
- Production run не запускался.

## 2. Какие файлы изменены

Docs:

- `docs/article_a2_plan.md`
- `docs/article_a2_feedback.md`

Code:

- `kb_rebuild/cli.py`
- `kb_rebuild/articles/a2/__init__.py`
- `kb_rebuild/articles/a2/models.py`
- `kb_rebuild/articles/a2/prompt.py`
- `kb_rebuild/articles/a2/schema.py`
- `kb_rebuild/articles/a2/batch_builder.py`
- `kb_rebuild/articles/a2/validation.py`
- `kb_rebuild/articles/a2/report.py`
- `kb_rebuild/articles/a2/runner.py`
- `kb_rebuild/articles/a2/prompts/evidence_extract_v1.md`

Tests:

- `tests/test_article_a2_batch_builder.py`
- `tests/test_article_a2_schema.py`
- `tests/test_article_a2_validation.py`
- `tests/test_article_a2_runner.py`
- `tests/test_article_a2_report.py`

Smoke outputs:

- `data/articles/a2/experiments/smoke_50/`
- `data/articles/a2/experiments/smoke_200/`

## 3. Какие команды запускались

```bash
.venv/bin/python -m py_compile kb_rebuild/articles/a2/models.py kb_rebuild/articles/a2/prompt.py kb_rebuild/articles/a2/schema.py kb_rebuild/articles/a2/batch_builder.py kb_rebuild/articles/a2/validation.py kb_rebuild/articles/a2/runner.py kb_rebuild/articles/a2/report.py kb_rebuild/cli.py
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m kb_rebuild article-a2-extract --data data --a1-dir data/articles/a1 --planning-dir data/articles/planning --out data/articles/a2/experiments/smoke_50 --provider gemini_direct --model gemini-3-flash-preview --structured-output-mode gemini_schema --limit 50 --max-tasks-per-batch 5 --batch-char-limit 40000 --max-inflight 4 --max-retries 3 --max-output-tokens 12000 --repair-max-output-tokens 24000 --thinking-level minimal --max-cost-usd 5 --experiment-name smoke_50 --no-resume
.venv/bin/python -m kb_rebuild article-a2-extract --data data --a1-dir data/articles/a1 --planning-dir data/articles/planning --out data/articles/a2/experiments/smoke_200 --provider gemini_direct --model gemini-3-flash-preview --structured-output-mode gemini_schema --limit 200 --max-tasks-per-batch 8 --batch-char-limit 60000 --max-inflight 8 --max-retries 3 --max-output-tokens 12000 --repair-max-output-tokens 24000 --thinking-level minimal --max-cost-usd 10 --experiment-name smoke_200
```

## 4. Tests

- Compile check: passed.
- Full test suite: 228 tests passed.

## 5. Smoke 50 result

Первый запуск до исправления локации Gemini упал provider-level ошибкой:

```text
Gemini HTTP 400: User location is not supported for the API use
```

После исправления локации smoke 50 прошел:

- `tasks_processed`: 50
- `tasks_success`: 13
- `tasks_review`: 37
- `tasks_failed`: 0
- `evidence_items_total`: 122
- `quote_not_found`: 1
- `quote_not_found_share`: 0.008197
- `invalid_json_count`: 0
- `schema_validation_failures`: 0
- `batch_splits`: 0
- `requests`: 12
- `estimated_cost_usd`: 0.089684
- `avg_latency_ms`: 8845
- `quality.passed`: true

## 6. Smoke 200 result

- `tasks_processed`: 200
- `tasks_success`: 34
- `tasks_review`: 166
- `tasks_failed`: 0
- `evidence_items_total`: 390
- `evidence_items_valid_quotes`: 381
- `quote_not_found`: 9
- `quote_not_found_share`: 0.023077
- `invalid_json_count`: 0
- `schema_validation_failures`: 0
- `batch_splits`: 0
- `requests`: 26
- `estimated_cost_usd`: 0.29626
- `avg_latency_ms`: 12040
- `quality.passed`: true

## 7. Production run

Production A2 не запускался, потому что ТЗ требует отдельное разрешение архитектора.

## 8-15. Summary metrics

Основной проверенный run: `data/articles/a2/experiments/smoke_200/`.

- Tasks processed: 200
- Evidence items created: 390
- No-evidence tasks: 0
- Review tasks: 166
- Failed tasks: 0
- Quote validation: `exact=359`, `normalized_exact=17`, `fuzzy=5`, `not_found=9`
- Invalid JSON / retries / batch splits: `invalid_json=0`, `schema_failures=0`, `batch_splits=0`
- Cost and latency: `$0.29626`, average latency `12040 ms`

## 16. Примеры хороших evidence items

- `Can f 1`: classification, quote exact: `Can f 1 (Липокалин): Это мажорный аллерген собаки`.
- `Fel d 1`: description, quote exact: `Основная продукция этого белка происходит в сальных железах кожи...`.
- `Бактериальные экзотоксины`: description, quote exact: `Продуцируются как грамположительными, так и грамотрицательными бактериями.`

## 17. Примеры no_evidence

В smoke 50 и smoke 200 no-evidence tasks не встретились.

## 18. Примеры review / quote issues

- `Интерферон бета-1b`: quote содержит многоточия, status `not_found`, reason `ellipsis_or_stitched_quote`.
- `Гемоглобин`: quote содержит склейку через многоточие, status `not_found`.
- `Кофеин`: list-like quote не найден как непрерывная подстрока, status `not_found`.

Review tasks в smoke 200 в основном связаны с A1 review flags / publication-review propagation. Evidence items при этом сохраняются, но получают review flags.

## 19. Что не сделано

- Не запускался production A2.
- Не создавались финальные статьи.
- Не компилировались Editor.js articles.
- Не менялись A1 entity JSON.
- Не менялись A0/A1/N1/N2/N3/N4 artifacts.
- Не запускался тест на 4000 элементов.
- Не запускались web search, citation/question generation, folders или graph build.

## 20. Риски

- `quote_not_found_share=2.31%` на smoke 200 ниже 5%, но quote issues показывают типичный риск: модель иногда склеивает list/bullet fragments или использует многоточия.
- `review_tasks=166/200`, потому что publication-review flags проходят дальше. Это корректно для safety, но downstream A3/A4 должен учитывать `needs_review_before_publication`.
- Smoke покрывает первые 200 A1 tasks, все они `biological_substance`; перед production стоит ожидать другой профиль ошибок на disease/drug/device/procedure.
- Production нужно запускать только с cache/resume/retry и мониторингом quote_not_found_share.

## 21. Что передать в A3

Главный output для A3 после production:

```text
data/articles/a2/evidence_items.jsonl
data/articles/a2/evidence_task_results.jsonl
```

Пока production не запускался, проверенные smoke outputs находятся здесь:

```text
data/articles/a2/experiments/smoke_200/evidence_items.jsonl
data/articles/a2/experiments/smoke_200/evidence_task_results.jsonl
data/articles/a2/experiments/smoke_200/a2_report.json
data/articles/a2/experiments/smoke_200/manual_qa_sample.csv
data/articles/a2/experiments/smoke_200/quote_validation_issues.jsonl
```

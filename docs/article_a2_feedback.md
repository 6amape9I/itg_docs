# Article A2 Feedback

ТЗ перечитано на этапах: after_plan, after_batch_builder, after_schema, after_validation_logic, after_runner, after_tests, before_smoke_50, before_smoke_200, before_feedback

## 1. Что сделано

- Реализован A2 `Evidence Extraction from Source Windows`.
- Добавлены batch builder, prompt, schema, quote validation, runner, cache/resume/retry/split, checkpoint reports, финальные reports и CLI.
- A2 читает `data/articles/a1/a2_extraction_task_queue.jsonl` и не меняет A1 entity JSON.
- Выполнены smoke outputs для `smoke_50` и `smoke_200`.
- По отдельному разрешению запущен и завершен production run `production_v1` без `--limit` и без `--no-resume`.
- Финальные production outputs сохранены в `data/articles/a2/production_v1/`.

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

Generated outputs:

- `data/articles/a2/experiments/smoke_50/`
- `data/articles/a2/experiments/smoke_200/`
- `data/articles/a2/production_v1/`

## 3. Какие команды запускались

```bash
.venv/bin/python -m py_compile kb_rebuild/articles/a2/models.py kb_rebuild/articles/a2/prompt.py kb_rebuild/articles/a2/schema.py kb_rebuild/articles/a2/batch_builder.py kb_rebuild/articles/a2/validation.py kb_rebuild/articles/a2/runner.py kb_rebuild/articles/a2/report.py kb_rebuild/cli.py
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m kb_rebuild article-a2-extract --data data --a1-dir data/articles/a1 --planning-dir data/articles/planning --out data/articles/a2/experiments/smoke_50 --provider gemini_direct --model gemini-3-flash-preview --structured-output-mode gemini_schema --limit 50 --max-tasks-per-batch 5 --batch-char-limit 40000 --max-inflight 4 --max-retries 3 --max-output-tokens 12000 --repair-max-output-tokens 24000 --thinking-level minimal --max-cost-usd 5 --experiment-name smoke_50 --no-resume
.venv/bin/python -m kb_rebuild article-a2-extract --data data --a1-dir data/articles/a1 --planning-dir data/articles/planning --out data/articles/a2/experiments/smoke_200 --provider gemini_direct --model gemini-3-flash-preview --structured-output-mode gemini_schema --limit 200 --max-tasks-per-batch 8 --batch-char-limit 60000 --max-inflight 8 --max-retries 3 --max-output-tokens 12000 --repair-max-output-tokens 24000 --thinking-level minimal --max-cost-usd 10 --experiment-name smoke_200
.venv/bin/python -m kb_rebuild article-a2-extract --data data --a1-dir data/articles/a1 --planning-dir data/articles/planning --out data/articles/a2/production_v1 --provider gemini_direct --model gemini-3-flash-preview --structured-output-mode gemini_schema --max-tasks-per-batch 8 --batch-char-limit 60000 --max-inflight 16 --max-retries 3 --max-output-tokens 12000 --repair-max-output-tokens 24000 --thinking-level minimal --max-cost-usd 100 --retry-failures --experiment-name production_v1
```

Дополнительно после добавления checkpoint reports:

```bash
.venv/bin/python -m py_compile kb_rebuild/articles/a2/runner.py kb_rebuild/articles/a2/report.py kb_rebuild/cli.py
.venv/bin/python -m unittest tests.test_article_a2_runner
.venv/bin/python -m unittest discover -s tests
```

## 4. Tests

- Compile check: passed.
- Full test suite: 228 tests passed.
- Runner-focused test after checkpoint patch: 8 tests passed.

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

Production A2 запускался после отдельного разрешения.

- Output: `data/articles/a2/production_v1/`
- `--limit`: not used
- `--no-resume`: not used
- Initial/final concurrency: `--max-inflight 16`
- Перезапуск на `32` не выполнялся: текущий run был уже стабилен и шел в production output; запускать второй writer в тот же `--out` было небезопасно.
- После уточнения, что `quote_not_found_share > 5%` не является stop-критерием, run продолжался до полного completion.
- Final CLI status: `quality_passed=True`

## 8-15. Summary metrics

Основной production run: `data/articles/a2/production_v1/`.

- Tasks processed: 34995 / 34995
- Evidence items created: 72843
- No-evidence tasks: 154
- Review tasks: 29008
- Failed tasks: 0
- Batches: `4514 total`, `4514 success`, `0 failed`, `0 splits`
- Quote validation: `exact=65759`, `normalized_exact=2375`, `fuzzy=1146`, `not_found=3563`
- Quote not found share: `0.048913`
- Invalid JSON / schema / network: `invalid_json=0`, `schema_validation_failures=35 recovered`, `http_status_counts={"network": 2}`
- Invalid LLM response records: 37
- Cost and latency: `$58.859867`, average latency `13784 ms`
- LLM requests: 4549
- `quality.all_processed_tasks_have_result`: true
- `quality.no_unknown_task_ids`: true
- `quality.passed`: true
- `warnings`: []

Artifact line counts:

- `evidence_task_results.jsonl`: 34995
- `evidence_items.jsonl`: 72843
- `no_evidence_tasks.jsonl`: 154
- `review_tasks.jsonl`: 29008
- `failed_tasks.jsonl`: 0
- `quote_validation_issues.jsonl`: 3563
- `invalid_llm_responses.jsonl`: 37
- `manual_qa_sample.csv`: 44 lines

## 16. Примеры хороших evidence items

- `Эндотоксин`: `definition`, quote `normalized_exact`, direct relevance.
- `Эндотоксин`: `composition`, quote `exact`, direct relevance.
- `Эндотоксин`: `mechanism`, quote `exact`, direct relevance.

## 17. Примеры no_evidence

- `a2task_000000286`: окно описывает диагностику и лечение лейкоза/лимфоцитоза, а не биологические характеристики NK-клеток.
- `a2task_000000348`: окно сфокусировано на ITP, а не на свойствах тромбоцитов.
- `a2task_000000309`: прокариотические клетки упомянуты только в контексте, полезного факта по tag_id нет.

## 18. Примеры review / quote issues

- `экзотоксины`: evidence extracted, но task ушел в review из-за propagated `publication_review`.
- `Кофеин`: часть list-like quotes получила `quote_validation_status=not_found`.
- `Эндорфины`: stitched quote с многоточиями получил reason `ellipsis_or_stitched_quote`.
- `Витамин D`: quote по лечению не найден как допустимая подстрока окна, item записан в `quote_validation_issues.jsonl`.

Review tasks в production в основном связаны с propagated A1/A0 review flags, fuzzy/not_found quote validation, related/unclear relevance или low-quality windows. Evidence items при этом сохраняются, но получают review flags и не должны идти в article compilation без downstream фильтрации.

## 19. Что не сделано

- Не создавались финальные статьи.
- Не компилировались Editor.js articles.
- Не менялись A1 entity JSON.
- Не менялись A0/A1/N1/N2/N3/N4 artifacts.
- Не запускался тест на 4000 элементов.
- Не запускались web search, citation/question generation, folders или graph build.
- Production outputs не копировались в root `data/articles/a2/`; они сохранены в утвержденном run folder `data/articles/a2/production_v1/`.

## 20. Риски

- `quote_not_found_share=4.8913%` близко к 5%, хотя финальный production report прошел quality gate. `not_found` evidence нельзя использовать в статьях без ручной проверки или downstream фильтрации.
- `review_tasks=29008/34995`; это ожидаемо из-за safety propagation и review flags, но A3/A4 должны строго учитывать `needs_review_before_publication`.
- `fuzzy=1146` тоже требует аккуратной downstream политики: fuzzy item сохранен как evidence, но должен быть review-sensitive.
- Production output лежит в `data/articles/a2/production_v1/`; если A3 ожидает canonical root paths, нужен явный promote/copy step.

## 21. Что передать в A3

Главный production output для A3:

```text
data/articles/a2/production_v1/evidence_items.jsonl
data/articles/a2/production_v1/evidence_task_results.jsonl
```

Сопутствующие production artifacts:

```text
data/articles/a2/production_v1/a2_report.json
data/articles/a2/production_v1/a2_manifest.json
data/articles/a2/production_v1/manual_qa_sample.csv
data/articles/a2/production_v1/quote_validation_issues.jsonl
data/articles/a2/production_v1/review_tasks.jsonl
data/articles/a2/production_v1/no_evidence_tasks.jsonl
data/articles/a2/production_v1/failed_tasks.jsonl
data/articles/a2/production_v1/invalid_llm_responses.jsonl
```

Canonical target names from the A2 instruction are:

```text
data/articles/a2/evidence_items.jsonl
data/articles/a2/evidence_task_results.jsonl
```

В этом run они не создавались в root, потому что production был запущен с `--out data/articles/a2/production_v1`.

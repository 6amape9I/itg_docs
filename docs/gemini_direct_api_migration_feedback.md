# Feedback по миграции на Gemini Direct API

Дата: 2026-05-05

Роль: LLM Orchestrator Engineer

## Что сделано

Добавлен production-путь `provider=gemini_direct` для batch tagging через прямой Google Gemini REST API.

Основное:

- добавлен `GeminiClient` с поддержкой `GEMINI_KEY_LIST` и `GEMINI_API_KEY`;
- поддержаны форматы `GEMINI_KEY_LIST`: comma, semicolon, JSON array;
- добавлен key-aware round-robin и per-key stats без логирования ключей;
- добавлен Gemini payload через `contents` и `generationConfig.responseMimeType=responseJsonSchema`;
- OpenRouter `response_format` не используется в `gemini_direct`;
- добавлен Gemini schema adapter;
- добавлен `tagging_v2_gemini`;
- batch cache теперь различает provider и учитывает hash фактического prompt;
- empty `clean_text` не отправляется в Gemini и дополнительно пишется в `empty_documents_name_candidates.jsonl`;
- добавлена команда `gemini-list-models`;
- добавлены report-поля `provider`, `model_requested`, `gemini_keys_count`, `gemini_key_stats`, `quote_summary`, `cost_per_document_usd`, `projected_full_corpus_cost_usd`, `docs_per_hour`, `warnings`;
- для Gemini 3 по умолчанию отправляется `thinkingConfig={"thinkingLevel":"minimal"}`;
- `--timeout-seconds 0` означает запуск без urllib timeout.

## Файлы изменены

- `kb_rebuild/cli.py`
- `kb_rebuild/llm/cache.py`
- `kb_rebuild/llm/models.py`
- `kb_rebuild/llm/tagging_batch.py`
- `kb_rebuild/llm/gemini_client.py`
- `kb_rebuild/llm/gemini_schema.py`
- `kb_rebuild/llm/providers.py`
- `kb_rebuild/llm/prompts/tagging_v2_gemini.md`
- `tests/test_llm_orchestrator_contract.py`
- `docs/gemini_available_models.md`
- `docs/gemini_direct_api_migration_plan.md`
- `docs/gemini_direct_api_migration_feedback.md`

`instructions/gemini_migration.md` был входным ТЗ и не редактировался мной.

## Команды и проверки

Compile check:

```bash
.venv/bin/python -m py_compile kb_rebuild/llm/gemini_client.py kb_rebuild/llm/gemini_schema.py kb_rebuild/llm/tagging_batch.py kb_rebuild/cli.py
```

Unit tests:

```bash
.venv/bin/python -m unittest discover -s tests
```

Результат: `Ran 46 tests`, `OK`.

Model discovery:

```bash
.venv/bin/python -m kb_rebuild gemini-list-models --data data
```

Результат: найдено 50 моделей. Артефакты:

- `data/reports/gemini_models.json`
- `docs/gemini_available_models.md`

Доступны нужные модели: `gemini-3-flash-preview`, `gemini-3-pro-preview`, `gemini-2.5-flash-lite`, `gemini-2.5-pro`, `gemini-2.0-flash`.

## Smoke 3

Команда на `gemini-3-flash-preview` после schema/thinking fixes:

```bash
.venv/bin/python -m kb_rebuild tag-batch --provider gemini_direct --data data --limit 3 --model gemini-3-flash-preview --schema-version document_tagging_v2 --prompt-version tagging_v2_gemini --batch-size 1 --max-inflight 1 --structured-output-mode gemini_schema --max-cost-usd 2 --experiment-name gemini_direct_smoke3_v1 --retry-failures --timeout-seconds 300
```

Результат:

- requested: 3;
- tagged: 2;
- failed: 1 `empty_clean_text`;
- HTTP errors: 0;
- 429: 0;
- quote validation: 14 exact, 1 normalized.

## Latest model check

`gemini-3-flash-latest` не существует для direct API по текущему discovery/API: вернул HTTP 404.

`gemini-flash-latest` существует и работает, фактически резолвится в `gemini-3-flash-preview`. Как experiment он полезен, но как production default его не стоит использовать из-за запрета latest-алиасов в ТЗ.

## Smoke 50

Лучший быстрый `gemini-flash-latest` smoke после усиления quote prompt:

- experiment: `gemini_direct_50_gemini_flash_latest_strict_quotes_inflight8_no_timeout_v1`;
- tagged: 49;
- failed: 1 `empty_clean_text`;
- API attempts: 10;
- retries: 0;
- invalid JSON: 0;
- HTTP errors: 0;
- 429: 0;
- cost: `$0.1299215`;
- wall clock: 24 seconds;
- docs/hour: 7350;
- quote not_found: 1 / 212 = 0.472%.

Production-ID `gemini-3-flash-preview` smoke:

- experiment: `gemini_direct_50_gemini_3_flash_preview_strict_quotes_inflight8_no_timeout_v1`;
- tagged: 49;
- failed: 1 `empty_clean_text`;
- API attempts: 10;
- retries: 0;
- invalid JSON: 0;
- HTTP errors: 0;
- 429: 0;
- cost: `$0.1358075`;
- wall clock: 28 seconds;
- docs/hour: 6300;
- quote not_found: 1 / 220 = 0.455%.

## Benchmark 200

По команде архитектора 4000 был остановлен, вместо него запущен 200-doc benchmark:

```bash
.venv/bin/python -m kb_rebuild tag-batch --provider gemini_direct --data data --limit 200 --model gemini-3-flash-preview --schema-version document_tagging_v2 --prompt-version tagging_v2_gemini --batch-size 5 --batch-char-limit 50000 --prompt-char-limit-per-doc 16000 --max-output-tokens 6000 --max-inflight 16 --min-request-interval-seconds 0 --rate-limit-backoff-seconds 120 --max-rate-limit-backoff-seconds 300 --max-retries 3 --max-cost-usd 10 --experiment-name gemini_direct_200_gemini_3_flash_preview_strict_quotes_inflight16_no_timeout_v1 --retry-failures --timeout-seconds 0
```

Результат:

- requested: 200;
- tagged: 197;
- failed: 3;
- все 3 failures: `empty_clean_text`;
- API attempts: 41;
- retries: 0;
- invalid JSON: 0;
- HTTP errors: 0;
- 429: 0;
- keys: 3, распределение запросов 14 / 14 / 13;
- cost: `$0.510403`;
- cost per tagged doc: `$0.00259088`;
- projected full corpus cost: `$41.92`;
- wall clock: 36 seconds;
- docs/hour: 19700;
- avg latency: 11883 ms;
- entities: 630;
- quote summary: found 611, normalized_found 22, fuzzy 19, not_found 11.

Quote `not_found` в 200-doc benchmark: 11 / 663 = 1.66%, выше целевого порога 1%.

## Сравнение с OpenRouter Gemini 4000

OpenRouter Gemini 4000 baseline:

- tagged: 3993 / 4000;
- model failures: 0;
- HTTP 429: 0;
- invalid JSON: 3, все восстановлены;
- cost: `$9.5935455`;
- docs/hour: около 5371;
- quote not_found: около 0.575%.

Direct Gemini 200:

- model failures: 0;
- HTTP 429: 0;
- invalid JSON: 0;
- projected cost: около `$41.92` на 16181 документов;
- скорость на 200-doc sample: около 19700 docs/hour;
- quote not_found: 1.66%.

Direct API быстрее и стабильнее по transport/JSON, но quote quality на 200 требует доработки или QA-gate.

## Что не сделано

- Полный 4000 benchmark не завершался: остановлен по команде архитектора.
- Полный корпус не запускался.
- Не мигрировались normalization/evidence/articles на direct Gemini, потому что текущий этап проверял batch tagging.
- Не исправлялись автоматически 11 `not_found` цитат в 200-doc результате.

## Риски

- `not_found` в 200-doc benchmark выше порога 1%. Типовые причины: цитата из `DOCUMENT_NAME`, склейка соседних bullet lines, переформулировка пунктуации, один случай с `...`.
- `gemini-flash-latest` работает, но latest-алиас не подходит как production default.
- Высокий `max_inflight=16` на 200 прошёл без 429, но перед полным корпусом стоит ещё раз подтвердить на 1000-2000.

## Вопросы архитектору

- Ужесточать prompt ещё сильнее, чтобы модель не брала цитаты из `DOCUMENT_NAME`, или разрешить validator искать в `DOCUMENT_NAME + CLEAN_TEXT`?
- Делать ли автоматический retry только для batch/doc, где quote `not_found` > 0?
- Принимать ли direct Gemini после 200 технически, но требовать отдельный quote-QA этап перед 4000/full?

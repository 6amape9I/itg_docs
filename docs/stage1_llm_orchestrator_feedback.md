# Stage 1 LLM Orchestrator Feedback

## Что сделано

- Добавлена команда controlled tagging:

```bash
python -m kb_rebuild tag --data data --limit 100 --model deepseek/deepseek-v4-flash --max-cost-usd 5
```

- Реализован OpenRouter client для `https://openrouter.ai/api/v1/chat/completions`.
- Добавлен дисковый LLM-кэш до реального вызова модели.
- Добавлен prompt `tagging_v1` и JSON Schema `document_tagging_v1`.
- Добавлены retry/fallback, budget preflight, usage/cost logging и failure-path без падения всего прогона.
- Добавлена проверка цитат: `quote_validation_status` и `quote_validation_details`.
- Добавлена управляемая обработка read timeout от OpenRouter: timeout теперь считается retryable error одного документа и не роняет весь batch.
- Добавлены throttle-флаги `--request-delay-seconds`, `--rate-limit-backoff-seconds`, `--retry-failures`.
- Добавлена поддержка `OPENROUTER_API_KEY_LIST`, `--use-api-key-list` и `--parallel-workers` для проверки параллелизма по ключам.
- Добавлены unit tests без реальных OpenRouter-вызовов.
- Выполнены реальные smoke/calibration попытки на parsed artifacts.

## Какие файлы изменены

- `docs/stage1_llm_orchestrator_plan.md`
- `docs/stage1_llm_orchestrator_feedback.md`
- `kb_rebuild/cli.py`
- `kb_rebuild/llm/__init__.py`
- `kb_rebuild/llm/cache.py`
- `kb_rebuild/llm/models.py`
- `kb_rebuild/llm/openrouter_client.py`
- `kb_rebuild/llm/schema_validation.py`
- `kb_rebuild/llm/tagging.py`
- `kb_rebuild/llm/prompts/tagging_v1.md`
- `kb_rebuild/llm/schemas/document_tagging.schema.json`
- `tests/test_llm_orchestrator_contract.py`

Также созданы generated artifacts в `data/llm_cache/`, `data/tagging/` и `data/reports/tagging_report.json`.

## Как запустить calibration run

Канонический запуск на 50 документов:

```bash
.venv/bin/python -m kb_rebuild tag --data data --limit 50 --model deepseek/deepseek-v4-flash --fallback-model deepseek/deepseek-v4-flash --max-cost-usd 3 --retry-failures
```

Последовательный запуск без задержки между документами:

```bash
.venv/bin/python -m kb_rebuild tag --data data --limit 50 --model deepseek/deepseek-v4-flash --fallback-model deepseek/deepseek-v4-flash --max-cost-usd 3 --request-delay-seconds 0 --retry-failures
```

Последовательный recovery-режим после 429/502:

```bash
.venv/bin/python -m kb_rebuild tag --data data --limit 50 --model deepseek/deepseek-v4-flash --fallback-model deepseek/deepseek-v4-flash --max-cost-usd 3 --request-delay-seconds 10 --rate-limit-backoff-seconds 90 --max-retries 2 --retry-failures
```

Параллельная проверка по 4 ключам из `OPENROUTER_API_KEY_LIST`:

```bash
.venv/bin/python -m kb_rebuild tag --data data --limit 50 --model deepseek/deepseek-v4-flash --fallback-model deepseek/deepseek-v4-flash --max-cost-usd 3 --request-delay-seconds 0 --max-retries 0 --retry-failures --use-api-key-list --parallel-workers 4
```

Диагностический fallback/pro запуск:

```bash
.venv/bin/python -m kb_rebuild tag --data data --limit 3 --model deepseek/deepseek-v4-pro --fallback-model deepseek/deepseek-v4-pro --max-cost-usd 1
```

## Переменные окружения

- Требуемая переменная: `OPENROUTER_API_KEY`.
- Дополнительно поддержана `OPENROUTER_API_KEY_LIST` для списка ключей. Значения ключей не логируются.
- Compatibility alias `OPEN_ROUTER_KEY` оставлен, но основной ожидаемый ключ — `OPENROUTER_API_KEY`.

## Как работает кэш

- Путь: `data/llm_cache/{cache_key}.json`.
- `cache_key` зависит от `model`, `prompt_version`, `schema_version`, `doc_id`, hash входа и request params.
- Полный prompt/request с текстом документа не сохраняется; сохраняются redacted request metadata, hashes, raw response, parsed response, usage, latency, cost и validation status.
- `valid` cache используется без API-вызова.
- `invalid` cache не принимается как успешный ответ.
- `error` cache не блокирует повторный live-запрос, потому что ошибки окружения/provider могут быть временными.

## Как работает бюджетный лимит

- CLI принимает `--max-cost-usd`.
- Перед cache-miss считается estimate по таблице стоимости моделей.
- После ответа стоимость пересчитывается по usage.
- Cache-hit не добавляет новую стоимость текущему запуску.
- При достижении лимита прогон останавливается и пишет `stop_reason` в `tagging_report.json`.

## Настроенные модели

- `deepseek/deepseek-v4-flash`
- `deepseek/deepseek-v4-pro`
- `google/gemini-3.1-flash-lite-preview`

`latest`-алиасы запрещены. Модель без настроенной цены отклоняется, потому что её нельзя корректно budget-limit.

## Результаты запусков

- Unit tests:

```bash
.venv/bin/python -m unittest discover -s tests
```

Результат: `Ran 15 tests ... OK`.
Актуальный результат после доработок: `Ran 21 tests ... OK`.

- Compile check:

```bash
.venv/bin/python -m py_compile kb_rebuild/llm/openrouter_client.py kb_rebuild/llm/tagging.py kb_rebuild/cli.py kb_rebuild/llm/openrouter_example.py
```

Результат: успешно.

- Первые default 50-doc calibration через `deepseek/deepseek-v4-flash` не дали валидного batch результата: upstream provider возвращал 429 rate limit.
- Fallback-only 50-doc calibration через `google/gemini-3.1-flash-lite-preview` не дал валидного batch результата: Google AI Studio вернул HTTP 400 `INVALID_ARGUMENT` на structured-output request.
- Smoke через `deepseek/deepseek-v4-pro` дал 1 валидный cached tagging record, но часть запросов получила upstream 429.
- `deepseek/deepseek-v4-flash` с последовательным no-delay режимом успешно обработал новые документы без 429 в коротком тесте: `limit=34`, `documents_tagged=33`, `documents_failed=1`, `llm_requests_count=1`, `rate_limit_count=0`, `sleep_seconds_total=0.0`.
- `OPENROUTER_API_KEY_LIST` содержит 4 ключа. Последовательная ротация ключей работает, но сама по себе не даёт выигрыша на cached/resume-прогонах.
- Параллельный режим `--parallel-workers 4` добавлен и протестирован. На `limit=38` он дал `documents_tagged=37`, `documents_failed=1`, `llm_requests_count=2`, `rate_limit_count=0`.
- Следующий параллельный тест на 4 новых live-документа (`limit=42`, 4 worker-а, без задержки, без retry) получил 4 upstream 429. Вывод: параллелизм по ключам не выглядит безопасным дефолтом; лимит, вероятно, общий на route/account/provider.
- Последовательный recovery после параллельных 429 с `request_delay=10`, `rate_limit_backoff=60/90`, `max_retries=1/2` восстановил документы 39-42. Финально по первым 42 документам `deepseek/deepseek-v4-flash`: 41 успешный tagging record, 1 failed — пустой `doc_000001`, где нет `clean_text`.
- Последний `data/reports/tagging_report.json`: `documents_requested=42`, `documents_tagged=41`, `documents_failed=1`, `entities_total=165`, `invalid_json_count=0`, `stop_reason=null`.

## Structured outputs issues

- `provider.require_parameters=true` включён, поэтому запросы не должны молча деградировать в неструктурированный текст.
- `deepseek/deepseek-v4-flash`: structured outputs работают; основной риск — upstream 429/502 при быстрых или параллельных запросах.
- `deepseek/deepseek-v4-pro`: upstream 429 от AtlasCloud, но один запрос прошёл и вернул валидный structured response с actual model id `deepseek/deepseek-v4-pro-20260423`.
- `google/gemini-3.1-flash-lite-preview`: HTTP 400 `INVALID_ARGUMENT` от Google AI Studio на текущем structured-output payload.

## Что не сделано

- Не получен стабильный 50-200 document calibration run с рекомендованным primary/fallback стеком без 429/400 на fallback routes.
- Не выполнялась нормализация тегов.
- Не выполнялось evidence extraction.
- Не создавались статьи.
- Не добавлялись внешние медицинские знания.

## Риски

- Для массового этапа нужен provider route или BYOK, иначе 429 может повториться на корпусе.
- `--parallel-workers 4` на 4 новых live-запросах вызвал 429 на каждом запросе; не использовать как production default без отдельного provider/BYOK решения.
- Для текущего OpenRouter route наиболее безопасный режим: последовательный запуск, `--retry-failures`, умеренный `--rate-limit-backoff-seconds`, опционально `--request-delay-seconds 0` на малых batch или 2-10 секунд на recovery/массовых batch.
- Нужно решить, использовать ли `deepseek-v4-pro` как временную calibration модель, несмотря на более высокую цену.
- Нужно отдельно проверить поддержку structured outputs у Gemini fallback или заменить fallback на модель/provider, который принимает `response_format.json_schema`.
- В `data/llm_cache/` есть error-cache от диагностических запусков; runner их не принимает как success и может перезаписать при повторном live-запросе.

## Вопросы архитектору

- Переименовать `.env` ключ в `OPENROUTER_API_KEY` или оставить compatibility alias `OPEN_ROUTER_KEY`?
- Подключать BYOK/provider integrations в OpenRouter для DeepSeek, чтобы убрать upstream 429?
- Утвердить альтернативную fallback-модель, которая гарантированно поддерживает structured outputs через OpenRouter?
- Нужно ли очищать diagnostic error-cache перед QA или оставить его как audit trail первых запусков?

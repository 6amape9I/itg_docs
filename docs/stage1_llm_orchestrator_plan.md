# Stage 1 LLM Orchestrator Plan

## Что я понял

Нужно добавить контролируемый LLM-слой для первичного тегирования уже распарсенных документов из `data/parsed/parsed_documents.jsonl`. Роль LLM Orchestrator Engineer не дублирует парсер и не нормализует теги. Выход этого этапа — сырые сущности документа, полученные через OpenRouter, с кэшем, JSON Schema, ретраями, fallback-моделью, бюджетным лимитом и отчётом.

Фактические LLM-вызовы допустимы только через отдельную CLI-команду `tag`, с кэшем и лимитом стоимости. API-ключ не хранится в коде, логах или артефактах; он читается из `OPENROUTER_API_KEY`, который может быть загружен из локального `.env`.

## Какие модули создам

- `kb_rebuild/llm/openrouter_client.py` — HTTP-клиент OpenRouter Chat Completions через стандартную библиотеку Python.
- `kb_rebuild/llm/cache.py` — дисковый JSON-кэш `data/llm_cache/{cache_key}.json`.
- `kb_rebuild/llm/models.py` — явная конфигурация разрешённых моделей и стоимости без `latest`-алиасов.
- `kb_rebuild/llm/schema_validation.py` — строгая локальная проверка tagging response без реального API.
- `kb_rebuild/llm/tagging.py` — orchestration: чтение parsed docs, построение prompt, кэш, ретраи, fallback, бюджет, outputs.
- `kb_rebuild/llm/prompts/tagging_v1.md` — версия промпта `tagging_v1`.
- `kb_rebuild/llm/schemas/document_tagging.schema.json` — схема версии `document_tagging_v1`.
- `tests/test_llm_orchestrator_contract.py` — тесты кэша, схемы, бюджета и failure-path без OpenRouter.

Также минимально изменю `kb_rebuild/cli.py`, добавив команду `tag`.

## Формат кэша

Кэш будет храниться в:

```text
data/llm_cache/{cache_key}.json
```

`cache_key` считается как SHA-256 от canonical JSON с:

- `model`;
- `prompt_version`;
- `schema_version`;
- `doc_id`;
- `input_hash`;
- основных параметров запроса: `temperature`, `max_tokens`, `provider.sort`, `provider.require_parameters`, `prompt_char_limit`, `request_kind`.

В кэше не будет полного prompt/request с текстом документа. Будут сохранены hash/metadata, raw response, parsed response, usage, latency, estimated cost, validation status и ошибки валидации.

## Как ограничу стоимость

- CLI поддержит `--max-cost-usd`.
- Перед каждым cache-miss будет preflight-estimate по таблице стоимости моделей.
- После ответа стоимость будет пересчитана по usage, если usage есть.
- Cache-hit не увеличивает фактическую стоимость текущего запуска.
- При достижении лимита прогон корректно остановится, уже записанные результаты сохранятся, причина попадёт в `data/reports/tagging_report.json`.

## Как буду валидировать JSON

- OpenRouter-запрос будет использовать structured outputs:
  - `response_format.type = "json_schema"`;
  - `json_schema.strict = true`;
  - `provider.require_parameters = true`.
- После ответа JSON всё равно валидируется локально.
- Проверяется структура верхнего уровня, `doc_id`, список `entities`, разрешённые `entity_type`, типы полей, диапазон `confidence`, отсутствие лишних полей.
- Если JSON невалиден, будет один или несколько ограниченных retry/repair-attempt по `--max-retries`.
- После исчерпания ретраев и fallback item записывается в `document_tagging_failures.jsonl`.

## Риски

- У конкретного provider endpoint может не быть structured outputs; при `require_parameters=true` такой запрос должен завершиться управляемой ошибкой или уйти на fallback.
- Некоторые parsed documents пустые; их нельзя отправлять в LLM без evidence-текста, они будут попадать в failure artifact с причиной `empty_clean_text`.
- Цитаты от LLM могут быть переформулированы; на этапе 1 сущность не удаляется, но получает `quote_validation_status`.
- Стоимость остаётся estimate, если OpenRouter не вернул точную usage/cost-метрику.
- Большие документы нужно обрезать до `prompt_char_limit`; факт обрезки сохраняется в metadata.

## Чеклист

- [x] Добавить prompt `tagging_v1`.
- [x] Добавить JSON Schema `document_tagging_v1`.
- [x] Реализовать модельную конфигурацию и запрет `latest`.
- [x] Реализовать OpenRouter client без логирования ключа.
- [x] Реализовать дисковый кэш до первого LLM-вызова.
- [x] Реализовать tagging runner с retry/fallback/budget.
- [x] Добавить CLI `python -m kb_rebuild tag --data data --limit 100 --model ... --max-cost-usd ...`.
- [x] Создать output artifacts `data/tagging/*` и `data/reports/tagging_report.json`.
- [x] Добавить тесты без реального OpenRouter.
- [x] Запустить unit tests и smoke/calibration run.
- [x] Создать feedback-файл.

## Использованные справочные источники

- OpenRouter Structured Outputs documentation.
- OpenRouter Provider Routing documentation.
- OpenRouter model cards для `deepseek/deepseek-v4-flash`, `deepseek/deepseek-v4-pro`, `google/gemini-3.1-flash-lite-preview`.

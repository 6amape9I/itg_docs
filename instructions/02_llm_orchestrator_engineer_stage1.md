# Инструкция для агента: LLM Orchestrator Engineer — этап 1

## Роль в проекте

Ты LLM Orchestrator Engineer. Твоя задача — подготовить контролируемую инфраструктуру вызовов LLM через OpenRouter: клиент, конфиг моделей, JSON Schema, кэширование, ретраи, бюджетные лимиты, логирование стоимости и тестовый прогон тегирования на 50–200 документах.

Ты не отвечаешь за парсинг Editor.js и не должен дублировать работу Pipeline Engineer. Твой вход — уже распарсенные документы из `data/parsed/parsed_documents.jsonl`.

## Контекст проекта

Проект пересобирает около 16 000 медицинских документов. Сначала документы парсятся, затем отправляются в LLM для первичного тегирования. Тегирование должно выделять только основные сущности документа: болезни, торговые названия лекарств, БАДы, симптомы, медицинские изделия, процедуры, диагностические методы, органы/системы и другие самостоятельные медицинские темы.

Важное архитектурное правило: мы не доверяем LLM как монолиту. LLM должна возвращать строго валидируемый JSON. Код обязан кэшировать запросы, проверять схемы, ограничивать бюджет, логировать usage и уметь продолжать работу после сбоя.

## Актуальный модельный стек для первого этапа

Основная модель для массового тегирования:

```text
deepseek/deepseek-v4-flash
```

Модель для сложных случаев и нормализации в следующих этапах:

```text
deepseek/deepseek-v4-pro
```

Fallback для массового тегирования:

```text
google/gemini-3.1-flash-lite-preview
```

На первом этапе нужно реализовать конфигурацию так, чтобы модель можно было менять без изменения кода.

Запрещено использовать `latest`-алиасы в production-прогоне. Модель должна быть указана полным стабильным OpenRouter ID.

## Обязательные действия перед началом

1. Прочитай все актуальные файлы в папке `instructions`.
2. Дождись, что Pipeline Engineer создал или описал ожидаемый формат `parsed_documents.jsonl`. Если файла ещё нет, используй тестовые фикстуры и не блокируй работу.
3. Создай файл плана:

```text
docs/stage1_llm_orchestrator_plan.md
```

4. В плане зафиксируй:
   - как ты понял задачу;
   - какие модули создашь;
   - какой формат кэша используешь;
   - как ограничишь стоимость;
   - как будешь валидировать JSON;
   - какие риски видишь.

## Главный результат этапа

После твоей работы должны появиться:

```text
kb_rebuild/llm/openrouter_client.py
kb_rebuild/llm/cache.py
kb_rebuild/llm/prompts/tagging_v1.md
kb_rebuild/llm/schemas/document_tagging.schema.json
kb_rebuild/llm/tagging.py
```

Или аналогичные файлы в существующей структуре проекта.

Должна быть CLI-команда тестового тегирования:

```bash
python -m kb_rebuild tag --data data --limit 100 --model deepseek/deepseek-v4-flash --max-cost-usd 5
```

Для первого реального теста использовать лимит 50–200 документов. Цель — проверить качество, стоимость, скорость, валидность JSON и долю ретраев, а не прогонять все 16 000 документов.

## OpenRouter API

API-ключ должен читаться только из переменной окружения:

```text
OPENROUTER_API_KEY
```

Нельзя хранить ключ в коде, конфиге, логах или документации.

Рекомендуемый endpoint:

```text
https://openrouter.ai/api/v1/chat/completions
```

Запрос должен поддерживать:

- `model`;
- `messages`;
- `temperature`;
- `max_tokens` или `max_completion_tokens`;
- `response_format` для JSON Schema;
- `provider.require_parameters = true`, чтобы OpenRouter не отправлял запрос провайдеру, который не поддерживает нужные параметры;
- `provider.sort = "throughput"` или `provider.sort = "price"` как конфигурируемый параметр.

По умолчанию для тегирования:

```json
{
  "temperature": 0,
  "provider": {
    "require_parameters": true,
    "sort": "throughput"
  }
}
```

Если structured outputs не поддерживаются конкретным endpoint, запрос должен завершиться управляемой ошибкой или перейти на fallback-модель, а не молча принимать неструктурированный текст.

## JSON Schema для первичного тегирования

Создай схему:

```text
kb_rebuild/llm/schemas/document_tagging.schema.json
```

Схема должна описывать ответ:

```json
{
  "doc_id": "doc_000001_a1b2c3d4",
  "entities": [
    {
      "surface": "гастрит",
      "canonical_candidate_ru": "Гастрит",
      "canonical_candidate_latin": "Gastritis",
      "entity_type": "disease",
      "is_primary": true,
      "confidence": 0.94,
      "evidence_quotes": [
        "Короткая дословная цитата из документа"
      ],
      "comment": "Почему это основная сущность"
    }
  ]
}
```

Разрешённые `entity_type`:

```text
disease
drug_trade_name
supplement
symptom
medical_device
procedure
diagnostic_method
organ_or_body_system
medical_concept
instruction
other
```

Важное правило по лекарствам: сущность лекарства — торговое название. МНН/действующее вещество можно сохранять в комментарии или будущих полях, но на этом этапе тегом является торговое название, если документ посвящён торговому препарату.

Важное правило по общим тегам: избегать слишком общих сущностей. Например, не нужно делать тег `Сердце`, если документ реально посвящён более узкой теме. Общие сущности можно сохранять как контекст только если они являются самостоятельной темой документа.

## Prompt для тегирования

Создай prompt-файл:

```text
kb_rebuild/llm/prompts/tagging_v1.md
```

Prompt должен объяснять модели:

1. Нужно выделить только основные сущности документа.
2. Не нужно извлекать все медицинские слова подряд.
3. Не нужно добавлять теги `лечение`, `диагностика`, `профилактика`, `инструкция`, если это не самостоятельная сущность.
4. Если документ про две основные темы, вернуть две сущности.
5. Если документ содержит операционную инструкцию, можно вернуть `procedure`, `medical_device` или `instruction`, если это действительно основная тема.
6. Для лекарств использовать торговое название как сущность.
7. Для каждой сущности нужна короткая цитата из документа.
8. Нужно вернуть русский canonical tag и, если возможно, латинское/международное название.
9. Нельзя добавлять внешние факты, которых нет в документе.

В prompt обязательно передавать:

```text
DOC_ID
DOCUMENT_NAME
CLEAN_TEXT
```

Если `clean_text` слишком длинный, на этом этапе можно обрезать его до конфигурируемого лимита, но нужно записывать факт обрезки в metadata. Не обрезай название документа.

## Кэширование LLM-запросов

Каждый LLM-вызов обязан кэшироваться.

Рекомендуемая структура:

```text
data/llm_cache/{cache_key}.json
```

`cache_key` должен зависеть от:

- `model`;
- `prompt_version`;
- `schema_version`;
- `doc_id`;
- hash входного текста;
- основных параметров запроса.

Содержимое кэша:

```json
{
  "cache_key": "...",
  "created_at": "2026-05-04T00:00:00Z",
  "model": "deepseek/deepseek-v4-flash",
  "prompt_version": "tagging_v1",
  "schema_version": "document_tagging_v1",
  "input_hash": "sha256...",
  "request": {
    "redacted": true
  },
  "response_raw": {},
  "response_parsed": {},
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "reasoning_tokens": 0
  },
  "estimated_cost_usd": 0.0,
  "latency_ms": 0,
  "validation_status": "valid"
}
```

Не нужно сохранять полный request в открытом виде, если он сильно раздувает кэш. Но обязательно сохрани достаточные hash/metadata для воспроизводимости.

## Ретраи и fallback

При ошибке нужно использовать ограниченные ретраи.

Рекомендуемая логика:

1. Первый запрос к primary model.
2. Если сетевой сбой или 5xx — retry с exponential backoff.
3. Если JSON невалиден — один repair retry с более жёстким system/user сообщением.
4. Если structured outputs не поддержаны или повторно невалидный JSON — fallback model.
5. Если fallback тоже не сработал — записать статус `failed`, не ломать весь прогон.

Максимум ретраев должен быть конфигурируемым, дефолт — 2.

## Бюджет и стоимость

На аккаунте сейчас ориентировочно есть 30 USD. Первый calibration run должен быть заметно дешевле полного бюджета.

CLI должен поддерживать:

```bash
--max-cost-usd 5
```

Если оценочная стоимость достигает лимита, пайплайн должен корректно остановиться, сохранить уже полученные результаты и записать причину остановки в отчёт.

Стоимость считать по таблице моделей в конфиге:

```yaml
models:
  deepseek/deepseek-v4-flash:
    input_usd_per_million_tokens: 0.14
    output_usd_per_million_tokens: 0.28
  deepseek/deepseek-v4-pro:
    input_usd_per_million_tokens: 0.435
    output_usd_per_million_tokens: 0.87
  google/gemini-3.1-flash-lite-preview:
    input_usd_per_million_tokens: 0.25
    output_usd_per_million_tokens: 1.50
```

Если API возвращает usage или стоимость точнее, используй реальные usage-данные.

## Выходные артефакты тегирования

Создай:

```text
data/tagging/document_tags_raw.jsonl
data/tagging/document_tagging_failures.jsonl
data/reports/tagging_report.json
```

`document_tags_raw.jsonl`:

```json
{
  "doc_id": "doc_000001_a1b2c3d4",
  "document_name": "Название",
  "model": "deepseek/deepseek-v4-flash",
  "prompt_version": "tagging_v1",
  "schema_version": "document_tagging_v1",
  "entities": [
    {
      "surface": "гастрит",
      "canonical_candidate_ru": "Гастрит",
      "canonical_candidate_latin": "Gastritis",
      "entity_type": "disease",
      "is_primary": true,
      "confidence": 0.94,
      "evidence_quotes": ["..."],
      "comment": "..."
    }
  ],
  "validation_status": "valid"
}
```

`document_tagging_failures.jsonl` должен содержать документы, где тегирование не удалось, с причиной.

`tagging_report.json`:

```json
{
  "stage": "tagging_calibration",
  "documents_requested": 100,
  "documents_tagged": 0,
  "documents_failed": 0,
  "entities_total": 0,
  "entities_by_type": {},
  "models_used": [],
  "llm_requests_count": 0,
  "llm_retries_count": 0,
  "cache_hits": 0,
  "cache_misses": 0,
  "estimated_cost_usd": 0.0,
  "avg_latency_ms": 0,
  "invalid_json_count": 0,
  "notes": []
}
```

## Валидация цитат в тегировании

На первом этапе цитаты в `evidence_quotes` должны быть короткими и дословными.

Код должен проверить, что каждая цитата встречается в `clean_text` или хотя бы fuzzy-matches с ним. Если цитата не найдена, не удаляй сущность автоматически, но пометь:

```json
"quote_validation_status": "not_found"
```

Это нужно для будущего evidence pipeline.

## Тесты

Минимальные тесты:

1. Генерация cache_key стабильна.
2. Повторный вызов с тем же input читает кэш и не вызывает API.
3. JSON Schema валидирует корректный ответ.
4. JSON Schema отклоняет ответ с неизвестным `entity_type`.
5. Budget limiter останавливает прогон при достижении лимита.
6. Failure-файл создаётся при simulated invalid response.

Для тестов нельзя реально обращаться к OpenRouter. Используй mock/fake client.

## Ограничения

Не запускай массовый прогон на все 16 000 документов без явного разрешения.

Не трать больше указанного `--max-cost-usd`.

Не храни API-ключ.

Не принимай невалидный JSON.

Не добавляй внешние медицинские знания.

Не нормализуй теги на этом этапе — только сырое первичное тегирование.

Не создавай статьи.

## Критерии приёмки этапа

Этап можно принимать, если:

- есть OpenRouter-клиент;
- есть кэш LLM-запросов;
- есть JSON Schema для tagging;
- есть prompt tagging_v1;
- есть CLI-команда `tag` с `--limit` и `--max-cost-usd`;
- есть usage/cost logging;
- есть fallback/retry логика;
- есть `document_tags_raw.jsonl` после тестового запуска;
- есть tagging report;
- есть тесты на кэш, схему и бюджет;
- есть feedback-файл.

## Feedback в конце работы

Создай файл:

```text
docs/stage1_llm_orchestrator_feedback.md
```

В нём укажи:

- что сделано;
- какие файлы изменены;
- как запустить calibration run на 50–200 документах;
- какие переменные окружения нужны;
- как работает кэш;
- как работает бюджетный лимит;
- какие модели настроены;
- какие проблемы возникли со structured outputs;
- сколько стоил тестовый запуск, если он выполнялся;
- какие вопросы передать архитектору.

## Справочные источники для реализации

- OpenRouter Structured Outputs documentation: https://openrouter.ai/docs/guides/features/structured-outputs
- OpenRouter Provider Routing documentation: https://openrouter.ai/docs/guides/routing/provider-selection
- DeepSeek V4 Flash model card on OpenRouter: https://openrouter.ai/deepseek/deepseek-v4-flash
- DeepSeek V4 Pro model card on OpenRouter: https://openrouter.ai/deepseek/deepseek-v4-pro
- Gemini 3.1 Flash Lite Preview model card on OpenRouter: https://openrouter.ai/google/gemini-3.1-flash-lite-preview

# Задание LLM Orchestrator Engineer: Gemini-first tagging polish

## Роль исполнителя

Ты отвечаешь за управляемый LLM-слой тегирования через OpenRouter. Твоя задача — превратить текущий DeepSeek-oriented calibration runner в стабильный Gemini-first benchmark/production candidate, не ломая кэш, бюджет, JSON validation и воспроизводимость.

## Главная цель

Реализовать и проверить режим, где основной моделью тегирования является:

```text
google/gemini-3-flash-preview
```

DeepSeek V4 Flash должен остаться доступен как baseline/reference, но не должен быть обязательным primary route.

## Обязательные изменения

### 1. Добавить Gemini 3 Flash в конфигурацию моделей

Добавить в `kb_rebuild/llm/models.py`:

```text
GEMINI_FLASH_TAGGING_MODEL = "google/gemini-3-flash-preview"
```

Pricing:

```text
input:  $0.50 / 1M tokens
output: $3.00 / 1M tokens
```

Сохранять запрет на `latest` aliases.

### 2. Сделать model preset

Добавить CLI-флаг:

```bash
--model-preset deepseek-flash|gemini-flash
```

Либо, если проще, оставить `--model`, но добавить documented command для Gemini-first.

Canonical Gemini command:

```bash
.venv/bin/python -m kb_rebuild tag \
  --data data \
  --limit 200 \
  --model google/gemini-3-flash-preview \
  --fallback-model google/gemini-3-flash-preview \
  --experiment-name gemini_flash_v1 \
  --max-cost-usd 5 \
  --request-delay-seconds 0 \
  --rate-limit-backoff-seconds 120 \
  --max-retries 2 \
  --retry-failures \
  --timeout-seconds 300
```

### 3. Добавить `--experiment-name`

Сейчас разные диагностические результаты могут смешиваться в одном output. Это недопустимо.

Добавить CLI-флаг:

```bash
--experiment-name gemini_flash_v1
```

Он должен влиять на output paths:

```text
data/tagging/experiments/{experiment_name}/document_tags_raw_active.jsonl
data/tagging/experiments/{experiment_name}/document_tagging_failures.jsonl
data/tagging/experiments/{experiment_name}/tagging_report.json
```

Для backward compatibility можно оставить старые пути, но новые эксперименты обязаны писать в отдельную папку.

Active output должен содержать ровно один record на `doc_id` для текущих `model + prompt_version + schema_version + experiment_name`.

### 4. Active/history split

Добавить разделение:

```text
document_tags_raw_active.jsonl
run_history.jsonl или document_tags_raw_history.jsonl
```

`active` — только итоговые записи для downstream normalization.

`history` — все диагностические попытки, разные модели, старые схемы, ошибки, retries.

Если это сложно сделать полностью, минимум: `document_tags_raw_active.jsonl` должен быть чистым и без дублей по `doc_id`.

### 5. Structured output modes для Gemini

Gemini может вести себя иначе, чем DeepSeek, на `response_format.json_schema`. Поэтому добавить режим:

```bash
--structured-output-mode strict|schema_lite|prompt_json
```

Поведение:

#### strict

Текущий режим:

```json
"response_format": {
  "type": "json_schema",
  "json_schema": {
    "name": "document_tagging",
    "strict": true,
    "schema": ...
  }
}
```

`provider.require_parameters=true`.

#### schema_lite

Если Gemini отдаёт HTTP 400 `INVALID_ARGUMENT`, попробовать упрощённую JSON Schema:

- убрать `minLength`;
- убрать `maxItems`;
- убрать `minimum` / `maximum`;
- убрать `additionalProperties`;
- оставить `type`, `properties`, `required`, `items`, `enum`.

`provider.require_parameters=true`.

#### prompt_json

Если strict/schema_lite не проходят, убрать `response_format` из payload и требовать JSON только промптом. Локальную валидацию, retry и repair сохранить обязательно.

Важно: `prompt_json` можно использовать для скорости и совместимости, но only если локальная validation стабильна.

### 6. Batch tagging

Добавить batch mode:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 200 \
  --batch-size 5 \
  --model google/gemini-3-flash-preview \
  --experiment-name gemini_flash_batch5_v1 \
  --max-cost-usd 10 \
  --max-inflight 1
```

Схема batch-ответа:

```json
{
  "documents": [
    {
      "doc_id": "doc_000123_abcd1234",
      "entities": []
    }
  ]
}
```

Требования:

- batch должен содержать только непустые документы;
- если один документ внутри batch невалиден, валидные документы сохраняются;
- проблемные документы отправляются в retry smaller batch или singleton;
- batch cache key должен учитывать все doc_id, input_hashes, model, prompt/schema version, batch size, structured-output-mode.

### 7. Global adaptive rate limiter

Даже если Gemini быстрый, нужен общий контроллер, а не независимые worker sleep.

Добавить общий rate limiter для всех live API calls:

```text
max_inflight
min_interval_between_request_starts
cooldown_until
429_counter
success_streak
```

Поведение:

- при 429: установить global cooldown = max(Retry-After, rate_limit_backoff_seconds);
- при 429: снизить `max_inflight` до 1;
- при серии успешных batch: разрешить повысить `max_inflight` до 2;
- добавить jitter 0.5–2.0 секунды перед live request;
- все worker-ы обязаны проходить через общий limiter.

Начальные настройки Gemini benchmark:

```text
one-doc smoke: max_inflight=1, request_delay=0
batch smoke: batch_size=5, max_inflight=1
после 20 успешных batch без 429: max_inflight=2
```

### 8. Добавить расширенную диагностику 429 и throughput

В report добавить:

```json
{
  "llm_api_attempts_total": 0,
  "llm_success_count": 0,
  "llm_error_count": 0,
  "http_status_counts": {},
  "http_429_count": 0,
  "retry_after_values": [],
  "requests_per_hour_effective": 0,
  "documents_per_hour_effective": 0,
  "tokens_per_hour_effective": 0,
  "wall_clock_seconds": 0,
  "batch_size": 1,
  "max_inflight": 1,
  "structured_output_mode": "strict",
  "experiment_name": "gemini_flash_v1"
}
```

`llm_requests_count` не должен означать только successful completions. Нужны отдельные счётчики попыток, успехов и ошибок.

### 9. Prompt/schema v2 для более точных типов

Создать `tagging_v2` и schema `document_tagging_v2`.

Добавить entity types:

```text
drug_class
biological_substance
immunobiological_preparation
microorganism
cell_or_biological_structure
```

Уточнить:

- `drug_trade_name` — только торговое/коммерческое название препарата;
- `drug_class` — класс препаратов: макролиды, фторхинолоны, бета-лактамы;
- `biological_substance` — лизоцим, интерфероны, пропердин, фибронектин;
- `immunobiological_preparation` — вакцины, иммуноглобулины, сыворотки как тип препаратов;
- `microorganism` — бактерии, вирусы, прионы, вироиды, конкретные виды;
- `cell_or_biological_structure` — клеточная стенка, нуклеоид, рибосомы, Т-лимфоциты, В-лимфоциты.

Добавить поле:

```text
article_candidate: boolean
```

Правило: `article_candidate=true`, если сущность потенциально должна стать самостоятельным документом-сущностью. Очень общие сущности могут быть `article_candidate=false`, если они полезнее как структурный/контекстный тег.

### 10. Жёсткое правило цитат

В prompt v2 добавить:

- цитата должна быть непрерывной подстрокой из CLEAN_TEXT;
- не использовать многоточия;
- не склеивать несколько разных фрагментов;
- не переформулировать;
- длина цитаты 40–250 символов, если возможно;
- если точной цитаты нет, не возвращать сущность.

Улучшить quote validation:

- exact match по clean_text;
- normalized exact match: пробелы, переносы, bullets, tabs схлопываются;
- fuzzy match только после normalized exact;
- report должен считать `found`, `normalized_found`, `fuzzy`, `not_found`.

## Обязательные benchmark-запуски

### Smoke 3 documents

```bash
.venv/bin/python -m kb_rebuild tag \
  --data data \
  --limit 3 \
  --model google/gemini-3-flash-preview \
  --fallback-model google/gemini-3-flash-preview \
  --experiment-name gemini_flash_smoke3_strict \
  --structured-output-mode strict \
  --max-cost-usd 1 \
  --retry-failures \
  --timeout-seconds 300
```

Если strict получает 400, повторить с `schema_lite`, потом `prompt_json`.

### Calibration 50 documents

```bash
.venv/bin/python -m kb_rebuild tag \
  --data data \
  --limit 50 \
  --model google/gemini-3-flash-preview \
  --fallback-model google/gemini-3-flash-preview \
  --experiment-name gemini_flash_50 \
  --structured-output-mode <best_mode> \
  --max-cost-usd 3 \
  --request-delay-seconds 0 \
  --rate-limit-backoff-seconds 120 \
  --max-retries 2 \
  --retry-failures \
  --timeout-seconds 300
```

### Calibration 200 documents, one-doc mode

```bash
.venv/bin/python -m kb_rebuild tag \
  --data data \
  --limit 200 \
  --model google/gemini-3-flash-preview \
  --fallback-model google/gemini-3-flash-preview \
  --experiment-name gemini_flash_200_onedoc \
  --structured-output-mode <best_mode> \
  --max-cost-usd 10 \
  --request-delay-seconds 0 \
  --rate-limit-backoff-seconds 120 \
  --max-retries 2 \
  --retry-failures \
  --timeout-seconds 300
```

### Calibration 200 documents, batch mode

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 200 \
  --batch-size 5 \
  --max-inflight 1 \
  --model google/gemini-3-flash-preview \
  --fallback-model google/gemini-3-flash-preview \
  --experiment-name gemini_flash_200_batch5 \
  --structured-output-mode <best_mode> \
  --max-cost-usd 10 \
  --rate-limit-backoff-seconds 120 \
  --max-retries 2 \
  --retry-failures \
  --timeout-seconds 300
```

## Acceptance criteria

Этап считается готовым, если:

- Gemini 3 Flash добавлен в model config и budget calculation;
- experiment output paths работают;
- active output чистый и без дублей по doc_id;
- strict/schema_lite/prompt_json modes реализованы или явно задокументировано, почему часть режимов не нужна;
- one-doc Gemini benchmark на 50 и 200 документов выполнен;
- batch Gemini benchmark на 200 документов выполнен или есть техническое объяснение, почему batch пока невозможен;
- report показывает реальную throughput: documents/hour, requests/hour, wall_clock_seconds;
- 429 diagnostics добавлены;
- QA может сравнить Gemini и DeepSeek по одинаковому набору документов;
- создан feedback-файл `docs/gemini_first_llm_orchestrator_feedback.md`.

## Feedback файл

В конце работы создать:

```text
docs/gemini_first_llm_orchestrator_feedback.md
```

В нём указать:

- что сделано;
- какие файлы изменены;
- какие команды запускались;
- результаты Gemini smoke/50/200;
- лучший structured-output-mode;
- скорость documents/hour;
- стоимость benchmark;
- количество 429/400/502;
- оценку стоимости полного корпуса;
- можно ли считать Gemini primary candidate;
- риски и вопросы архитектору.

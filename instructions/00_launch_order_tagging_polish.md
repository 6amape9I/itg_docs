# Порядок запуска агентов: полировка этапа тегирования

## Контекст

Этап парсинга Editor.js считается принятым. Его не нужно переписывать. Текущая задача — стабилизировать этап первичного LLM-тегирования перед масштабированием на весь корпус.

Текущий calibration на 42 документа показал, что базовый LLM-каркас работает: JSON-ответы валидны, кэш есть, стоимость низкая, теги в целом извлекаются. Но production-прогон на 16 000 документов пока запрещён, потому что выявлены проблемы:

- `document_tags_raw.jsonl` содержит смесь результатов разных запусков и моделей;
- при параллельном запуске возникают 429 от OpenRouter/upstream provider;
- нет глобального adaptive rate limiter-а для worker-ов;
- один документ = один API-запрос, что слишком медленно для корпуса;
- Gemini fallback сейчас ломается на structured-output payload;
- текущая schema слишком бедная для микробиологии/иммунологии и заставляет модель использовать неверные типы сущностей;
- модель иногда извлекает вторичные или слишком широкие сущности как полноценные теги;
- доля `fuzzy`/`not_found` цитат слишком высокая для будущего evidence-пайплайна.

## Исполнители на этот этап

На эту полировку нужно запустить двух агентов:

1. `LLM Orchestrator Engineer` — основной исполнитель. Он дорабатывает код тегирования, prompt/schema, batch-запросы, кэш, rate limiting, отчёты и CLI.
2. `QA / Test Engineer` — проверяющий исполнитель. Он пишет валидаторы, тесты и quality report, затем проводит аудит 50–200 документов после доработки LLM-агента.

Pipeline Engineer на этом этапе не нужен, если только LLM или QA не обнаружат ошибку в parsed artifacts. Парсер принят.

## Рекомендуемый порядок работы

### Шаг 1. Запустить LLM Orchestrator Engineer

Передать агенту файл:

```text
instructions/01_llm_orchestrator_tagging_polish.md
```

Агент должен сначала создать план:

```text
docs/stage1_tagging_polish_llm_plan.md
```

После выполнения он должен создать feedback:

```text
docs/stage1_tagging_polish_llm_feedback.md
```

Пока LLM-агент не закончит, полный production-прогон на 16 000 документов не запускать.

### Шаг 2. Запустить QA / Test Engineer

QA-агента можно запустить после того, как LLM-агент создаст план. Часть валидаторов QA может писать параллельно, но финальную проверку он должен делать только после завершения LLM-агента.

Передать агенту файл:

```text
instructions/02_qa_test_engineer_tagging_polish.md
```

QA должен сначала создать план:

```text
docs/stage1_tagging_polish_qa_plan.md
```

После проверки он должен создать feedback:

```text
docs/stage1_tagging_polish_qa_feedback.md
```

## Запреты на время полировки

До завершения этой полировки запрещено:

- запускать тегирование на все 16 000 документов;
- использовать `--parallel-workers > 1` без глобального adaptive rate limiter-а;
- считать несколько API-ключей OpenRouter независимым решением 429;
- использовать Gemini fallback по умолчанию;
- отдавать старый смешанный `document_tags_raw.jsonl` в нормализацию;
- продолжать downstream-этапы normalization/evidence/articles на текущем смешанном output.

## Рекомендуемый calibration-порядок после доработки

После завершения LLM-агента сначала запустить малый прогон:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 50 \
  --batch-size 5 \
  --max-inflight 1 \
  --min-request-interval-seconds 5 \
  --model deepseek/deepseek-v4-flash \
  --fallback-model none \
  --max-cost-usd 3 \
  --max-retries 3 \
  --retry-failures \
  --timeout-seconds 300
```

Затем QA-проверка:

```bash
.venv/bin/python -m kb_rebuild validate-tagging --data data --limit 50
```

Если 50 документов стабильны, запустить 200 документов:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 200 \
  --batch-size 5 \
  --max-inflight 1 \
  --min-request-interval-seconds 5 \
  --model deepseek/deepseek-v4-flash \
  --fallback-model none \
  --max-cost-usd 5 \
  --max-retries 3 \
  --retry-failures \
  --timeout-seconds 300
```

И снова QA:

```bash
.venv/bin/python -m kb_rebuild validate-tagging --data data --limit 200
```

Если в таком режиме 429 не появляются или корректно восстанавливаются, можно будет обсуждать следующий шаг: повышение `batch-size` до 8–10 или аккуратное включение `max-inflight=2`.

## Что делать при 429

Если возникает 429:

1. Не увеличивать количество worker-ов.
2. Не добавлять новые API-ключи как основное решение.
3. Проверить, записаны ли `Retry-After`, `status_code`, sample body и route/model diagnostics.
4. Использовать общий cooldown для всех worker-ов.
5. Снизить `max-inflight` до 1.
6. Увеличить cooldown до 120–300 секунд.
7. Для диагностики можно один раз попробовать `--provider-sort price`, но не считать это гарантированным решением.

## Критерии успеха полировки

Полировка считается успешной, если:

- есть batch-команда тегирования;
- есть active-only output, где ровно один результат на `doc_id`;
- history/debug результаты не смешиваются с active output;
- Gemini fallback отключён по умолчанию;
- schema v2 и prompt v2 устраняют основные ошибки типов сущностей;
- добавлен глобальный adaptive rate limiter;
- 50-document calibration проходит стабильно;
- 200-document calibration проходит стабильно или восстанавливается после редких 429;
- QA создаёт отчёт по качеству тегов, цитат, дублей, entity types и suspicious entities;
- после QA архитектор может принять решение: масштабировать на корпус или отправить на ещё одну доработку.
## Дополнительный эксперимент: Gemini Flash как основная модель

После доработки batch tagging и global rate limiter нужно провести отдельный контролируемый эксперимент, где основной моделью будет не DeepSeek, а Gemini Flash.

Важно: это не fallback-режим. Gemini Flash нужно проверять как самостоятельную primary-модель в отдельном experiment output, чтобы не смешивать результаты с DeepSeek baseline.

### Модель эксперимента

Основная модель эксперимента:

```text
google/gemini-3-flash-preview
```

Опциональная дешёвая дополнительная проверка, только если строгий structured-output smoke проходит:

```text
google/gemini-3.1-flash-lite-preview
```

Но `google/gemini-3.1-flash-lite-preview` не должен возвращаться как default fallback, потому что в предыдущем тесте он уже давал HTTP 400 `INVALID_ARGUMENT` на текущем structured-output payload.

### Порядок Gemini-эксперимента

Эксперимент выполняется только после того, как LLM Orchestrator Engineer реализует:

- `tag-batch`;
- schema/prompt v2;
- active/history split;
- experiment output isolation;
- global adaptive rate limiter;
- расширенную диагностику HTTP 400/429.

Сначала выполнить structured-output smoke на 3 документах:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 3 \
  --batch-size 3 \
  --max-inflight 1 \
  --min-request-interval-seconds 5 \
  --model google/gemini-3-flash-preview \
  --fallback-model none \
  --experiment-name gemini_flash_strict \
  --structured-output-mode strict \
  --max-cost-usd 1 \
  --max-retries 1 \
  --timeout-seconds 300
```

Если strict structured output проходит, выполнить 50 документов:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 50 \
  --batch-size 5 \
  --max-inflight 1 \
  --min-request-interval-seconds 5 \
  --model google/gemini-3-flash-preview \
  --fallback-model none \
  --experiment-name gemini_flash_strict \
  --structured-output-mode strict \
  --max-cost-usd 5 \
  --max-retries 3 \
  --retry-failures \
  --timeout-seconds 300
```

Если 50 документов стабильны, выполнить 200 документов на тех же первых 200 документах, что и DeepSeek baseline:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 200 \
  --batch-size 5 \
  --max-inflight 1 \
  --min-request-interval-seconds 5 \
  --model google/gemini-3-flash-preview \
  --fallback-model none \
  --experiment-name gemini_flash_strict \
  --structured-output-mode strict \
  --max-cost-usd 15 \
  --max-retries 3 \
  --retry-failures \
  --timeout-seconds 300
```

### Если Gemini strict structured output возвращает HTTP 400

Если `google/gemini-3-flash-preview` возвращает HTTP 400 на strict JSON Schema payload, агент должен не считать эксперимент проваленным сразу, а реализовать совместимый диагностический режим:

```text
--structured-output-mode prompt_json
```

В этом режиме:

- `response_format=json_schema` не используется;
- prompt требует вернуть строго JSON;
- local schema validation остаётся обязательной;
- invalid JSON ведёт к retry/repair;
- результат помечается как `structured_output_mode = prompt_json`;
- такой режим не считается равным strict mode и сравнивается отдельно.

Smoke-команда для совместимого режима:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 3 \
  --batch-size 3 \
  --max-inflight 1 \
  --model google/gemini-3-flash-preview \
  --fallback-model none \
  --experiment-name gemini_flash_prompt_json \
  --structured-output-mode prompt_json \
  --max-cost-usd 1 \
  --max-retries 2 \
  --timeout-seconds 300
```

### Изоляция outputs

Gemini-эксперимент не должен перезаписывать DeepSeek active output.

Ожидаемые пути:

```text
data/experiments/gemini_flash_strict/tagging/document_tags_raw_active.jsonl
data/experiments/gemini_flash_strict/tagging/document_tagging_failures_active.jsonl
data/experiments/gemini_flash_strict/reports/tagging_report.json
data/experiments/gemini_flash_strict/reports/tagging_quality_report.json
```

Для DeepSeek baseline можно использовать либо основной `data/tagging`, либо аналогичную experiment-директорию:

```text
data/experiments/deepseek_flash_baseline/...
```

Предпочтительно использовать experiment-директории для обоих сравнительных прогонов.

### Сравнение с DeepSeek baseline

QA должен сравнить DeepSeek и Gemini на одном и том же наборе документов:

- successful documents;
- failed documents;
- invalid JSON;
- HTTP 400/429/502;
- средняя latency;
- фактическая/оценочная стоимость;
- entities per document;
- распределение `entity_type`;
- распределение `tag_role`;
- доля `article_candidate`;
- доля `exact/normalized/fuzzy/not_found` цитат;
- suspicious `drug_trade_name`;
- suspicious `organ_or_body_system`;
- overly broad article candidates;
- качество 20-30 ручных примеров.

### Когда можно заменить DeepSeek на Gemini Flash

Gemini Flash можно рекомендовать как новую основную модель только если:

- 200-document run проходит без критических HTTP 400/429 проблем;
- JSON/schema validation не хуже DeepSeek;
- качество entity types не хуже DeepSeek;
- доля `not_found` цитат не хуже DeepSeek;
- скорость заметно лучше или 429 существенно меньше;
- стоимость остаётся приемлемой;
- QA явно пишет `RECOMMENDATION: GEMINI_FLASH_CAN_REPLACE_DEEPSEEK_FOR_TAGGING`.

Если Gemini лучше по качеству, но дороже, архитектор принимает отдельное решение.

Если Gemini быстрее, но хуже по типам/цитатам, использовать её как основную модель нельзя.

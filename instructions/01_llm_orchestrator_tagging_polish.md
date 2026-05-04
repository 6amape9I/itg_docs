# LLM Orchestrator Engineer: полировка этапа тегирования

## Роль в проекте

Ты отвечаешь за контролируемый LLM-слой первичного тегирования документов. Твоя задача — сделать этот этап пригодным для масштабирования: без смешивания исторических результатов, с batch-запросами, глобальным rate limiting, понятной отчётностью по 429 и более точной schema/prompt-логикой.

Ты не отвечаешь за парсинг Editor.js, нормализацию тегов, evidence extraction и написание финальных статей. Эти этапы не трогай, если только твои изменения не требуют минимального совместимого интерфейса.

## Текущая проблема

Текущий calibration на 42 документа показал частичный успех, но production-прогон запрещён до доработки.

Выявлены проблемы:

- `document_tags_raw.jsonl` содержит результаты разных запусков/моделей, а не только активный набор;
- параллельный запуск по нескольким ключам создаёт burst и вызывает 429;
- текущий sleep локален для worker-а, а не глобален для всего процесса;
- один документ отправляется одним API-запросом, что слишком медленно;
- fallback на `google/gemini-3.1-flash-lite-preview` сейчас возвращает 400 на structured-output payload;
- текущая schema не различает торговые названия лекарств, классы препаратов, биологические вещества, микроорганизмы и клеточные структуры;
- prompt недостаточно жёстко запрещает извлечение вторичных примеров как основных тегов;
- evidence quotes иногда не являются точной непрерывной цитатой из `CLEAN_TEXT`;
- отчётность не даёт полной картины по outbound API attempts, 429, Retry-After и cooldown.

## Перед началом работы

Создай план:

```text
docs/stage1_tagging_polish_llm_plan.md
```

В плане укажи:

- что понял;
- какие файлы изменишь;
- какие новые CLI-команды или флаги добавишь;
- какие схемы/prompt versions введёшь;
- какие тесты добавишь;
- как проверишь результат без большого production-прогона;
- какие риски остаются.

После выполнения создай feedback:

```text
docs/stage1_tagging_polish_llm_feedback.md
```

В feedback обязательно укажи:

- что сделано;
- какие файлы изменены;
- как запускать 50-doc и 200-doc calibration;
- какие тесты запускались;
- результаты тестов;
- результаты live calibration, если запускался;
- какие 429/400/502 встречались;
- что осталось нерешённым;
- можно ли, по твоему мнению, переходить к QA и почему.

## Задача 1. Разделить active output и history/debug output

Сейчас downstream может случайно взять смешанный `document_tags_raw.jsonl`, где есть результаты разных запусков и моделей. Это недопустимо.

Нужно сделать active-only output.

Обязательные файлы:

```text
data/tagging/document_tags_raw_active.jsonl
data/tagging/document_tagging_failures_active.jsonl
data/tagging/tagging_active_manifest.json
data/reports/tagging_report.json
```

Допустимо сохранить совместимый alias:

```text
data/tagging/document_tags_raw.jsonl
```

Но если этот файл остаётся, он должен быть active-only. В нём не должно быть истории старых моделей, старых prompt versions, старых schema versions и дублей `doc_id`.

Историю можно хранить отдельно, например:

```text
data/tagging/history/document_tags_history.jsonl
```

или оставить в `data/llm_cache/`, но active output не должен смешиваться с history.

`tagging_active_manifest.json` должен содержать:

```json
{
  "run_id": "tagging_YYYYMMDD_HHMMSS",
  "model": "deepseek/deepseek-v4-flash",
  "fallback_model": null,
  "prompt_version": "tagging_v2",
  "schema_version": "document_tagging_v2",
  "limit": 200,
  "documents_requested": 200,
  "documents_tagged": 199,
  "documents_failed": 1,
  "created_at": "...",
  "active_success_path": "data/tagging/document_tags_raw_active.jsonl",
  "active_failures_path": "data/tagging/document_tagging_failures_active.jsonl"
}
```

Правило: active output должен содержать максимум одну успешную запись на `doc_id`.

Если повторный запуск с тем же `doc_id` успешен, он заменяет активную запись. Старую запись можно отправить в history, но нельзя оставлять в active.

## Задача 2. Ввести schema v2 для тегирования

Создай новую схему:

```text
kb_rebuild/llm/schemas/document_tagging_v2.schema.json
```

Новая schema version:

```text
document_tagging_v2
```

Старая schema v1 может остаться для истории и совместимости, но production/calibration должен использовать v2.

### Минимальная структура ответа для одиночного документа

```json
{
  "doc_id": "doc_000123_abcd1234",
  "entities": [
    {
      "surface": "Ваксигрип",
      "canonical_candidate_ru": "Ваксигрип",
      "canonical_candidate_latin": "Vaxigrip",
      "entity_type": "drug_trade_name",
      "tag_role": "article_candidate",
      "is_primary": true,
      "confidence": 0.94,
      "evidence_quotes": [
        "непрерывная дословная цитата из CLEAN_TEXT"
      ],
      "comment": "Почему это самостоятельная основная сущность документа"
    }
  ]
}
```

### Разрешённые entity_type

Нужно поддержать минимум такие типы:

```text
disease
drug_trade_name
drug_class
supplement
symptom
medical_device
procedure
diagnostic_method
organ_or_body_system
medical_concept
instruction
microorganism
cell_or_biological_structure
biological_substance
immunobiological_preparation
other
```

Правила типов:

- `drug_trade_name` — только торговые/коммерческие названия препаратов, вакцин, БАДов, если они используются как продуктовые названия. Примеры: `Ваксигрип`, `Инфлувак`, `Энджерикс В`.
- `drug_class` — классы и группы лекарств. Примеры: `антибиотики`, `бета-лактамные антибиотики`, `макролиды`, `тетрациклины`, `фторхинолоны`.
- `biological_substance` — биологические вещества и факторы. Примеры: `лизоцим`, `интерфероны`, `пропердин`, `фибронектин`.
- `immunobiological_preparation` — вакцины, сыворотки, иммунобиологические препараты как общий тип, если нет конкретного торгового названия.
- `microorganism` — бактерии, вирусы, прионы, вироиды, грибы, простейшие, конкретные виды и роды.
- `cell_or_biological_structure` — бактериальная клетка, клеточная стенка, нуклеоид, рибосомы, Т-лимфоциты, В-лимфоциты, NK-клетки.
- `organ_or_body_system` — только органы и системы организма человека/животного: сердце, печень, ЖКТ, дыхательная система и т.п. Не использовать для клеточных структур.
- `diagnostic_method` — методы диагностики и лабораторные методы: ИФА, ПЦР, реакция Манчини, реакция агглютинации.
- `instruction` — операционная инструкция как самостоятельная тема: как надевать перчатки, как проводить обработку, как хранить материал.

### tag_role

Добавь обязательное поле:

```text
tag_role
```

Разрешённые значения:

```text
article_candidate
folder_candidate
context_only
```

Правила:

- `article_candidate` — по этой сущности потенциально можно собрать самостоятельный документ.
- `folder_candidate` — широкая сущность полезна для структуры, но не обязательно должна становиться самостоятельной статьёй на этом этапе.
- `context_only` — сущность важна для понимания документа, но в данном документе она не является основной темой.

Примеры:

- Документ про конкретную вакцину `Ваксигрип` → `Ваксигрип` как `article_candidate`.
- Документ про вакцины в целом → `вакцины` может быть `article_candidate`, если документ реально раскрывает эту тему.
- Документ про классификацию бактерий, где `Escherichia coli` приведена только как пример → `Escherichia coli` должна быть либо не извлечена, либо `context_only` с низкой уверенностью. Лучше не извлекать.
- Документ про `реакцию Манчини` → `реакция Манчини` как `diagnostic_method` и `article_candidate`.

## Задача 3. Ввести prompt v2

Создай новый prompt:

```text
kb_rebuild/llm/prompts/tagging_v2.md
```

Prompt version:

```text
tagging_v2
```

Prompt должен быть более строгим, чем v1.

Обязательные правила в prompt:

1. Извлекать только основные самостоятельные сущности документа.
2. Не извлекать все медицинские слова подряд.
3. Не извлекать примеры, перечисленные вскользь, как самостоятельные основные теги.
4. Избегать слишком широких тегов, если документ реально посвящён более специфичной сущности.
5. Широкие теги можно возвращать только как `folder_candidate` или `context_only`, если они нужны для структуры.
6. Для лекарств `drug_trade_name` — только торговое название, а не класс препарата и не действующее вещество.
7. Классы препаратов относить к `drug_class`.
8. Микроорганизмы относить к `microorganism`.
9. Клеточные структуры и клетки иммунной системы относить к `cell_or_biological_structure`.
10. Биологические вещества относить к `biological_substance`.
11. Методы диагностики относить к `diagnostic_method`.
12. Операционные инструкции разрешены как самостоятельные сущности через `instruction`, `procedure` или `medical_device`.
13. Каждая `evidence_quote` должна быть непрерывной дословной подстрокой из `CLEAN_TEXT`.
14. Не использовать многоточия внутри цитаты.
15. Не склеивать фрагменты из разных мест документа.
16. Не переформулировать цитату своими словами.
17. Если точной цитаты нет, не возвращать сущность.
18. Не добавлять внешние факты, которых нет в документе.
19. `canonical_candidate_latin` можно заполнять только если латинское/международное название явно следует из документа или является общеупотребимым названием сущности; если нет уверенности — пустая строка.

Добавь несколько коротких examples прямо в prompt. Примеры должны покрывать:

- торговое название vs класс препарата;
- диагностический метод;
- микроорганизм как основная тема vs микроорганизм как пример;
- клеточную структуру;
- операционную инструкцию.

## Задача 4. Batch tagging

Одиночный режим можно оставить, но нужно добавить batch-режим.

Основная новая команда:

```bash
python -m kb_rebuild tag-batch --data data --limit 200 --batch-size 5 --model deepseek/deepseek-v4-flash
```

Можно реализовать как отдельную CLI-команду `tag-batch` или как режим внутри `tag`, но итоговый интерфейс должен быть понятен и отражён в feedback.

### Batch response schema

Создай отдельную schema для batch, например:

```text
kb_rebuild/llm/schemas/document_tagging_batch_v2.schema.json
```

Ответ batch-запроса:

```json
{
  "documents": [
    {
      "doc_id": "doc_000001_abcd1234",
      "entities": []
    },
    {
      "doc_id": "doc_000002_efgh5678",
      "entities": []
    }
  ]
}
```

Каждый `doc_id` в batch response должен соответствовать одному из отправленных документов. Лишние `doc_id` запрещены. Пропущенные `doc_id` считаются ошибкой batch-а.

### Формирование batch-а

Batch должен учитывать:

- `--batch-size`, например 5 по умолчанию;
- `--batch-char-limit`, например 50 000 символов на batch;
- `--prompt-char-limit-per-doc`, например 12 000–16 000 символов на документ;
- пустые `clean_text` не отправлять в LLM, а писать в failures как `empty_clean_text`.

### Ошибки batch-а

Если batch response невалиден:

1. Попробовать retry/repair batch-а, если retries остались.
2. Если batch снова невалиден, split batch пополам.
3. Если single-document batch всё ещё невалиден, записать failure только для этого документа.
4. Валидные документы из успешных smaller batches сохранить.

Важно: ошибка одного документа не должна терять весь batch.

### Кэш batch-а

Batch-запрос должен кэшироваться.

Cache key должен учитывать:

- model;
- prompt_version;
- schema_version;
- batch doc_ids;
- hash входов документов;
- request params;
- batch_size / char limits.

При этом active output сохраняется на уровне документа: один record на `doc_id`.

## Задача 5. Глобальный adaptive rate limiter

Текущий локальный sleep внутри worker-а недостаточен. Нужно добавить общий rate limiter для всех live OpenRouter API calls.

Создай отдельный модуль, например:

```text
kb_rebuild/llm/rate_limiter.py
```

Rate limiter должен поддерживать:

```text
max_inflight
min_request_interval_seconds
cooldown_until
Retry-After
exponential backoff
jitter
429-aware cooldown
concurrency reduction after 429
optional slow concurrency increase after stable success streak
```

Минимальные CLI-флаги:

```text
--max-inflight
--min-request-interval-seconds
--rate-limit-backoff-seconds
--max-rate-limit-backoff-seconds
```

Начальные безопасные значения для calibration:

```text
max_inflight = 1
min_request_interval_seconds = 5
rate_limit_backoff_seconds = 120
max_rate_limit_backoff_seconds = 300
```

Правила:

- Все worker-ы должны получать разрешение на live API call через один общий limiter.
- При 429 весь процесс входит в общий cooldown.
- Если OpenRouter вернул `Retry-After`, использовать максимум из `Retry-After` и локального backoff.
- При 429 снижать effective concurrency до 1.
- Не делать burst при старте нескольких worker-ов.
- Не считать несколько API-ключей гарантией независимых лимитов.

## Задача 6. Fallback-модели

Gemini fallback сейчас не должен использоваться по умолчанию.

Измени default так, чтобы production/calibration по умолчанию работал без Gemini fallback:

```text
fallback_model = None
```

или:

```text
fallback_model = same_as_primary
```

Предпочтительно — `None`, если CLI это поддерживает.

CLI должен принимать:

```bash
--fallback-model none
```

и интерпретировать это как отсутствие fallback.

Gemini можно оставить в pricing config как явную экспериментальную модель, но не использовать автоматически.

## Задача 7. Улучшить quote validation

Нужно снизить долю `not_found` и сделать статусы понятнее.

Сейчас можно оставить старые статусы, но добавь более прозрачную логику:

```text
exact
normalized
fuzzy
not_found
```

Где:

- `exact` — цитата найдена как точная подстрока в `clean_text`;
- `normalized` — цитата найдена после нормализации пробелов, переносов, табов, bullets и HTML entities;
- `fuzzy` — найдено похожее место, но цитата не является точной непрерывной подстрокой;
- `not_found` — цитата не подтверждена.

Для `quote_validation_status` можно использовать summary:

```text
all_exact
all_found
mixed
not_found
no_quotes
```

Не удаляй сущность автоматически только из-за `fuzzy`, но обязательно записывай status и details.

Для будущего evidence-этапа `exact` и `normalized` предпочтительны; `fuzzy` — warning; `not_found` — серьёзный warning.

## Задача 8. Расширить отчётность

`tagging_report.json` должен показывать не только успешные completions, но и все outbound attempts.

Добавь минимум:

```json
{
  "llm_api_attempts_total": 0,
  "llm_success_count": 0,
  "llm_error_count": 0,
  "http_status_counts": {
    "429": 0,
    "502": 0
  },
  "rate_limit_count": 0,
  "retry_after_values_seconds": [],
  "cooldown_events_count": 0,
  "cooldown_seconds_total": 0,
  "batch_requests_count": 0,
  "batch_documents_requested": 0,
  "batch_documents_succeeded": 0,
  "batch_documents_failed": 0,
  "batch_split_count": 0,
  "active_records_count": 0,
  "active_duplicate_doc_ids": 0,
  "quote_validation_summary": {},
  "suspicious_notes": []
}
```

OpenRouter API key нельзя логировать. Response body можно сохранять только как короткий sample и без чувствительных ключей.

## Задача 9. Тесты

Добавь unit tests без live OpenRouter-вызовов.

Минимум тестов:

- schema v2 валидирует правильный response;
- schema v2 отклоняет неизвестный `entity_type`;
- schema v2 требует `tag_role`;
- batch schema валидирует batch response;
- batch validator отклоняет лишний `doc_id`;
- batch validator отклоняет пропущенный `doc_id`;
- active output не содержит дублей `doc_id`;
- history/debug output не попадает в active output;
- `--fallback-model none` отключает fallback;
- global rate limiter не разрешает стартовый burst;
- 429 вызывает общий cooldown;
- quote validator различает `exact`, `normalized`, `fuzzy`, `not_found`.

Запуск:

```bash
.venv/bin/python -m unittest discover -s tests
```

## Задача 10. Calibration commands

После доработки нужно, если возможно, выполнить live calibration на 50 документов.

Рекомендуемый старт:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 50 \
  --batch-size 5 \
  --batch-char-limit 50000 \
  --prompt-char-limit-per-doc 16000 \
  --max-inflight 1 \
  --min-request-interval-seconds 5 \
  --model deepseek/deepseek-v4-flash \
  --fallback-model none \
  --max-cost-usd 3 \
  --max-retries 3 \
  --retry-failures \
  --timeout-seconds 300
```

Если 50 документов стабильны, выполнить 200:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 200 \
  --batch-size 5 \
  --batch-char-limit 50000 \
  --prompt-char-limit-per-doc 16000 \
  --max-inflight 1 \
  --min-request-interval-seconds 5 \
  --model deepseek/deepseek-v4-flash \
  --fallback-model none \
  --max-cost-usd 5 \
  --max-retries 3 \
  --retry-failures \
  --timeout-seconds 300
```

Если возникает 429:

- не повышать worker count;
- проверить, что cooldown общий;
- зафиксировать `Retry-After` и sample response body;
- повторить с cooldown 120–300 секунд;
- можно один раз диагностически попробовать `--provider-sort price`.

## Критерии приёмки для твоей работы

Твоя работа считается готовой к QA, если:

- `tag-batch` или эквивалентный batch-режим реализован;
- active output отделён от history;
- в active output нет дублей `doc_id`;
- schema v2 и prompt v2 используются по умолчанию для нового calibration;
- Gemini fallback отключён по умолчанию;
- есть глобальный adaptive rate limiter;
- 429 приводит к общему cooldown, а не к независимому продолжению worker-ов;
- добавлены unit tests;
- создан `docs/stage1_tagging_polish_llm_feedback.md`;
- в feedback есть понятные команды для запуска 50 и 200 документов.
## Дополнительная задача 11. Gemini Flash primary experiment

По запросу владельца проекта нужно добавить эксперимент, где базовой моделью первичного тегирования будет Gemini Flash вместо DeepSeek.

Это отдельный experiment-трек. Не превращай Gemini в fallback по умолчанию. Не смешивай Gemini results с DeepSeek active output.

### 11.1. Добавить модели в pricing/config

Добавь в `kb_rebuild/llm/models.py` поддержку модели:

```text
google/gemini-3-flash-preview
```

Ориентировочная стоимость для budget limit:

```text
input:  $0.50 / 1M tokens
output: $3.00 / 1M tokens
```

Также можно оставить уже добавленную или добавить опциональную модель:

```text
google/gemini-3.1-flash-lite-preview
```

Но `google/gemini-3.1-flash-lite-preview` не использовать как default fallback, пока отдельный smoke не подтвердит совместимость structured output.

### 11.2. Добавить experiment isolation

Добавь CLI-параметр:

```text
--experiment-name
```

Если `--experiment-name` задан, все tagging outputs должны писаться не в основной `data/tagging`, а в:

```text
data/experiments/{experiment_name}/tagging/document_tags_raw_active.jsonl
data/experiments/{experiment_name}/tagging/document_tags_raw_history.jsonl
data/experiments/{experiment_name}/tagging/document_tagging_failures_active.jsonl
data/experiments/{experiment_name}/tagging/document_tagging_failures_history.jsonl
data/experiments/{experiment_name}/reports/tagging_report.json
```

Это нужно, чтобы можно было честно сравнить:

```text
deepseek_flash_baseline
gemini_flash_strict
gemini_flash_prompt_json
```

Основной `data/tagging/document_tags_raw_active.jsonl` не должен быть перезаписан Gemini-экспериментом.

### 11.3. Добавить structured output modes

Добавь CLI-параметр:

```text
--structured-output-mode strict|prompt_json
```

Default:

```text
strict
```

#### strict

Использовать текущий строгий OpenRouter JSON Schema payload:

```json
"response_format": {
  "type": "json_schema",
  "json_schema": {
    "name": "document_tagging_batch",
    "strict": true,
    "schema": {}
  }
}
```

И оставить:

```json
"provider": {
  "require_parameters": true
}
```

#### prompt_json

Этот режим нужен только для диагностики Gemini, если strict mode возвращает HTTP 400.

В `prompt_json`:

- не отправлять `response_format=json_schema`;
- можно отправить `response_format={"type":"json_object"}`, только если это подтверждённо принимается route-ом;
- если `json_object` тоже даёт 400, убрать `response_format` полностью;
- prompt должен требовать строго JSON без markdown;
- local schema validation обязательна;
- invalid JSON должен вести к retry/repair;
- в active record и report сохранить `structured_output_mode`.

Важно: `prompt_json` — экспериментальный режим. Он не равен strict structured outputs по надёжности.

### 11.4. Gemini smoke tests

Добавь в feedback результаты команд ниже.

Smoke strict на 3 документах:

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

Если strict проходит, запустить 50 документов:

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

Если 50 документов стабильны, запустить 200 документов:

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

Если strict на 3 документах даёт HTTP 400, выполнить prompt_json smoke:

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

### 11.5. DeepSeek baseline для честного сравнения

Если experiment isolation реализован, желательно прогнать DeepSeek baseline также в experiment directory:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 200 \
  --batch-size 5 \
  --max-inflight 1 \
  --min-request-interval-seconds 5 \
  --model deepseek/deepseek-v4-flash \
  --fallback-model none \
  --experiment-name deepseek_flash_baseline \
  --structured-output-mode strict \
  --max-cost-usd 10 \
  --max-retries 3 \
  --retry-failures \
  --timeout-seconds 300
```

Важно: Gemini и DeepSeek должны сравниваться на одном наборе документов. Для первого сравнения достаточно одинакового `--limit 200`, если порядок `parsed_documents.jsonl` не меняется.

### 11.6. Report fields для эксперимента

В `tagging_report.json` добавь поля:

```json
{
  "experiment_name": "gemini_flash_strict",
  "primary_model_family": "gemini",
  "model": "google/gemini-3-flash-preview",
  "structured_output_mode": "strict",
  "response_format_used": "json_schema | json_object | none",
  "provider_require_parameters": true,
  "http_400_count": 0,
  "http_429_count": 0,
  "http_502_count": 0,
  "structured_output_errors_count": 0
}
```

### 11.7. Критерии успешности Gemini-эксперимента

Gemini Flash может быть рекомендована как новая primary model только если:

- strict mode проходит хотя бы на 50 документах, либо prompt_json mode показывает стабильный valid JSON без ручных repair-циклов;
- 200-document run завершается без массовых 400/429;
- `invalid_json_count = 0` или ниже/не хуже DeepSeek baseline;
- `quote_validation_summary` не хуже DeepSeek baseline;
- suspicious entity type count не хуже DeepSeek baseline;
- средняя latency и общая скорость лучше или сопоставима;
- стоимость приемлема и не ломает дневной бюджет;
- QA создаёт сравнительный отчёт DeepSeek vs Gemini.

Если Gemini даёт лучший semantic quality, но значительно дороже, не переключай default самостоятельно. Зафиксируй результат и передай архитектору.

Если Gemini strict mode даёт 400, а prompt_json даёт нестабильный JSON, оставь DeepSeek primary.

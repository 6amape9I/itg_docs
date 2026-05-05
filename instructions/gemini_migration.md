ТЗ: Миграция LLM-пайплайна с OpenRouter на прямой Google Gemini API
0. Контекст и архитектурное решение

Текущий проект itg_docs решает задачу первичной пересборки медицинской базы знаний. На входе есть documents.csv, после парсинга получаются parsed_documents.jsonl и document_blocks.jsonl. Этап парсинга принят и не требует переработки.

На этапе LLM-тегирования ранее использовался OpenRouter. Эксперименты с DeepSeek показали неприемлемую задержку, нестабильность маршрута и 429/502/503 на provider route. Эксперимент с Gemini через OpenRouter показал, что модель google/gemini-3-flash-preview способна стабильно обслуживать наш объём.

Последний эксперимент на 4000 документов завершился успешно: 4000 документов запрошено, 3993 размечено, 7 failures относятся только к empty_clean_text, успешность по непустым документам — 100%, http_429_count=0, llm_error_count=0, invalid_json_count=3, все invalid JSON случаи восстановлены ретраями. Скорость составила примерно 5371 документов/час, стоимость — около $9.59 за 4000 документов, прогноз на 16 181 документ — около $38.88 и примерно 3 часа при той же скорости.

Архитектурное решение: полностью переводим production LLM-пайплайн с OpenRouter на прямой Google Gemini API. DeepSeek больше не используется как production-модель. OpenRouter-код можно оставить как legacy/baseline, но production tagging, normalization, evidence extraction и article compilation должны уметь работать через gemini_direct.

Google Gemini API поддерживает прямой REST endpoint generateContent, а structured output задаётся через generationConfig.responseMimeType = "application/json" и JSON Schema через generationConfig.responseJsonSchema либо совместимый schema-параметр API. Gemini structured output поддерживает подмножество JSON Schema и генерирует JSON, соответствующий переданной схеме.

Google также предоставляет endpoint models.list, который позволяет программно получить доступные модели и их метаданные, включая token limits и поддерживаемые методы. Поэтому список моделей не должен быть только захардкожен: агент обязан добавить команду discovery и сохранить фактический список моделей, доступный по ключам проекта.

1. Цель этапа

Нужно мигрировать LLM-инфраструктуру проекта на прямой Google Gemini API, сохранив текущую успешную логику batch-тегирования:

batch mode;

active/history split;

LLM cache;

resume;

retry failures;

structured output;

валидация JSON;

валидация цитат;

отчёты по скорости, стоимости, ошибкам и качеству.

После миграции нужно доказать, что direct Gemini API даёт результаты не хуже OpenRouter Gemini на малой выборке и готов к полному прогону корпуса.

2. Не цели этапа

Не нужно переписывать парсер Editor.js.

Не нужно продолжать эксперименты с compact output schema.

Не нужно делать полный production-прогон всего корпуса без smoke/benchmark и проверки архитектором случайной выборки.

Не нужно возвращать DeepSeek как fallback.

Не нужно добавлять внешние медицинские знания.

Не нужно начинать нормализацию тегов до того, как direct Gemini tagging будет принят.

3. Текущий статус репозитория

В проекте уже есть:

kb_rebuild/llm/openrouter_client.py — OpenRouter client, который отправляет запросы в https://openrouter.ai/api/v1/chat/completions, использует Authorization: Bearer ..., OpenRouter-style payload, response_format и provider.require_parameters. Это нужно оставить как legacy, но не использовать в production Gemini-direct режиме.

kb_rebuild/llm/tagging_batch.py — batch runner, который читает parsed_documents.jsonl, делает batch-запросы, использует cache, active/history outputs, split-on-invalid, retry, quote validation и отчёты. Это основа, которую нужно адаптировать под Gemini direct provider.

kb_rebuild/llm/rate_limiter.py — adaptive rate limiter с max_inflight, min_request_interval_seconds, cooldown после 429 и снижением effective concurrency. Для прямого Gemini нужно расширить эту идею до key-aware rate limiting.

kb_rebuild/llm/prompts/tagging_v2.md — текущий prompt v2. Он уже содержит правильные правила: извлекать только основные сущности, не извлекать все слова подряд, не извлекать примеры вскользь, различать drug_trade_name, drug_class, microorganism, cell_or_biological_structure, требовать дословные цитаты и роли article_candidate, folder_candidate, context_only. Его нужно адаптировать под Gemini, но не ломать смысл.

kb_rebuild/llm/schemas/document_tagging_batch_v2.schema.json — текущая verbose batch schema. Она должна остаться основной. Compact schema не использовать в production.

kb_rebuild/llm/models.py — сейчас содержит OpenRouter-style model IDs вроде google/gemini-3-flash-preview. Для прямого Gemini нужны model IDs без OpenRouter-префикса, например gemini-3-flash-preview.

4. Модельная стратегия

Агент должен реализовать модельную стратегию для задач проекта. Список ниже — стартовая архитектурная рекомендация. При запуске discovery-команды агент должен сохранить фактические доступные модели и отметить, какие из них подходят для каждой роли.

Основные кандидаты Google Gemini:

gemini-3-flash-preview — основной production-кандидат для массового тегирования, evidence extraction, folder hierarchy и массового QA. Официальная документация описывает Gemini 3 Flash Preview как модель с 1M input context, 65 536 output token limit, поддержкой structured outputs, batch API, caching и code execution.

gemini-3-pro-preview — модель для сложной нормализации тегов, арбитража спорных кластеров, сложной компиляции статей и выборочного QA. В документации Gemini 3 Pro Preview также указан 1M input context, 65 536 output token limit и поддержка structured outputs.

gemini-2.5-flash-lite — потенциальная дешёвая/быстрая модель для простых массовых задач, если она доступна по ключам и проходит smoke test. Документация описывает Gemini 2.5 Flash-Lite как быстрый Flash-вариант, оптимизированный для cost-efficiency и throughput, с 1M input context и structured outputs.

gemini-2.5-pro — стабильный Pro-кандидат для сложных задач, если gemini-3-pro-preview недоступен, нестабилен или слишком дорог. Документация указывает для Gemini 2.5 Pro 1M input context, 65 536 output token limit и structured outputs.

gemini-2.0-flash — запасной stable Flash-кандидат, если Gemini 3 Flash временно недоступен. Документация указывает для Gemini 2.0 Flash 1M context window и structured outputs.

Ролевое назначение моделей:

TAGGING_PRIMARY:
  preferred: gemini-3-flash-preview
  fallback_if_unavailable: gemini-2.5-flash-lite или gemini-2.0-flash

EVIDENCE_EXTRACTION_PRIMARY:
  preferred: gemini-3-flash-preview
  fallback_if_unavailable: gemini-2.5-flash-lite

TAG_NORMALIZATION_PRIMARY:
  preferred: gemini-3-pro-preview
  fallback_if_unavailable: gemini-2.5-pro
  cheap_candidate_for_easy_clusters: gemini-3-flash-preview

ARTICLE_COMPILATION_PRIMARY:
  preferred_for_complex_articles: gemini-3-pro-preview
  preferred_for_simple_articles: gemini-3-flash-preview
  fallback_if_unavailable: gemini-2.5-pro

FOLDER_HIERARCHY_PRIMARY:
  preferred: gemini-3-flash-preview

QA_AUDIT_PRIMARY:
  mass_checks: gemini-3-flash-preview
  hard_arbitration: gemini-3-pro-preview

Важно: в production-конфиге не использовать latest-алиасы. Preview-модели можно использовать, но model ID должен быть явно записан, например gemini-3-flash-preview. Google documentation описывает stable, preview, latest и experimental version patterns; latest-алиас может быть hot-swapped, поэтому для воспроизводимого пайплайна он нежелателен.

5. Переменные окружения

Агент должен добавить поддержку .env:

GEMINI_KEY_LIST="key1,key2,key3"

Также поддержать одиночный ключ:

GEMINI_API_KEY="key"

Правила:

Если есть GEMINI_KEY_LIST, использовать список ключей.

Если GEMINI_KEY_LIST отсутствует, использовать GEMINI_API_KEY.

Если нет ни одного Gemini-ключа, команда direct Gemini должна завершаться понятной ошибкой.

Ключи нельзя логировать.

Ключи нельзя сохранять в cache, reports, history, manifest.

Форматы GEMINI_KEY_LIST, которые нужно поддержать:

GEMINI_KEY_LIST="key1,key2,key3"
GEMINI_KEY_LIST="key1;key2;key3"
GEMINI_KEY_LIST='["key1", "key2", "key3"]'
6. Новый Gemini direct client

Создать файл:

kb_rebuild/llm/gemini_client.py

Клиент должен уметь:

читать один или несколько ключей;

делать round-robin по ключам;

поддерживать key-aware cooldown;

делать прямой REST-запрос к Google Gemini API;

возвращать унифицированный объект completion, совместимый с batch runner;

извлекать текст ответа;

извлекать usage metadata, если она есть;

логировать latency;

обрабатывать HTTP 400/401/403/429/500/503;

распознавать retryable errors;

распознавать structured-output/schema errors;

не логировать ключи.

Базовый REST endpoint:

https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent

Заголовки:

Content-Type: application/json
x-goog-api-key: <key>

Пример payload для Gemini direct:

{
  "contents": [
    {
      "role": "user",
      "parts": [
        {
          "text": "PROMPT_TEXT_HERE"
        }
      ]
    }
  ],
  "generationConfig": {
    "temperature": 0,
    "maxOutputTokens": 6000,
    "responseMimeType": "application/json",
    "responseJsonSchema": {
      "type": "object",
      "properties": {},
      "required": []
    }
  }
}

Для Gemini structured output использовать именно Gemini-style config, а не OpenRouter-style response_format. В официальных примерах REST structured output задаётся через generationConfig.responseMimeType = "application/json" и generationConfig.responseJsonSchema.

Клиент должен возвращать dataclass, например:

@dataclass(frozen=True)
class GeminiCompletion:
    raw: dict[str, Any]
    content: str
    usage: dict[str, int]
    model: str
    finish_reason: str
    latency_ms: int
    api_key_index: int

usage привести к текущему формату проекта:

{
  "prompt_tokens": 0,
  "completion_tokens": 0,
  "reasoning_tokens": 0
}

Если Gemini возвращает usageMetadata.promptTokenCount, usageMetadata.candidatesTokenCount, usageMetadata.totalTokenCount, использовать их.

Если usage отсутствует, считать cost estimate по приблизительному char-to-token, но помечать usage_source = "estimated".

7. Provider abstraction

Нельзя привязывать batch runner только к OpenRouter или только к Gemini.

Добавить provider abstraction:

kb_rebuild/llm/providers.py

Или минимально:

class LLMClientProtocol(Protocol):
    def generate_json(self, request: LLMRequest) -> LLMCompletion:
        ...

Production CLI должен поддерживать:

--provider gemini_direct

OpenRouter оставить как legacy:

--provider openrouter

Default для tag-batch после миграции:

provider = gemini_direct
model = gemini-3-flash-preview
8. Gemini model discovery

Добавить CLI-команду:

.venv/bin/python -m kb_rebuild gemini-list-models --data data

Команда должна:

прочитать GEMINI_KEY_LIST или GEMINI_API_KEY;

вызвать Gemini models.list;

сохранить raw response:

data/reports/gemini_models.json

сформировать человекочитаемый отчёт:

docs/gemini_available_models.md

В отчёте указать:

name;

baseModelId;

version;

displayName;

description;

inputTokenLimit;

outputTokenLimit;

supportedGenerationMethods;

поддерживает ли модель generateContent;

предполагаемая роль в проекте.

Endpoint models.list официально описан как способ программно получить доступные модели и метаданные, включая поддерживаемые функции и context window sizing.

Пример ожидаемого отчёта:

# Gemini Available Models

Generated at: ...

## Recommended mapping

TAGGING_PRIMARY = gemini-3-flash-preview
NORMALIZATION_PRIMARY = gemini-3-pro-preview
ARTICLE_COMPILATION_PRIMARY = gemini-3-pro-preview
...

## Raw available models

| name | baseModelId | input | output | methods | recommended_role |
|---|---:|---:|---:|---|---|
9. Structured output schema for Gemini

Сохранить verbose-схему document_tagging_batch_v2.

Не использовать compact schema в production.

Создать Gemini-compatible schema builder:

kb_rebuild/llm/gemini_schema.py

Он должен преобразовывать текущую JSON Schema в формат, который принимает Gemini.

Учитывать, что Gemini structured output поддерживает подмножество JSON Schema. Нужно убрать или адаптировать поля, которые могут ломать Gemini API:

$schema;

$id;

кастомные поля вроде schema_version;

слишком сложные additionalProperties;

любые неподдерживаемые конструкции.

Но локальная validation schema должна остаться строгой. То есть:

Gemini получает совместимую schema.

Код после ответа валидирует по нашей строгой локальной schema.

Для Gemini request использовать:

"generationConfig": {
  "responseMimeType": "application/json",
  "responseJsonSchema": { ... }
}

Если responseJsonSchema по какой-то причине не работает у конкретной модели, разрешается fallback mode:

gemini_schema_lite

Но production default должен быть structured output, а не просто prompt-only JSON.

10. Gemini-specific prompt

Создать файл:

kb_rebuild/llm/prompts/tagging_v2_gemini.md

Он должен быть адаптацией текущего tagging_v2.md.

Смысловые правила оставить:

извлекать только основные самостоятельные сущности;

не извлекать все медицинские слова подряд;

не извлекать примеры вскользь;

избегать слишком широких тегов;

drug_trade_name — только торговое название;

drug_class — классы препаратов;

microorganism — микроорганизмы;

cell_or_biological_structure — клеточные структуры и клетки иммунной системы;

biological_substance — биологические вещества;

diagnostic_method — методы диагностики;

операционные инструкции разрешены через instruction, procedure, medical_device;

цитата должна быть непрерывной дословной подстрокой из CLEAN_TEXT;

не добавлять внешние факты.

Усилить совместимость с Gemini:

В prompt не писать “OpenRouter”.

Не писать “JSON Schema будет передана OpenRouter”.

Написать: “Ответ должен соответствовать response schema, переданной через Gemini API”.

Язык ответа — русский, кроме canonical_candidate_latin.

Не просить модель объяснять свои действия вне JSON.

Не просить chain-of-thought.

Не просить markdown.

Сохраняем текущие поля output:

doc_id
entities
surface
canonical_candidate_ru
canonical_candidate_latin
entity_type
article_candidate
tag_role
is_primary
confidence
evidence_quotes
comment

Compact-поля d/e/s/ru/t/r/c/q не использовать.

11. Batch runner migration

Текущий BatchTaggingRunner должен уметь работать с provider=gemini_direct.

Нужно сохранить:

--limit;

--batch-size;

--batch-char-limit;

--prompt-char-limit-per-doc;

--max-output-tokens;

--max-inflight;

--min-request-interval-seconds;

--rate-limit-backoff-seconds;

--max-rate-limit-backoff-seconds;

--max-retries;

--experiment-name;

--retry-failures;

--no-resume;

active/history split;

batch cache;

split-on-invalid;

quote validation;

tagging_report.json;

tagging_active_manifest.json.

Нужно добавить:

--provider gemini_direct
--model gemini-3-flash-preview
--model-role TAGGING_PRIMARY

Пример новой команды:

.venv/bin/python -m kb_rebuild tag-batch \
  --provider gemini_direct \
  --data data \
  --limit 4000 \
  --model gemini-3-flash-preview \
  --schema-version document_tagging_v2 \
  --prompt-version tagging_v2_gemini \
  --batch-size 5 \
  --batch-char-limit 50000 \
  --prompt-char-limit-per-doc 16000 \
  --max-output-tokens 6000 \
  --max-inflight 4 \
  --min-request-interval-seconds 1 \
  --rate-limit-backoff-seconds 120 \
  --max-rate-limit-backoff-seconds 300 \
  --max-retries 3 \
  --max-cost-usd 30 \
  --experiment-name gemini_direct_4000_batch5_inflight4_v1 \
  --retry-failures \
  --timeout-seconds 300
12. Key-aware rate limiting

Сейчас rate limiter глобальный. Для GEMINI_KEY_LIST нужно сделать key-aware limiter.

Требования:

каждый ключ имеет свой cooldown;

если ключ получил 429, этот ключ временно не используется;

остальные ключи продолжают работать;

если все ключи в cooldown, runner ждёт ближайший доступный ключ;

429 должен попадать в report;

ошибки 401/403 по конкретному ключу должны отключать ключ до конца run;

ключи не логировать;

в report показывать только key_index, не сам ключ.

Новые метрики:

{
  "provider": "gemini_direct",
  "gemini_keys_count": 3,
  "gemini_key_stats": {
    "0": {
      "requests": 0,
      "success": 0,
      "errors": 0,
      "http_429": 0,
      "cooldown_events": 0,
      "disabled": false
    }
  }
}
13. Cost model

Обновить kb_rebuild/llm/models.py.

Для direct Gemini model IDs добавить pricing:

GEMINI_3_FLASH_PREVIEW = "gemini-3-flash-preview"
GEMINI_3_PRO_PREVIEW = "gemini-3-pro-preview"
GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
GEMINI_2_5_PRO = "gemini-2.5-pro"
GEMINI_2_0_FLASH = "gemini-2.0-flash"

Pricing для Gemini 3:

gemini-3-flash-preview: $0.50 / 1M input tokens, $3 / 1M output tokens
gemini-3-pro-preview: $2 / 1M input tokens and $12 / 1M output tokens under 200k tokens; $4 / $18 above 200k tokens

Эти цены указаны в Gemini 3 Developer Guide.

Для остальных моделей агент должен либо:

взять актуальные цены из официальной Google pricing page, если есть доступ;

или добавить pricing_status = "unknown" и запретить использовать модель с --max-cost-usd, пока цена не задана;

или оставить только те модели, для которых цена явно задана.

Важно: если модель без pricing используется с budget-limit, команда должна завершаться ошибкой, а не считать стоимость неправильно.

14. Cache compatibility

LLM cache должен учитывать provider.

Cache key должен включать:

{
  "provider": "gemini_direct",
  "model": "gemini-3-flash-preview",
  "prompt_version": "tagging_v2_gemini",
  "schema_version": "document_tagging_batch_v2",
  "structured_output_mode": "gemini_response_json_schema",
  "doc_ids": [],
  "input_hash": "...",
  "request_params": {}
}

Нельзя использовать OpenRouter cache для Gemini direct и наоборот.

В cache record добавить:

{
  "provider": "gemini_direct",
  "model_requested": "gemini-3-flash-preview",
  "model_actual": "models/gemini-3-flash-preview",
  "api_key_index": 0,
  "usage_source": "api|estimated"
}

Ключи не сохранять.

15. Outputs

Для экспериментов использовать:

data/tagging/experiments/{experiment_name}/document_tags_raw_active.jsonl
data/tagging/experiments/{experiment_name}/document_tags_raw_history.jsonl
data/tagging/experiments/{experiment_name}/document_tagging_failures.jsonl
data/tagging/experiments/{experiment_name}/document_tagging_failures_history.jsonl
data/tagging/experiments/{experiment_name}/tagging_report.json
data/tagging/experiments/{experiment_name}/tagging_active_manifest.json

Production active output после принятия direct Gemini можно будет писать в:

data/tagging/document_tags_raw_active.jsonl

Но в этом этапе production alias не обязателен. Главное — experiment isolation.

16. Empty documents policy

Документы с пустым clean_text не отправлять в Gemini.

Считать их input failures, не model failures.

Сохранять в:

document_tagging_failures.jsonl

с причиной:

empty_clean_text

Дополнительно создать файл:

data/tagging/experiments/{experiment_name}/empty_documents_name_candidates.jsonl

Туда записывать:

{
  "doc_id": "...",
  "document_name": "...",
  "reason": "empty_clean_text",
  "suggested_action": "manual_review_or_name_based_tagging_later"
}

Не нужно генерировать теги из name в этом этапе, потому что нет цитат и нельзя валидировать evidence. В 4000-документном эксперименте все 7 failures были именно empty_clean_text, и это допустимый input failure.

17. Quote validation

Сохранить текущую валидацию цитат.

После direct Gemini run report должен содержать:

{
  "quote_summary": {
    "found": 0,
    "normalized_found": 0,
    "fuzzy": 0,
    "not_found": 0
  }
}

Критерий для smoke/benchmark:

not_found <= 1% от всех quote validations;

found + normalized_found + fuzzy >= 99% желательно, но минимум 98%;

если not_found > 1%, не запускать полный корпус без разбора.

В 4000-документном эксперименте not_found составил примерно 0.575%, что допустимо для перехода к большему прогону, но эти случаи нужно отдавать в QA после полного tagging.

18. Context-only policy

Высокая доля context_only не является блокером для tagging.

Но downstream должен использовать роли правильно:

article_candidate = true и tag_role = article_candidate — кандидат на самостоятельный документ-сущность;

folder_candidate — помогает структуре папок и тематической иерархии;

context_only — полезно для графа и связей, но не должно автоматически становиться финальной статьёй.

В report добавить распределение:

{
  "entities_by_role": {
    "article_candidate": 0,
    "folder_candidate": 0,
    "context_only": 0
  }
}

Если context_only > 50% от всех сущностей, это не стоп, но report должен добавить warning:

high_context_only_share
19. Gemini direct smoke tests

После реализации агент обязан выполнить:

19.1 Model discovery
.venv/bin/python -m kb_rebuild gemini-list-models --data data

Ожидаемые артефакты:

data/reports/gemini_models.json
docs/gemini_available_models.md
19.2 Smoke 3 documents
.venv/bin/python -m kb_rebuild tag-batch \
  --provider gemini_direct \
  --data data \
  --limit 3 \
  --model gemini-3-flash-preview \
  --schema-version document_tagging_v2 \
  --prompt-version tagging_v2_gemini \
  --batch-size 1 \
  --max-inflight 1 \
  --structured-output-mode gemini_schema \
  --max-cost-usd 2 \
  --experiment-name gemini_direct_smoke3_v1 \
  --retry-failures \
  --timeout-seconds 300
19.3 Smoke 50 documents
.venv/bin/python -m kb_rebuild tag-batch \
  --provider gemini_direct \
  --data data \
  --limit 50 \
  --model gemini-3-flash-preview \
  --schema-version document_tagging_v2 \
  --prompt-version tagging_v2_gemini \
  --batch-size 5 \
  --max-inflight 2 \
  --structured-output-mode gemini_schema \
  --max-cost-usd 5 \
  --experiment-name gemini_direct_50_batch5_inflight2_v1 \
  --retry-failures \
  --timeout-seconds 300
19.4 Benchmark 4000 documents

Запускать только если 3 и 50 прошли.

.venv/bin/python -m kb_rebuild tag-batch \
  --provider gemini_direct \
  --data data \
  --limit 4000 \
  --model gemini-3-flash-preview \
  --schema-version document_tagging_v2 \
  --prompt-version tagging_v2_gemini \
  --batch-size 5 \
  --batch-char-limit 50000 \
  --prompt-char-limit-per-doc 16000 \
  --max-output-tokens 6000 \
  --max-inflight 4 \
  --min-request-interval-seconds 1 \
  --rate-limit-backoff-seconds 120 \
  --max-rate-limit-backoff-seconds 300 \
  --max-retries 3 \
  --max-cost-usd 30 \
  --experiment-name gemini_direct_4000_batch5_inflight4_v1 \
  --retry-failures \
  --timeout-seconds 300
20. Reports

tagging_report.json должен содержать минимум:

{
  "provider": "gemini_direct",
  "model_requested": "gemini-3-flash-preview",
  "models_used": [],
  "documents_requested": 0,
  "documents_tagged": 0,
  "documents_failed": 0,
  "entities_total": 0,
  "entities_by_type": {},
  "entities_by_role": {},
  "quote_summary": {},
  "estimated_cost_usd": 0,
  "cost_per_document_usd": 0,
  "projected_full_corpus_cost_usd": 0,
  "docs_per_hour": 0,
  "requests_per_hour": 0,
  "wall_clock_seconds": 0,
  "avg_latency_ms": 0,
  "llm_requests_count": 0,
  "llm_success_count": 0,
  "llm_error_count": 0,
  "invalid_json_count": 0,
  "llm_retries_count": 0,
  "http_status_counts": {},
  "rate_limit_count": 0,
  "gemini_keys_count": 0,
  "gemini_key_stats": {},
  "cache_hits": 0,
  "cache_misses": 0,
  "batch_split_count": 0,
  "stop_reason": null,
  "warnings": []
}
21. Tests

Обязательные unit tests:

парсинг GEMINI_KEY_LIST;

Gemini client не логирует ключи;

Gemini request payload содержит generationConfig.responseMimeType = application/json;

Gemini request payload содержит schema;

OpenRouter request builder не используется при provider=gemini_direct;

cache key различает provider=openrouter и provider=gemini_direct;

model ID google/gemini-3-flash-preview не используется в direct Gemini mode;

direct Gemini model ID gemini-3-flash-preview валиден;

key-aware limiter ставит в cooldown только конкретный ключ;

401/403 отключают конкретный ключ;

429 ретраится по другому ключу, если он доступен;

empty clean_text не отправляется в Gemini;

batch output валидируется локальной schema;

quote validation работает после direct Gemini output.

Запуск:

.venv/bin/python -m unittest discover -s tests

Также compile check:

.venv/bin/python -m py_compile \
  kb_rebuild/llm/gemini_client.py \
  kb_rebuild/llm/gemini_schema.py \
  kb_rebuild/llm/tagging_batch.py \
  kb_rebuild/cli.py
22. Acceptance criteria

Этап считается выполненным, если:

Добавлен gemini_direct provider.

Добавлен GeminiClient.

Поддержан GEMINI_KEY_LIST.

Добавлен gemini-list-models.

Созданы data/reports/gemini_models.json и docs/gemini_available_models.md.

Batch tagging работает через direct Gemini API.

Structured output работает через Gemini-style schema.

OpenRouter-style response_format не используется в direct Gemini mode.

tagging_v2_gemini создан.

Verbose schema используется; compact output не используется.

Unit tests проходят.

Smoke 3 документов проходит.

Smoke 50 документов проходит.

Если возможно, benchmark 4000 документов проходит.

В feedback есть сравнение direct Gemini benchmark с OpenRouter Gemini 4000 benchmark.

23. Feedback-файл исполнителя

После работы агент обязан создать:

docs/gemini_direct_api_migration_feedback.md

В feedback указать:

что сделано;

какие файлы изменены;

какие команды запускались;

результаты tests;

результаты model discovery;

результаты smoke 3;

результаты smoke 50;

результаты 4000 benchmark, если запускался;

стоимость;

скорость;

HTTP ошибки;

invalid JSON;

quote validation;

какие модели доступны по ключам;

какая модель выбрана для каждой роли;

что не сделано;

риски;

вопросы архитектору.

24. Важные архитектурные ответы

empty_clean_text считаем допустимым input failure. Не генерируем теги из одного name на этом этапе.

62 not_found цитаты в 4000-прогоне не блокируют миграцию, потому что доля около 0.575%, но после полного прогона нужен отдельный QA список всех not_found.

Высокая доля context_only не блокирует tagging. Но нормализация и сборка статей должны использовать только article_candidate как основной источник будущих документов-сущностей.

Полный корпус запускать только после того, как архитектор посмотрит случайную выборку direct Gemini результатов.

25. Ожидаемая команда полного запуска после принятия миграции

Эту команду не запускать, пока архитектор не примет direct Gemini smoke/benchmark.

.venv/bin/python -m kb_rebuild tag-batch \
  --provider gemini_direct \
  --data data \
  --limit 16181 \
  --model gemini-3-flash-preview \
  --schema-version document_tagging_v2 \
  --prompt-version tagging_v2_gemini \
  --batch-size 5 \
  --batch-char-limit 50000 \
  --prompt-char-limit-per-doc 16000 \
  --max-output-tokens 6000 \
  --max-inflight 4 \
  --min-request-interval-seconds 1 \
  --rate-limit-backoff-seconds 120 \
  --max-rate-limit-backoff-seconds 300 \
  --max-retries 3 \
  --max-cost-usd 80 \
  --experiment-name gemini_direct_full_corpus_batch5_inflight4_v1 \
  --retry-failures \
  --timeout-seconds 300
26. Чеклист агента

Перед началом:

Прочитать это ТЗ.

Прочитать текущие файлы kb_rebuild/llm/openrouter_client.py, tagging_batch.py, rate_limiter.py, models.py, tagging_v2.md, document_tagging_batch_v2.schema.json.

Создать план:

docs/gemini_direct_api_migration_plan.md

Выполнение:

Добавить Gemini direct client.

Добавить provider abstraction.

Добавить Gemini model discovery.

Добавить Gemini model config.

Добавить Gemini schema adapter.

Добавить Gemini prompt.

Интегрировать provider в tag-batch.

Добавить key-aware limiter.

Обновить cache key.

Обновить reports.

Добавить tests.

Запустить tests.

Запустить model discovery.

Запустить smoke 3.

Запустить smoke 50.

По возможности запустить 4000 benchmark.

В конце:

Создать feedback:

docs/gemini_direct_api_migration_feedback.md

Не запускать полный корпус без отдельного разрешения архитектора.
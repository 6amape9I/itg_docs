# Задание для LLM Orchestrator Engineer: token optimization + DeepSeek 429 fallback to Gemini

## Роль

Ты отвечаешь за управляемый LLM-слой тегирования: OpenRouter client, prompt/schema versions, кэш, routing, fallback, batch mode, бюджет, retry и отчётность. Твоя задача — сделать тегирование быстрым и экономичным без ухудшения качества.

## Цель доработки

Нужно реализовать новую версию тегирования, которая:

1. Уменьшает output tokens за счёт compact schema.
2. Поддерживает batch tagging.
3. Позволяет использовать DeepSeek как дешёвый primary, но при HTTP 429 сразу отправляет задачу в Gemini 3 Flash Preview без долгого ожидания.
4. Позволяет использовать Gemini 3 Flash Preview как production primary.
5. Сохраняет active/history outputs так, чтобы downstream не получал дубли и диагностический мусор.

## Модели

Добавить/проверить в model config:

```text
deepseek/deepseek-v4-flash
google/gemini-3-flash-preview
```

Gemini 3 Flash Preview должен поддерживаться как:

- primary model;
- fallback model;
- model in hybrid route.

Не использовать `latest`-алиасы.

## CLI: новые параметры

Добавить или расширить команду `tag` / `tag-batch` так, чтобы были доступны параметры:

```text
--primary-model deepseek/deepseek-v4-flash
--fallback-model google/gemini-3-flash-preview
--routing-strategy single|manual_fallback|openrouter_models
--fallback-on-status 429
--primary-max-retries 0
--fallback-max-retries 2
--primary-cooldown-after-429-seconds 300
--primary-timeout-seconds 20
--fallback-timeout-seconds 300
--schema-version compact_tagging_v2
--prompt-version tagging_v2_compact
--batch-size 5
--max-inflight 1
--experiment-name gemini_first_or_hybrid
```

Минимально рабочие команды:

Gemini primary:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 200 \
  --primary-model google/gemini-3-flash-preview \
  --routing-strategy single \
  --schema-version compact_tagging_v2 \
  --prompt-version tagging_v2_compact \
  --batch-size 5 \
  --max-inflight 1 \
  --max-cost-usd 10 \
  --experiment-name gemini3_flash_compact_b5
```

Hybrid DeepSeek → Gemini:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 200 \
  --primary-model deepseek/deepseek-v4-flash \
  --fallback-model google/gemini-3-flash-preview \
  --routing-strategy manual_fallback \
  --fallback-on-status 429 \
  --primary-max-retries 0 \
  --fallback-max-retries 2 \
  --primary-cooldown-after-429-seconds 300 \
  --primary-timeout-seconds 20 \
  --fallback-timeout-seconds 300 \
  --schema-version compact_tagging_v2 \
  --prompt-version tagging_v2_compact \
  --batch-size 5 \
  --max-inflight 1 \
  --max-cost-usd 10 \
  --experiment-name hybrid_deepseek_gemini_compact_b5
```

## Compact schema v2

Создать JSON Schema `compact_document_tagging.schema.json`.

One-document response:

```json
{
  "d": "doc_000123_abcd1234",
  "e": [
    {
      "s": "surface",
      "ru": "canonical candidate in Russian",
      "t": "entity_type",
      "r": "article",
      "c": 0.93,
      "q": "short exact quote"
    }
  ]
}
```

Batch response:

```json
{
  "docs": [
    {
      "d": "doc_000123_abcd1234",
      "e": []
    }
  ]
}
```

Allowed `r` values:

```text
article
context
folder
```

Interpretation:

- `article` — сущность подходит для будущего самостоятельного документа;
- `context` — важна для понимания документа, но не обязательно нужна как отдельная статья;
- `folder` — слишком широкая сущность, полезная скорее для структуры папок.

Allowed `t` values:

```text
disease
drug_trade_name
drug_class
supplement
immunobiological_preparation
biological_substance
symptom
medical_device
procedure
diagnostic_method
organ_or_body_system
microorganism
cell_or_biological_structure
medical_concept
instruction
other
```

## Expansion layer

После получения compact response код обязан расширить его в текущий downstream-friendly формат.

Правила expansion:

- `d` → `doc_id`;
- `e` → `entities`;
- `s` → `surface`;
- `ru` → `canonical_candidate_ru`;
- `t` → `entity_type`;
- `r` → `tag_role`;
- `c` → `confidence`;
- `q` → `evidence_quotes: [q]`;
- `canonical_candidate_latin` выставить пустой строкой;
- `comment` выставить пустой строкой;
- `is_primary` можно выставить `true` только в expanded compatibility output, но не требовать от модели.

## Prompt v2 compact

Создать новый prompt `tagging_v2_compact.md`.

Требования к prompt:

- не просить модель писать объяснения;
- не просить `comment`;
- не просить латинское название;
- требовать одну короткую точную цитату;
- требовать не извлекать вторичные примеры;
- требовать отличать `drug_trade_name` от `drug_class`;
- требовать помечать широкие сущности как `folder` или `context`, а не как `article`.

Правила цитаты:

```text
q must be a continuous exact substring from the document text.
Do not paraphrase.
Do not join distant fragments.
Do not use ellipsis.
Recommended quote length: 40-180 characters.
If no exact quote exists, do not return the entity.
```

## Input optimization

Добавить функцию построения `tagging_text`.

Параметры:

```text
--tagging-text-mode full|compact
--tagging-char-limit 8000
```

Для `compact`:

- всегда включать document name;
- включать все headers, но ограничить общий объём headers;
- включать первые 6000-8000 символов clean_text;
- для длинных документов добавлять последние 1000-1500 символов;
- сохранять информацию `input_truncated=true/false`;
- не делать LLM-summary перед тегированием.

Нужно протестировать `tagging-char-limit` 4000, 8000, 16000 на одинаковом наборе документов.

## Batch tagging

Реализовать batch mode:

- один batch содержит N документов;
- prompt/schema отправляются один раз на batch;
- response содержит массив результатов по doc_id;
- валидные документы внутри batch сохраняются;
- невалидные документы идут в singleton retry или smaller batch;
- cache key зависит от списка doc_id, input_hashes, prompt_version, schema_version, model routing config и batch_size.

В active output всё равно должна быть одна запись на один документ.

## Manual fallback behavior

При `routing-strategy=manual_fallback`:

1. Отправить задачу в primary model.
2. Если primary вернул HTTP 429:
   - не делать обычный long sleep для этой задачи;
   - немедленно отправить ту же задачу в fallback model;
   - поставить primary model в cooldown на `--primary-cooldown-after-429-seconds`;
   - записать `fallback_reason=primary_http_429`.
3. Пока primary в cooldown, новые задачи сразу идут в fallback model с `fallback_reason=primary_cooldown`.
4. Если fallback получил HTTP 429, применять adaptive cooldown/retry для fallback, потому что это production fast route.
5. Если primary получил timeout по `--primary-timeout-seconds`, допустимо fallback в Gemini с `fallback_reason=primary_timeout`.
6. Если primary дал валидный быстрый ответ, использовать его.

## Optional OpenRouter models routing experiment

Добавить экспериментальный режим `routing-strategy=openrouter_models`, который отправляет в OpenRouter массив models:

```json
{
  "models": [
    "deepseek/deepseek-v4-flash",
    "google/gemini-3-flash-preview"
  ]
}
```

Этот режим нужен только для сравнения. Production default — manual fallback, потому что нам нужна точная диагностика причин fallback и стоимости.

## Active/history outputs

Не смешивать диагностические результаты разных моделей и версий в active файл.

Нужно создать структуру:

```text
data/tagging/experiments/{experiment_name}/document_tags_raw_active.jsonl
data/tagging/experiments/{experiment_name}/document_tagging_failures_active.jsonl
data/tagging/experiments/{experiment_name}/tagging_report.json
```

`document_tags_raw_active.jsonl` должен содержать максимум одну запись на `doc_id`.

Историю можно хранить в cache или отдельном history-файле, но downstream будет читать только active.

## Metrics

В `tagging_report.json` добавить:

```json
{
  "documents_requested": 0,
  "documents_tagged": 0,
  "documents_failed": 0,
  "docs_per_hour": 0,
  "actual_models_used": {},
  "documents_by_actual_model": {},
  "fallback_reasons": {},
  "primary_429_count": 0,
  "fallback_429_count": 0,
  "primary_cooldown_bypass_count": 0,
  "avg_prompt_tokens": 0,
  "avg_completion_tokens": 0,
  "avg_cost_per_document_usd": 0,
  "projected_full_corpus_cost_usd": 0,
  "quote_validation_status_counts": {},
  "invalid_json_count": 0,
  "batch_size": 0,
  "max_inflight": 0
}
```

## Required benchmark runs

1. Current/expanded DeepSeek baseline on already available results: no new API required.
2. Gemini compact one-doc mode on 50 docs.
3. Gemini compact batch size 5 on 200 docs.
4. Hybrid DeepSeek→Gemini compact batch size 5 on 200 docs.
5. Optional OpenRouter `models` routing on 50 docs.

## Acceptance criteria

- `document_tags_raw_active.jsonl` has no duplicate `doc_id`.
- `invalid_json_count = 0` or every invalid doc is retried singleton.
- `not_found` quotes should be <= 5% of entities, or every not_found item must be reported.
- Gemini compact projected full-corpus tagging cost should be lower than non-compact Gemini baseline.
- Hybrid mode must never block for long DeepSeek 429 recovery before sending to Gemini.
- QA can compare quality with previous 42-record baseline.

## Feedback file

At the end write:

```text
docs/token_fallback_llm_orchestrator_feedback.md
```

Include:

- what changed;
- exact commands run;
- benchmark table;
- cost and speed table;
- observed 429 behavior;
- recommendation: Gemini primary, DeepSeek→Gemini hybrid, or DeepSeek disabled.

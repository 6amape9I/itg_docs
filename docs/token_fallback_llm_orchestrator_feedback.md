# Token Fallback LLM Orchestrator Feedback

## Что сделано

- Добавлен Gemini-first route для `google/gemini-3-flash-preview`.
- Добавлены experiment outputs в `data/tagging/experiments/{experiment_name}/`.
- Добавлены schema/prompt v2:
  - `document_tagging_v2`
  - `document_tagging_batch_v2`
  - `compact_tagging_v2`
  - `tagging_v2`
  - `tagging_v2_compact`
- Добавлена compact output schema `d/e/s/ru/t/r/c/q`.
- Добавлен expansion layer: compact response превращается в downstream-friendly records с `doc_id`, `entities`, `canonical_candidate_ru`, `tag_role`, `article_candidate`, `evidence_quotes`.
- Добавлены `strict`, `schema_lite`, `prompt_json` modes. Для Gemini рабочим оказался `schema_lite`.
- Добавлен batch runner с active/history split, batch cache, split-on-invalid и global adaptive limiter.
- Реализован реальный `max_inflight > 1` для batch mode.
- Добавлены throughput metrics: docs/hour, requests/hour, wall clock, HTTP status counts.

## Файлы изменены

- `kb_rebuild/cli.py`
- `kb_rebuild/llm/models.py`
- `kb_rebuild/llm/schema_validation.py`
- `kb_rebuild/llm/tagging.py`
- `kb_rebuild/llm/tagging_batch.py`
- `kb_rebuild/llm/rate_limiter.py`
- `kb_rebuild/llm/prompts/tagging_v2.md`
- `kb_rebuild/llm/prompts/tagging_v2_compact.md`
- `kb_rebuild/llm/schemas/document_tagging_v2.schema.json`
- `kb_rebuild/llm/schemas/document_tagging_batch_v2.schema.json`
- `kb_rebuild/llm/schemas/compact_document_tagging.schema.json`
- `tests/test_llm_orchestrator_contract.py`

## Команды и результаты

Unit tests:

```bash
.venv/bin/python -m unittest discover -s tests
```

Результат: `Ran 36 tests ... OK`.

Gemini strict smoke:

- `gemini_flash_smoke3_strict`
- result: `0 tagged / 3 failed`
- HTTP: `400: 2`

Gemini schema_lite smoke:

- `gemini_flash_smoke3_schema_lite`
- result: `2 tagged / 1 empty_clean_text`
- HTTP errors: `0`
- speed: `553.846 docs/hour`

Gemini schema_lite one-doc 50:

- `gemini_flash_50`
- result: `49 tagged / 1 empty_clean_text`
- HTTP errors: `0`
- speed: `567.203 docs/hour`
- cost: `$0.2684195`

Gemini schema_lite one-doc 200:

- `gemini_flash_200_onedoc`
- result: `197 tagged / 3 empty_clean_text`
- HTTP errors: `0`
- speed: `693.255 docs/hour`
- cost: `$0.800502`

Gemini schema_lite batch5 max_inflight=1:

- `gemini_flash_200_batch5`
- result: `197 tagged / 3 empty_clean_text`
- HTTP errors: `0`
- speed: `1151.299 docs/hour`
- cost: `$0.5564895`

Gemini schema_lite batch5 max_inflight=2:

- `gemini_flash_200_batch5_inflight2_live`
- result: `197 tagged / 3 empty_clean_text`
- HTTP errors: `0`
- speed: `1992.135 docs/hour`
- cost: `$0.5534675`

Gemini schema_lite batch5 max_inflight=4:

- `gemini_flash_200_batch5_inflight4_live`
- result: `197 tagged / 3 empty_clean_text`
- HTTP errors: `0`
- speed: `4488.608 docs/hour`
- cost: `$0.5592565`

Gemini compact schema_lite smoke:

- `gemini_compact_smoke3`
- result: `2 tagged / 1 empty_clean_text`
- HTTP errors: `0`
- compact response expanded successfully

Gemini compact schema_lite batch5 max_inflight=4:

- `gemini_compact_200_batch5_inflight4`
- result: `197 tagged / 3 empty_clean_text`
- HTTP errors: `0`
- speed: `3674.611 docs/hour`
- cost: `$0.659101`
- `invalid_json_count=21`, recovered via retry/split; final active failures are only empty documents.

## Benchmark table

| Experiment | Mode | Docs/hour | Cost | HTTP errors | Notes |
|---|---:|---:|---:|---:|---|
| `gemini_flash_200_onedoc` | verbose one-doc | 693 | $0.8005 | 0 | stable |
| `gemini_flash_200_batch5` | verbose batch5 x1 | 1151 | $0.5565 | 0 | stable |
| `gemini_flash_200_batch5_inflight2_live` | verbose batch5 x2 | 1992 | $0.5535 | 0 | stable |
| `gemini_flash_200_batch5_inflight4_live` | verbose batch5 x4 | 4489 | $0.5593 | 0 | stable |
| `gemini_compact_200_batch5_inflight4` | compact batch5 x4 | 3675 | $0.6591 | 0 | many recovered invalid batch responses |

## Вывод по новой compact schema

Compact schema работает технически: модель возвращает `docs/d/e/s/ru/t/r/c/q`, local validation проходит, active output расширяется в совместимый формат.

Но текущий `tagging_v2_compact` извлекает больше сущностей и чаще требует retry/split, поэтому на 200 документах compact оказался дороже verbose batch5. Это не провал схемы, но prompt надо ужать: меньше `context`, меньше вторичных сущностей, возможно ниже `max_output_tokens` и более жёсткое ограничение числа entities.

## 429/400/502

- Gemini strict structured output дал HTTP 400.
- Gemini schema_lite на 3/50/200 docs дал 0 HTTP 429/400/502.
- Gemini batch parallel до `max_inflight=4` дал 0 HTTP 429.
- Старый DeepSeek batch, запущенный до Gemini-first смены курса, завершился с HTTP `429`, `502`, `503`; его результаты не следует использовать для downstream.

## Рекомендация

На текущих данных Gemini 3 Flash можно считать primary candidate.

Лучший рабочий режим сейчас:

```bash
.venv/bin/python -m kb_rebuild tag-batch \
  --data data \
  --limit 200 \
  --primary-model google/gemini-3-flash-preview \
  --fallback-model google/gemini-3-flash-preview \
  --schema-version document_tagging_v2 \
  --prompt-version tagging_v2 \
  --structured-output-mode schema_lite \
  --batch-size 5 \
  --max-inflight 4 \
  --max-cost-usd 10 \
  --experiment-name gemini_flash_200_batch5_inflight4_live \
  --retry-failures \
  --timeout-seconds 300
```

Projected full-corpus cost from verbose batch5 x4: about `$45-50` for 16,181 documents. Projected speed at observed rate: about `3.6 hours` for the corpus, before QA and retries.

## Что осталось

- Manual fallback DeepSeek→Gemini is only partially represented in CLI/config; full primary-cooldown bypass logic still needs implementation before using hybrid as production route.
- Compact prompt needs another polish pass before it can be considered cheaper than verbose.
- Need QA audit of entity quality, especially high `context_only` volume and compact-vs-verbose entity count.

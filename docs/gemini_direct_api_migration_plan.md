# План миграции на Gemini Direct API

Дата: 2026-05-05

Роль: LLM Orchestrator Engineer

## Что понял

Production LLM-путь нужно перевести с OpenRouter/DeepSeek на прямой Google Gemini API. OpenRouter остаётся legacy/baseline, но `tag-batch` по умолчанию должен уметь работать через `provider=gemini_direct` с моделью `gemini-3-flash-preview`, Gemini-style structured output, кэшем, ретраями, active/history outputs и прежней локальной валидацией.

DeepSeek не должен быть production fallback. Compact output schema не используется для нового production-пути.

## Артефакты

Планируемые новые артефакты:

- `kb_rebuild/llm/gemini_client.py`
- `kb_rebuild/llm/gemini_schema.py`
- `kb_rebuild/llm/providers.py`
- `kb_rebuild/llm/prompts/tagging_v2_gemini.md`
- `docs/gemini_direct_api_migration_plan.md`
- `docs/gemini_direct_api_migration_feedback.md`
- после discovery: `data/reports/gemini_models.json`
- после discovery: `docs/gemini_available_models.md`

## Планируемые изменения

- `kb_rebuild/cli.py`: добавить `--provider`, `--model-role`, `gemini-list-models`, выбор клиента по provider.
- `kb_rebuild/llm/models.py`: добавить direct Gemini model IDs, pricing и модельные роли.
- `kb_rebuild/llm/cache.py`: включить provider в cache key.
- `kb_rebuild/llm/tagging_batch.py`: добавить provider-aware request builder, Gemini payload, Gemini cache metadata, empty-doc candidates, новые report поля.
- `kb_rebuild/llm/rate_limiter.py`: оставить глобальный limiter для OpenRouter и добавить совместимость с provider errors.
- `tests/test_llm_orchestrator_contract.py`: добавить обязательные unit tests по Gemini direct.

## Допущения

- One-doc legacy `tag` остаётся OpenRouter-oriented; production migration делается для batch tagging, как основного принятого пути.
- Direct Gemini получает один user content, где system prompt и documents объединены в один текст. Это ближе к REST `generateContent` и не использует OpenRouter `response_format`.
- Если model discovery или smoke упрутся в сетевой доступ, код и unit tests всё равно должны быть готовы; результат будет зафиксирован в feedback.

## Риски

- Gemini может не принять строгую JSON Schema с некоторыми ключевыми словами, поэтому нужен adapter и fallback `gemini_schema_lite`.
- Стоимости заданы только для моделей, где цена указана в ТЗ. Модели без pricing нельзя использовать с бюджетным лимитом.
- Реальный smoke зависит от доступности ключей и сетевого доступа в окружении.

## Чеклист

- [x] Добавить Gemini direct client.
- [x] Добавить provider abstraction.
- [x] Добавить Gemini schema adapter.
- [x] Добавить Gemini prompt.
- [x] Обновить модели/pricing/roles.
- [x] Обновить batch runner под `gemini_direct`.
- [x] Добавить discovery-команду.
- [x] Добавить/обновить unit tests.
- [x] Запустить compile check.
- [x] Запустить unittest.
- [x] Запустить model discovery.
- [x] Запустить smoke 3.
- [x] Запустить smoke 50, если smoke 3 прошёл.
- [x] Запустить benchmark 200 вместо 4000 по команде архитектора.
- [x] Создать feedback-файл.

# Token Fallback LLM Orchestrator Plan

## Что понял

Нужно перейти от verbose schema v2 к compact schema, чтобы снизить output tokens и стоимость, сохранив совместимость downstream через expansion layer. Gemini 3 Flash остаётся production primary candidate, но также нужен hybrid route: дешёвый DeepSeek primary, а при 429/timeout немедленный fallback в Gemini без долгого ожидания.

## Артефакты

- `kb_rebuild/llm/schemas/compact_document_tagging.schema.json`
- `kb_rebuild/llm/prompts/tagging_v2_compact.md`
- experiment outputs в `data/tagging/experiments/{experiment_name}/`
- `docs/token_fallback_llm_orchestrator_feedback.md`

## Файлы для изменения

- `kb_rebuild/llm/schema_validation.py`
- `kb_rebuild/llm/tagging_batch.py`
- `kb_rebuild/llm/models.py`
- `kb_rebuild/cli.py`
- `tests/test_llm_orchestrator_contract.py`

## CLI

- `--primary-model`
- `--routing-strategy single|manual_fallback|openrouter_models`
- `--fallback-on-status 429`
- `--primary-max-retries`
- `--fallback-max-retries`
- `--primary-cooldown-after-429-seconds`
- `--primary-timeout-seconds`
- `--fallback-timeout-seconds`
- `--schema-version compact_tagging_v2`
- `--prompt-version tagging_v2_compact`
- `--tagging-text-mode full|compact`
- `--tagging-char-limit`

## Проверка

- Unit tests for compact schema validation and expansion.
- Gemini compact smoke/50.
- Gemini compact batch5 200.
- Hybrid DeepSeek→Gemini compact batch5 200 if time/provider allow.

## Риски

- Compact prompt может ухудшить качество тегов из-за отсутствия comment/latin; это должно оценить QA.
- Hybrid DeepSeek still may be slow on timeout if primary timeout is too high; default should be low for hybrid.
- Need active output to remain expanded and downstream-friendly even when raw cache response is compact.

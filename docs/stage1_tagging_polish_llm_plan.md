# Stage 1 Tagging Polish LLM Plan

Superseded by `docs/gemini_first_llm_orchestrator_plan.md` after the Gemini-first architectural decision.

## Что понял

Нужно стабилизировать первичное LLM-тегирование перед масштабированием: отделить active output от истории, перейти на schema/prompt v2, добавить batch-запросы, общий adaptive rate limiter, расширенную отчётность по API attempts и сделать Gemini отдельным experiment-треком, а не fallback по умолчанию.

Production-прогон на весь корпус запрещён. Проверки должны быть ограничены unit tests и малым calibration run.

## Артефакты

- `data/tagging/document_tags_raw_active.jsonl`
- `data/tagging/document_tagging_failures_active.jsonl`
- `data/tagging/tagging_active_manifest.json`
- `data/tagging/document_tags_raw.jsonl` как active-only alias
- `data/reports/tagging_report.json`
- experiment outputs в `data/experiments/{experiment_name}/...`
- новые schema/prompt файлы v2

## Файлы для изменения

- `kb_rebuild/cli.py`
- `kb_rebuild/llm/models.py`
- `kb_rebuild/llm/schema_validation.py`
- `kb_rebuild/llm/tagging.py`
- `kb_rebuild/llm/rate_limiter.py`
- `kb_rebuild/llm/prompts/tagging_v2.md`
- `kb_rebuild/llm/schemas/document_tagging_v2.schema.json`
- `kb_rebuild/llm/schemas/document_tagging_batch_v2.schema.json`
- `tests/test_llm_orchestrator_contract.py`
- `docs/stage1_tagging_polish_llm_feedback.md`

## Новые CLI/флаги

- новая команда `tag-batch`
- `--batch-size`
- `--batch-char-limit`
- `--prompt-char-limit-per-doc`
- `--max-inflight`
- `--min-request-interval-seconds`
- `--max-rate-limit-backoff-seconds`
- `--experiment-name`
- `--structured-output-mode strict|prompt_json`
- `--fallback-model none`

## Версии

- prompt: `tagging_v2`
- single schema: `document_tagging_v2`
- batch schema: `document_tagging_batch_v2`

## Риски

- Live OpenRouter может снова вернуть 429/502/timeout; это должно попасть в report/failures, а не ломать процесс.
- Batch JSON может быть невалидным; нужно split-поведение, чтобы не терять весь batch.
- `prompt_json` для Gemini менее надёжен, поэтому помечается отдельно.
- Старые mixed outputs нельзя использовать как active source.

## Чеклист

- [ ] Добавить schema/prompt v2.
- [ ] Расширить schema validation для `tag_role` и batch response.
- [ ] Добавить global rate limiter.
- [ ] Добавить batch runner и `tag-batch`.
- [ ] Реализовать active/history output split и manifest.
- [ ] Отключить Gemini fallback по умолчанию.
- [ ] Добавить experiment isolation и structured output modes.
- [ ] Обновить quote validation.
- [ ] Расширить report.
- [ ] Добавить unit tests.
- [ ] Запустить unit tests и compile check.
- [ ] Выполнить малый live calibration, если сеть/provider позволяют.
- [ ] Создать feedback.

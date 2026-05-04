# Gemini First LLM Orchestrator Plan

## Что понял

DeepSeek V4 Flash больше не рассматривается как основной production route для тегирования из-за скорости и 429. Новый основной кандидат — `google/gemini-3-flash-preview`. DeepSeek остаётся доступным как baseline/reference.

Нужно довести текущий controlled LLM layer до Gemini-first benchmark: isolated experiment outputs, active/history split, schema/prompt v2, structured-output modes `strict`, `schema_lite`, `prompt_json`, one-doc и batch benchmark, throughput/cost/HTTP diagnostics.

## Артефакты

- `data/tagging/experiments/{experiment_name}/document_tags_raw_active.jsonl`
- `data/tagging/experiments/{experiment_name}/document_tags_raw_history.jsonl`
- `data/tagging/experiments/{experiment_name}/document_tagging_failures.jsonl`
- `data/tagging/experiments/{experiment_name}/document_tagging_failures_history.jsonl`
- `data/tagging/experiments/{experiment_name}/tagging_report.json`
- `data/tagging/experiments/{experiment_name}/tagging_active_manifest.json`
- `docs/gemini_first_llm_orchestrator_feedback.md`

## Файлы для изменения

- `kb_rebuild/llm/models.py`
- `kb_rebuild/llm/schema_validation.py`
- `kb_rebuild/llm/tagging.py`
- `kb_rebuild/llm/tagging_batch.py`
- `kb_rebuild/llm/rate_limiter.py`
- `kb_rebuild/llm/prompts/tagging_v2.md`
- `kb_rebuild/llm/schemas/document_tagging_v2.schema.json`
- `kb_rebuild/llm/schemas/document_tagging_batch_v2.schema.json`
- `kb_rebuild/cli.py`
- `tests/test_llm_orchestrator_contract.py`

## CLI

- `--model-preset deepseek-flash|gemini-flash`
- `--experiment-name`
- `--structured-output-mode strict|schema_lite|prompt_json`
- `tag` with `--experiment-name` runs one-doc v2 Gemini-first path through the batch runner with `batch_size=1`.
- `tag-batch` runs batch v2 path.

## Проверка

- Unit tests: `.venv/bin/python -m unittest discover -s tests`
- Compile check on changed modules.
- Gemini smoke 3 docs in strict, fallback to `schema_lite` then `prompt_json` if strict returns HTTP 400.
- If smoke is stable, run 50-doc Gemini calibration. 200-doc benchmark only if timing/provider behaviour is practical inside the current session.

## Риски

- Gemini strict schema may return HTTP 400; `schema_lite` and `prompt_json` are fallback modes for benchmark.
- Batch outputs may be slower or larger than expected; singleton split must prevent one bad document from losing the whole batch.
- The previous interrupted DeepSeek calibration may finish later; its output is old-path DeepSeek diagnostic and must not be treated as Gemini active output.

## Чеклист

- [ ] Add Gemini model constant and preset.
- [ ] Add `article_candidate` to schema/prompt v2.
- [ ] Add `schema_lite`.
- [ ] Route `tag --experiment-name` to one-doc v2 runner.
- [ ] Move experiment output paths under `data/tagging/experiments`.
- [ ] Add throughput and HTTP diagnostics.
- [ ] Update tests.
- [ ] Run tests/compile.
- [ ] Run Gemini smoke and document best structured-output mode.
- [ ] Create feedback.

# Article A4 Feedback

## What Was Done

- Implemented A4 article compilation package under `kb_rebuild/articles/a4/`.
- Added representative task selection from A3 `a4_compilation_input.jsonl`.
- Added Russian article compilation prompt and Gemini structured-output schema.
- Added local validation for task/tag matching, Editor.js blocks, source fact group IDs, review flag preservation, unknown fact IDs, title sanity, and retry/split failure handling.
- Added A4 runner with LLM cache/resume, budget guard, compiled article file output, reports, diagnostics, manual QA sample, and explicit no-production/no-limit refusal.
- Added CLI command `article-a4-compile`.
- Fixed `kb_rebuild/llm/gemini_schema.py` so property names such as `title` are preserved inside `properties` when adapting schemas for Gemini.

## Files Changed

- `docs/article_a4_plan.md`
- `docs/article_a4_feedback.md`
- `kb_rebuild/cli.py`
- `kb_rebuild/llm/gemini_schema.py`
- `kb_rebuild/articles/a4/__init__.py`
- `kb_rebuild/articles/a4/models.py`
- `kb_rebuild/articles/a4/task_builder.py`
- `kb_rebuild/articles/a4/prompt.py`
- `kb_rebuild/articles/a4/prompts/article_compile_v1.md`
- `kb_rebuild/articles/a4/schema.py`
- `kb_rebuild/articles/a4/validation.py`
- `kb_rebuild/articles/a4/report.py`
- `kb_rebuild/articles/a4/runner.py`
- `tests/test_article_a4_task_builder.py`
- `tests/test_article_a4_schema.py`
- `tests/test_article_a4_validation.py`
- `tests/test_article_a4_runner.py`
- `tests/test_article_a4_report.py`

## Commands Run

```bash
.venv/bin/python -m py_compile kb_rebuild/articles/a4/models.py kb_rebuild/articles/a4/task_builder.py kb_rebuild/articles/a4/prompt.py kb_rebuild/articles/a4/schema.py kb_rebuild/articles/a4/validation.py kb_rebuild/articles/a4/runner.py kb_rebuild/articles/a4/report.py kb_rebuild/cli.py
.venv/bin/python -m unittest tests.test_article_a4_task_builder tests.test_article_a4_schema tests.test_article_a4_validation tests.test_article_a4_runner tests.test_article_a4_report
.venv/bin/python -m unittest discover -s tests
```

Smoke commands were run exactly as allowed by the A4 instruction:

```bash
.venv/bin/python -m kb_rebuild article-a4-compile --data data --a3-dir data/articles/a3 --a1-dir data/articles/a1 --entities-dir data/articles/entities --normalization-final-dir data/normalization/final --out data/articles/a4/experiments/smoke_50 --provider gemini_direct --model gemini-3-flash-preview --structured-output-mode gemini_schema --limit 50 --max-tags-per-batch 1 --max-fact-groups-per-tag 80 --max-quotes-per-tag 120 --batch-char-limit 70000 --max-inflight 4 --max-retries 3 --max-output-tokens 16000 --repair-max-output-tokens 32000 --thinking-level minimal --max-cost-usd 10 --experiment-name smoke_50 --no-resume
.venv/bin/python -m kb_rebuild article-a4-compile --data data --a3-dir data/articles/a3 --a1-dir data/articles/a1 --entities-dir data/articles/entities --normalization-final-dir data/normalization/final --out data/articles/a4/experiments/smoke_200 --provider gemini_direct --model gemini-3-flash-preview --structured-output-mode gemini_schema --limit 200 --max-tags-per-batch 2 --max-fact-groups-per-tag 80 --max-quotes-per-tag 120 --batch-char-limit 70000 --max-inflight 8 --max-retries 3 --max-output-tokens 16000 --repair-max-output-tokens 32000 --thinking-level minimal --max-cost-usd 20 --experiment-name smoke_200
```

## Tests Passed

- A4 unit tests: 26 tests OK after the Gemini schema adapter regression test was added.
- Full suite: 279 tests OK.
- Compile check: passed.

## Smoke 50 Result

Final successful run:

- `tasks_processed`: 50
- `article_drafts_total`: 50
- `compiled_articles`: 25
- `compiled_with_review_flag`: 25
- `tasks_failed`: 0
- `invalid_json_count`: 0
- `schema_validation_failures`: 1, recovered by retry
- `requests`: 51
- `estimated_cost_usd`: 0.721122
- `avg_latency_ms`: 13309
- `quality.passed`: true
- Output: `data/articles/a4/experiments/smoke_50/`

First smoke 50 attempt failed with 50 Gemini HTTP 400 responses because the Gemini schema adapter dropped the `title` property name. The adapter was fixed and the smoke was rerun successfully.

## Smoke 200 Result

- `tasks_processed`: 200
- `article_drafts_total`: 200
- `compiled_articles`: 100
- `compiled_with_review_flag`: 100
- `tasks_failed`: 0
- `invalid_json_count`: 0
- `schema_validation_failures`: 4, recovered by retries
- `requests`: 126
- `estimated_cost_usd`: 2.12008
- `avg_latency_ms`: 16385
- `quality.passed`: true
- Output: `data/articles/a4/experiments/smoke_200/`

## Production Run

Production A4 не запускался. Для production требуется отдельное одобрение архитектора.

## Output Checks

- Smoke 50 compiled article files: 50
- Smoke 200 compiled article files: 200
- Smoke 200 failures: 0
- Smoke 200 quality issues: 0
- Smoke 200 review rows: 100
- Manual QA sample: `data/articles/a4/experiments/smoke_200/manual_qa_articles_sample.csv`
- Quality diagnostics: `data/articles/a4/experiments/smoke_200/article_quality_diagnostics.json`
- Cost/latency report: `data/articles/a4/experiments/smoke_200/cost_latency_report.json`

## Examples

Compiled article examples:

- `data/articles/a4/experiments/smoke_200/compiled_articles/microorganism/microorganism_b9a8e300f9.json`
- `data/articles/a4/experiments/smoke_200/compiled_articles/supplement/supplement_2dd72d45e5.json`

Review-flag article examples:

- `data/articles/a4/experiments/smoke_200/compiled_articles/disease/disease_86c38e6f84.json`
- `data/articles/a4/experiments/smoke_200/compiled_articles/disease/disease_6e41c182d5.json`
- `data/articles/a4/experiments/smoke_200/compiled_articles/disease/disease_246e1472bc.json`

Failure examples:

- Final smoke 50 failures: none.
- Final smoke 200 failures: none.
- Recovered invalid responses were caused by missing source IDs on a content block or by cited IDs omitted from `used_fact_group_ids`; retries repaired them.

## Quality Diagnostics

Smoke 200 quality flags:

- `all_processed_tasks_have_result`: true
- `all_compiled_article_files_exist`: true
- `all_compiled_articles_have_editorjs`: true
- `all_content_blocks_have_source_fact_group_ids`: true
- `no_unknown_fact_group_ids_used`: true
- `review_flags_preserved`: true
- `passed`: true

## Risks

- Local validation enforces source metadata, not full semantic fact-checking of every sentence.
- The model sometimes omits a block source or forgets to include a cited ID in `used_fact_group_ids`; retries recovered all such cases in smoke 200.
- Some articles are long and may need product/editorial QA before production publication.
- Production scale may expose more schema repair cases, so production should keep retries and diagnostics enabled.

## Architect Approval Needed Before Production

- Explicit approval to run `data/articles/a4/production_v1`.
- Final production parameters: `max_inflight`, budget, retry policy, resume behavior.
- Acceptance of recovered schema validation failures as non-blocking when final outputs pass quality gates.
- Manual review of the smoke QA sample before approving production.

ТЗ перечитано на этапах: after_plan, after_task_builder, after_schema, after_validation, after_runner, after_tests, before_smoke_50, before_smoke_200, before_feedback

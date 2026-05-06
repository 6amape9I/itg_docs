# Article A4 Production Feedback

## A4.1 Changes

- Added `A4Config.allow_production: bool = False`.
- Added CLI flag `--allow-production`.
- Updated A4 config validation:
  - no-limit A4 runs require `allow_production=true`;
  - production output paths require `allow_production=true`;
  - smoke runs with explicit `--limit` continue to work without the production flag.
- Added `allow_production` to `a4_manifest.json` config.
- Fixed production resume semantics:
  - `--retry-failures` now still skips successful completed tags;
  - cumulative resume keeps previous successful drafts/tasks instead of overwriting JSONL with only the next slice;
  - resumed task and batch IDs continue after previous outputs;
  - duplicate tag rows in existing resumed outputs are deduped by `tag_id`.

## Tests

Commands:

```bash
.venv/bin/python -m unittest tests.test_article_a4_task_builder tests.test_article_a4_runner
.venv/bin/python -m unittest discover -s tests
```

Result:

- A4 task builder + runner tests: 14 OK.
- Full suite: 283 OK.

Added coverage:

- production/no-limit without `--allow-production` is forbidden;
- production/no-limit with `--allow-production` is allowed;
- smoke-style limits 50 and 200 still work without `--allow-production`;
- resume keeps cumulative outputs and unique task IDs;
- `--retry-failures` resume still skips successful completed tags.

## Production Checkpoint 1000

Command:

```bash
.venv/bin/python -m kb_rebuild article-a4-compile --data data --a3-dir data/articles/a3 --a1-dir data/articles/a1 --entities-dir data/articles/entities --normalization-final-dir data/normalization/final --out data/articles/a4/production_v1 --provider gemini_direct --model gemini-3-flash-preview --structured-output-mode gemini_schema --limit 1000 --max-tags-per-batch 2 --max-fact-groups-per-tag 80 --max-quotes-per-tag 120 --batch-char-limit 70000 --max-inflight 16 --max-retries 3 --max-output-tokens 16000 --repair-max-output-tokens 32000 --thinking-level minimal --max-cost-usd 25 --retry-failures --experiment-name production_v1 --allow-production
```

Result:

- `tasks_processed`: 1000
- `article_drafts_total`: 1000
- `compiled_articles`: 500
- `compiled_with_review_flag`: 500
- `tasks_failed`: 0
- `article_quality_issues`: 0
- `invalid_json_count`: 0
- `schema_validation_failures`: 7, recovered
- `http_status_counts`: {}
- `estimated_cost_usd`: 7.792503
- `quality.passed`: true

Checkpoint criteria passed, so production was continued with resume.

## Full Production

Command:

```bash
.venv/bin/python -m kb_rebuild article-a4-compile --data data --a3-dir data/articles/a3 --a1-dir data/articles/a1 --entities-dir data/articles/entities --normalization-final-dir data/normalization/final --out data/articles/a4/production_v1 --provider gemini_direct --model gemini-3-flash-preview --structured-output-mode gemini_schema --max-tags-per-batch 2 --max-fact-groups-per-tag 80 --max-quotes-per-tag 120 --batch-char-limit 70000 --max-inflight 32 --max-retries 3 --max-output-tokens 16000 --repair-max-output-tokens 32000 --thinking-level minimal --max-cost-usd 150 --retry-failures --experiment-name production_v1 --allow-production
```

Final result after cumulative resume repair:

- `tasks_requested`: 9748
- `tasks_processed`: 9748
- `article_drafts_total`: 9748
- `compiled_articles`: 2960
- `compiled_with_review_flag`: 6788
- `tasks_failed`: 0
- `article_quality_issues`: 0
- `invalid_json_count`: 1, recovered
- `schema_validation_failures`: 49, recovered
- `http_status_counts`: {}
- `requests`: 5540
- `estimated_cost_usd`: 54.6445985
- `avg_latency_ms`: 10912
- `quality.passed`: true

One `compile_from_fact_groups` article was promoted by the model to `compiled_with_review_flag`:

- `drug_trade_name_f4cf6c9e17` / `Моноприл`: reason says dosage conflict between 10 mg and 11 mg requires checking.

## Output Checks

- `data/articles/a4/production_v1/article_drafts.jsonl`: 9748 rows
- `data/articles/a4/production_v1/article_compilation_tasks.jsonl`: 9748 rows
- compiled article files: 9748
- duplicate `tag_id` in drafts/tasks: 0
- duplicate `task_id` in drafts/tasks: 0
- failures: 0
- quality issues: 0
- review queue rows: 6788
- invalid LLM response records: 49, all recovered

Primary artifacts:

- `data/articles/a4/production_v1/a4_report.json`
- `data/articles/a4/production_v1/a4_manifest.json`
- `data/articles/a4/production_v1/article_drafts.jsonl`
- `data/articles/a4/production_v1/manual_qa_articles_sample.csv`
- `data/articles/a4/production_v1/article_quality_diagnostics.json`
- `data/articles/a4/production_v1/cost_latency_report.json`

## Notes

- An initial production command before CLI pass-through was fixed failed before any LLM work because `allow_production` was not passed to `A4Config`.
- The first full no-limit resume reprocessed the checkpoint successes because `--retry-failures` was incorrectly interpreted as retrying successes too. Code was fixed and production output was repaired by a no-new-LLM resume rewrite to 9748 unique tags.
- Final report and JSONL artifacts are cumulative and deduplicated.

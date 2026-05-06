# Article A4 Plan

## What I Understood

A4 compiles article drafts from A3 fact groups into Editor.js-compatible JSON. It may call the LLM only for smoke runs. It must not run production, must not mutate A1/A2/A3 or entity JSON artifacts, and must preserve review flags from A3.

Only tags with `a4_strategy in {compile_from_fact_groups, compile_with_review_flag}` and `ready_for_a4=true` get LLM compilation tasks. Direct-copy, stub-only, review-stub, and insufficient-evidence tags are represented as statuses only and are not compiled as normal articles.

## Inputs

Required inputs:

- `data/articles/a3/a4_compilation_input.jsonl`
- `data/articles/a3/fact_groups.jsonl`
- `data/articles/a3/tag_fact_group_index.jsonl`
- `data/articles/a3/a3_report.json`
- `data/articles/a3/a3_manifest.json`
- `data/articles/a1/article_status_index.jsonl`
- `data/articles/a1/a1_report.json`
- `data/articles/a1/a1_manifest.json`
- `data/articles/entities/`
- `data/normalization/final/tags_canonical.csv`
- `data/normalization/final/tag_aliases.csv`

## Outputs

Smoke outputs only:

- `data/articles/a4/experiments/smoke_50/`
- `data/articles/a4/experiments/smoke_200/`

Each run writes tasks, batches, article drafts, status updates, compiled article JSON files, failures/review/invalid/quality outputs, CSVs, report, manifest, diagnostics, and smoke-specific report.

## Task Builder Design

- Read A3 `a4_compilation_input.jsonl` and `fact_groups.jsonl`.
- Select only ready `compile_from_fact_groups` and `compile_with_review_flag` rows.
- Smoke selection is representative: balance strategy and entity type, include high-volume tags, and avoid direct/stub/review/insufficient-evidence rows.
- Rank fact groups by core/supporting, importance, fact type priority, exact quote, confidence, source count, then concise text.
- Apply `max_fact_groups_per_tag`, `max_quotes_per_tag`, and soft fact-type caps.
- Preserve excluded fact group IDs in task metadata.

## Prompt/Schema Design

- Prompt is Russian and instructs the model to write only from supplied fact groups.
- Structured output is strict JSON with Editor.js-compatible `content.blocks`.
- Each non-header block must cite `source_fact_group_ids`.
- Output must include article status, used/unused fact group IDs, review flags, confidence, and reason.

## Validation Rules

- Response `task_id` and `tag_id` must match task.
- Article status must be allowed.
- Editor.js content must have non-empty blocks.
- Header blocks may have no source IDs; paragraph/list/table blocks must have valid source IDs.
- No unknown fact group IDs may be cited.
- Review flags must be preserved or extended.
- Empty titles, empty headers, empty paragraphs/lists/tables fail validation.

## Smoke Selection Strategy

- `smoke_50`: include both compile strategies, mixed entity types, high-volume tags where possible.
- `smoke_200`: broader balanced selection with high-volume, review-flag, short/simple, and long/multi-source tags.
- No production run and no `--limit 4000`.

## Tests

Add tests for:

- task builder;
- schema;
- validation;
- runner;
- report.

Run:

```bash
.venv/bin/python -m py_compile kb_rebuild/articles/a4/models.py kb_rebuild/articles/a4/task_builder.py kb_rebuild/articles/a4/prompt.py kb_rebuild/articles/a4/schema.py kb_rebuild/articles/a4/validation.py kb_rebuild/articles/a4/runner.py kb_rebuild/articles/a4/report.py kb_rebuild/cli.py
.venv/bin/python -m unittest discover -s tests
```

## Production Statement

Production A4 will not be run. Only `smoke_50` and `smoke_200` with explicit `--limit` are allowed in this implementation turn.

## Risks

- LLM can produce unsupported prose; validation must enforce per-block citations.
- High-volume tags can exceed prompt limits; selection/ranking must cap fact groups conservatively.
- Review flags are numerous and must not be lost.
- Smoke quality may reveal prompt/schema issues before architect approval for production.

## Checklist

- [x] Re-read instruction after plan.
- [x] Implement task builder.
- [x] Re-read instruction after task builder.
- [x] Implement prompt/schema.
- [x] Re-read instruction after schema.
- [x] Implement validation.
- [x] Re-read instruction after validation.
- [x] Implement runner/report/CLI.
- [x] Re-read instruction after runner.
- [x] Run compile and tests.
- [x] Re-read instruction after tests.
- [x] Run smoke 50 only.
- [x] Re-read instruction before smoke 50.
- [x] If smoke 50 passes, run smoke 200.
- [x] Re-read instruction before smoke 200.
- [x] Create feedback.
- [x] Re-read instruction before feedback.

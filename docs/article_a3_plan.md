# Article A3 Plan

## What I Understood

A3 is a deterministic evidence cleanup stage. It must consume A2 production evidence, split every evidence item into exactly one of valid/review/rejected, dedupe and group usable/review evidence into compact fact groups, then build complete per-tag coverage and A4 handoff inputs.

A3 must not call LLMs, use web search, write articles, mutate A1/A2 artifacts, or add new medical claims.

## Inputs

Required inputs:

- `data/articles/a2/production_v1/evidence_items.jsonl`
- `data/articles/a2/production_v1/evidence_task_results.jsonl`
- `data/articles/a2/production_v1/quote_validation_issues.jsonl`
- `data/articles/a2/production_v1/a2_report.json`
- `data/articles/a2/production_v1/a2_manifest.json`
- `data/articles/a1/article_status_index.jsonl`
- `data/articles/a1/tag_work_plan_adjusted.jsonl`
- `data/articles/a1/a1_report.json`
- `data/articles/a1/a1_manifest.json`
- `data/normalization/final/tags_canonical.csv`
- `data/normalization/final/tag_aliases.csv`

## Outputs

Primary A4 outputs:

- `data/articles/a3/fact_groups.jsonl`
- `data/articles/a3/tag_fact_group_index.jsonl`
- `data/articles/a3/a4_compilation_input.jsonl`

QA/report outputs:

- `evidence_items_valid.jsonl`
- `evidence_items_review.jsonl`
- `evidence_items_rejected.jsonl`
- `evidence_deduped.jsonl`
- `tags_without_usable_evidence.jsonl`
- `tag_evidence_coverage.jsonl`
- CSV diagnostics and samples
- `a3_report.json`
- `a3_manifest.json`

## Filtering Rules

- `exact` and `normalized_exact` direct evidence can be valid if claim/quote are non-empty and confidence meets threshold.
- `needs_review_before_publication=true` does not reject otherwise valid evidence, but the flag must propagate into fact groups and A4 strategy.
- `fuzzy`, `related_entity`, related/unclear relevance, low-quality windows, non-empty review reasons, or low confidence go to review.
- `not_found`, empty claim/quote, stitched/ellipsis quotes, and not-relevant evidence go to rejected.

## Dedupe Rules

- Remove exact duplicates by `tag_id`, `fact_type`, normalized claim, normalized quote, `doc_id`, and `window_id`.
- Preserve all original `evidence_item_id` values in provenance.
- Same normalized quote with different claim becomes one candidate group.
- Same normalized claim with different quotes becomes multi-source support.
- Numeric/dosage/type conflicts must not be merged as normal groups.

## Fact Grouping Rules

- Group only inside `tag_id + fact_type`.
- Use exact normalized claim/quote matches first, then deterministic high similarity using `difflib.SequenceMatcher` and token Jaccard.
- Representative claim and quote must be selected from existing evidence, never synthesized.
- Fuzzy-only groups become `review_only` and not usable for A4.
- Groups with exact/normalized plus fuzzy remain usable but review-flagged.

## Coverage Strategy

- Build `tag_fact_group_index.jsonl` for every A1 tag.
- Build `a4_compilation_input.jsonl` for every A1 tag with explicit strategy.
- Preserve direct-copy, stub-only, and review-stub statuses.
- Pending tags with usable groups compile from fact groups or compile with review flag.
- Pending tags without usable groups go to `insufficient_evidence_review` and `tags_without_usable_evidence.jsonl`.

## Quality Gates

- Every A2 evidence item is accounted for exactly once in valid/review/rejected.
- No duplicate evidence IDs in layer outputs.
- No `not_found` evidence in usable fact groups.
- No fuzzy-only group marked usable.
- All fact groups have tag/canonical/entity metadata.
- Tag index covers all A1 tags.
- A4 ready tags have at least one usable fact group.
- `quality.passed=true` is required for a successful run.

## Tests

Add focused tests for:

- filtering;
- dedupe;
- grouping;
- coverage;
- runner;
- report.

Run:

```bash
.venv/bin/python -m py_compile kb_rebuild/articles/a3/models.py kb_rebuild/articles/a3/filtering.py kb_rebuild/articles/a3/dedupe.py kb_rebuild/articles/a3/grouping.py kb_rebuild/articles/a3/coverage.py kb_rebuild/articles/a3/report.py kb_rebuild/articles/a3/runner.py kb_rebuild/cli.py
.venv/bin/python -m unittest discover -s tests
```

## Risks

- A2 has many review-propagated records; A3 must preserve usable evidence without silently making review-heavy facts publication-ready.
- Quote `not_found` is near the quality threshold and must remain rejected.
- Conservative deterministic grouping may leave more groups than ideal, but it is safer than semantic overmerge.
- A4 may expect canonical root `data/articles/a2/` paths later; A3 will use the accepted `production_v1` paths.

## Checklist

- [ ] Re-read instruction after plan.
- [ ] Implement A3 models and filtering.
- [ ] Re-read instruction after filtering.
- [ ] Implement dedupe.
- [ ] Re-read instruction after dedupe.
- [ ] Implement grouping.
- [ ] Re-read instruction after grouping.
- [ ] Implement coverage/index/A4 input.
- [ ] Re-read instruction after coverage.
- [ ] Implement reports, manifest, CLI, and tests.
- [ ] Re-read instruction after tests.
- [ ] Run production A3 command.
- [ ] Re-read instruction before production run.
- [ ] Create A3 feedback.
- [ ] Re-read instruction before feedback.

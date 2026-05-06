# N4 Final Canonical Layer Plan

## Scope

N4 builds the final deterministic canonical tag layer from all N1/N1.1
`auto_clusters` plus safe N3 accepted merge decisions.

This stage does not call an LLM, does not create evidence/articles/folders/graph
artifacts, and does not modify N1, N2, N3, `data/tagging/*`, or `data/parsed/*`
artifacts.

## Governing Instructions

- `instructions/normaalization_agent_instruction.md`
- `instructions/02_normalization_global_vision.md`
- `instructions/03_normalization_engineer_agent_guide.md`
- `instructions/01_n4_instruction.md`
- Previous normalization feedback documents through N3

Required reread checkpoints:

- after plan
- after models
- after core logic
- after tests
- before production run
- before feedback

## Implementation Plan

1. Add deterministic N4 package under `kb_rebuild/normalization/n4/`.
2. Add CLI command `normalize-n4` in `kb_rebuild/cli.py`.
3. Load and validate mandatory inputs:
   - N1/N1.1 auto clusters and mentions
   - N1 manifest/report
   - N2 candidate nodes, manifest, report
   - N3 accepted, rejected, split, review, report, manifest, diagnostics
4. Build graph:
   - node: every `auto_cluster_id`
   - accepted N3 cluster: merge edge between mapped auto clusters
   - rejected/review/split files: constraints and provenance only
5. Apply merge safety:
   - reject critical conflicts before union
   - write `merge_conflicts.jsonl`
   - preserve noncritical review reasons on final component
6. Build canonical components:
   - one `tag_id` per connected component
   - deterministic canonical RU/Latin selection
   - deterministic alias set from component clusters and mention names
   - `need_review` and review reasons from component state
7. Emit final outputs under `data/normalization/final/`:
   - canonical tag tables
   - alias table
   - normalized document-tag links
   - by-document JSONL
   - specialist/reviewer exports
   - audits and reports
8. Enforce coverage:
   - every auto cluster is represented
   - every normalized mention gets a `tag_id`
   - every original/raw/normalized name is resolvable through canonical names or aliases
9. Add required N4 tests:
   - graph
   - canonical selection
   - aliases
   - links
   - coverage
   - review exports
   - runner
10. Run targeted tests, then full test suite.
11. Run deterministic production command from the N4 instruction.
12. Write `docs/normalization_n4_feedback.md` with exact output counts and coverage verdicts.

## Files To Create Or Modify

Create:

- `kb_rebuild/normalization/n4/__init__.py`
- `kb_rebuild/normalization/n4/models.py`
- `kb_rebuild/normalization/n4/graph.py`
- `kb_rebuild/normalization/n4/canonical.py`
- `kb_rebuild/normalization/n4/aliases.py`
- `kb_rebuild/normalization/n4/links.py`
- `kb_rebuild/normalization/n4/review.py`
- `kb_rebuild/normalization/n4/runner.py`
- `tests/test_normalization_n4_graph.py`
- `tests/test_normalization_n4_canonical.py`
- `tests/test_normalization_n4_aliases.py`
- `tests/test_normalization_n4_links.py`
- `tests/test_normalization_n4_coverage.py`
- `tests/test_normalization_n4_review.py`
- `tests/test_normalization_n4_runner.py`

Modify:

- `kb_rebuild/cli.py`

Create after production:

- `docs/normalization_n4_feedback.md`

## Acceptance Criteria

- `final_normalization_report.json` exists and includes exact counts.
- `final_normalization_manifest.json` exists and records inputs, command options, and stage version.
- `coverage_audit_missing_aliases.csv` is empty except header.
- `coverage_audit_missing_mentions.csv` is empty except header.
- `document_tag_links_normalized.jsonl` row count equals N1 `mentions_total`.
- All N1/N1.1 auto clusters are covered.
- All mentions get a `tag_id`.
- All original raw tag names are recognized through canonical names or aliases.
- Required N4 tests pass.

## Risks

- N3 accepted clusters can reference N2 node IDs that no longer map to an auto cluster.
- N3 labels may be valid merge evidence but not complete alias evidence.
- Drug trade name merges must be conservative and should block active-substance aliases.
- Coverage must be driven from mentions, not only from accepted N3 clusters.

## Status

- [x] Read governing instructions and previous feedback.
- [x] Create N4 plan.
- [x] Reread N4 instruction after plan.
- [x] Reread N4 instruction after models.
- [x] Reread N4 instruction after core logic.
- [x] Implement N4 package and CLI.
- [x] Add N4 tests.
- [x] Run tests.
- [x] Reread N4 instruction after tests.
- [x] Reread N4 instruction before production.
- [x] Run production N4.
- [x] Verify coverage and outputs.
- [x] Reread N4 instruction before feedback.
- [x] Write N4 feedback.

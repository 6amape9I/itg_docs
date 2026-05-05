# Normalization N1.1 Feedback

## What Changed

N1 deterministic normalization was polished for N2 readiness.

Main changes:

- Added cluster status model: `auto_merged`, `review_group`, `isolated_mention`.
- Added `merge_allowed`, `blocking_flags`, `risk_flags`, and `routing_flags` to auto-clusters.
- Stopped splitting identical short aliases into multiple cluster rows; they now become one `review_group`.
- Split mention flags into `risk_flags`, `routing_flags`, and backward-compatible `suspicious_flags`.
- Removed `context_only` / `folder_candidate` from risk-based suspicious logic.
- Improved product cleanup and product canonical display selection.
- Protected standalone unit-like brand tokens such as `Г` in `Гепатромбин Г`.
- Added trailing numeric product variant detection.
- Added disease type/subtype marker detection and subtype signatures.
- Added singleton entity candidate reports.
- Added cluster duplicate diagnostics.

No LLM calls were added. No `data/tagging/*` files were modified.

## Files Changed

Code:

- `kb_rebuild/normalization/models.py`
- `kb_rebuild/normalization/text.py`
- `kb_rebuild/normalization/mentions.py`
- `kb_rebuild/normalization/auto_cluster.py`
- `kb_rebuild/normalization/report.py`
- `kb_rebuild/normalization/n1_runner.py`

Tests:

- `tests/test_normalization_text.py`
- `tests/test_normalization_mentions.py`
- `tests/test_normalization_auto_cluster.py`
- `tests/test_normalization_n1_runner.py`

Docs:

- `docs/normalization_n1_1_feedback.md`

## Commands Run

```bash
.venv/bin/python -m py_compile kb_rebuild/normalization/text.py kb_rebuild/normalization/mentions.py kb_rebuild/normalization/auto_cluster.py kb_rebuild/normalization/report.py kb_rebuild/normalization/n1_runner.py kb_rebuild/cli.py
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m kb_rebuild normalize-n1 --data data --out data/normalization
```

## Test Results

- `py_compile`: passed
- `unittest discover`: 70 tests passed
- Production N1.1 run: completed

## New Counts

From `data/normalization/normalization_n1_report.json`:

- `auto_merged_clusters_total`: 4,249
- `review_groups_total`: 340
- `isolated_mentions_total`: 18,192
- `risk_mentions`: 7,652
- `routing_mentions`: 42,324
- `routing_context_only_mentions`: 20,968
- `routing_folder_candidate_mentions`: 1,609
- `singleton_entity_candidates`: 13,952
- `singleton_fast_path_recommended`: 7,633
- `cluster_duplicate_diagnostics`: 0

Compatibility counts:

- `mentions_total`: 42,324
- `unique_raw_values`: 22,710
- `unique_normalized_values`: 22,116
- `auto_clusters_total`: 22,781
- `auto_clusters_review_required`: 7,768
- `suspicious_mentions`: 7,652
- `quote_issue_mentions`: 300
- `failed_documents`: 20
- `invalid_tagging_records`: 0

## ARX Result

`ARX` is now one review group instead of multiple visual duplicate rows:

- `auto_cluster_id`: `ac_000033`
- `auto_cluster_key`: `biological_substance::arx`
- `cluster_status`: `review_group`
- `merge_allowed`: `false`
- `mentions_count`: 3
- `blocking_flags`: `possible_abbreviation`, `very_short_alias`
- `risk_flags`: `latin_only`, `possible_abbreviation`, `very_short_alias`

`cluster_duplicate_diagnostics.csv` has only the header; no duplicate `entity_type + auto_cluster_key` rows remain.

## Product Examples

`Берлиприл` variants:

- Aliases include `Берлиприл`, `Берлиприл 10`, `Берлиприл 20`, `Берлиприл 20 мг`, `Берлиприл 5`, `Берлиприл 5 мг`.
- Canonical display is now `Берлиприл`.
- Cluster is a `review_group` because trailing numeric variants add `possible_numeric_dosage_variant`.

`Гепатромбин Г`:

- Canonical display remains `Гепатромбин Г`.
- Product norm remains `гепатромбин г`.
- Standalone `Г` is no longer removed as a gram unit.

`Коэнзим Q10`:

- Numeric protection keeps `Q10`.
- It is not stripped to `Коэнзим Q`.

## Disease Type/Subtype Examples

`GM1 ганглиозидоз тип 1`, `GM1 ганглиозидоз тип 2`, and `GM1 ганглиозидоз тип 3` are separate clusters.

They carry:

- `has_type_subtype_marker`
- subtype signatures such as `type_1`, `type_2`, `type_3`
- `merge_allowed=false`
- `review_required=true`

`Сахарный диабет 1 типа` and `Сахарный диабет 2 типа` are also separate review groups and do not auto-merge with the base disease.

## New Outputs

Added under `data/normalization/`:

- `risk_mentions.jsonl`
- `routing_mentions.jsonl`
- `singleton_entity_candidates.csv`
- `singleton_entity_candidates.jsonl`
- `cluster_duplicate_diagnostics.csv`

`normalization_n1_manifest.json` now includes `stage_version: n1.1` and paths to these outputs.

## Risks

- `routing_mentions` equals all mentions because every mention currently receives one of `article_candidate`, `context_only`, or `folder_candidate`.
- `mixed_cyrillic_latin` remains a noisy but useful review signal for disease subtype markers and gene-like names.
- Product numeric variant detection is conservative; ambiguous brand numbers are grouped for review instead of auto-merged.
- Singleton fast path is only a candidate report; it should not become final canonical truth without downstream policy.

## For N2

Use:

- `auto_clusters.jsonl` as the deterministic cluster base.
- `cluster_status` and `merge_allowed` to separate safe merges from review groups.
- `blocking_flags` for hard stop reasons.
- `risk_mentions.jsonl` for candidate priority.
- `singleton_entity_candidates.jsonl` for possible fast-path entity creation.
- `cluster_duplicate_diagnostics.csv` as a sanity gate before candidate generation.

N2 should still avoid semantic merge without validation, especially for abbreviations, disease subtypes, product variants, and parent-child disease terms.

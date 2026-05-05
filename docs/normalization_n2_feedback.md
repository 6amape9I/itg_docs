# Normalization N2 Feedback

## Scope

Implemented deterministic N2 candidate generation on top of N1.1 outputs. N2 does not call an LLM and does not create final merges; it only prepares candidate nodes, candidate pairs, blocked/rejected pairs, review groups, reports, and N3 handoff artifacts.

## Code Changes

- Added `kb_rebuild/normalization/n2/` with models, feature scoring, blocking rules, pair generation, safe grouping, reporting, and runner orchestration.
- Added CLI command `normalize-n2` in `kb_rebuild/cli.py`.
- Added N2 tests for feature scoring, blocking, pair generation, grouping, runner validation, product variants, and duplicate-safe group counts.
- Added product variant alias nodes for `drug_trade_name` and `supplement` review clusters, so variants like `Берлиприл 10`, `Берлиприл 20 мг`, `Берлиприл 5 мг` appear as N2 candidates even when N1.1 kept them in one review cluster.
- Group counts now deduplicate overlapping `mention_ids`, which prevents base-node plus alias-node groups from inflating mention/article counts.

## Production Run

Command:

```bash
.venv/bin/python -m kb_rebuild normalize-n2 --data data --normalization-dir data/normalization --out data/normalization/n2 --min-score 0.72 --high-priority-score 0.88 --max-pairs-per-type 50000
```

Outputs:

- `data/normalization/n2/candidate_nodes.jsonl`
- `data/normalization/n2/candidate_pairs.jsonl`
- `data/normalization/n2/blocked_pairs.jsonl`
- `data/normalization/n2/rejected_pairs.jsonl`
- `data/normalization/n2/candidate_groups.jsonl`
- `data/normalization/n2/candidate_groups.csv`
- `data/normalization/n2/high_priority_candidate_groups.csv`
- `data/normalization/n2/singleton_fast_path_candidates.csv`
- `data/normalization/n2/candidate_generation_report.json`
- `data/normalization/n2/candidate_generation_manifest.json`

## Final Counts

- nodes: 23049
- candidate pairs: 1830
- high priority pairs: 1830
- blocked pairs: 50241
- rejected low-score pairs: 24858
- candidate groups: 6269
- high / medium / low groups: 888 / 182 / 199
- blocked review groups: 5000
- singleton fast-path candidates: 7633

Important reason counts:

- `shared_latin_candidate`: 1775
- `exact_normalized_match`: 951
- `product_variant_match`: 388
- `parenthetical_alias_match`: 187
- `abbreviation_match`: 26

Blocking reason counts:

- `disease_subtype_conflict`: 48234
- `parent_child_suspect`: 2651
- `parent_child_blocked`: 1743
- `taxonomic_level_conflict`: 21

## Examples

- Abbreviation: `cg_000030` groups `МРТ` with `Магнитно-резонансная томография`.
- Product variants: `cg_000161` groups `Берлиприл`, `Берлиприл 10`, `Берлиприл 20`, `Берлиприл 20 мг`, `Берлиприл 5`, `Берлиприл 5 мг`; deduped `mentions_count=6`.
- Disease aliases: `cg_000463` groups `Ангионевротический отек` with `Отек Квинке`; `cg_000888` groups `Гипертоническая болезнь` with `Эссенциальная гипертензия`.
- Microorganism aliases: `cg_000283` groups `Bacillus anthracis`, `Бацилла антрацис`, `Сибиреязвенная бацилла`, `Сибиреязвенная палочка`.
- Taxonomy blocked: `Aedes` vs `Aedes aegypti`, `Borrelia` vs `Borrelia burgdorferi`, `Candida` vs `Candida albicans`.
- Parent-child blocked: `Аденомиома` vs `Аденомиома желчного пузыря`, `Базальноклеточная карцинома` vs `Базальноклеточная карцинома глаза`.

## Validation

- `.venv/bin/python -m py_compile kb_rebuild/normalization/n2/*.py kb_rebuild/cli.py`
- `.venv/bin/python -m unittest discover -s tests`
- Final test result: 94 tests OK.
- Output file line counts match the report counts.
- Candidate group duplicate id check: 0 duplicates.
- `data/tagging/*` was not modified.

## Handoff Notes

- N2 is intentionally conservative: blocked pairs are not dropped, they are written to `blocked_pairs.jsonl` and represented as `blocked_review` groups for audit.
- Disease subtype blocking is aggressive. It correctly catches many type/subtype conflicts, but it can also block eponym/synonym cases with roman numerals, for example `Мукополисахаридоз II типа` vs `Синдром Хантера`. N3 should either keep this conservative behavior or add a curated synonym override layer.
- Product alias expansion is candidate-only. Groups with `product_variant_match` should still require N3 validation before any merge decision.
- Disease generic buckets (`синдром`, `болезнь`, `аутосомно`, etc.) are capped/skipped by design to avoid unsafe all-to-all pair explosions; the disease type still hit `max_pairs_per_type=50000`, and the runner kept the strongest evaluated pairs.

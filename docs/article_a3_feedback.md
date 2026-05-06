# Article A3 Feedback

ТЗ перечитано на этапах: after_plan, after_filtering, after_dedupe, after_grouping, after_coverage, after_tests, before_production_run, before_feedback

## 1. Что сделано

- Реализован deterministic A3 `Evidence Dedupe & Fact Grouping`.
- A3 читает A2 production output из `data/articles/a2/production_v1/`.
- Все A2 evidence items разложены в `valid`, `review`, `rejected`.
- `not_found` evidence вынесен в rejected и не попадает в usable fact groups.
- Fuzzy-only evidence groups помечены как `review_only` и `usable_for_a4=false`.
- Построены fact groups, per-tag index, coverage и A4 handoff input.
- A3 не вызывал LLM, не использовал web и не менял A1/A2 outputs.

## 2. Какие файлы изменены

Docs:

- `docs/article_a3_plan.md`
- `docs/article_a3_feedback.md`

Code:

- `kb_rebuild/cli.py`
- `kb_rebuild/articles/a3/__init__.py`
- `kb_rebuild/articles/a3/models.py`
- `kb_rebuild/articles/a3/filtering.py`
- `kb_rebuild/articles/a3/dedupe.py`
- `kb_rebuild/articles/a3/grouping.py`
- `kb_rebuild/articles/a3/coverage.py`
- `kb_rebuild/articles/a3/report.py`
- `kb_rebuild/articles/a3/runner.py`

Tests:

- `tests/test_article_a3_filtering.py`
- `tests/test_article_a3_dedupe.py`
- `tests/test_article_a3_grouping.py`
- `tests/test_article_a3_coverage.py`
- `tests/test_article_a3_runner.py`
- `tests/test_article_a3_report.py`

Generated outputs:

- `data/articles/a3/`

## 3. Какие команды запускались

```bash
.venv/bin/python -m unittest tests.test_article_a3_filtering tests.test_article_a3_dedupe tests.test_article_a3_grouping tests.test_article_a3_coverage tests.test_article_a3_report tests.test_article_a3_runner
.venv/bin/python -m py_compile kb_rebuild/articles/a3/models.py kb_rebuild/articles/a3/filtering.py kb_rebuild/articles/a3/dedupe.py kb_rebuild/articles/a3/grouping.py kb_rebuild/articles/a3/coverage.py kb_rebuild/articles/a3/report.py kb_rebuild/articles/a3/runner.py kb_rebuild/cli.py
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m kb_rebuild article-a3-group-evidence --data data --a2-dir data/articles/a2/production_v1 --a1-dir data/articles/a1 --normalization-final-dir data/normalization/final --out data/articles/a3 --min-confidence 0.5 --max-quotes-per-fact-group 8 --max-fact-groups-per-tag 200
```

## 4. Tests

- A3-specific suite: 25 tests passed.
- Full test suite: 253 tests passed.
- Compile check: passed.

## 5-15. Summary metrics

Source A2 evidence items total: 72843.

- Valid evidence: 66114
- Review evidence: 3166
- Rejected evidence: 3563
- Exact duplicates removed: 0
- Deduped evidence items: 69280
- Fact groups total: 67950
- Usable fact groups: 64305
- Review-only fact groups: 1701
- Tags with valid evidence: 9748
- Tags without usable evidence: 103
- Ready-for-A4 tags: 9748
- Direct-copy tags: 6806
- Stub-only tags: 3839
- Review-stub tags: 2017
- Compile-with-review-flag tags: 6787

Quote status distribution after filtering:

- `exact`: 65759
- `normalized_exact`: 2375
- `fuzzy`: 1146
- `not_found`: 3563

Quality:

- `all_evidence_items_accounted_for`: true
- `no_duplicate_evidence_item_id_in_layer_outputs`: true
- `no_not_found_in_usable_fact_groups`: true
- `no_fuzzy_only_fact_group_marked_usable`: true
- `all_fact_groups_have_tag_id`: true
- `all_a4_ready_tags_have_fact_groups`: true
- `tag_fact_group_index_complete`: true
- `quality.passed`: true

Line counts:

- `evidence_items_valid.jsonl`: 66114
- `evidence_items_review.jsonl`: 3166
- `evidence_items_rejected.jsonl`: 3563
- `evidence_deduped.jsonl`: 69280
- `fact_groups.jsonl`: 67950
- `tag_fact_group_index.jsonl`: 22513
- `a4_compilation_input.jsonl`: 22513
- `tags_without_usable_evidence.jsonl`: 103
- `tag_evidence_coverage.jsonl`: 22513

## 16. Примеры хороших fact groups

- `Система комплемента`: `definition`, representative quote `exact`, `a4_usage=core_fact`, `usable_for_a4=true`.
- `Система комплемента`: `mechanism`, representative quote `exact`, `a4_usage=core_fact`, `usable_for_a4=true`.
- `Система комплемента`: `cause_or_risk_factor`, representative quote `exact`, `a4_usage=supporting_fact`, `usable_for_a4=true`.

## 17. Примеры rejected not_found evidence

- `Кофеин`: `usage_or_dosage`, rejected reason `quote_not_found`.
- `Кофеин`: `side_effect`, rejected reason `quote_not_found`.
- `Кофеин`: `prevention`, rejected reason `quote_not_found`.

## 18. Примеры review-only fuzzy evidence

- `Серотонин`: `mechanism`, `quote_status_counts.fuzzy=1`, `usable_for_a4=false`.
- `Агар-агар`: `mechanism`, `quote_status_counts.fuzzy=1`, `usable_for_a4=false`.
- `Витамин D`: `mechanism`, `quote_status_counts.fuzzy=1`, `usable_for_a4=false`.

## 19. High-volume tags

Top high-volume tags from `high_volume_tags.csv`:

- `Магнитно-резонансная томография`: 565 evidence items, 534 fact groups, 198 usable groups.
- `Вирус папилломы человека`: 445 evidence items, 415 fact groups, 197 usable groups.
- `Хеликобактер пилори`: 268 evidence items, 246 fact groups, 189 usable groups.
- `Артериальная гипертензия`: 256 evidence items, 211 fact groups, 182 usable groups.
- `Сахарный диабет`: 247 evidence items, 233 fact groups, 158 usable groups.

## 20. Риски

- Fact groups remain numerous: 67950 groups from 69280 deduped valid/review items. This is conservative and avoids semantic overmerge, but A4 may need ranking/section budgeting.
- `compile_with_review_flag_tags=6787`; many A4-ready tags still require publication review flags to propagate.
- `review_only_fact_groups=1701` and `rejected=3563` must stay out of default article compilation.
- `max_fact_groups_per_tag=200` is used as a safety/config value, but high-volume tags can still require A4-side truncation or prioritization by section/fact type.

## 21. What to pass to A4

Главный output для A4:

```text
data/articles/a3/a4_compilation_input.jsonl
data/articles/a3/fact_groups.jsonl
data/articles/a3/tag_fact_group_index.jsonl
```

Supporting A3 outputs:

```text
data/articles/a3/a3_report.json
data/articles/a3/a3_manifest.json
data/articles/a3/tag_evidence_coverage.jsonl
data/articles/a3/tags_without_usable_evidence.jsonl
data/articles/a3/manual_qa_fact_groups_sample.csv
data/articles/a3/rejected_evidence_summary.csv
data/articles/a3/review_evidence_summary.csv
data/articles/a3/high_volume_tags.csv
```

A4 should use only `a4_usage in {core_fact, supporting_fact}` by default and must preserve `needs_review_before_publication`.

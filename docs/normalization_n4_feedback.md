# N4 Final Canonical Layer Feedback

## 1. Что сделано

Реализован N4 deterministic final canonical layer:

- все N1/N1.1 `auto_clusters` включены в final canonical layer;
- N3 accepted clusters применены как merge-rules поверх полного множества auto clusters;
- standalone auto clusters сохранены как отдельные final tags;
- построены final canonical tags, aliases, normalized document-tag links, by-doc links;
- выполнены coverage audit и review/audit exports;
- добавлен CLI `normalize-n4`;
- добавлены обязательные N4 tests.

N4 не вызывал LLM.

## 2. Какие файлы изменены

Созданы:

- `docs/normalization_n4_plan.md`
- `docs/normalization_n4_feedback.md`
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

Изменён:

- `kb_rebuild/cli.py`

Сгенерированы production outputs:

- `data/normalization/final/tags_canonical.csv`
- `data/normalization/final/tag_aliases.csv`
- `data/normalization/final/document_tag_links_normalized.jsonl`
- `data/normalization/final/document_tag_links_normalized.csv`
- `data/normalization/final/document_tags_normalized_by_doc.jsonl`
- `data/normalization/final/final_canonical_tag_names.csv`
- `data/normalization/final/specialist_review_full.csv`
- `data/normalization/final/specialist_review_sample.csv`
- `data/normalization/final/canonical_review_detailed.csv`
- `data/normalization/final/coverage_audit.json`
- `data/normalization/final/coverage_audit_missing_mentions.csv`
- `data/normalization/final/coverage_audit_missing_aliases.csv`
- `data/normalization/final/alias_conflicts.csv`
- `data/normalization/final/merge_conflicts.jsonl`
- `data/normalization/final/drug_policy_review.csv`
- `data/normalization/final/unresolved_review_groups.jsonl`
- `data/normalization/final/final_normalization_report.json`
- `data/normalization/final/final_normalization_manifest.json`

## 3. Какие команды запускались

```bash
.venv/bin/python -m compileall kb_rebuild/normalization/n4 kb_rebuild/cli.py
.venv/bin/python -m unittest tests/test_normalization_n4_graph.py tests/test_normalization_n4_canonical.py tests/test_normalization_n4_aliases.py tests/test_normalization_n4_links.py tests/test_normalization_n4_coverage.py tests/test_normalization_n4_review.py tests/test_normalization_n4_runner.py
.venv/bin/python -m unittest discover
.venv/bin/python -m unittest discover -s tests -p 'test*.py'
.venv/bin/python -m kb_rebuild normalize-n4 --data data --normalization-dir data/normalization --n2-dir data/normalization/n2 --n3-dir data/normalization/n3 --out data/normalization/final --review-sample-size 500
```

`unittest discover` без параметров нашёл 0 tests в текущем repo layout, поэтому полный прогон выполнен явным `discover -s tests -p 'test*.py'`.

## 4. Сколько tests passed

- N4 targeted tests: 20 passed.
- Full explicit test suite: 167 passed.

## 5-11. Production counts

- mentions_total: 42,324
- document_tag_links_total: 42,324
- final canonical tags: 22,513
- standalone auto_cluster tags: 22,294
- merged N3 tags: 219
- aliases: 52,530
- documents_with_normalized_tags: 16,161
- auto_clusters_total: 22,781
- n3_accepted_clusters_total: 333

## 12. Coverage audit

- mentions_without_tag_id: 0
- aliases_missing_for_original_mentions: 0
- all_original_tag_names_recognized: true
- passed: true
- links_to_missing_tag_id: 0
- documents_with_mentions: 16,161
- documents_with_normalized_tags: 16,161

`coverage_audit_missing_mentions.csv` and `coverage_audit_missing_aliases.csv` contain only headers.

## 13-16. Review and conflicts

- need_review tags: 9,325
- alias conflicts: 1,354
- merge conflicts: 1
- drug policy review items: 1
- unresolved review groups: 11

The single critical merge conflict is drug policy protection:

- `n3c_000091`, `cg_000151`
- labels: `Бетасерк`, `Бетагистина дигидрохлорид (Бетасерк)`
- action: merge blocked
- review_reason: `drug_trade_name_active_substance_conflict`

Alias conflicts are noncritical N4 review flags: coverage still passes because expected mention values resolve to their final `tag_id`.

## 17-19. Review file paths

- final canonical tag names: `data/normalization/final/final_canonical_tag_names.csv`
- specialist full review: `data/normalization/final/specialist_review_full.csv`
- specialist sample review: `data/normalization/final/specialist_review_sample.csv`

## 20. Что не сделано

- не вызывался LLM;
- не делались новые semantic merges вне N3 accepted decisions;
- не менялись N1/N2/N3 artifacts;
- не менялись `data/tagging/*` и `data/parsed/*`;
- не создавались статьи, evidence, folders или graph knowledge artifacts.

## 21. Риски

- `alias_conflicts.csv` содержит 1,354 review cases; они не ломают coverage, но требуют специалистской проверки перед жёстким применением alias lookup в downstream.
- 9,325 tags имеют `need_review=true`, в основном из N1 risk/review flags и N4 conflict flags.
- 11 N3 web/human review groups не применялись как merge edges и переданы в `unresolved_review_groups.jsonl`.
- Drug trade-name policy заблокировал 1 потенциально опасный merge.

## 22. Что передать следующему этапу

Основной downstream input:

- `data/normalization/final/tags_canonical.csv`
- `data/normalization/final/tag_aliases.csv`
- `data/normalization/final/document_tag_links_normalized.jsonl`
- `data/normalization/final/document_tags_normalized_by_doc.jsonl`

Для специалистской проверки:

- `data/normalization/final/final_canonical_tag_names.csv`
- `data/normalization/final/specialist_review_full.csv`
- `data/normalization/final/specialist_review_sample.csv`
- `data/normalization/final/alias_conflicts.csv`
- `data/normalization/final/drug_policy_review.csv`
- `data/normalization/final/unresolved_review_groups.jsonl`

## Required verdicts

- Все N1/N1.1 auto_clusters покрыты: yes
- Все mentions получили tag_id: yes
- Все исходные raw tag names распознаются через canonical+aliases: yes

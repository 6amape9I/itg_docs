# Normalization N2.1 Feedback

## Что изменено

- Добавлен quality layer для N2: `candidate_group_status`, `n3_ready`, `exclusion_reasons`, `clean_candidate_reasons`, `weak_candidate_reasons`.
- Разделены N3-ready группы и audit/review группы. Главный вход для N3 теперь: `data/normalization/n2/n3_candidate_groups.jsonl`.
- Добавлены отдельные outputs для `blocked_review`, `low_confidence`, `ambiguous_abbreviation`, `hub_parent_child_suspect`, `generic_alias_conflict`.
- Ужесточены exact match и abbreviation matching: generic aliases и generated acronyms больше не являются clean strong evidence.
- Добавлены scope conflicts для diagnostic methods, procedures, diseases и drug classes.
- Добавлена hub-node protection: node не может остаться в более чем 5 N3-ready группах.
- Manifest теперь содержит `stage_version=n2.1`.

## Изменённые файлы

- `kb_rebuild/normalization/n2/features.py`
- `kb_rebuild/normalization/n2/blocking.py`
- `kb_rebuild/normalization/n2/scope_conflict.py`
- `kb_rebuild/normalization/n2/pair_generation.py`
- `kb_rebuild/normalization/n2/grouping.py`
- `kb_rebuild/normalization/n2/models.py`
- `kb_rebuild/normalization/n2/report.py`
- `kb_rebuild/normalization/n2/runner.py`
- `kb_rebuild/cli.py`
- `tests/test_normalization_n2_*.py`

## Команды

```bash
.venv/bin/python -m py_compile kb_rebuild/normalization/n2/features.py kb_rebuild/normalization/n2/blocking.py kb_rebuild/normalization/n2/pair_generation.py kb_rebuild/normalization/n2/grouping.py kb_rebuild/normalization/n2/report.py kb_rebuild/normalization/n2/runner.py kb_rebuild/normalization/n2/scope_conflict.py kb_rebuild/cli.py
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m kb_rebuild normalize-n2 --data data --normalization-dir data/normalization --out data/normalization/n2 --min-score 0.72 --high-priority-score 0.88 --max-pairs-per-type 50000
```

Tests: 105 passed.

## Counts

Old N2 production:

- total groups: 6269
- N3 candidate groups: not separated
- blocked review groups: 5000
- ambiguous abbreviation groups: not separated
- generic alias conflicts: not separated
- hub parent-child suspects: not separated

N2.1 production:

- total groups: 6918
- N3 candidate groups: 1241
- blocked/review groups: 5281
- low confidence candidate groups: 396
- ambiguous abbreviation groups: 13
- generic alias conflicts: 4
- hub parent-child suspects: 985
- quality gate: passed

Quality gate:

- recommended groups with `both_context_only`: 0
- recommended groups with parent-child/scope suspect: 0
- recommended groups with generic alias conflict: 0
- recommended groups with ambiguous abbreviation: 0
- nodes in more than 5 N3 groups: 0

## Bad Examples Excluded From N3

These no longer appear in `n3_candidate_groups.csv`:

- `Квантифероновый тест` / `Кератотопография` / `Компьютерная томография` groups are in `ambiguous_abbreviation_groups.csv`.
- `МРТ гипофиза`, `МРТ позвоночника`, scoped MRI groups are in `hub_parent_child_suspects.csv` / `blocked_review_groups.csv`.
- diagnostic method object conflicts such as scoped CT/MRI variants are not N3-ready.
- disease location conflicts and procedure object conflicts are blocked/review-only.

## Good Examples Preserved

Still N3-ready:

- `Аддисонова болезнь | Болезнь Аддисона`
- `Акне | Угревая сыпь`
- `Ингибиторы АПФ | Ингибиторы ангиотензинпревращающего фермента`
- `Bacillus anthracis | Сибиреязвенная палочка`
- `HVP | HVP (Эйч Ви Пи)`

Some requested positives, such as `ПЦР | Полимеразная цепная реакция`, `ИФА | Иммуноферментный анализ`, and `Escherichia coli | Кишечная палочка`, are already inside single N1.1/N2 candidate nodes in this dataset, so they do not need separate N2 pair/group rows.

## Top Reasons

Top candidate reasons:

- `high_sequence_similarity`: 35420
- `abbreviation_match`: 14318
- `moderate_sequence_similarity`: 2655
- `high_token_similarity`: 2551
- `shared_latin_candidate`: 1778
- `exact_normalized_match`: 956

Top clean reasons:

- `high_sequence_similarity_without_scope_conflict`: 32598
- `known_safe_abbreviation_match`: 1945
- `shared_latin_candidate_non_short`: 1757
- `canonical_alias_exact_match`: 891
- `product_variant_match`: 388

Top exclusion reasons:

- `disease_subtype_conflict`: 4280
- `parent_child_suspect`: 346
- `diagnostic_method_scope_conflict`: 347
- `hub_parent_child_suspect`: 264
- `diagnostic_method_parent_child_scope`: 133
- `procedure_object_scope_conflict`: 2

## N3 Handoff

Use only:

```text
data/normalization/n2/n3_candidate_groups.jsonl
```

Do not use the full `candidate_groups.jsonl` as N3 input; it is now an audit superset and contains blocked/review/low-confidence groups.

## Риски

- Scope dictionaries are intentionally conservative and should be expanded with observed false positives.
- Hub protection may demote some real broad synonym clusters; those remain auditable in `blocked_review_groups.*`.
- N2.1 still does not merge anything and does not create canonical tag tables.

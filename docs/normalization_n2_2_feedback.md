# N2.2 Feedback

## Что изменено

- Поднят stage version до `n2.2` в report и manifest.
- Добавлен строгий N3-ready score gate: `group_score >= 0.72` либо hard alias exception.
- Hard alias exception ограничен reasons: `primary_label_exact_match`, `explicit_parenthetical_alias_match`, `explicit_alias_exact_match`, `product_variant_match`, `canonical_alias_exact_match`.
- Добавлены subtype, cellular, complex, disease location и scope markers на уровне групп.
- Добавлены статусы групп: `subtype_conflict`, `location_scope_conflict`, `quality_score_rejected`.
- Добавлены N2.2 output CSV: `subtype_conflict_groups.csv`, `location_scope_conflict_groups.csv`, `quality_score_rejected_groups.csv`, `known_bad_n3_matches.csv`.
- Добавлен known-bad scanner для N3-ready групп.
- Обновлены report, diagnostics, manifest и CSV-поля: `hard_alias_reason`, `score_gate_passed`, `subtype_markers`, `location_markers`, `cellular_markers`, `complex_markers`, `quality_gate_flags`.

## Файлы изменены

- `kb_rebuild/normalization/n2/blocking.py`
- `kb_rebuild/normalization/n2/grouping.py`
- `kb_rebuild/normalization/n2/models.py`
- `kb_rebuild/normalization/n2/report.py`
- `kb_rebuild/normalization/n2/runner.py`
- `kb_rebuild/normalization/n2/scope_conflict.py`
- `tests/test_normalization_n2_grouping.py`
- `tests/test_normalization_n2_quality_gate.py`
- `tests/test_normalization_n2_runner.py`
- `tests/test_normalization_n2_2_quality_gate.py`
- `tests/test_normalization_n2_2_subtype_conflicts.py`
- `tests/test_normalization_n2_2_scope_conflicts.py`
- `tests/test_normalization_n2_2_known_bad_scanner.py`
- `docs/normalization_n2_2_feedback.md`

Generated N2 outputs were refreshed under `data/normalization/n2/`.

## Команды

```bash
.venv/bin/python -m py_compile kb_rebuild/normalization/n2/features.py kb_rebuild/normalization/n2/blocking.py kb_rebuild/normalization/n2/scope_conflict.py kb_rebuild/normalization/n2/pair_generation.py kb_rebuild/normalization/n2/grouping.py kb_rebuild/normalization/n2/report.py kb_rebuild/normalization/n2/runner.py kb_rebuild/cli.py
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m kb_rebuild normalize-n2 --data data --normalization-dir data/normalization --out data/normalization/n2 --min-score 0.72 --high-priority-score 0.88 --max-pairs-per-type 50000
```

Tests passed: `120`.

## Counts

| Metric | N2.1 | N2.2 |
|---|---:|---:|
| total groups | 6918 | 6878 |
| N3 candidate groups | 1241 | 363 |
| blocked/review/audit groups | 5281 | 6295 |
| subtype conflict groups | n/a | 3969 |
| location scope conflict groups | n/a | 1097 |
| quality score rejected groups | n/a | 1201 |
| known bad matches | n/a | 0 |

Quality gate: `passed=true`.

## Quality Gate

- `n3_groups_with_score_below_0_72_without_hard_alias_reason`: 0
- `n3_disease_groups_with_multiple_type_values`: 0
- `n3_disease_groups_with_base_vs_subtype_conflict`: 0
- `n3_groups_with_disease_location_conflict`: 0
- `n3_groups_with_cellular_subtype_conflict`: 0
- `n3_groups_with_complex_subtype_conflict`: 0
- `n3_groups_with_disease_modifier_mismatch`: 0
- `n3_groups_with_quality_risk_without_hard_alias_reason`: 0
- `n3_groups_matching_known_bad_examples`: 0
- `nodes_in_more_than_5_n3_groups`: 0

## Removed / Reclassified

- Removed from N3 by stricter score policy: N3-ready count reduced from 1241 to 363; `quality_score_rejected_groups=1201`, and `score_below_n3_threshold_without_hard_alias_reason` appears in 6027 group exclusions.
- Reclassified because subtype/cellular/complex conflicts: `subtype_conflict_groups=3969`.
- Reclassified because location/scope conflicts: `location_scope_conflict_groups=1097`.

Examples now excluded:

- `Гиперфенилаланинемия тип A... | ...тип B... | ...тип C...` -> `different_subtype_values_inside_group`
- `Дефицит митохондриального комплекса I... | ...комплекса IV...` -> `complex_subtype_conflict`
- `Плоскоклеточная карцинома кожи | Плоскоклеточный рак легкого` -> `disease_location_conflict`
- `Биопсия кожи | Биопсия`-style groups -> diagnostic/procedure scope conflict buckets
- `УЗИ орбиты | Ультразвуковая допплерография | Ультразвуковое исследование орбиты` -> score rejected

Known bad examples from the instruction are absent from `n3_candidate_groups.csv`; `known_bad_n3_matches.csv` contains only the header.

## Good Groups Preserved

All required positive examples remain in `n3_candidate_groups.csv`:

- `Аддисонова болезнь | Болезнь Аддисона`
- `Акне | Угревая сыпь`
- `Ингибиторы АПФ | Ингибиторы ангиотензинпревращающего фермента`
- `Bacillus anthracis | ... | Сибиреязвенная палочка`
- `HVP | HVP (Эйч Ви Пи) | Hvp эйч ви пи`

## Риски

- Фильтр стал намеренно строгим; часть правдоподобных aliases ушла в audit buckets, особенно disease groups с location/scope markers.
- `disease_parent_child_scope` может быть консервативным для некоторых реальных synonyms, например терминов с органной локализацией.
- Некоторые hard exact disease groups сохраняют raw `disease_modifier_mismatch` как risk flag, но не считаются gate violation, если `quality_gate_flags` пустые.

## Что передать в N3

Передавать только:

```text
data/normalization/n2/n3_candidate_groups.jsonl
```

Это 363 N3-ready groups with `candidate_group_status=n3_candidate`, `score_gate_passed=true`, and empty `quality_gate_flags`.

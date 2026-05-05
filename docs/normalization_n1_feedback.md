# Normalization N1 Feedback

## What Was Done

Implemented the deterministic N1 normalization layer over immutable tagging output.

The new CLI command reads `data/tagging/document_tags_raw_active.jsonl`, optional failures/empty-candidate inputs, flattens LLM entities into mentions, creates deterministic normalized forms, builds conservative exact auto-clusters, and writes quality/statistical artifacts under `data/normalization/`.

No LLM calls are made. No `data/tagging/*` files are written.

## Files Changed

Code:

- `kb_rebuild/cli.py`
- `kb_rebuild/normalization/__init__.py`
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

- `docs/normalization_n1_plan.md`
- `docs/normalization_n1_feedback.md`

## Artifacts Created

Under `data/normalization/`:

- `tag_mentions_raw.jsonl`
- `tag_mentions_normalized.jsonl`
- `tags_raw.csv`
- `auto_clusters.jsonl`
- `auto_clusters.csv`
- `normalization_n1_report.json`
- `normalization_n1_manifest.json`
- `type_role_stats.csv`
- `suspicious_mentions.jsonl`
- `failed_documents_snapshot.jsonl`
- `top_aliases_by_type.csv`
- `top_canonical_candidates.csv`
- `quote_issue_mentions.jsonl`
- `article_candidate_mentions.jsonl`
- `context_only_mentions.jsonl`
- `invalid_tagging_records.jsonl`

## How To Run

```bash
.venv/bin/python -m kb_rebuild normalize-n1 --data data
```

Equivalent explicit run:

```bash
.venv/bin/python -m kb_rebuild normalize-n1 \
  --data data \
  --tagging-active-path data/tagging/document_tags_raw_active.jsonl \
  --failures-path data/tagging/document_tagging_failures_active.jsonl \
  --empty-candidates-path data/tagging/empty_documents_name_candidates.jsonl \
  --out data/normalization
```

## How To Check

```bash
ls -lah data/normalization
sed -n '1,220p' data/normalization/normalization_n1_report.json
head -n 3 data/normalization/tag_mentions_raw.jsonl
head -n 3 data/normalization/tag_mentions_normalized.jsonl
head -n 3 data/normalization/auto_clusters.jsonl
.venv/bin/python -m unittest discover -s tests
```

## Commands Run

```bash
.venv/bin/python -m py_compile kb_rebuild/normalization/text.py kb_rebuild/normalization/mentions.py kb_rebuild/normalization/auto_cluster.py kb_rebuild/normalization/report.py kb_rebuild/normalization/n1_runner.py kb_rebuild/cli.py
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m kb_rebuild normalize-n1 --data data
```

## Test Results

- `py_compile`: passed
- `unittest discover`: 63 tests passed
- Production N1 run: completed

## Results

- `mentions_total`: 42,324
- `unique_raw_values`: 22,710
- `unique_normalized_values`: 22,116
- `auto_clusters_total`: 22,993
- `auto_clusters_review_required`: 10,285
- `suspicious_mentions`: 25,184
- `quote_issue_mentions`: 300
- `failed_documents_count`: 20
- `invalid_tagging_records`: 0
- `documents_with_tags`: 16,161

## Top Entity Types

| entity_type | mentions |
|---|---:|
| disease | 21,132 |
| diagnostic_method | 5,439 |
| biological_substance | 2,695 |
| drug_class | 2,640 |
| procedure | 2,560 |
| drug_trade_name | 2,005 |
| microorganism | 1,412 |
| symptom | 1,046 |
| medical_concept | 775 |
| supplement | 744 |
| organ_or_body_system | 566 |
| cell_or_biological_structure | 455 |
| other | 341 |
| medical_device | 310 |
| instruction | 119 |
| immunobiological_preparation | 85 |

## Top Tag Roles

| tag_role | mentions |
|---|---:|
| context_only | 20,968 |
| article_candidate | 19,747 |
| folder_candidate | 1,609 |

## Top Raw Tags

| raw tag | mentions |
|---|---:|
| Генетическое тестирование | 443 |
| Магнитно-резонансная томография | 430 |
| Электромиография | 233 |
| Оптическая когерентная томография | 212 |
| Коэнзим Q10 | 169 |
| Вирус папилломы человека | 167 |
| Эхокардиография | 140 |
| Кортикостероиды | 135 |
| Дерматоскопия | 125 |
| Магнитно-резонансная томография головного мозга | 107 |
| Колоноскопия | 89 |
| Компьютерная томография | 87 |
| Ультразвуковое исследование | 84 |
| Биопсия | 82 |
| Электроэнцефалография | 82 |
| Когнитивно-поведенческая терапия | 80 |
| Helicobacter pylori | 75 |
| GJB2 | 73 |
| Артериальная гипертензия | 73 |
| Сахарный диабет | 70 |
| Маммография | 70 |
| Электроретинография | 69 |
| Цистоскопия | 66 |
| Биопсия кожи | 60 |
| Нестероидные противовоспалительные препараты | 60 |
| Аудиометрия | 60 |
| Болезнь Крона | 58 |
| Бисфосфонаты | 56 |
| Трансплантация костного мозга | 52 |
| Альфа-фетопротеин | 52 |
| Бета-адреноблокаторы | 49 |
| Полимеразная цепная реакция | 48 |
| Электрокардиография | 47 |
| Остеопороз | 46 |
| Катаракта | 46 |
| Биопсия почки | 45 |
| Сердечная недостаточность | 45 |
| Биомикроскопия глаза | 45 |
| Химиотерапия | 44 |
| Кохлеарный имплантат | 43 |
| Кератопластика | 43 |
| Рентгенография | 43 |
| Синдром Ли-Фраумени | 43 |
| Золотистый стафилококк | 42 |
| Электронейромиография | 42 |
| Спирометрия | 41 |
| Вальпроевая кислота | 39 |
| Ларингоскопия | 38 |
| Плазмаферез | 38 |
| Гидроцефалия | 38 |

## Top Normalized Tags

| normalized tag | mentions |
|---|---:|
| генетическое тестирование | 450 |
| магнитно-резонансная томография | 438 |
| электромиография | 235 |
| оптическая когерентная томография | 216 |
| коэнзим q10 | 169 |
| вирус папилломы человека | 167 |
| эхокардиография | 143 |
| кортикостероиды | 137 |
| дерматоскопия | 128 |
| магнитно-резонансная томография головного мозга | 108 |
| колоноскопия | 90 |
| компьютерная томография | 89 |
| электроэнцефалография | 85 |
| ультразвуковое исследование | 84 |
| биопсия | 83 |
| когнитивно-поведенческая терапия | 82 |
| helicobacter pylori | 75 |
| артериальная гипертензия | 74 |
| gjb2 | 73 |
| сахарный диабет | 72 |
| маммография | 72 |
| электроретинография | 69 |
| цистоскопия | 66 |
| аудиометрия | 64 |
| биопсия кожи | 62 |
| нестероидные противовоспалительные препараты | 62 |
| болезнь крона | 58 |
| бисфосфонаты | 56 |
| трансплантация костного мозга | 54 |
| бета-адреноблокаторы | 52 |
| альфа-фетопротеин | 52 |
| остеопороз | 50 |
| полимеразная цепная реакция | 49 |
| электрокардиография | 47 |
| биопсия почки | 46 |
| катаракта | 46 |
| кохлеарный имплантат | 45 |
| химиотерапия | 45 |
| рентгенография | 45 |
| сердечная недостаточность | 45 |
| биомикроскопия глаза | 45 |
| кератопластика | 44 |
| синдром ли-фраумени | 43 |
| спирометрия | 42 |
| золотистый стафилококк | 42 |
| электронейромиография | 42 |
| глюкокортикостероиды | 39 |
| ларингоскопия | 39 |
| язвенный колит | 39 |
| вальпроевая кислота | 39 |

## What Was Not Done

- LLM merge was not implemented.
- Candidate pairs/groups for N2 were not implemented.
- LLM cluster validation for N3 was not implemented.
- Final `tags_canonical.csv` was not created.
- Final `tag_aliases.csv` was not created.
- Final `document_tag_links_normalized.jsonl` was not created.
- Empty-document name-based tagging/recovery was not implemented.

## Risks

- Product form cleanup is conservative, but brand names that contain dosage-form words may still need review.
- Abbreviations are intentionally not auto-merged; they require N2/N3 validation.
- Parent-child disease terms and specificity modifiers require N2/N3 validation.
- Many `context_only` mentions are expected and preserved, but downstream must not treat them as article entities.
- `mixed_cyrillic_latin` is noisy for strings with type numbers like `1B`; it is a review signal, not a hard error.

## N2 Notes

- Candidate generation should operate only within `entity_type`.
- Use `auto_clusters.jsonl` as deterministic groups and `suspicious_mentions.jsonl` for review/candidate priority.
- Focus N2 on abbreviations, Latin/Russian aliases, product-name variants, and high-frequency normalized aliases.
- Avoid connected-component transitive merge without validation.

## Questions For Architect

- Should `mixed_cyrillic_latin` ignore terminal subtype markers like `1B`, `2A`, and gene-like symbols for disease names?
- Should N2 prioritize high-frequency `context_only` diagnostic methods, or keep article candidates first?
- Should product cleanup maintain an allowlist of brands where form words are part of the commercial name?

# Article Planning A0 Feedback

ТЗ перечитано на этапах: after_plan, after_loaders, after_matching_logic, after_window_builder, after_strategy_logic, after_tests, before_production_run, before_feedback

## 1. Что сделано

- Добавлен deterministic A0 package `kb_rebuild/articles/planning`.
- Добавлена CLI-команда `article-plan-a0`.
- Реализованы загрузка final normalization + parsed artifacts, alias dictionary, quote/alias/title/fallback matching, source window builder, strategy selection, reports и manifest.
- Создан production planning layer в `data/articles/planning/`.
- LLM, Gemini, OpenRouter и web search не вызывались.

## 2. Какие файлы изменены

Docs:

- `docs/article_planning_a0_plan.md`
- `docs/article_planning_a0_feedback.md`

Code:

- `kb_rebuild/cli.py`
- `kb_rebuild/articles/__init__.py`
- `kb_rebuild/articles/planning/__init__.py`
- `kb_rebuild/articles/planning/models.py`
- `kb_rebuild/articles/planning/loaders.py`
- `kb_rebuild/articles/planning/matching.py`
- `kb_rebuild/articles/planning/windows.py`
- `kb_rebuild/articles/planning/strategy.py`
- `kb_rebuild/articles/planning/report.py`
- `kb_rebuild/articles/planning/runner.py`

Tests:

- `tests/test_article_planning_loaders.py`
- `tests/test_article_planning_matching.py`
- `tests/test_article_planning_windows.py`
- `tests/test_article_planning_strategy.py`
- `tests/test_article_planning_runner.py`

Production outputs:

- `data/articles/planning/tag_source_index.jsonl`
- `data/articles/planning/tag_work_plan.jsonl`
- `data/articles/planning/source_block_windows.jsonl`
- `data/articles/planning/direct_copy_candidates.jsonl`
- `data/articles/planning/singleton_candidates.jsonl`
- `data/articles/planning/stub_only_tags.jsonl`
- `data/articles/planning/review_stub_tags.jsonl`
- `data/articles/planning/no_source_window_tags.jsonl`
- `data/articles/planning/article_planning_report.json`
- `data/articles/planning/article_planning_manifest.json`
- `data/articles/planning/tag_work_plan.csv`
- `data/articles/planning/strategy_summary_by_entity_type.csv`
- `data/articles/planning/high_frequency_tags.csv`
- `data/articles/planning/source_window_quality_report.csv`

## 3. Какие команды запускались

```bash
.venv/bin/python -m py_compile kb_rebuild/articles/planning/models.py kb_rebuild/articles/planning/loaders.py kb_rebuild/articles/planning/matching.py kb_rebuild/articles/planning/windows.py kb_rebuild/articles/planning/strategy.py kb_rebuild/articles/planning/report.py kb_rebuild/articles/planning/runner.py kb_rebuild/cli.py
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m kb_rebuild article-plan-a0 --data data --normalization-final-dir data/normalization/final --parsed-dir data/parsed --normalization-dir data/normalization --out data/articles/planning --max-neighbor-blocks 2 --max-window-chars 12000 --short-document-char-limit 12000 --high-frequency-doc-threshold 20 --low-count-doc-threshold 3
```

## 4. Tests

- Compile check: passed.
- Full test suite: 184 tests passed.

## 5. Final tags обработано

- `final_tags_total`: 22,513
- `tag_source_index.jsonl`: 22,513 rows
- `tag_work_plan.jsonl`: 22,513 rows
- `tags_with_mentions`: 22,513
- `tags_without_mentions`: 0

## 6. Source windows

- `source_windows_total`: 57,925
- `high_quality_windows`: 57,477
- `medium_quality_windows`: 428
- `low_quality_windows`: 20

Window match methods:

```json
{
  "alias_match": 16350,
  "mention_only_fallback": 20,
  "quote_match": 41541,
  "short_doc_fallback": 2,
  "title_match": 12
}
```

## 7. Strategy counts

```json
{
  "direct_copy_candidate": 6344,
  "high_frequency_map_reduce": 71,
  "low_count_batch_extract": 1482,
  "multi_doc_map_reduce": 727,
  "review_stub": 3349,
  "single_doc_extract": 6701,
  "stub_only": 3839
}
```

## 8. Strategy counts by entity_type

Подробный CSV создан:

```text
data/articles/planning/strategy_summary_by_entity_type.csv
```

Крупнейшие группы:

- `disease`: 5,290 direct copy, 5,579 single doc extract, 1,414 review stub, 931 low count, 440 multi doc, 30 high frequency, 539 stub only.
- `drug_trade_name`: 638 direct copy, 61 single doc extract, 23 review stub, 253 low count, 63 multi doc, 194 stub only.
- `diagnostic_method`: 141 single doc extract, 294 review stub, 40 low count, 39 multi doc, 20 high frequency, 416 stub only.

## 9-13. Candidate counts

- `direct_copy_candidates`: 6,344
- `singleton_candidates`: 18,018
- `stub_only_tags`: 3,839
- `review_stub_tags`: 3,349
- `no_source_window_tags`: 0

## 14. Оценка будущих LLM tasks

- `estimated_llm_extraction_tasks`: 27,555
- `estimated_article_compilation_tasks`: 8,981

Direct copy и stub/review paths не включены в LLM task estimate.

## 15. Топ high-frequency tags

| tag_id | canonical_tag_ru | entity_type | docs | windows | strategy |
|---|---|---|---:|---:|---|
| `diagnostic_method_cb21d54b40` | Генетическое тестирование | diagnostic_method | 450 | 450 | review_stub |
| `diagnostic_method_ae7b5dcf5a` | Магнитно-резонансная томография | diagnostic_method | 438 | 480 | review_stub |
| `diagnostic_method_c046c3523a` | Электромиография | diagnostic_method | 235 | 236 | high_frequency_map_reduce |
| `diagnostic_method_6cda66529f` | Оптическая когерентная томография | diagnostic_method | 216 | 220 | review_stub |
| `microorganism_326752262d` | Вирус папилломы человека | microorganism | 167 | 231 | high_frequency_map_reduce |
| `supplement_7fa11b45f2` | Коэнзим Q10 | supplement | 166 | 167 | review_stub |
| `diagnostic_method_b0d633ea7b` | Эхокардиография | diagnostic_method | 143 | 172 | high_frequency_map_reduce |
| `drug_class_39dceb5a94` | Кортикостероиды | drug_class | 137 | 189 | review_stub |
| `diagnostic_method_5831243dbd` | Дерматоскопия | diagnostic_method | 128 | 145 | high_frequency_map_reduce |
| `diagnostic_method_c357f3a785` | Магнитно-резонансная томография головного мозга | diagnostic_method | 116 | 118 | review_stub |

## 16. Примеры direct_copy candidates

- `biological_substance_85054c0be3` — Иммуноглобулин тяжелой и легкой цепи, `doc_005876_3cbeefcc`, coverage 1.0.
- `biological_substance_372c6c9dbb` — Магния сульфат, `doc_007632_51ba2d72`, coverage 1.0.
- `biological_substance_d3c89cb841` — Норадреналин, `doc_009210_7d60bd1f`, coverage 1.0.
- `biological_substance_25b3113b1b` — Рокурония бромид, `doc_011820_36ab0db8`, coverage 1.0.
- `disease_5f523380ae` — 2-аминоадипиновая 2-оксоадипиновая ацидурия, `doc_000051_bbb98c1e`, coverage 1.0.

## 17. Примеры no_source_window cases

No-source cases отсутствуют:

```text
data/articles/planning/no_source_window_tags.jsonl = 0 rows
```

Есть 20 low-quality `mention_only_fallback` windows; они сохранены как source windows с review flag, поэтому не попали в no-source.

## 18. Что не сделано

- Не создавались final article JSON.
- Не создавались evidence items или quotes JSON.
- Не вызывались LLM/Gemini/OpenRouter.
- Не менялись `data/normalization/*`, `data/parsed/*`, `data/tagging/*`.
- Не строились папки и graph knowledge.
- Direct copy candidates только предложены, фактического копирования на A0 нет.

## 19. Риски

- 9,325 tags имеют `need_review=true`; A0 маршрутизирует критические cases в `review_stub`, но review policy следующего этапа всё равно должна учитывать эти flags.
- 20 windows построены через `mention_only_fallback`; они низкого качества и требуют отдельной QA-проверки перед evidence extraction.
- 6,344 direct copy candidates являются candidates, а не разрешением на автоматическое создание статей; A1 должен валидировать Editor.js copy policy.
- High-frequency tags часто являются review-heavy; для A2 понадобится ограничение окон, дедупликация и batching.

## 20. Что передать следующему этапу

Главный output следующего этапа:

```text
data/articles/planning/tag_work_plan.jsonl
data/articles/planning/source_block_windows.jsonl
```

Дополнительно передать:

```text
data/articles/planning/direct_copy_candidates.jsonl
data/articles/planning/singleton_candidates.jsonl
data/articles/planning/review_stub_tags.jsonl
data/articles/planning/source_window_quality_report.csv
data/articles/planning/article_planning_report.json
data/articles/planning/article_planning_manifest.json
```

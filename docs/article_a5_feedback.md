# Article A5 Feedback

## Что сделано

A5 реализован как детерминированный финальный экспорт статей без LLM/web-вызовов. Экспорт собран по всем `tag_id` из A1, с приоритетом A4 compiled drafts, затем A1 direct/stub/review, затем A3 `insufficient_evidence_review`. Для каждого тега созданы article JSON для n8n и docs, companion quotes/questions JSON для docs, индексы, coverage audit, manifest/report и QA CSV.

Имена экспортных файлов используют формат `{entity_type}_{canonical_tag_ru}.json`; если `canonical_tag_ru` пустой, используется `canonical_tag_latin`. Для quotes используется `{entity_type}_{canonical_name}_quotes.json`. Небезопасные символы нормализуются, при коллизии добавляется suffix с `tag_id`.

Главный output для n8n:
data/articles/final_exports/for_n8n/

Главный output для docs:
data/articles/final_exports/for_docs/

Все 22 513 tag_id экспортированы: yes

## Какие файлы изменены

- `docs/article_a5_plan.md`
- `docs/article_a5_feedback.md`
- `kb_rebuild/cli.py`
- `kb_rebuild/articles/a5/__init__.py`
- `kb_rebuild/articles/a5/models.py`
- `kb_rebuild/articles/a5/loaders.py`
- `kb_rebuild/articles/a5/source_selection.py`
- `kb_rebuild/articles/a5/editorjs.py`
- `kb_rebuild/articles/a5/quotes.py`
- `kb_rebuild/articles/a5/exporter.py`
- `kb_rebuild/articles/a5/report.py`
- `kb_rebuild/articles/a5/runner.py`
- `tests/test_article_a5_source_selection.py`
- `tests/test_article_a5_editorjs.py`
- `tests/test_article_a5_quotes.py`
- `tests/test_article_a5_exporter.py`
- `tests/test_article_a5_runner.py`
- `tests/test_article_a5_report.py`

## Команды

- `.venv/bin/python -m py_compile kb_rebuild/cli.py kb_rebuild/articles/a5/__init__.py kb_rebuild/articles/a5/models.py kb_rebuild/articles/a5/loaders.py kb_rebuild/articles/a5/source_selection.py kb_rebuild/articles/a5/editorjs.py kb_rebuild/articles/a5/quotes.py kb_rebuild/articles/a5/exporter.py kb_rebuild/articles/a5/report.py kb_rebuild/articles/a5/runner.py`
- `.venv/bin/python -m unittest tests.test_article_a5_source_selection tests.test_article_a5_editorjs tests.test_article_a5_quotes tests.test_article_a5_exporter tests.test_article_a5_runner tests.test_article_a5_report`
- `.venv/bin/python -m unittest discover -s tests`
- `.venv/bin/python -m kb_rebuild article-a5-export --data data --a1-dir data/articles/a1 --a3-dir data/articles/a3 --a4-dir data/articles/a4/production_v1 --entities-dir data/articles/entities --normalization-final-dir data/normalization/final --out data/articles/final_exports --overwrite`

## Tests passed

- A5 targeted tests: 22 tests passed.
- Full suite: 305 tests passed.
- Production A5 command completed with `quality_passed=True`.

## Итоговые counts

- `final_tags_total`: 22513
- `for_n8n_article_files`: 22513
- `for_docs_article_files`: 22513
- `for_docs_quotes_files`: 22513
- `questions_total`: 57877
- `quotes_total`: 57877

## Counts by article_status

| article_status | count |
|---|---:|
| compiled_article | 2960 |
| compiled_with_review_flag | 6788 |
| direct_copy_article | 6806 |
| insufficient_evidence_review | 103 |
| review_stub | 2017 |
| stub_only | 3839 |

## Counts by entity_type

| entity_type | count |
|---|---:|
| biological_substance | 1318 |
| cell_or_biological_structure | 209 |
| diagnostic_method | 950 |
| disease | 14223 |
| drug_class | 670 |
| drug_trade_name | 1232 |
| immunobiological_preparation | 48 |
| instruction | 95 |
| medical_concept | 660 |
| medical_device | 153 |
| microorganism | 505 |
| organ_or_body_system | 270 |
| other | 232 |
| procedure | 919 |
| supplement | 432 |
| symptom | 597 |

## Coverage audit result

`data/articles/final_exports/export_coverage_audit.json`:

- `passed`: true
- `all_tags_exported_to_for_n8n`: true
- `for_n8n_flat`: true
- `all_tags_exported_to_for_docs`: true
- `all_for_docs_have_quotes_file`: true
- `article_export_index_complete`: true
- `quotes_index_complete`: true
- `no_duplicate_filenames`: true
- `no_missing_tag_id`: true
- `all_articles_valid_editorjs`: true
- `all_content_format_editorjs`: true
- `all_for_docs_quotes_files_valid_json`: true
- `duplicate_filenames`: 0

## Примеры файлов

for_n8n:

- `data/articles/final_exports/for_n8n/microorganism_Микоплазма гениталиум.json`
- `data/articles/final_exports/for_n8n/biological_substance_1-альфа-гидроксилаза.json`

for_docs:

- `data/articles/final_exports/for_docs/microorganism/microorganism_Микоплазма гениталиум.json`
- `data/articles/final_exports/for_docs/biological_substance/biological_substance_1-альфа-гидроксилаза.json`

quotes companion:

- `data/articles/final_exports/for_docs/microorganism/microorganism_Микоплазма гениталиум_quotes.json`
- `data/articles/final_exports/for_docs/biological_substance/biological_substance_1-альфа-гидроксилаза_quotes.json`

## Repaired / missing / quality issues

- `malformed_editorjs_repaired`: 0
- `missing_article_source`: 0
- `missing_tags`: 0
- `duplicate_filenames`: 0
- `export_quality_issues`: 0
- `export_quality_issues.jsonl`: 0 rows
- `export_missing_tags.csv`: header only
- `export_duplicate_filenames.csv`: header only

## Что передать дальше

Для n8n передавать:

- `data/articles/final_exports/for_n8n/`
- при необходимости контрольный индекс `data/articles/final_exports/article_export_index.csv`

Для docs hierarchy stage передавать:

- `data/articles/final_exports/for_docs/`
- `data/articles/final_exports/article_export_index.jsonl`
- `data/articles/final_exports/quotes_index.jsonl`
- `data/articles/final_exports/export_coverage_audit.json`

ТЗ перечитано на этапах: after_plan, after_source_selection, after_editorjs_validation, after_quotes_builder, after_exporter, after_tests, before_production_run, before_feedback

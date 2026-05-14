# Article A5 Export Plan

## Понимание этапа

A5 - детерминированный финальный экспорт статей по всем `tag_id` из A1. Этап не вызывает LLM или web, не меняет A1-A4 и normalization, не создает новые факты и не переписывает медицинский контент. Его задача - собрать единый экспорт для n8n и docs, сохранить review-флаги и доказуемо проверить полноту.

## Входы

- A1: `article_status_index.jsonl`, `a1_report.json`, `a1_manifest.json`, `data/articles/entities/`.
- A3: `a4_compilation_input.jsonl`, `fact_groups.jsonl`, `tag_fact_group_index.jsonl`, `a3_report.json`, `a3_manifest.json`.
- A4: `data/articles/a4/production_v1/article_drafts.jsonl`, `a4_report.json`, `a4_manifest.json`, `article_quality_diagnostics.json`.
- N4 final: `tags_canonical.csv`, `tag_aliases.csv`, `final_normalization_report.json`, `final_normalization_manifest.json`.

## Политика выбора источника

1. Если для `tag_id` есть A4 draft со статусом `compiled_article` или `compiled_with_review_flag`, экспортируется A4.
2. Иначе `direct_copy_article`, `stub_only` и `review_stub` берутся из A1 entity JSON.
3. Если A3 пометил тег как `insufficient_evidence_review`, а A4 draft отсутствует, экспортируется A1 entity JSON с финальным статусом `insufficient_evidence_review`.
4. Если источник не найден или невалиден, создается безопасная review-заглушка со статусом `export_repair_stub`, причина пишется в quality issues и итоговый quality gate падает.

## Выходы

- `data/articles/final_exports/for_n8n/{entity_type}_{canonical_name}.json` - плоский экспорт без подкаталогов.
- `data/articles/final_exports/for_docs/{entity_type}/{entity_type}_{canonical_name}.json` - экспорт для docs.
- `data/articles/final_exports/for_docs/{entity_type}/{entity_type}_{canonical_name}_quotes.json` - companion файл вопросов и цитат.
- Индексы, отчеты и QA: `article_export_index.*`, `quotes_index.*`, `export_coverage_audit.json`, `export_quality_issues.jsonl`, `manual_qa_export_sample.csv`, distributions, `a5_report.json`, `a5_manifest.json`.

`canonical_name` берется из `canonical_tag_ru`; если ru пустой, используется `canonical_tag_latin`. Небезопасные символы в имени файла заменяются, а при коллизии добавляется suffix с `tag_id`.

## Quotes

Для A4-статей companion строится из `used_fact_group_ids` и A3 `fact_groups.jsonl`. В quotes попадают только `usable_for_a4=true` и quote status `exact` или `normalized_exact`. Для direct copy и stub/review статусов quotes остаются пустыми с объясняющим `quotes_source_status`.

Вопросы генерируются детерминированно по `fact_type`; дубликаты вопроса получают уточнение по `section_hint` или типу факта.

## Editor.js

Контент валидируется как объект Editor.js с непустым `blocks`. Поддерживаются `header`, `paragraph`, `list`, `table`; у каждого блока должен быть объект `data`, у текстовых блоков - непустой текст. Если источник сломан, A5 не чинит медицинский текст, а заменяет контент безопасной review-заглушкой.

## Coverage

Quality gate должен подтвердить:

- ровно один JSON в `for_n8n` на каждый final tag и отсутствие подкаталогов;
- ровно один article JSON и один quotes JSON в `for_docs` на каждый final tag;
- индексы покрывают все `tag_id`;
- нет missing tag_id и duplicate filenames;
- все JSON валидны, `content_format=editorjs`, `content.blocks` существует;
- все quotes-файлы валидны;
- A1, A3, A4 и N4 input quality gates пройдены, A4 не имеет failed tasks или article quality issues.

## Тесты

Покрыть:

- source selection;
- Editor.js validation и safe repair stub;
- quotes/question builder;
- exporter paths and duplicate detection;
- runner smoke на маленьком fixture;
- report quality gate.

Проверки перед production: `py_compile` для A5/CLI, targeted A5 tests, полный `unittest discover`.

## Риски

- Фактическая A3/A4 схема может содержать неполные списки source ids; экспорт должен нормализовать пустые списки без падения.
- Старые файлы в output могут исказить coverage; при `--overwrite` A5 очищает только собственные поддиректории и известные файлы внутри `out`.
- Canonical names могут содержать `/`, кавычки, управляющие символы, очень длинный текст или дубли; filename builder должен сохранять читаемость, но гарантировать безопасный путь и уникальность.
- Review-документы не блокируют экспорт, но должны сохранять review status/reasons.

## Checklist

- [x] Перечитать ТЗ: `after_plan`.
- [x] Реализовать модели, загрузчики и source selection.
- [x] Перечитать ТЗ: `after_source_selection`.
- [x] Реализовать Editor.js validation/repair.
- [x] Перечитать ТЗ: `after_editorjs_validation`.
- [x] Реализовать quotes builder.
- [x] Перечитать ТЗ: `after_quotes_builder`.
- [x] Реализовать exporter/report/runner/CLI.
- [x] Перечитать ТЗ: `after_exporter`.
- [x] Добавить и выполнить targeted A5 tests.
- [x] Выполнить полный test suite.
- [x] Перечитать ТЗ: `after_tests`.
- [x] Запустить production export.
- [x] Проверить production artifacts.
- [x] Перечитать ТЗ: `before_feedback`.
- [x] Заполнить `docs/article_a5_feedback.md`.

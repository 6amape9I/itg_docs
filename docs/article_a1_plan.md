# Article A1 Plan

## Что понял

A1 должен создать bootstrap layer для всех финальных сущностей после A0. Главный результат:

```text
data/articles/entities/{entity_type}/{tag_id}.json
data/articles/a1/article_status_index.jsonl
data/articles/a1/a2_extraction_task_queue.jsonl
```

A1 не пишет полноценные LLM-статьи. Этап делает A0.1 strategy repair, создаёт stub/review/direct-copy/pending entity JSON, строит A2 extraction task queue и гарантирует покрытие всех final `tag_id`.

## Как реализую A0.1

Создам adjusted слой, не меняя A0 outputs:

```text
data/articles/a1/a0_1_strategy_adjustments.jsonl
data/articles/a1/tag_work_plan_adjusted.jsonl
data/articles/a1/tag_work_plan_adjusted.csv
data/articles/a1/a0_1_strategy_adjustment_report.json
```

Правила:

- `review_stub` + `article_candidate=true` + `documents_count>0` + `source_windows_count>0` + no article-blocking reasons -> reroute в article pipeline.
- Blocking reasons: `drug_policy_review`, `drug_trade_name_active_substance_conflict`, `merge_conflict`, `entity_type_conflict`, `rejected_constraint_conflict`, `unresolved_review`, `unresolved review`, `empty_canonical_tag_ru`, `canonical_empty`, `unknown_node_id`, `critical_merge_conflict`.
- Publication-review reasons, включая `alias_conflict` и `n1_review_required`, не блокируют статью, но ставят `needs_review_before_publication=true`.
- `article_candidate=false` не превращается в article strategy.
- `source_windows_count=0` остаётся review/no-source path.

## Inputs

A0 planning:

```text
data/articles/planning/tag_source_index.jsonl
data/articles/planning/tag_work_plan.jsonl
data/articles/planning/source_block_windows.jsonl
data/articles/planning/direct_copy_candidates.jsonl
data/articles/planning/singleton_candidates.jsonl
data/articles/planning/article_planning_report.json
data/articles/planning/article_planning_manifest.json
```

Normalization final:

```text
data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv
data/normalization/final/document_tag_links_normalized.jsonl
data/normalization/final/document_tags_normalized_by_doc.jsonl
data/normalization/final/final_normalization_report.json
data/normalization/final/final_normalization_manifest.json
```

Parsed:

```text
data/parsed/parsed_documents.jsonl
data/parsed/document_blocks.jsonl
```

## Files изменю

Создам:

```text
kb_rebuild/articles/a1/__init__.py
kb_rebuild/articles/a1/models.py
kb_rebuild/articles/a1/strategy_repair.py
kb_rebuild/articles/a1/entity_json.py
kb_rebuild/articles/a1/direct_copy.py
kb_rebuild/articles/a1/task_queue.py
kb_rebuild/articles/a1/report.py
kb_rebuild/articles/a1/runner.py
```

Изменю:

```text
kb_rebuild/cli.py
```

Tests:

```text
tests/test_article_a1_strategy_repair.py
tests/test_article_a1_entity_json.py
tests/test_article_a1_direct_copy.py
tests/test_article_a1_task_queue.py
tests/test_article_a1_runner.py
```

Docs:

```text
docs/article_a1_plan.md
docs/article_a1_feedback.md
```

## Outputs

A1 directory:

```text
data/articles/a1/tag_work_plan_adjusted.jsonl
data/articles/a1/tag_work_plan_adjusted.csv
data/articles/a1/a0_1_strategy_adjustments.jsonl
data/articles/a1/a0_1_strategy_adjustment_report.json
data/articles/a1/article_status_index.jsonl
data/articles/a1/article_status_index.csv
data/articles/a1/direct_copy_articles.jsonl
data/articles/a1/stub_articles.jsonl
data/articles/a1/review_stub_articles.jsonl
data/articles/a1/pending_extraction_articles.jsonl
data/articles/a1/a2_extraction_task_queue.jsonl
data/articles/a1/a2_extraction_task_queue.csv
data/articles/a1/a1_report.json
data/articles/a1/a1_manifest.json
data/articles/a1/direct_copy_rejected.jsonl
data/articles/a1/direct_copy_validation_report.csv
data/articles/a1/publication_review_queue.jsonl
data/articles/a1/hard_review_queue.jsonl
data/articles/a1/article_file_coverage_audit.json
data/articles/a1/article_file_coverage_missing_tags.csv
```

Entity JSON:

```text
data/articles/entities/{entity_type}/{tag_id}.json
```

## Entity JSON

Каждый final `tag_id` получает один JSON с required fields из ТЗ:

- status: `stub_only`, `review_stub`, `direct_copy_article`, `pending_single_doc_extract`, `pending_low_count_batch_extract`, `pending_multi_doc_map_reduce`, `pending_high_frequency_map_reduce`, либо `failed_or_blocked`.
- `content_format=editorjs`.
- Stub/review/pending content не добавляет медицинских фактов.
- `sources` и `provenance` ссылаются на planning/A1 artifacts.

## Direct Copy Validation

`direct_copy_candidate` станет `direct_copy_article` только если:

- `article_candidate=true`
- `needs_review_before_article=false`
- `documents_count=1`
- `source_windows_count>=1`
- `competing_article_candidate_tags_in_doc=0`
- best window quality high/medium
- coverage >= 0.8 или `short_doc_fallback`
- source document exists
- parsed blocks exist and are not empty

Если validation fails, status станет `pending_single_doc_extract`, запись попадёт в `direct_copy_rejected.jsonl`.

## A2 Task Queue

Для pending extraction стратегий создам task по каждому source window:

```text
single_doc_extract
low_count_batch_extract
multi_doc_map_reduce
high_frequency_map_reduce
```

Не создаю tasks для `stub_only`, `review_stub`, `direct_copy_article`.

Low-quality windows получают:

- `priority=low`
- `needs_review_before_publication=true`
- `review_reasons += ["low_quality_source_window"]`

## Tests

Покрытие:

- A0.1 reroute для alias_conflict-only.
- Hard blockers остаются `review_stub`.
- Entity JSON required fields и Editor.js skeleton.
- Direct copy accept/reject и source block metadata.
- A2 queue creation and priority.
- Runner outputs, coverage audit, missing manifest/report failures.

## Риски

- 22,513 entity JSON файлов создаются массово; overwrite должен быть явным через default run, а `--no-overwrite` обязан защищать outputs.
- Direct copy candidates являются только candidates; validation должна быть строгой и отбраковывать сомнительные cases.
- Publication-review rerouting не снимает review, а переносит его в `needs_review_before_publication`.
- A2 queue может быть крупной; важно сохранить window text/block ids без LLM calls.

## Чеклист

- [x] Прочитать `instructions/01_a1_article.md`.
- [x] Прочитать A0 feedback/report/manifest и samples A0 outputs.
- [x] Создать этот план.
- [x] Перечитать ТЗ на checkpoint `after_plan`.
- [x] Реализовать A0.1 strategy repair.
- [x] Перечитать ТЗ на checkpoint `after_strategy_repair`.
- [x] Реализовать entity JSON logic.
- [x] Перечитать ТЗ на checkpoint `after_entity_json_logic`.
- [x] Реализовать direct copy validation.
- [x] Перечитать ТЗ на checkpoint `after_direct_copy_logic`.
- [x] Реализовать A2 task queue.
- [x] Перечитать ТЗ на checkpoint `after_task_queue_logic`.
- [x] Реализовать report/runner и CLI.
- [x] Добавить tests.
- [x] Перечитать ТЗ на checkpoint `after_tests`.
- [x] Запустить compile check и tests.
- [x] Перечитать ТЗ на checkpoint `before_production_run`.
- [x] Запустить production A1.
- [x] Проверить coverage audit и обязательные outputs.
- [x] Перечитать ТЗ на checkpoint `before_feedback`.
- [x] Создать `docs/article_a1_feedback.md`.

ТЗ перечитывается на этапах: after_plan, after_strategy_repair, after_entity_json_logic, after_direct_copy_logic, after_task_queue_logic, after_tests, before_production_run, before_feedback.

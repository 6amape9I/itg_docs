# Article A1 Feedback

ТЗ перечитано на этапах: after_plan, after_strategy_repair, after_entity_json_logic, after_direct_copy_logic, after_task_queue_logic, after_tests, before_production_run, before_feedback

## 1. Что сделано

- Реализован A1 `Entity JSON Bootstrap + A0.1 Strategy Repair`.
- Создан adjusted work plan, который не меняет A0 outputs.
- `review_stub` с non-blocking publication-review reasons rerouted в article pipeline.
- Создан один entity JSON на каждый final `tag_id`.
- Созданы status index, direct/stub/review/pending индексы, A2 extraction task queue, report, manifest и coverage audit.
- LLM/Gemini/OpenRouter/web search не вызывались.

## 2. Какие файлы изменены

Docs:

- `docs/article_a1_plan.md`
- `docs/article_a1_feedback.md`

Code:

- `kb_rebuild/cli.py`
- `kb_rebuild/articles/a1/__init__.py`
- `kb_rebuild/articles/a1/models.py`
- `kb_rebuild/articles/a1/strategy_repair.py`
- `kb_rebuild/articles/a1/entity_json.py`
- `kb_rebuild/articles/a1/direct_copy.py`
- `kb_rebuild/articles/a1/task_queue.py`
- `kb_rebuild/articles/a1/report.py`
- `kb_rebuild/articles/a1/runner.py`

Tests:

- `tests/test_article_a1_strategy_repair.py`
- `tests/test_article_a1_entity_json.py`
- `tests/test_article_a1_direct_copy.py`
- `tests/test_article_a1_task_queue.py`
- `tests/test_article_a1_runner.py`

Production outputs:

- `data/articles/a1/tag_work_plan_adjusted.jsonl`
- `data/articles/a1/tag_work_plan_adjusted.csv`
- `data/articles/a1/a0_1_strategy_adjustments.jsonl`
- `data/articles/a1/a0_1_strategy_adjustment_report.json`
- `data/articles/a1/article_status_index.jsonl`
- `data/articles/a1/article_status_index.csv`
- `data/articles/a1/direct_copy_articles.jsonl`
- `data/articles/a1/stub_articles.jsonl`
- `data/articles/a1/review_stub_articles.jsonl`
- `data/articles/a1/pending_extraction_articles.jsonl`
- `data/articles/a1/a2_extraction_task_queue.jsonl`
- `data/articles/a1/a2_extraction_task_queue.csv`
- `data/articles/a1/a1_report.json`
- `data/articles/a1/a1_manifest.json`
- `data/articles/a1/direct_copy_rejected.jsonl`
- `data/articles/a1/direct_copy_validation_report.csv`
- `data/articles/a1/publication_review_queue.jsonl`
- `data/articles/a1/hard_review_queue.jsonl`
- `data/articles/a1/article_file_coverage_audit.json`
- `data/articles/a1/article_file_coverage_missing_tags.csv`
- `data/articles/entities/{entity_type}/{tag_id}.json`

## 3. Какие команды запускались

```bash
.venv/bin/python -m py_compile kb_rebuild/articles/a1/models.py kb_rebuild/articles/a1/strategy_repair.py kb_rebuild/articles/a1/entity_json.py kb_rebuild/articles/a1/direct_copy.py kb_rebuild/articles/a1/task_queue.py kb_rebuild/articles/a1/report.py kb_rebuild/articles/a1/runner.py kb_rebuild/cli.py
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m kb_rebuild article-a1-bootstrap --data data --articles-planning-dir data/articles/planning --normalization-final-dir data/normalization/final --parsed-dir data/parsed --out data/articles/a1 --entities-out data/articles/entities
```

## 4. Tests

- Compile check: passed.
- Full test suite: 202 tests passed.

## 5-17. Production counts

- `final_tags_total`: 22,513
- `entity_json_files_created`: 22,513
- `article_status_index_rows`: 22,513
- `a0_review_stub_original`: 3,349
- `a0_1_rerouted_from_review_stub`: 1,332
- `review_stub_articles` after A0.1: 2,017
- `direct_copy_article`: 6,806
- `direct_copy_rejected`: 0
- `pending_single_doc_extract`: 7,025
- `pending_low_count_batch_extract`: 1,779
- `pending_multi_doc_map_reduce`: 940
- `pending_high_frequency_map_reduce`: 107
- `a2_extraction_tasks_total`: 34,995
- `stub_only_articles`: 3,839
- `publication_review_queue_total`: 9,325
- `hard_review_queue_total`: 2,017

Coverage audit:

```json
{
  "article_status_index_rows": 22513,
  "entity_json_files_created": 22513,
  "final_tags_total": 22513,
  "missing_entity_json_files": 0,
  "passed": true,
  "status_index_missing_tags": 0
}
```

Quality:

```json
{
  "a2_task_queue_created": true,
  "all_article_files_exist": true,
  "all_tags_have_entity_json": true,
  "article_status_index_complete": true,
  "no_llm_called": true,
  "passed": true
}
```

## 18. Примеры rerouted tags

- `biological_substance_fba168de6d` — Бактериальные экзотоксины: `review_stub` -> `single_doc_extract`, reason `alias_conflict`.
- `biological_substance_7d642ecd9e` — Бактериальные эндотоксины: `review_stub` -> `single_doc_extract`, reason `alias_conflict`.
- `biological_substance_00973012d7` — Система комплемента: `review_stub` -> `low_count_batch_extract`, publication review reasons include `alias_conflict`, `n1_review_required`.
- `diagnostic_method_ae7b5dcf5a` — Магнитно-резонансная томография: `review_stub` -> `high_frequency_map_reduce`, 480 A2 tasks.
- `supplement_7fa11b45f2` — Коэнзим Q10: `review_stub` -> `high_frequency_map_reduce`, 167 A2 tasks.

## 19. Примеры direct_copy_article

- `biological_substance_85054c0be3` — Иммуноглобулин тяжелой и легкой цепи.
- `biological_substance_372c6c9dbb` — Магния сульфат.
- `biological_substance_d3c89cb841` — Норадреналин.
- `biological_substance_25b3113b1b` — Рокурония бромид.
- `disease_5f523380ae` — 2-аминоадипиновая 2-оксоадипиновая ацидурия.

## 20. Примеры rejected direct_copy

В production rejected direct-copy отсутствуют:

```text
data/articles/a1/direct_copy_rejected.jsonl = 0 rows
```

Validation failure paths покрыты unit tests:

- competing article tags -> reject;
- low coverage -> reject;
- missing/empty source document blocks -> reject.

## 21. Что не сделано

- Не создавались LLM full articles.
- Не извлекались evidence items.
- Не делалась article compilation.
- Не вызывались LLM/Gemini/OpenRouter.
- Не менялись A0 outputs, N1/N2/N3/N4 outputs, `data/tagging/*`, `data/parsed/*`.
- Не строились folders или knowledge graph.

## 22. Риски

- `publication_review_queue_total=9,325`; эти сущности могут идти в pipeline, но требуют review перед публикацией.
- `hard_review_queue_total=2,017`; эти сущности остаются review/stub path до ручной или отдельной policy-проверки.
- `a2_extraction_task_queue.jsonl` содержит 34,995 tasks; A2 должен делать batching, cache/resume/retry и cost/error reporting.
- High-frequency tasks требуют отдельного dedupe/batching режима, а не простого sequential extraction.

## 23. Что передать в A2

Главный output для A2:

```text
data/articles/a1/a2_extraction_task_queue.jsonl
data/articles/a1/article_status_index.jsonl
data/articles/a1/tag_work_plan_adjusted.jsonl
```

Дополнительно:

```text
data/articles/a1/publication_review_queue.jsonl
data/articles/a1/hard_review_queue.jsonl
data/articles/a1/a1_report.json
data/articles/a1/a1_manifest.json
data/articles/a1/article_file_coverage_audit.json
data/articles/entities/
```

Operational policy for A2/A3/A4:

- LLM smoke/benchmark разрешён только на 50-200 элементов.
- Тест на 4000 элементов запрещён.
- Production LLM run должен использовать batch processing.
- `max_inflight` минимум 16, лучше 32-64 при отсутствии ошибок.
- Для первых smoke tests использовать `max_inflight=4-8`.
- Не ставить слишком жёсткий `max_output_tokens`.
- Обязательны cache/resume/retry, structured output, cost/latency/error report.

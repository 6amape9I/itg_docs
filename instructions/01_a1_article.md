# A1. Entity JSON Bootstrap + A0.1 Strategy Repair

## 0. Контекст

A0 Article Planning уже выполнен и принят как deterministic planning stage.

A0 создал:

```text
data/articles/planning/tag_source_index.jsonl
data/articles/planning/tag_work_plan.jsonl
data/articles/planning/source_block_windows.jsonl
data/articles/planning/direct_copy_candidates.jsonl
data/articles/planning/singleton_candidates.jsonl
data/articles/planning/stub_only_tags.jsonl
data/articles/planning/review_stub_tags.jsonl
data/articles/planning/article_planning_report.json
data/articles/planning/article_planning_manifest.json

По A0 production feedback:

final_tags_total = 22513
tag_source_index rows = 22513
tag_work_plan rows = 22513
tags_with_mentions = 22513
tags_without_mentions = 0
source_windows_total = 57925
direct_copy_candidate = 6344
single_doc_extract = 6701
low_count_batch_extract = 1482
multi_doc_map_reduce = 727
high_frequency_map_reduce = 71
stub_only = 3839
review_stub = 3349
estimated_llm_extraction_tasks = 27555
estimated_article_compilation_tasks = 8981

A0 не вызывал LLM. A1 тоже по умолчанию не должен вызывать LLM.

1. Главная цель A1

A1 должен создать первый слой JSON-файлов сущностей для всех финальных tag_id.

Главный результат:

каждый final tag_id получает entity JSON файл

Файл может быть в одном из статусов:

stub_only
review_stub
direct_copy_article
pending_single_doc_extract
pending_low_count_batch_extract
pending_multi_doc_map_reduce
pending_high_frequency_map_reduce
failed_or_blocked

A1 не обязан создавать полноценные статьи для всех тегов. A1 должен:

применить A0.1 strategy repair;
создать stub/review JSON для stub paths;
создать direct-copy JSON для безопасных direct-copy candidates;
создать pending JSON для тегов, которые пойдут в LLM extraction/compilation на следующих этапах;
создать очереди задач для будущего A2/A3;
гарантировать, что каждый tag_id представлен в article_status_index.jsonl.
2. Критическая правка A0.1

A0 слишком консервативно отправил часть важных article_candidate=true тегов в review_stub только из-за alias_conflict.

Для article generation это неправильно.

alias_conflict сам по себе не должен блокировать сбор статьи. Он должен означать:

можно собирать статью
но статья требует review перед публикацией

Поэтому A1 обязан сначала создать скорректированный work plan:

data/articles/a1/a0_1_strategy_adjustments.jsonl
data/articles/a1/tag_work_plan_adjusted.jsonl
data/articles/a1/tag_work_plan_adjusted.csv
data/articles/a1/a0_1_strategy_adjustment_report.json

A1 не должен менять A0 outputs. Он создаёт новый adjusted слой.

3. Review policy для A0.1

Разделить review reasons на две группы.

3.1 Article-blocking review reasons

Эти причины блокируют полноценную статью на A1 и должны оставлять стратегию review_stub:

drug_policy_review
drug_trade_name_active_substance_conflict
merge_conflict
entity_type_conflict
rejected_constraint_conflict
unresolved_review
unresolved review
empty_canonical_tag_ru
canonical_empty
unknown_node_id
critical_merge_conflict

Если tag имеет article-blocking reason:

strategy = review_stub
needs_review_before_article = true
needs_review_before_publication = true
3.2 Publication-review reasons

Эти причины НЕ должны автоматически блокировать статью:

alias_conflict
n1_review_required
risk:quote_not_found
risk:possible_abbreviation
risk:very_short_alias
risk:contains_short_alias
risk:low_confidence
quote_issue
possible_abbreviation

Если tag имеет только publication-review reasons, но:

article_candidate = true
documents_count > 0
source_windows_count > 0

то A1 должен пересчитать стратегию так, будто tag может идти в article pipeline, но с флагом:

needs_review_before_publication = true
publication_review_reasons = [...]

Пример:

Генетическое тестирование
Магнитно-резонансная томография
Оптическая когерентная томография
Коэнзим Q10
Кортикостероиды

Если такие теги имеют article_candidate=true и источники, они не должны оставаться review_stub только из-за alias_conflict.

4. A0.1 rerouting rules

Для каждой строки tag_work_plan.jsonl:

4.1 Если стратегия review_stub

Если:

article_candidate = true
documents_count > 0
source_windows_count > 0
review_reasons contain no article-blocking reasons

то пересчитать strategy по обычным правилам:

documents_count = 1 → single_doc_extract или direct_copy_candidate, если direct-copy criteria выполнены
2–3 docs → low_count_batch_extract
4–20 docs → multi_doc_map_reduce
>20 docs → high_frequency_map_reduce

При этом обязательно поставить:

needs_review_before_publication = true
publication_review_reasons = original review_reasons
strategy_adjusted = true
strategy_adjustment_reason = "publication_review_not_article_blocking"
4.2 Если strategy уже non-review

Оставить как есть, но добавить поля:

needs_review_before_publication
publication_review_reasons
article_blocking_review_reasons
4.3 Если article_candidate=false

Не превращать в article strategy.

Оставить:

stub_only

или:

review_stub
4.4 Если source_windows_count=0

Оставить:

no_source_window_review

или:

review_stub
5. Не цели A1

На A1 запрещено:

вызывать LLM в production;
вызывать Gemini/OpenRouter для полного корпуса;
делать evidence extraction;
делать article compilation через LLM;
делать web search;
изменять A0 outputs;
изменять N1/N2/N3/N4 outputs;
изменять data/tagging/*;
изменять data/parsed/*;
создавать финальные full articles для map-reduce тегов;
строить папки;
строить knowledge graph.

A1 — это bootstrap/stub/direct-copy/pending layer, не LLM extraction stage.

6. Разрешение на LLM-тесты для будущих этапов

В этом A1 LLM по умолчанию не нужен.

Но для будущих A2/A3/A4 этапов в проекте уже есть ключи Gemini, и архитектор разрешает:

малые LLM smoke/benchmark тесты на 50–200 элементов

Запрещено:

тестовый запуск на 4000 элементов

Production LLM запуск должен быть эффективным:

хороший batch size;
не слишком строгий max_output_tokens;
параллельность минимум 16;
лучше 32–64, если нет ошибок;
для первых тестов max_inflight 4–8;
обязательный cache/resume/retry;
structured output;
cost limit;
подробный report.

Если агент в будущем реализует LLM stage, он обязан учитывать этот operational policy.

7. Входные файлы A1

Основные входы:

data/articles/planning/tag_source_index.jsonl
data/articles/planning/tag_work_plan.jsonl
data/articles/planning/source_block_windows.jsonl
data/articles/planning/direct_copy_candidates.jsonl
data/articles/planning/singleton_candidates.jsonl
data/articles/planning/article_planning_report.json
data/articles/planning/article_planning_manifest.json

Normalization final:

data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv
data/normalization/final/document_tag_links_normalized.jsonl
data/normalization/final/document_tags_normalized_by_doc.jsonl
data/normalization/final/final_normalization_report.json
data/normalization/final/final_normalization_manifest.json

Parsed documents:

data/parsed/parsed_documents.jsonl
data/parsed/document_blocks.jsonl
8. Выходные файлы A1

Создать директорию:

data/articles/a1/

Обязательные outputs:

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

Entity JSON files:

data/articles/entities/{entity_type}/{tag_id}.json

Audit/review outputs:

data/articles/a1/direct_copy_rejected.jsonl
data/articles/a1/direct_copy_validation_report.csv
data/articles/a1/publication_review_queue.jsonl
data/articles/a1/hard_review_queue.jsonl
data/articles/a1/article_file_coverage_audit.json
data/articles/a1/article_file_coverage_missing_tags.csv
9. Обязательное покрытие entity JSON

A1 должен создать один JSON-файл на каждый final tag_id.

Если в tags_canonical.csv 22 513 строк, то:

article_status_index.jsonl rows = 22513
число entity JSON файлов = 22513

Каждый tag_id должен быть в:

data/articles/entities/{entity_type}/{tag_id}.json

Даже если это stub_only или review_stub.

10. Entity JSON schema

Каждый entity JSON должен иметь структуру:

{
  "tag_id": "disease_...",
  "canonical_tag_ru": "Астма",
  "canonical_tag_latin": null,
  "entity_type": "disease",

  "article_status": "stub_only",
  "source_strategy": "stub_only",
  "needs_review_before_article": false,
  "needs_review_before_publication": false,
  "review_reasons": [],

  "article_candidate": true,
  "primary_role": "article_candidate",
  "mentions_count": 0,
  "documents_count": 0,

  "content_format": "editorjs",
  "content": {
    "time": 0,
    "version": "2.28.0",
    "blocks": []
  },

  "sources": {
    "source_doc_ids": [],
    "source_window_ids": [],
    "source_windows_count": 0
  },

  "provenance": {
    "created_from_stage": "A1",
    "normalization_source": "data/normalization/final",
    "planning_source": "data/articles/planning",
    "adjusted_plan_source": "data/articles/a1/tag_work_plan_adjusted.jsonl"
  }
}
11. Editor.js content rules
11.1 Stub content

Для stub_only:

{
  "blocks": [
    {
      "type": "header",
      "data": {
        "text": "Каноническое название",
        "level": 2
      }
    },
    {
      "type": "paragraph",
      "data": {
        "text": "Страница сущности создана как служебная карточка. Полноценная статья не сформирована, так как сущность не является самостоятельным article-candidate тегом."
      }
    }
  ]
}

Не добавлять медицинских фактов, которых нет в источниках.

11.2 Review stub content

Для review_stub:

{
  "blocks": [
    {
      "type": "header",
      "data": {
        "text": "Каноническое название",
        "level": 2
      }
    },
    {
      "type": "paragraph",
      "data": {
        "text": "Страница требует проверки перед сборкой статьи."
      }
    }
  ]
}

Добавить review reasons в metadata, а не как медицинский факт.

11.3 Pending extraction content

Для:

pending_single_doc_extract
pending_low_count_batch_extract
pending_multi_doc_map_reduce
pending_high_frequency_map_reduce

создать минимальный JSON с title и статусом ожидания evidence extraction.

11.4 Direct copy content

Для direct_copy_article можно использовать source document blocks.

Но A1 должен соблюдать:

не добавлять новых фактов;
не переписывать текст LLM;
сохранять provenance;
не копировать документ, если direct-copy validation не прошла.
12. Direct copy validation

A1 может превратить direct_copy_candidate в direct_copy_article, только если:

strategy after A0.1 = direct_copy_candidate
article_candidate = true
need_review_before_article = false
needs_review_before_publication may be true only for non-blocking reasons
documents_count = 1
source_windows_count >= 1
competing_article_candidate_tags_in_doc = 0
best window quality is high or medium
coverage_ratio_estimate >= 0.8 OR match_method = short_doc_fallback
source document exists
source document has parsed blocks
document is not empty

Если validation fails:

article_status = pending_single_doc_extract
source_strategy = single_doc_extract
record in direct_copy_rejected.jsonl

Direct copy rejected не является ошибкой.

13. Direct copy content construction

Если direct copy accepted:

Найти source doc.
Взять все parsed blocks документа.
Преобразовать их в Editor.js blocks.
Удалить пустые blocks.
Сохранить original block ids в metadata.
Поставить:
article_status = direct_copy_article
source_strategy = direct_copy_candidate

Если parsed block type известен:

header → Editor.js header
paragraph → paragraph
list → list
table → table

Если block type неизвестен:

paragraph fallback
14. Pending extraction task queue

Для всех стратегий:

single_doc_extract
low_count_batch_extract
multi_doc_map_reduce
high_frequency_map_reduce

создать task queue для A2:

data/articles/a1/a2_extraction_task_queue.jsonl

Одна строка = одно extraction task по source window.

Формат:

{
  "task_id": "a2task_000000001",
  "tag_id": "...",
  "canonical_tag_ru": "...",
  "canonical_tag_latin": null,
  "entity_type": "disease",
  "source_strategy": "single_doc_extract",
  "doc_id": "...",
  "document_name": "...",
  "window_id": "...",
  "window_text": "...",
  "window_char_length": 1234,
  "block_ids": [],
  "block_indexes": [],
  "heading_context": [],
  "match_method": "quote_match",
  "window_quality": "high",
  "needs_review_before_publication": false,
  "priority": "high|medium|low",
  "batch_group_key": "disease:single_doc_extract",
  "estimated_input_chars": 1234,
  "recommended_max_output_tokens": 2000
}
14.1 Не создавать extraction tasks для
stub_only
review_stub
direct_copy_article
14.2 Low-quality windows

Если window_quality=low, task можно создать, но:

priority = low
needs_review_before_publication = true
review_reasons includes low_quality_source_window
15. Task priority

Присвоить priority:

high
article_candidate=true
need_review_before_article=false
window_quality=high
strategy in single_doc_extract|low_count_batch_extract
medium
multi_doc_map_reduce
window_quality=medium
needs_review_before_publication=true but no hard blockers
low
high_frequency_map_reduce
window_quality=low
need_review_before_publication=true

High-frequency не значит low priority всегда. Но для A2 high-frequency будет обрабатываться отдельным batching/dedupe режимом.

16. Article status index

Создать:

data/articles/a1/article_status_index.jsonl

Одна строка = один tag_id.

Формат:

{
  "tag_id": "...",
  "canonical_tag_ru": "...",
  "canonical_tag_latin": null,
  "entity_type": "disease",
  "article_status": "pending_single_doc_extract",
  "source_strategy_original": "review_stub",
  "source_strategy_adjusted": "single_doc_extract",
  "strategy_adjusted": true,
  "article_file_path": "data/articles/entities/disease/disease_xxx.json",
  "article_candidate": true,
  "mentions_count": 1,
  "documents_count": 1,
  "source_windows_count": 1,
  "a2_extraction_tasks_count": 1,
  "needs_review_before_article": false,
  "needs_review_before_publication": true,
  "review_reasons": [],
  "publication_review_reasons": ["alias_conflict"]
}
17. Reports

Создать:

data/articles/a1/a1_report.json

Минимальная структура:

{
  "stage": "article_a1_entity_json_bootstrap",
  "stage_version": "a1.0",
  "created_at": "...",

  "counts": {
    "final_tags_total": 22513,
    "entity_json_files_created": 22513,
    "article_status_index_rows": 22513,

    "a0_review_stub_original": 0,
    "a0_1_rerouted_from_review_stub": 0,

    "stub_only_articles": 0,
    "review_stub_articles": 0,
    "direct_copy_articles": 0,
    "direct_copy_rejected": 0,

    "pending_single_doc_extract": 0,
    "pending_low_count_batch_extract": 0,
    "pending_multi_doc_map_reduce": 0,
    "pending_high_frequency_map_reduce": 0,

    "a2_extraction_tasks_total": 0,
    "publication_review_queue_total": 0,
    "hard_review_queue_total": 0
  },

  "by_entity_type": {},

  "quality": {
    "all_tags_have_entity_json": true,
    "all_article_files_exist": true,
    "article_status_index_complete": true,
    "no_llm_called": true,
    "a2_task_queue_created": true,
    "passed": true
  },

  "warnings": []
}

Создать manifest:

data/articles/a1/a1_manifest.json

В manifest записать все inputs/outputs/config.

18. Coverage audit

Создать:

data/articles/a1/article_file_coverage_audit.json
data/articles/a1/article_file_coverage_missing_tags.csv

Audit:

{
  "final_tags_total": 22513,
  "entity_json_files_created": 22513,
  "missing_entity_json_files": 0,
  "article_status_index_rows": 22513,
  "status_index_missing_tags": 0,
  "passed": true
}

Acceptance:

missing_entity_json_files = 0
status_index_missing_tags = 0
passed = true
19. Tests

Добавить tests:

tests/test_article_a1_strategy_repair.py
tests/test_article_a1_entity_json.py
tests/test_article_a1_direct_copy.py
tests/test_article_a1_task_queue.py
tests/test_article_a1_runner.py
19.1 Strategy repair tests
review_stub + article_candidate + alias_conflict only → rerouted to extraction strategy.
review_stub + drug_policy_review → stays review_stub.
review_stub + merge_conflict → stays review_stub.
context_only + article_candidate=false → stub_only.
rerouted plan has needs_review_before_publication=true.
19.2 Entity JSON tests
creates one JSON per tag.
JSON has required fields.
stub content is valid Editor.js.
review stub content is valid Editor.js.
pending extraction content is valid Editor.js.
no unsupported facts inserted.
19.3 Direct copy tests
accepted direct-copy candidate creates direct_copy_article.
direct-copy with competing article tags is rejected.
direct-copy with low coverage is rejected.
direct-copy preserves source block metadata.
19.4 Task queue tests
extraction tasks created for single_doc_extract.
extraction tasks created for low_count/multi/high.
no tasks for stub_only/review_stub/direct_copy_article.
task has window_text and block_ids.
low quality window task has low priority/review flag.
19.5 Runner tests
refuses missing A0 manifest.
refuses missing final normalization report.
creates all outputs.
coverage audit passes.
no LLM client used.

Запуск:

.venv/bin/python -m unittest discover -s tests

Compile check:

.venv/bin/python -m py_compile \
  kb_rebuild/articles/a1/models.py \
  kb_rebuild/articles/a1/strategy_repair.py \
  kb_rebuild/articles/a1/entity_json.py \
  kb_rebuild/articles/a1/direct_copy.py \
  kb_rebuild/articles/a1/task_queue.py \
  kb_rebuild/articles/a1/report.py \
  kb_rebuild/articles/a1/runner.py \
  kb_rebuild/cli.py
20. Рекомендуемая структура кода

Создать пакет:

kb_rebuild/articles/a1/

Файлы:

kb_rebuild/articles/a1/__init__.py
kb_rebuild/articles/a1/models.py
kb_rebuild/articles/a1/strategy_repair.py
kb_rebuild/articles/a1/entity_json.py
kb_rebuild/articles/a1/direct_copy.py
kb_rebuild/articles/a1/task_queue.py
kb_rebuild/articles/a1/report.py
kb_rebuild/articles/a1/runner.py

Назначение:

models.py          — dataclasses/constants/status enums
strategy_repair.py — A0.1 strategy adjustment
entity_json.py     — create stub/review/pending/direct-copy entity JSON
direct_copy.py     — direct-copy validation and Editor.js conversion
task_queue.py      — A2 extraction task queue generation
report.py          — CSV/JSON writers and reports
runner.py          — orchestration

CLI:

python -m kb_rebuild article-a1-bootstrap --data data

Флаги:

--articles-planning-dir data/articles/planning
--normalization-final-dir data/normalization/final
--parsed-dir data/parsed
--out data/articles/a1
--entities-out data/articles/entities
--review-sample-size 500
--no-overwrite
21. Команда запуска A1
.venv/bin/python -m kb_rebuild article-a1-bootstrap \
  --data data \
  --articles-planning-dir data/articles/planning \
  --normalization-final-dir data/normalization/final \
  --parsed-dir data/parsed \
  --out data/articles/a1 \
  --entities-out data/articles/entities
22. Acceptance criteria

A1 принимается, если:

A0.1 adjusted work plan создан;
review_stub из-за alias_conflict-only rerouted;
hard review blockers остались review_stub;
article_status_index.jsonl создан;
article_status_index rows = final_tags_total;
entity JSON files created = final_tags_total;
stub/review/direct/pending statuses корректны;
direct_copy validation работает;
A2 extraction task queue создан;
coverage audit passed;
tests passed;
feedback создан;
LLM не вызывалась.
23. Feedback после A1

Создать:

docs/article_a1_feedback.md

Feedback должен содержать:

1. Что сделано.
2. Какие файлы изменены.
3. Какие команды запускались.
4. Сколько tests passed.
5. Сколько final tags.
6. Сколько entity JSON создано.
7. Сколько review_stub было до A0.1.
8. Сколько review_stub rerouted после A0.1.
9. Сколько осталось hard review_stub.
10. Сколько direct_copy_article.
11. Сколько direct_copy_rejected.
12. Сколько pending_single_doc_extract.
13. Сколько pending_low_count_batch_extract.
14. Сколько pending_multi_doc_map_reduce.
15. Сколько pending_high_frequency_map_reduce.
16. Сколько A2 extraction tasks.
17. Coverage audit.
18. Примеры rerouted tags.
19. Примеры direct_copy_article.
20. Примеры rejected direct_copy.
21. Что не сделано.
22. Риски.
23. Что передать в A2.

Обязательно указать:

Главный output для A2:
data/articles/a1/a2_extraction_task_queue.jsonl
data/articles/a1/article_status_index.jsonl
data/articles/a1/tag_work_plan_adjusted.jsonl
24. Поведение агента

Перед началом создать план:

docs/article_a1_plan.md

План должен содержать:

что понял;
как реализует A0.1;
какие inputs использует;
какие files изменит;
какие outputs создаст;
как будет создавать entity JSON;
как будет валидировать direct copy;
как будет строить A2 task queue;
какие tests добавит;
риски;
чеклист.

Агент обязан перечитать ТЗ:

after_plan
after_strategy_repair
after_entity_json_logic
after_direct_copy_logic
after_task_queue_logic
after_tests
before_production_run
before_feedback

В feedback добавить строку:

ТЗ перечитано на этапах: after_plan, after_strategy_repair, after_entity_json_logic, after_direct_copy_logic, after_task_queue_logic, after_tests, before_production_run, before_feedback

Если память агента очищена, сначала перечитать:

instructions/current_a1_instruction.md
docs/article_planning_a0_feedback.md
data/articles/planning/article_planning_report.json
data/articles/planning/article_planning_manifest.json
data/articles/planning/tag_work_plan.jsonl
data/articles/planning/source_block_windows.jsonl
data/normalization/final/final_normalization_report.json

и только потом продолжать.

25. Операционная политика для будущих LLM-этапов

A1 сам не должен вызывать LLM.

Но в feedback нужно передать A2/A3/A4 следующее:

LLM smoke/benchmark разрешён только на 50–200 элементов.
Тест на 4000 элементов запрещён.
Production LLM run должен быть efficient:
  batch processing;
  max_inflight минимум 16;
  лучше 32–64 при отсутствии ошибок;
  на smoke 4–8;
  не ставить слишком жёсткий max_output_tokens;
  использовать cache/resume/retry;
  использовать structured output;
  писать cost/latency/error report.
26. Главное напоминание

A1 не должен пытаться “написать все статьи”.

A1 должен гарантировать:

каждый tag_id представлен entity JSON;
все stub/direct/pending статусы корректны;
важные article_candidate теги не заблокированы только из-за alias_conflict;
A2 получает чистую очередь extraction tasks.

Главный результат A1:

data/articles/entities/{entity_type}/{tag_id}.json
data/articles/a1/article_status_index.jsonl
data/articles/a1/a2_extraction_task_queue.jsonl
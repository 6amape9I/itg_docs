# Article Planning A0 Plan

## 1. Что понял из задачи

A0 запускает новый deterministic article planning track после N4. Этап должен построить карту источников, source block windows и work plan для каждого final `tag_id`, не вызывая LLM и не создавая статьи. Главный downstream output:

```text
data/articles/planning/tag_work_plan.jsonl
data/articles/planning/source_block_windows.jsonl
```

Каждый final canonical tag должен получить строку в `tag_source_index.jsonl` и `tag_work_plan.jsonl`.

## 2. Входные файлы

Обязательные:

```text
data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv
data/normalization/final/document_tag_links_normalized.jsonl
data/normalization/final/document_tags_normalized_by_doc.jsonl
data/normalization/final/final_normalization_report.json
data/parsed/parsed_documents.jsonl
data/parsed/document_blocks.jsonl
```

Дополнительные:

```text
data/normalization/tag_mentions_normalized.jsonl
data/normalization/tag_mentions_raw.jsonl
data/normalization/final/final_normalization_manifest.json
docs/normalization_n4_feedback.md
docs/normalization_n3_feedback.md
```

Если `tag_mentions_normalized.jsonl` отсутствует, A0 продолжит без quote context и запишет warning.

## 3. Файлы кода

Создать:

```text
kb_rebuild/articles/__init__.py
kb_rebuild/articles/planning/__init__.py
kb_rebuild/articles/planning/models.py
kb_rebuild/articles/planning/loaders.py
kb_rebuild/articles/planning/matching.py
kb_rebuild/articles/planning/windows.py
kb_rebuild/articles/planning/strategy.py
kb_rebuild/articles/planning/report.py
kb_rebuild/articles/planning/runner.py
```

Изменить:

```text
kb_rebuild/cli.py
```

## 4. Outputs A0

Обязательные JSONL/JSON:

```text
data/articles/planning/tag_source_index.jsonl
data/articles/planning/tag_work_plan.jsonl
data/articles/planning/source_block_windows.jsonl
data/articles/planning/direct_copy_candidates.jsonl
data/articles/planning/singleton_candidates.jsonl
data/articles/planning/stub_only_tags.jsonl
data/articles/planning/review_stub_tags.jsonl
data/articles/planning/no_source_window_tags.jsonl
data/articles/planning/article_planning_report.json
data/articles/planning/article_planning_manifest.json
```

CSV для человека:

```text
data/articles/planning/tag_work_plan.csv
data/articles/planning/strategy_summary_by_entity_type.csv
data/articles/planning/high_frequency_tags.csv
data/articles/planning/source_window_quality_report.csv
```

## 5. Как будет строиться tag_source_index

1. Загрузить все rows из `tags_canonical.csv`.
2. Загрузить aliases из `tag_aliases.csv` и сгруппировать по `tag_id`.
3. Загрузить `document_tag_links_normalized.jsonl` и сгруппировать mentions по `tag_id`.
4. Для каждого final `tag_id` создать запись независимо от наличия mentions.
5. `source_doc_ids` дедуплицировать и сортировать в порядке первого появления.
6. `mentions_count` и `documents_count` считать по links, не по CSV полям, чтобы downstream план соответствовал реальным links.

## 6. Как будут находиться block windows

Приоритет matching:

```text
quote_match
alias_match
title_match
short_doc_fallback
mention_only_fallback
```

Matching будет normalized exact, без агрессивного fuzzy:

```text
lowercase
ё/е
unicode normalize
dash normalize
space normalize
```

Window builder включит matched block, ближайшие header blocks и `max_neighbor_blocks` соседей. Окна внутри `tag_id + doc_id` будут объединяться при overlap. Если window получается слишком большим, сначала будут убраны соседние blocks, но matched blocks останутся.

## 7. Как будет выбираться strategy

Поддержать enum:

```text
stub_only
review_stub
direct_copy_candidate
single_doc_extract
low_count_batch_extract
multi_doc_map_reduce
high_frequency_map_reduce
no_source_window_review
```

Правила:

- `need_review=true` с критическими review reasons -> `review_stub`.
- `article_candidate=false` и context/folder role без review -> `stub_only`.
- mentions есть, а windows нет -> `no_source_window_review`.
- чистый singleton с dominant document title match/coverage -> `direct_copy_candidate`.
- singleton с window, но без direct copy criteria -> `single_doc_extract`.
- 2-3 docs -> `low_count_batch_extract`.
- docs above low threshold and up to high threshold -> `multi_doc_map_reduce`.
- docs above high threshold -> `high_frequency_map_reduce`.

Если выбор сомнителен, стратегия будет безопаснее: review/extraction вместо direct copy.

## 8. Tests

Добавить:

```text
tests/test_article_planning_loaders.py
tests/test_article_planning_matching.py
tests/test_article_planning_windows.py
tests/test_article_planning_strategy.py
tests/test_article_planning_runner.py
```

Покрыть загрузчики, normalized matching, construction/merge windows, strategy selection и runner outputs/count consistency.

## 9. Риски

- `need_review=true` есть у большого числа tags; A0 должен не пытаться исправлять normalization, а маршрутизировать осторожно.
- Short aliases могут давать ложные совпадения; для коротких aliases будет medium/low quality или пропуск в пользу fallback.
- Quote context зависит от `tag_mentions_normalized.jsonl`; отсутствие или несовпадение quote не должно ломать A0.
- Direct copy будет только candidate, фактическое копирование запрещено на A0.
- Full production run читает крупные JSONL/CSV; реализация должна быть простой и потокобезопасной по памяти для текущего корпуса.

## 10. Что точно не буду делать

```text
вызывать LLM/Gemini/OpenRouter
делать web search
создавать article JSON
создавать evidence через LLM
менять data/normalization/*
менять data/parsed/*
менять data/tagging/*
удалять старые artifacts
строить folders или graph knowledge
```

## 11. Чеклист выполнения

- [x] Прочитать global vision, A0 requirements и bootstrap.
- [x] Прочитать N3/N4 feedback и final report/manifest.
- [x] Создать этот plan.
- [x] Перечитать ТЗ на checkpoint `after_plan`.
- [x] Реализовать loaders.
- [x] Перечитать ТЗ на checkpoint `after_loaders`.
- [x] Реализовать matching logic.
- [x] Перечитать ТЗ на checkpoint `after_matching_logic`.
- [x] Реализовать window builder.
- [x] Перечитать ТЗ на checkpoint `after_window_builder`.
- [x] Реализовать strategy logic.
- [x] Перечитать ТЗ на checkpoint `after_strategy_logic`.
- [x] Реализовать report/runner и CLI.
- [x] Добавить tests.
- [x] Перечитать ТЗ на checkpoint `after_tests`.
- [x] Запустить compile check и tests.
- [x] Перечитать ТЗ на checkpoint `before_production_run`.
- [x] Запустить production A0.
- [x] Проверить обязательные outputs.
- [x] Перечитать ТЗ на checkpoint `before_feedback`.
- [x] Создать `docs/article_planning_a0_feedback.md`.

ТЗ перечитывается на этапах: after_plan, after_loaders, after_matching_logic, after_window_builder, after_strategy_logic, after_tests, before_production_run, before_feedback.

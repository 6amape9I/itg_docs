# A0. Article Planning & Source Window Builder

## 0. Контекст

A0 — первый этап нового трека сборки документов-сущностей.

У нас уже есть финальный canonical layer после N4:

```text
data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv
data/normalization/final/document_tag_links_normalized.jsonl
data/normalization/final/document_tags_normalized_by_doc.jsonl
```

N4 подтвердил, что все 42 324 mentions получили `tag_id`, все исходные имена тегов распознаются через canonical+aliases, и есть 22 513 final canonical tags.

A0 должен подготовить план сборки статей для всех final tags.

A0 не вызывает LLM.

## 1. Цель A0

Создать детерминированный planning layer для будущей сборки статей.

A0 должен:

1. Прочитать финальные canonical tags и normalized document-tag links.
2. Прочитать parsed documents и Editor.js blocks.
3. Для каждого `tag_id` собрать source index.
4. Найти релевантные source block windows.
5. Определить стратегию обработки каждого tag_id.
6. Создать отчёт с оценкой объёмов будущей LLM-работы.
7. Ничего не генерировать через LLM.

Главный результат:

```text
data/articles/planning/tag_work_plan.jsonl
```

Этот файл будет определять, какие теги пойдут в direct copy, какие в singleton extraction, какие в multi-doc extraction, а какие будут stub/review.

## 2. Не цели A0

На A0 запрещено:

- вызывать LLM;
- создавать статьи;
- создавать evidence extraction через LLM;
- изменять `data/normalization/*`;
- изменять `data/parsed/*`;
- изменять исходные documents;
- создавать final article JSON;
- создавать quotes JSON;
- строить папки;
- строить граф знаний.

A0 только планирует и готовит source windows.

## 3. Входные файлы

### 3.1 Финальный normalization layer

```text
data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv
data/normalization/final/document_tag_links_normalized.jsonl
data/normalization/final/document_tags_normalized_by_doc.jsonl
data/normalization/final/final_normalization_report.json
data/normalization/final/final_normalization_manifest.json
```

### 3.2 Parsed documents

```text
data/parsed/parsed_documents.jsonl
data/parsed/document_blocks.jsonl
```

### 3.3 Дополнительный mention context

```text
data/normalization/tag_mentions_normalized.jsonl
data/normalization/tag_mentions_raw.jsonl
```

`tag_mentions_normalized.jsonl` нужен для quote/evidence details из tagging stage, если они есть.

## 4. Выходные файлы

Создать директорию:

```text
data/articles/planning/
```

Обязательные outputs:

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

Дополнительные CSV для человека:

```text
data/articles/planning/tag_work_plan.csv
data/articles/planning/strategy_summary_by_entity_type.csv
data/articles/planning/high_frequency_tags.csv
data/articles/planning/source_window_quality_report.csv
```

## 5. Рекомендуемая структура кода

Создать пакет:

```text
kb_rebuild/articles/planning/
```

Файлы:

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

Назначение:

```text
models.py    — dataclasses для TagSourceIndex, SourceWindow, WorkPlan
loaders.py   — чтение final normalization и parsed artifacts
matching.py  — поиск mentions/aliases/quotes в blocks
windows.py   — построение block windows
strategy.py  — выбор strategy для tag_id
report.py    — CSV/JSON reports
runner.py    — orchestration
```

Добавить CLI-команду:

```bash
python -m kb_rebuild article-plan-a0 --data data
```

Флаги:

```bash
--normalization-final-dir data/normalization/final
--parsed-dir data/parsed
--normalization-dir data/normalization
--out data/articles/planning
--max-neighbor-blocks 2
--max-window-chars 12000
--short-document-char-limit 12000
--high-frequency-doc-threshold 20
--low-count-doc-threshold 3
--review-sample-size 500
--no-overwrite
```

## 6. Input validation

A0 должен отказаться запускаться, если:

```text
tags_canonical.csv отсутствует;
tag_aliases.csv отсутствует;
document_tag_links_normalized.jsonl отсутствует;
parsed_documents.jsonl отсутствует;
document_blocks.jsonl отсутствует;
final_normalization_report.quality.passed != true;
final_normalization_report.counts.document_tag_links_total != число строк document_tag_links_normalized.jsonl;
```

Если `tag_mentions_normalized.jsonl` отсутствует, A0 может продолжить без quote-context, но обязан записать warning.

## 7. Tag source index

Создать:

```text
data/articles/planning/tag_source_index.jsonl
```

Одна строка = один final tag_id.

Формат:

```json
{
  "tag_id": "disease_abc123",
  "canonical_tag_ru": "Астма",
  "canonical_tag_latin": "Asthma",
  "entity_type": "disease",
  "article_candidate": true,
  "need_review": false,
  "primary_role": "article_candidate",
  "mentions_count": 12,
  "documents_count": 4,
  "aliases": ["Астма", "Бронхиальная астма"],
  "source_doc_ids": ["doc_001", "doc_002"],
  "source_mentions": [
    {
      "mention_id": "m_000001_00",
      "doc_id": "doc_001",
      "document_name": "Бронхиальная астма",
      "raw_surface": "астма",
      "tag_role": "article_candidate",
      "confidence": 0.95
    }
  ]
}
```

Требования:

- каждый tag_id из `tags_canonical.csv` должен быть представлен;
- если у tag_id нет mentions, он всё равно должен попасть с `mentions_count=0` и strategy later = `stub_only` или `review_stub`;
- source_doc_ids должны быть deduplicated.

## 8. Alias dictionary for matching

A0 должен построить alias dictionary:

```text
tag_id → normalized aliases
```

Источники:

```text
tags_canonical.canonical_tag_ru
tags_canonical.canonical_tag_latin
tag_aliases.alias
tag_aliases.alias_latin
document_tag_links raw_surface/canonical candidates for that tag_id
```

Для поиска в blocks использовать normalized matching:

```text
lowercase
ё/е
unicode normalize
dash normalize
space normalize
```

Нельзя делать слишком агрессивный fuzzy matching на A0. Если нет exact/normalized match, ставить low-quality fallback.

## 9. Source block windows

Создать:

```text
data/articles/planning/source_block_windows.jsonl
```

Одна строка = одно окно источника для tag_id в документе.

Формат:

```json
{
  "window_id": "win_000000001",
  "tag_id": "disease_abc123",
  "canonical_tag_ru": "Астма",
  "canonical_tag_latin": "Asthma",
  "entity_type": "disease",
  "doc_id": "doc_001",
  "document_name": "Бронхиальная астма",
  "mention_ids": ["m_000001_00"],
  "matched_aliases": ["астма"],
  "block_ids": ["b_001", "b_002", "b_003"],
  "block_indexes": [0, 1, 2],
  "heading_context": ["Бронхиальная астма"],
  "window_text": "...",
  "window_char_length": 3450,
  "match_method": "quote_match|alias_match|title_match|short_doc_fallback|mention_only_fallback",
  "window_quality": "high|medium|low",
  "needs_review": false,
  "review_reasons": []
}
```

## 10. Block matching logic

Для каждой mention/tag в документе искать relevant blocks.

### 10.1 Quote match

Если в `tag_mentions_normalized` есть evidence quote, искать quote в block text.

Если найдено:

```text
match_method = quote_match
window_quality = high
```

### 10.2 Alias match

Искать canonical/aliases в block text.

Если найдено:

```text
match_method = alias_match
window_quality = high или medium
```

High если найден canonical или frequent alias.
Medium если найден короткий alias или ambiguous alias.

### 10.3 Title match

Если alias найден только в document_name, но не в blocks:

```text
match_method = title_match
window_quality = medium или low
```

Title match не является evidence сам по себе, но может показать, что весь документ про тег.

### 10.4 Short document fallback

Если документ короткий:

```text
clean_text length <= short_document_char_limit
```

и document has only one strong article_candidate tag, можно взять весь документ как window:

```text
match_method = short_doc_fallback
window_quality = medium
```

### 10.5 Mention-only fallback

Если ничего не найдено, но document_tag_link существует:

```text
match_method = mention_only_fallback
window_quality = low
needs_review = true
```

Такие окна не должны идти в direct_copy. Они могут идти в extraction только с review flag.

## 11. Window construction

Когда найден один или несколько matched blocks:

1. Включить matched blocks.
2. Добавить предыдущие header blocks до ближайшего раздела.
3. Добавить `max_neighbor_blocks` до и после.
4. Если matched block — list/table, включить целиком.
5. Не превышать `max_window_chars`, если возможно.
6. Если окно слишком большое, обрезать соседние blocks, но не matched block.
7. Объединить overlapping windows внутри одного `tag_id + doc_id`.

## 12. Work plan

Создать:

```text
data/articles/planning/tag_work_plan.jsonl
```

Одна строка = один final tag_id.

Формат:

```json
{
  "tag_id": "disease_abc123",
  "canonical_tag_ru": "Астма",
  "canonical_tag_latin": "Asthma",
  "entity_type": "disease",
  "article_candidate": true,
  "need_review": false,
  "primary_role": "article_candidate",
  "mentions_count": 12,
  "documents_count": 4,
  "source_windows_count": 4,
  "high_quality_windows_count": 3,
  "low_quality_windows_count": 1,
  "strategy": "multi_doc_map_reduce",
  "strategy_reasons": ["article_candidate", "documents_count_gt_low_count_threshold"],
  "estimated_llm_extraction_tasks": 4,
  "estimated_article_compilation_tasks": 1,
  "can_create_stub_without_llm": false,
  "can_direct_copy": false,
  "needs_review_before_article": false
}
```

## 13. Strategy selection rules

### 13.1 `stub_only`

Выбрать если:

```text
article_candidate=false
primary_role=context_only или folder_candidate
need_review=false
```

### 13.2 `review_stub`

Выбрать если:

```text
need_review=true
```

и review reason критический:

```text
alias_conflict
drug_policy_review
merge_conflict
unresolved_review
```

### 13.3 `direct_copy_candidate`

Выбрать если:

```text
article_candidate=true
need_review=false
documents_count=1
source_windows_count>=1
document has only one article_candidate tag OR this tag is clearly dominant
document_name matches canonical or alias
window covers most of document OR short_doc_fallback
```

### 13.4 `single_doc_extract`

Выбрать если:

```text
article_candidate=true
documents_count=1
not direct_copy_candidate
source_windows_count>=1
```

### 13.5 `low_count_batch_extract`

Выбрать если:

```text
article_candidate=true
2 <= documents_count <= low_count_doc_threshold
```

### 13.6 `multi_doc_map_reduce`

Выбрать если:

```text
article_candidate=true
documents_count > low_count_doc_threshold
documents_count <= high_frequency_doc_threshold
```

### 13.7 `high_frequency_map_reduce`

Выбрать если:

```text
article_candidate=true
documents_count > high_frequency_doc_threshold
```

### 13.8 `no_source_window_review`

Выбрать если:

```text
source_windows_count=0
```

но tag has mentions.

## 14. Direct copy candidates

Создать:

```text
data/articles/planning/direct_copy_candidates.jsonl
```

Одна строка = tag_id со стратегией `direct_copy_candidate`.

Включить:

```text
tag_id
canonical_tag_ru
doc_id
document_name
reason
source_window_ids
coverage_ratio_estimate
```

A0 только предлагает direct copy. Фактическое копирование будет в следующем этапе.

## 15. Singleton candidates

Создать:

```text
data/articles/planning/singleton_candidates.jsonl
```

Включить все tag_id с:

```text
documents_count=1
```

Поля:

```text
tag_id
canonical_tag_ru
entity_type
strategy
doc_id
document_name
article_candidate
need_review
source_windows_count
competing_article_candidate_tags_in_doc
```

## 16. Stub-only tags

Создать:

```text
data/articles/planning/stub_only_tags.jsonl
```

Для tags, где стратегия `stub_only`.

## 17. Review stub tags

Создать:

```text
data/articles/planning/review_stub_tags.jsonl
```

Для tags, где стратегия `review_stub` или `no_source_window_review`.

## 18. No source window tags

Создать:

```text
data/articles/planning/no_source_window_tags.jsonl
```

Если tag has document links, но A0 не смог найти block window.

Это важный QA-файл: такие случаи могут означать, что matching logic слабый или document blocks потеряли текст.

## 19. CSV outputs

### 19.1 `tag_work_plan.csv`

Поля:

```text
tag_id
canonical_tag_ru
canonical_tag_latin
entity_type
article_candidate
need_review
primary_role
mentions_count
documents_count
source_windows_count
high_quality_windows_count
low_quality_windows_count
strategy
strategy_reasons
estimated_llm_extraction_tasks
estimated_article_compilation_tasks
```

### 19.2 `strategy_summary_by_entity_type.csv`

Поля:

```text
entity_type
strategy
tags_count
mentions_count_total
documents_count_total
source_windows_count_total
estimated_llm_extraction_tasks_total
estimated_article_compilation_tasks_total
```

### 19.3 `high_frequency_tags.csv`

Поля:

```text
tag_id
canonical_tag_ru
entity_type
documents_count
mentions_count
source_windows_count
strategy
```

### 19.4 `source_window_quality_report.csv`

Поля:

```text
match_method
window_quality
windows_count
tags_count
documents_count
avg_window_chars
```

## 20. Reports

Создать:

```text
data/articles/planning/article_planning_report.json
```

Минимальная структура:

```json
{
  "stage": "article_planning_a0",
  "stage_version": "a0.0",
  "created_at": "...",
  "counts": {
    "final_tags_total": 0,
    "article_candidate_tags": 0,
    "context_only_tags": 0,
    "folder_candidate_tags": 0,
    "need_review_tags": 0,
    "tags_with_mentions": 0,
    "tags_without_mentions": 0,
    "source_windows_total": 0,
    "high_quality_windows": 0,
    "medium_quality_windows": 0,
    "low_quality_windows": 0,
    "direct_copy_candidates": 0,
    "singleton_candidates": 0,
    "stub_only_tags": 0,
    "review_stub_tags": 0,
    "no_source_window_tags": 0,
    "estimated_llm_extraction_tasks": 0,
    "estimated_article_compilation_tasks": 0
  },
  "strategy_counts": {},
  "strategy_counts_by_entity_type": {},
  "window_match_method_counts": {},
  "warnings": []
}
```

Создать manifest:

```text
data/articles/planning/article_planning_manifest.json
```

Содержит:

```text
stage
stage_version
created_at
input paths
output paths
config
```

## 21. Quality gates

A0 должен проверить:

```text
каждый tag_id из tags_canonical представлен в tag_source_index;
каждый tag_id из tags_canonical представлен в tag_work_plan;
каждый source window ссылается на существующий tag_id;
каждый source window ссылается на существующий doc_id;
каждый source window имеет непустой window_text;
каждый strategy входит в enum;
direct_copy_candidate имеет documents_count=1;
stub_only не имеет article_candidate=true;
no_source_window_tags записаны, если есть mentions без windows;
```

Критические ошибки:

```text
missing tag_id in work_plan;
source window references missing tag_id;
source window references missing doc_id;
empty window_text for non-stub strategy;
```

## 22. Tests

Добавить tests:

```text
tests/test_article_planning_loaders.py
tests/test_article_planning_matching.py
tests/test_article_planning_windows.py
tests/test_article_planning_strategy.py
tests/test_article_planning_runner.py
```

### 22.1 Loader tests

- loads tags_canonical;
- loads aliases;
- loads document links;
- loads blocks;
- fails on missing required inputs.

### 22.2 Matching tests

- quote match finds block;
- alias match finds block;
- title match works when block match absent;
- no fuzzy overmatch for short aliases;
- normalized ё/е match works.

### 22.3 Window tests

- matched block included;
- previous header included;
- neighbor blocks included;
- max_window_chars respected;
- overlapping windows merge.

### 22.4 Strategy tests

- context_only → stub_only;
- critical need_review → review_stub;
- clean singleton dominant doc → direct_copy_candidate;
- singleton mixed doc → single_doc_extract;
- low count → low_count_batch_extract;
- high frequency → high_frequency_map_reduce;
- no windows → no_source_window_review.

### 22.5 Runner tests

- creates all required outputs;
- every tag has work plan;
- source windows valid;
- report counts consistent;
- no LLM calls.

Запуск:

```bash
.venv/bin/python -m unittest discover -s tests
```

Compile check:

```bash
.venv/bin/python -m py_compile \
  kb_rebuild/articles/planning/models.py \
  kb_rebuild/articles/planning/loaders.py \
  kb_rebuild/articles/planning/matching.py \
  kb_rebuild/articles/planning/windows.py \
  kb_rebuild/articles/planning/strategy.py \
  kb_rebuild/articles/planning/report.py \
  kb_rebuild/articles/planning/runner.py \
  kb_rebuild/cli.py
```

## 23. Команда запуска

```bash
.venv/bin/python -m kb_rebuild article-plan-a0 \
  --data data \
  --normalization-final-dir data/normalization/final \
  --parsed-dir data/parsed \
  --normalization-dir data/normalization \
  --out data/articles/planning \
  --max-neighbor-blocks 2 \
  --max-window-chars 12000 \
  --short-document-char-limit 12000 \
  --high-frequency-doc-threshold 20 \
  --low-count-doc-threshold 3
```

## 24. Acceptance criteria

A0 принимается, если:

- добавлена CLI-команда `article-plan-a0`;
- создан пакет `kb_rebuild/articles/planning`;
- создан `tag_source_index.jsonl`;
- создан `tag_work_plan.jsonl`;
- создан `source_block_windows.jsonl`;
- создан `direct_copy_candidates.jsonl`;
- создан `singleton_candidates.jsonl`;
- создан `stub_only_tags.jsonl`;
- создан `review_stub_tags.jsonl`;
- создан `no_source_window_tags.jsonl`;
- создан `article_planning_report.json`;
- создан `article_planning_manifest.json`;
- каждый final tag_id имеет work plan;
- source windows валидны;
- strategy distribution рассчитана;
- no LLM calls;
- tests проходят;
- feedback создан.

## 25. Feedback после A0

Создать:

```text
docs/article_planning_a0_feedback.md
```

Feedback должен содержать:

```text
1. Что сделано.
2. Какие файлы изменены.
3. Какие команды запускались.
4. Сколько tests passed.
5. Сколько final tags обработано.
6. Сколько source windows найдено.
7. Strategy counts.
8. Strategy counts by entity_type.
9. Сколько direct_copy candidates.
10. Сколько singleton candidates.
11. Сколько stub_only tags.
12. Сколько review_stub tags.
13. Сколько no_source_window tags.
14. Оценка будущих LLM extraction tasks.
15. Топ high-frequency tags.
16. Примеры direct_copy candidates.
17. Примеры no_source_window cases.
18. Что не сделано.
19. Риски.
20. Что передать следующему этапу.
```

Обязательно указать:

```text
Главный output следующего этапа:
data/articles/planning/tag_work_plan.jsonl
data/articles/planning/source_block_windows.jsonl
```

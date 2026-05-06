# Инициализационная инструкция для Codex-агента: Article Planning Engineer

## 0. Кто ты

Ты Codex-агент в роли Article Planning Engineer.

Твоя задача — начать новый глобальный трек сборки документов-сущностей после завершённой нормализации тегов.

Ты работаешь над этапом:

```text
A0. Article Planning & Source Window Builder
```

Твоя работа не связана с генерацией статей через LLM. Ты строишь детерминированный planning layer, который подготовит весь следующий LLM/evidence/article pipeline.

## 1. Что уже сделано до тебя

Завершены этапы:

```text
Parsing documents.csv
LLM tagging
N1/N1.1 deterministic normalization
N2/N2.2 candidate generation
N3 LLM validation
N4 final canonical layer
```

После N4 появились главные входы для нового трека:

```text
data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv
data/normalization/final/document_tag_links_normalized.jsonl
data/normalization/final/document_tags_normalized_by_doc.jsonl
```

Также есть parsed Editor.js block layer:

```text
data/parsed/parsed_documents.jsonl
data/parsed/document_blocks.jsonl
```

Новый трек должен создать для каждого `tag_id` статью, stub или review JSON.

A0 пока только планирует этот процесс.

## 2. Что тебе нужно прочитать перед началом

Перед работой обязательно прочитай:

```text
instructions/00_entity_article_global_vision.md
instructions/01_a0_article_planning_source_windows_requirements.md
instructions/02_article_planning_agent_bootstrap.md
```

Также прочитай последние normalization feedback, если они есть:

```text
docs/normalization_n4_feedback.md
docs/normalization_n3_feedback.md
```

И посмотри финальные report/manifest:

```text
data/normalization/final/final_normalization_report.json
data/normalization/final/final_normalization_manifest.json
```

Если какого-то файла нет, не падай сразу. Запиши это в plan и продолжи, если обязательные входы для A0 доступны.

## 3. Как ты должен работать

Ты обязан начать с плана.

Создай файл:

```text
docs/article_planning_a0_plan.md
```

В плане укажи:

```text
1. Что понял из задачи.
2. Какие входные файлы будешь использовать.
3. Какие файлы кода планируешь создать/изменить.
4. Какие outputs создаст A0.
5. Как будет строиться tag_source_index.
6. Как будет находиться block windows.
7. Как будет выбираться strategy для tag_id.
8. Какие tests добавишь.
9. Какие риски видишь.
10. Что точно не будешь делать.
11. Чеклист выполнения.
```

Не начинай писать код до создания плана.

## 4. Перечитывание инструкции

Ты обязан перечитывать ТЗ во время работы.

Минимальные checkpoints:

```text
after_plan
after_loaders
after_matching_logic
after_window_builder
after_strategy_logic
after_tests
before_production_run
before_feedback
```

В feedback обязательно добавь строку:

```text
ТЗ перечитано на этапах: after_plan, after_loaders, after_matching_logic, after_window_builder, after_strategy_logic, after_tests, before_production_run, before_feedback
```

Если память/контекст были очищены, не продолжай с середины наугад. Сначала перечитай инструкции, план, feedback и текущие reports.

## 5. Твои основные задачи

### 5.1 Создать package

Создать:

```text
kb_rebuild/articles/planning/
```

Минимальные файлы:

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

### 5.2 Добавить CLI

Добавить команду:

```bash
python -m kb_rebuild article-plan-a0 --data data
```

### 5.3 Создать source index

Создать:

```text
data/articles/planning/tag_source_index.jsonl
```

Каждый final tag_id должен быть представлен.

### 5.4 Создать block windows

Создать:

```text
data/articles/planning/source_block_windows.jsonl
```

Использовать Editor.js blocks, aliases, quotes, mentions, document titles и соседние blocks.

### 5.5 Создать work plan

Создать:

```text
data/articles/planning/tag_work_plan.jsonl
```

Каждый final tag_id должен получить strategy.

### 5.6 Создать reports

Создать:

```text
data/articles/planning/article_planning_report.json
data/articles/planning/article_planning_manifest.json
```

И CSV summaries.

## 6. Чего нельзя делать

На A0 запрещено:

```text
вызывать LLM;
вызывать Gemini;
вызывать OpenRouter;
делать web search;
создавать статьи;
создавать evidence через LLM;
менять data/normalization/*;
менять data/parsed/*;
менять data/tagging/*;
удалять старые artifacts;
создавать финальные article JSON;
создавать папочную структуру;
строить graph knowledge.
```

A0 — только deterministic planning.

## 7. Ключевые стратегии tag_id

Ты должен реализовать стратегию для каждого final tag_id:

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

Если сомневаешься между дорогой и безопасной стратегией — выбирай более безопасную и помечай review.

## 8. Как относиться к singleton тегам

Singleton tag — это тег, который встречается в одном документе.

Но singleton не всегда означает direct copy.

Direct copy можно предлагать только если:

```text
article_candidate=true
need_review=false
document has no competing strong article_candidate tags
название документа похоже на canonical или alias
окно покрывает большую часть документа или документ короткий
```

Если документ смешанный, стратегия должна быть:

```text
single_doc_extract
```

## 9. Как относиться к context_only / folder_candidate

Не удалять их.

Они должны получить work plan и будущий stub JSON.

Но не отправлять их в дорогой article generation, если они не являются article_candidate.

## 10. Как искать blocks

Приоритет:

```text
1. quote match из tag_mentions_normalized, если доступен;
2. canonical/alias exact normalized match;
3. document title match;
4. short document fallback;
5. mention-only fallback.
```

Не использовать агрессивный fuzzy search. Он может ловить ложные совпадения.

Окно должно включать:

```text
matched block;
ближайшие heading blocks;
1-2 соседних blocks;
полный list/table block, если match внутри него.
```

## 11. Tests обязательны

Добавить tests:

```text
tests/test_article_planning_loaders.py
tests/test_article_planning_matching.py
tests/test_article_planning_windows.py
tests/test_article_planning_strategy.py
tests/test_article_planning_runner.py
```

Запуск:

```bash
.venv/bin/python -m unittest discover -s tests
```

Также выполнить compile check:

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

Если tests не проходят, этап нельзя считать завершённым.

## 12. Production run

После tests запустить:

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

После запуска проверить:

```text
data/articles/planning/tag_source_index.jsonl
data/articles/planning/tag_work_plan.jsonl
data/articles/planning/source_block_windows.jsonl
data/articles/planning/article_planning_report.json
data/articles/planning/article_planning_manifest.json
```

## 13. Feedback после работы

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

## 14. Как понять, что работа хорошая

Хороший A0 — это не тот, который сделал максимум full_article стратегий.

Хороший A0 — это тот, который:

```text
не потерял ни одного final tag_id;
не потерял ни одного document-tag link;
нашёл block windows там, где это возможно;
не отправил context_only в дорогой путь;
выделил singleton/direct candidates;
пометил review/no-source cases;
дал честную оценку будущих LLM tasks;
создал понятные reports.
```

## 15. Главное напоминание

A0 должен защитить следующий LLM-этап от хаоса.

Твоя задача — подготовить карту работ:

```text
какие tag_id требуют статью;
какие могут быть stub;
какие можно обработать напрямую;
какие требуют extraction;
какие требуют review;
какие source windows использовать.
```

Не пытайся решить A1/A2/A3 заранее.

# Глобальное видение трека: сборка документов-сущностей по финальным тегам

## 0. Контекст

К этому моменту завершён трек нормализации тегов.

У нас есть финальный canonical layer:

```text
data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv
data/normalization/final/document_tag_links_normalized.jsonl
data/normalization/final/document_tags_normalized_by_doc.jsonl
```

По N4 итогам:

```text
mentions_total = 42 324
document_tag_links_total = 42 324
final canonical tags = 22 513
aliases = 52 530
documents_with_normalized_tags = 16 161
```

Важно: финальные теги — это полный слой сущностей. N3 accepted clusters были только правилами объединения, а N4 применил эти правила поверх всех N1/N1.1 auto-clusters. Значит, новый трек должен работать не с raw tags и не с N3 clusters, а с финальными `tag_id`.

## 1. Цель нового трека

Для каждого финального нормализованного тега создать JSON-файл сущности.

Итоговая цель:

```text
tag_id → entity JSON file
```

Для полноценных article-candidate сущностей нужно получить структурированную статью в формате Editor.js JSON.

Для context-only/folder/review сущностей нужно создать stub/review JSON, чтобы ни одна сущность не потерялась.

Главный результат трека:

```text
каждый final tag_id имеет файл состояния/контента
```

Возможные состояния:

```text
full_article
single_doc_article
direct_copy_article
stub_only
review_stub
failed
```

## 2. Почему нельзя делать наивный pipeline

Наивный pipeline:

```text
1. взять tag_id
2. собрать все документы
3. по каждому упоминанию вызвать LLM
4. из всех кусков собрать статью
5. сохранить article.json
```

Проблемы:

- слишком много лишних LLM-запросов;
- много тегов являются singleton или context-only;
- много документов смешанные, и полный текст будет засорять prompt;
- модель будет видеть лишние темы и вытаскивать шум;
- высокочастотные теги будут дорогими;
- без evidence слоя статья может начать галлюцинировать;
- без планирования невозможно оценить стоимость и время.

## 3. Новый принцип

Мы не обрабатываем документы целиком.

Мы строим для каждого `tag_id` источниковую карту:

```text
tag_id → source documents → relevant block windows → evidence → article/stub
```

То есть новая единица обработки — не документ, а:

```text
source block window for tag_id
```

## 4. Главные входы нового трека

Нормализация:

```text
data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv
data/normalization/final/document_tag_links_normalized.jsonl
data/normalization/final/document_tags_normalized_by_doc.jsonl
data/normalization/final/final_normalization_report.json
```

Парсинг документов:

```text
data/parsed/parsed_documents.jsonl
data/parsed/document_blocks.jsonl
```

Дополнительный контекст:

```text
data/normalization/tag_mentions_normalized.jsonl
data/normalization/tag_mentions_raw.jsonl
```

`tag_mentions_normalized.jsonl` полезен, потому что там могут быть quote/evidence поля из tagging stage, по которым можно найти релевантные блоки.

## 5. Выходы всего article-трека

Предлагаемая итоговая структура:

```text
data/articles/planning/
  tag_source_index.jsonl
  tag_work_plan.jsonl
  source_block_windows.jsonl
  article_planning_report.json
  article_planning_manifest.json


data/articles/evidence/
  evidence_extraction_tasks.jsonl
  evidence_items.jsonl
  fact_groups.jsonl
  evidence_report.json


data/articles/final/
  articles/{tag_id}.json
  quotes/{tag_id}_quotes.json
  article_generation_report.json
  article_manifest.json
  failed_or_review_articles.jsonl
```

Для каждого `tag_id` в идеале должен появиться один из файлов:

```text
full article JSON
stub JSON
review stub JSON
failed JSON
```

## 6. Типы стратегий обработки tag_id

Нельзя гонять все 22k+ тегов одинаково. Нужен `tag_work_plan`.

Основные стратегии:

### 6.1 `stub_only`

Для тегов, которые не являются самостоятельными article candidates.

Примеры:

```text
context_only
folder_candidate
article_candidate=false
```

Результат: минимальный entity JSON без LLM.

### 6.2 `review_stub`

Для тегов с критическим `need_review=true`.

Например:

```text
alias_conflict
drug_policy_review
merge_conflict
unresolved review source
```

Результат: stub JSON с причиной review. Полноценную статью можно делать позже после ручной проверки.

### 6.3 `direct_copy_candidate`

Для чистых singleton-тегов, где документ фактически целиком посвящён этой сущности.

Критерии:

```text
documents_count = 1
article_candidate = true
need_review = false
в документе нет конкурирующих сильных article_candidate тегов
название документа похоже на canonical_tag_ru или alias
исходный документ не слишком смешанный
```

Результат: исходный Editor.js документ можно взять как основу статьи без LLM или с минимальной валидацией.

### 6.4 `single_doc_extract`

Для тегов, которые встречаются в одном документе, но документ смешанный.

Результат: берём только relevant block windows и делаем один небольшой LLM extraction/compilation.

### 6.5 `low_count_batch_extract`

Для тегов с небольшим числом источников, например 2–3 документа.

Результат: батчевое извлечение evidence по block windows.

### 6.6 `multi_doc_map_reduce`

Для тегов с несколькими источниками.

Результат:

```text
map: извлечь evidence из каждого source window
reduce: дедуплицировать evidence
compile: собрать статью
```

### 6.7 `high_frequency_map_reduce`

Для частотных тегов с большим количеством документов.

Нужно ещё сильнее сжимать источники:

```text
ограничивать число окон на документ
дедуплицировать похожие окна
группировать факты до article compilation
```

## 7. Block windows вместо полных документов

Мы имеем структурированные Editor.js blocks, поэтому нельзя по умолчанию отправлять весь документ в LLM.

Для каждого mention/tag нужно искать релевантные blocks:

```text
точная quote из tagging → block match
alias/canonical search → block match
heading context → previous headers
neighbor context → +/- 1 или 2 блока
list/table context → включать целый list/table block
```

Окно должно быть достаточно маленьким, но не терять смысл.

Пример `source_block_window`:

```json
{
  "window_id": "win_000001",
  "tag_id": "disease_abc123",
  "canonical_tag_ru": "Астма",
  "entity_type": "disease",
  "doc_id": "doc_000001_xxx",
  "document_name": "Бронхиальная астма",
  "mention_ids": ["m_000001_00"],
  "block_ids": ["b_001", "b_002", "b_003"],
  "heading_context": ["Бронхиальная астма"],
  "window_text": "...",
  "match_method": "quote_match|alias_match|title_match|fallback_short_doc",
  "window_quality": "high|medium|low",
  "needs_review": false
}
```

## 8. Evidence-first подход

Статья не должна писаться напрямую из всех документов.

Правильный порядок:

```text
source windows → evidence items → fact groups → article
```

Evidence item:

```json
{
  "tag_id": "...",
  "source_doc_id": "...",
  "block_ids": [],
  "quote": "дословная цитата",
  "fact_type": "definition|symptoms|diagnostics|treatment|usage|safety|other",
  "claim_draft": "краткий смысл цитаты",
  "importance": "high|medium|low",
  "confidence": 0.0
}
```

Статья должна строиться только из evidence/fact groups, а не из внешних знаний.

## 9. Шаблоны статей по entity_type

Шаблон зависит от типа сущности.

### disease

```text
Что это
Причины и факторы риска
Симптомы
Диагностика
Лечение
Профилактика
Осложнения
Когда обращаться к врачу
Связанные сущности
```

### drug_trade_name

```text
Что это
Форма/состав, если есть в источниках
Показания
Применение
Противопоказания
Побочные эффекты
Особые указания
Связанные заболевания и симптомы
```

Важно: лекарственная сущность — торговое название. Нельзя превращать статью о торговом названии в статью о действующем веществе без отдельного решения.

### supplement

```text
Что это
Состав/компоненты
Для чего применяется
Способ применения, если есть
Предосторожности
Связанные состояния
```

### diagnostic_method

```text
Что это
Для чего применяется
Как проводится
Что показывает
Подготовка
Ограничения
Связанные состояния
```

### procedure / instruction

```text
Что это
Когда применяется
Порядок выполнения
Меры безопасности
Ошибки/ограничения
```

### microorganism / biological_substance / cell_or_biological_structure

Делать справочный шаблон:

```text
Что это
Где встречается / роль
Клиническое значение
Диагностика / связь с заболеваниями
Связанные сущности
```

## 10. LLM strategy

LLM использовать не сразу, а после A0 planning.

Предлагаемый стек:

```text
A0 planning: без LLM
A1 singleton/direct: без LLM или минимум LLM
A2 extraction: Gemini Flash, batch, structured output
A3 dedupe: deterministic + optional embeddings
A4 article compilation: Gemini Flash для простого, Gemini Pro/Flash с большим max tokens для сложного
A5 validation: deterministic + optional LLM audit
```

Gemini Direct уже доказал, что выдерживает высокую параллельность. Но каждый LLM-этап должен иметь:

```text
cache
resume
max-cost
max-inflight
structured output
retry
report
```

## 11. Quality gates для article-трека

Минимальные проверки:

```text
каждый final tag_id имеет article/stub/review/failed status
каждый full article имеет valid Editor.js JSON
каждый article имеет title = canonical_tag_ru
каждый evidence quote найден в исходном block/window
нет claims без supporting evidence, если статья full_article
нет внешних медицинских фактов без источника
нет смешения другого tag_id
```

## 12. Рекомендуемый порядок работ

Первым этапом делать только:

```text
A0. Article Planning & Source Window Builder
```

A0 без LLM должен дать:

```text
сколько тегов full_article
сколько singleton
сколько direct_copy
сколько stub_only
сколько review_stub
сколько high_frequency
сколько source windows
сколько тегов без найденных source windows
```

После A0 уже можно точно планировать LLM extraction/compilation.

## 13. Главный вывод

Новый трек должен быть не “LLM обработай всё”, а управляемый pipeline:

```text
planning → source windows → evidence → fact groups → article/stub → validation
```

Главная ценность A0 — не генерация текста, а правильная маршрутизация 22 513 тегов перед дорогими LLM-этапами.

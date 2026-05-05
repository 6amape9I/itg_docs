# 01_n1_deterministic_normalization_requirements.md

# N1. Подготовка и deterministic normalization

## 0. Контекст

Этап LLM-тегирования завершён и считается upstream-этапом. По актуальному manifest: `provider=gemini_direct`, `model=gemini-3-flash-preview`, `prompt_version=tagging_v2_gemini`, `schema_version=document_tagging_v2`, успешно размечено 16 161 документов из 16 181, failures — 20. :contentReference[oaicite:0]{index=0}

Новый этап N1 не должен изменять результаты tagging. Он должен читать tagging-output как входной audit trail и создавать отдельный слой нормализации в `data/normalization/`.

Главная задача N1 — подготовить данные к схлопыванию тегов: собрать все raw mentions, привести строки к нормализованному виду, автоматически объединить только очевидные дубли и подготовить статистику для следующего этапа candidate clustering / LLM validation.

## 1. Цель N1

Нужно реализовать первый этап нормализации тегов:

1. Прочитать `data/tagging/document_tags_raw_active.jsonl`.
2. Прочитать `data/tagging/document_tagging_failures_active.jsonl`, если файл существует.
3. Прочитать `data/tagging/empty_documents_name_candidates.jsonl`, если файл существует.
4. Преобразовать все сущности из tagging-output в плоский список mentions.
5. Для каждой mention создать deterministic normalized forms.
6. Создать auto-clusters только для очевидных дублей.
7. Создать отчёты по качеству, типам, ролям, quote status, частотности тегов.
8. Сохранить все артефакты в `data/normalization/`.
9. Не вызывать LLM.
10. Не менять tagging-файлы.
11. Не делать финальное semantic merge.
12. Не создавать `tags_canonical.csv` как окончательную правду на этом этапе.

## 2. Не цели N1

На этапе N1 запрещено:

- вызывать Gemini, OpenRouter или любую другую LLM;
- схлопывать разные `entity_type`;
- схлопывать широкую и узкую сущность только из-за похожести строки;
- делать embedding clustering;
- делать LLM cluster validation;
- создавать финальные статьи;
- создавать финальную иерархию папок;
- редактировать `data/tagging/*`;
- удалять raw tags;
- перезаписывать tagging-output;
- исправлять failed documents;
- генерировать теги из `document_name` для `empty_clean_text`.

## 3. Главный принцип

Raw tagging-output является неизменяемым источником.

Нормализация создаёт новый слой поверх него:

```text
raw mention → normalized mention → deterministic cluster candidate

N1 не должен утверждать, что все clusters являются финальными сущностями. Он только создаёт безопасные auto-clusters и подготавливает основу для N2/N3.

4. Рекомендуемая структура кода

Создать пакет:

kb_rebuild/normalization/

Минимальные файлы:

kb_rebuild/normalization/__init__.py
kb_rebuild/normalization/models.py
kb_rebuild/normalization/text.py
kb_rebuild/normalization/mentions.py
kb_rebuild/normalization/auto_cluster.py
kb_rebuild/normalization/report.py
kb_rebuild/normalization/n1_runner.py

Назначение:

models.py       — dataclass / typed structures для mentions, normalized mentions, clusters
text.py         — функции строковой нормализации
mentions.py     — flatten tagging-output в mentions
auto_cluster.py — deterministic auto-clustering obvious duplicates only
report.py       — статистика и отчёты
n1_runner.py    — orchestration этапа N1

В kb_rebuild/cli.py добавить команду:

python -m kb_rebuild normalize-n1 --data data

Дополнительные флаги:

--tagging-active-path data/tagging/document_tags_raw_active.jsonl
--failures-path data/tagging/document_tagging_failures_active.jsonl
--empty-candidates-path data/tagging/empty_documents_name_candidates.jsonl
--out data/normalization
--min-mentions-for-report 1
--no-overwrite

По умолчанию команда должна использовать стандартные пути.

5. Входные файлы

Основной вход:

data/tagging/document_tags_raw_active.jsonl

Ожидаемый формат каждой строки:

{
  "doc_id": "...",
  "document_name": "...",
  "provider": "gemini_direct",
  "model": "gemini-3-flash-preview",
  "prompt_version": "tagging_v2_gemini",
  "schema_version": "document_tagging_v2",
  "entities": [
    {
      "surface": "...",
      "canonical_candidate_ru": "...",
      "canonical_candidate_latin": "...",
      "entity_type": "...",
      "article_candidate": true,
      "tag_role": "article_candidate",
      "is_primary": true,
      "confidence": 0.95,
      "evidence_quotes": ["..."],
      "quote_validation_status": "all_exact",
      "quote_validation_details": [],
      "comment": "..."
    }
  ]
}

Дополнительные входы:

data/tagging/document_tagging_failures_active.jsonl
data/tagging/empty_documents_name_candidates.jsonl

Если дополнительных файлов нет, команда не должна падать. Она должна записать warning в report.

6. Выходные артефакты N1

Создать директорию:

data/normalization/

Обязательные файлы:

data/normalization/tag_mentions_raw.jsonl
data/normalization/tag_mentions_normalized.jsonl
data/normalization/tags_raw.csv
data/normalization/auto_clusters.jsonl
data/normalization/auto_clusters.csv
data/normalization/normalization_n1_report.json
data/normalization/normalization_n1_manifest.json
data/normalization/type_role_stats.csv
data/normalization/suspicious_mentions.jsonl
data/normalization/failed_documents_snapshot.jsonl

Опциональные, но желательные:

data/normalization/top_aliases_by_type.csv
data/normalization/top_canonical_candidates.csv
data/normalization/quote_issue_mentions.jsonl
data/normalization/article_candidate_mentions.jsonl
data/normalization/context_only_mentions.jsonl
7. Формат tag_mentions_raw.jsonl

Одна строка = одна entity mention из tagging-output.

{
  "mention_id": "m_000000001",
  "doc_id": "doc_000001_xxxxxxxx",
  "document_name": "Название документа",
  "entity_index": 0,

  "surface": "сырой surface",
  "canonical_candidate_ru": "сырой candidate ru",
  "canonical_candidate_latin": "сырой candidate latin",

  "entity_type": "disease",
  "tag_role": "article_candidate",
  "article_candidate": true,
  "is_primary": true,
  "confidence": 0.95,

  "evidence_quotes": ["..."],
  "quote_validation_status": "all_exact",
  "quote_validation_details": [],

  "provider": "gemini_direct",
  "model": "gemini-3-flash-preview",
  "prompt_version": "tagging_v2_gemini",
  "schema_version": "document_tagging_v2",

  "source_file": "data/tagging/document_tags_raw_active.jsonl"
}

mention_id должен быть детерминированным. Например:

m_{line_number:07d}_{entity_index:02d}

или hash от doc_id + entity_index + surface + canonical_candidate_ru.

8. Формат tag_mentions_normalized.jsonl

Одна строка = одна mention + все deterministic normalized fields.

{
  "mention_id": "m_000000001",
  "doc_id": "doc_000001_xxxxxxxx",
  "document_name": "Название документа",

  "raw": {
    "surface": "Ахондроплазия",
    "canonical_candidate_ru": "Ахондроплазия",
    "canonical_candidate_latin": "Achondroplasia"
  },

  "normalized": {
    "surface_norm": "ахондроплазия",
    "candidate_ru_norm": "ахондроплазия",
    "candidate_latin_norm": "achondroplasia",
    "primary_norm": "ахондроплазия",
    "display_candidate_ru": "Ахондроплазия",
    "display_candidate_latin": "Achondroplasia"
  },

  "entity_type": "disease",
  "tag_role": "article_candidate",
  "article_candidate": true,
  "confidence": 1.0,

  "normalization_flags": [
    "lowercase",
    "trim",
    "yo_to_e"
  ],

  "suspicious_flags": []
}

primary_norm выбирается так:

Если canonical_candidate_ru непустой, использовать его.
Иначе использовать surface.
Если оба пустые, mention пометить как suspicious.
9. Строковая нормализация

Реализовать функции в kb_rebuild/normalization/text.py.

Базовая нормализация для всех типов:

strip
lowercase
ё → е
unicode normalize NFKC
заменить разные тире на дефис
заменить множественные пробелы одним
убрать пробелы вокруг дефиса
убрать пробелы вокруг slash при необходимости
удалить внешние кавычки
удалить точку/запятую/двоеточие/точку с запятой в конце
удалить лишние внешние скобки
нормализовать латинские буквы в lower-case
убрать html entities, если встретятся

Примеры:

" Болезнь Альцгеймера. " → "болезнь альцгеймера"
"Вольтарен — эмульгель" → "вольтарен-эмульгель"
"Вольтарен – эмульгель" → "вольтарен-эмульгель"
"Vitamax(бад)" → base norm "vitamax(бад)", drug/supplement norm "vitamax"
"β-лактамные антибиотики" → "бета-лактамные антибиотики"

Поддержать замену греческих символов:

β → бета
α → альфа
γ → гамма
δ → дельта
10. Type-specific normalization
10.1 drug_trade_name

Для drug_trade_name создать дополнительный product_name_norm.

Удалять только очевидные формы выпуска / упаковки / дозировки:

таблетки
таблетка
капсулы
капсула
гель
мазь
крем
раствор
сироп
спрей
капли
порошок
саше
суспензия
ампулы
флакон
флаконы
пакетики
пастилки
суппозитории
для наружного применения
для приема внутрь
покрытые оболочкой
пленочной оболочкой
кишечнорастворимые
мг
мкг
мл
г
%
№
n
шт
штук

Удалять числовые дозировки и упаковки:

60 шт
№30
N 20
2%
500 мг
10 мл

Примеры:

"Вольтарен эмульгель гель для наружного применения 2%" → "вольтарен эмульгель"
"Агнукастон таблетки, покрытые оболочкой 60 шт" → "агнукастон"
"Антистин-привин" → "антистин-привин"

Но не удалять слова, если после удаления строка становится пустой или слишком короткой. В таком случае добавлять suspicious flag.

10.2 supplement

Похожая логика:

Удалять:

бад
биологически активная добавка
таблетки
капсулы
порошок
саше
60 шт
№30

Пример:

"Vitamax(бад)" → "vitamax"
10.3 drug_class

Нормализовать:

β → бета
бета лактамные → бета-лактамные
бета-лактамы → бета-лактамные антибиотики

Но на N1 не делать слишком умные синонимы. Только obvious string rules.

10.4 diagnostic_method

Создать simple abbreviation candidates:

иммуноферментный анализ → ифа
enzyme-linked immunosorbent assay → elisa
полимеразная цепная реакция → пцр

На N1 не схлопывать аббревиатуры автоматически, если нет точного evidence в raw aliases. Можно добавить abbreviation_candidate.

10.5 microorganism

Нормализовать:

E. coli → e coli
Escherichia coli → escherichia coli

Не объединять genus и species.

Если строка состоит из одного латинского genus, добавить suspicious flag:

possible_genus_level_entity
10.6 disease

Не удалять модификаторы:

острый
хронический
врожденный
приобретенный
первичный
вторичный
идиопатический
аутоиммунный
наследственный
метастатический

Если модификатор есть, добавить flag:

has_specificity_modifier

Это нужно для будущего N2/N3, чтобы не схлопнуть общий и специфичный диагноз.

11. Suspicious flags

Добавлять suspicious_flags в normalized mentions.

Минимальный набор:

empty_surface
empty_canonical_candidate_ru
very_short_alias
contains_dosage
contains_packaging
contains_specificity_modifier
possible_abbreviation
possible_trade_name_with_dosage
possible_parent_child_term
quote_not_found
low_confidence
context_only
folder_candidate
latin_only
mixed_cyrillic_latin
possible_name_only_entity

Примеры:

confidence < 0.75 → low_confidence
quote_validation_status содержит not_found → quote_not_found
alias длиной <= 3 символа → very_short_alias + possible_abbreviation
tag_role=context_only → context_only
tag_role=folder_candidate → folder_candidate
12. Auto-clustering

Создать auto_clusters.jsonl и auto_clusters.csv.

Auto-cluster — это безопасная группа mentions, которые почти наверняка являются одной строковой сущностью.

На N1 разрешены только безопасные auto-merge правила.

12.1 Auto-cluster key

Создать auto_cluster_key:

entity_type + "::" + normalized.primary_norm

Для drug_trade_name и supplement использовать:

entity_type + "::" + product_name_norm

если product_name_norm валиден.

Для остальных типов:

entity_type + "::" + primary_norm
12.2 Что можно auto-merge

Автоматически объединять только если:

одинаковый entity_type;
одинаковый auto_cluster_key;
normalized string совпадает после safe normalization;
нет критических suspicious flags.

Разрешённые отличия:

регистр
ё/е
дефис/тире
лишние пробелы
внешние кавычки
точка в конце
очевидные формы упаковки для drug_trade_name/supplement
12.3 Что нельзя auto-merge

Не объединять автоматически:

разные entity_type;
disease с разными specificity modifiers;
microorganism genus и species;
drug_trade_name и biological_substance;
drug_trade_name и drug_class;
disease и symptom;
diagnostic_method и procedure;
короткие аббревиатуры;
parent/child terms;
aliases с low_confidence;
aliases с quote_not_found, если они единственное подтверждение кластера.
12.4 Auto-cluster format

auto_clusters.jsonl:

{
  "auto_cluster_id": "ac_000001",
  "entity_type": "disease",
  "auto_cluster_key": "disease::ахондроплазия",

  "canonical_display_candidate": "Ахондроплазия",
  "canonical_latin_candidate": "Achondroplasia",

  "aliases": [
    "Ахондроплазия",
    "ахондроплазия"
  ],

  "normalized_aliases": [
    "ахондроплазия"
  ],

  "mention_ids": [
    "m_000000001",
    "m_000000182"
  ],

  "documents_count": 2,
  "mentions_count": 2,

  "roles_count": {
    "article_candidate": 2
  },

  "article_candidate_count": 2,
  "context_only_count": 0,
  "folder_candidate_count": 0,

  "confidence_stats": {
    "min": 0.92,
    "avg": 0.97,
    "max": 1.0
  },

  "quote_status_count": {
    "all_exact": 2
  },

  "normalization_method": "deterministic_exact_norm",
  "review_required": false,
  "review_reasons": []
}
12.5 Canonical display choice

На N1 canonical display candidate — не финальный canonical tag, но нужно выбрать удобный вариант.

Правила:

Брать наиболее частый canonical_candidate_ru.
Если есть вариант с нормальной капитализацией, выбрать его.
Не выбирать all-lowercase, если есть human-looking вариант.
Для латиницы сохранять общепринятую капитализацию, если она встречалась.
Для drug_trade_name сохранять брендовый вариант, если он встречался.
13. CSV outputs
13.1 tags_raw.csv

Поля:

raw_value
normalized_value
entity_type
tag_role
article_candidate
mentions_count
documents_count
avg_confidence
quote_not_found_count
examples
13.2 auto_clusters.csv

Поля:

auto_cluster_id
entity_type
canonical_display_candidate
canonical_latin_candidate
aliases
normalized_aliases
mentions_count
documents_count
article_candidate_count
folder_candidate_count
context_only_count
avg_confidence
quote_not_found_count
review_required
review_reasons
13.3 type_role_stats.csv

Поля:

entity_type
tag_role
article_candidate
mentions_count
documents_count
unique_normalized_count
14. Reports

Создать normalization_n1_report.json.

Минимальная структура:

{
  "stage": "normalization_n1",
  "created_at": "...",

  "input": {
    "tagging_active_path": "data/tagging/document_tags_raw_active.jsonl",
    "failures_path": "data/tagging/document_tagging_failures_active.jsonl",
    "empty_candidates_path": "data/tagging/empty_documents_name_candidates.jsonl"
  },

  "counts": {
    "documents_with_tags": 0,
    "failed_documents": 0,
    "mentions_total": 0,
    "unique_raw_values": 0,
    "unique_normalized_values": 0,
    "auto_clusters_total": 0,
    "auto_clusters_review_required": 0,
    "suspicious_mentions": 0,
    "quote_issue_mentions": 0
  },

  "entity_type_counts": {},
  "tag_role_counts": {},
  "article_candidate_counts": {
    "true": 0,
    "false": 0
  },

  "quote_status_counts": {},

  "top_entity_types": [],
  "top_raw_tags": [],
  "top_normalized_tags": [],

  "warnings": []
}

Создать normalization_n1_manifest.json:

{
  "stage": "normalization_n1",
  "created_at": "...",
  "source_tagging_run_id": "...",
  "source_provider": "gemini_direct",
  "source_model": "gemini-3-flash-preview",
  "source_prompt_version": "tagging_v2_gemini",
  "source_schema_version": "document_tagging_v2",

  "outputs": {
    "tag_mentions_raw": "data/normalization/tag_mentions_raw.jsonl",
    "tag_mentions_normalized": "data/normalization/tag_mentions_normalized.jsonl",
    "tags_raw_csv": "data/normalization/tags_raw.csv",
    "auto_clusters_jsonl": "data/normalization/auto_clusters.jsonl",
    "auto_clusters_csv": "data/normalization/auto_clusters.csv",
    "report": "data/normalization/normalization_n1_report.json"
  }
}
15. Failed documents

Сохранить snapshot:

data/normalization/failed_documents_snapshot.jsonl

Он должен содержать все failed documents из tagging stage.

N1 не должен пытаться их исправлять.

Для empty_clean_text добавить:

{
  "doc_id": "...",
  "document_name": "...",
  "failure_reason": "empty_clean_text",
  "suggested_followup": "name_only_recovery_after_normalization"
}
16. Quote issue mentions

Создать:

data/normalization/quote_issue_mentions.jsonl

Туда положить mentions, где:

quote_validation_status содержит not_found;
любая цитата содержит ... или …;
evidence quote пустая;
quote_validation_details содержит not_found.

Формат:

{
  "mention_id": "...",
  "doc_id": "...",
  "document_name": "...",
  "entity_type": "...",
  "canonical_candidate_ru": "...",
  "quote_validation_status": "...",
  "evidence_quotes": [],
  "issue_type": "quote_not_found"
}
17. Валидация

N1 runner должен проверять:

input tagging active file exists;
JSONL строки валидны;
каждый record имеет doc_id;
entities является списком;
каждая mention получает mention_id;
mention_id уникален;
auto_cluster_id уникален;
каждый mention_id из auto_clusters существует в tag_mentions_normalized;
tagging input не изменяется;
output directory создан;
report записан.

Если часть строк невалидна, pipeline не должен падать полностью. Невалидные records сохранять в:

data/normalization/invalid_tagging_records.jsonl

и добавлять warning в report.

18. Unit tests

Добавить тесты:

tests/test_normalization_text.py
tests/test_normalization_mentions.py
tests/test_normalization_auto_cluster.py
tests/test_normalization_n1_runner.py

Минимальные кейсы:

Text normalization
lowercase
trim
ё/е
тире/дефис
внешние кавычки
точка в конце
греческая beta
drug dosage removal
supplement (бад) cleanup
Mentions flattening
один документ с одной сущностью
документ с несколькими сущностями
документ без entities
malformed record
missing canonical_candidate_ru
quote_not_found mention
Auto-cluster
identical normalized disease merges
different entity_type does not merge
drug dosage variants merge
chronic/acute disease does not unsafe-merge if rules detect modifier
abbreviation is flagged review_required
genus/species microorganism not auto-merged
Runner
creates all required files
report counts are correct
does not modify input file
handles missing failures file
writes failed snapshot

Запуск:

.venv/bin/python -m unittest discover -s tests

Compile check:

.venv/bin/python -m py_compile \
  kb_rebuild/normalization/text.py \
  kb_rebuild/normalization/mentions.py \
  kb_rebuild/normalization/auto_cluster.py \
  kb_rebuild/normalization/report.py \
  kb_rebuild/normalization/n1_runner.py \
  kb_rebuild/cli.py
19. Команда запуска N1

После реализации:

.venv/bin/python -m kb_rebuild normalize-n1 \
  --data data \
  --tagging-active-path data/tagging/document_tags_raw_active.jsonl \
  --failures-path data/tagging/document_tagging_failures_active.jsonl \
  --empty-candidates-path data/tagging/empty_documents_name_candidates.jsonl \
  --out data/normalization
20. Acceptance criteria

N1 считается выполненным, если:

добавлена CLI-команда normalize-n1;
tagging-output не изменяется;
создан пакет kb_rebuild/normalization;
создан tag_mentions_raw.jsonl;
создан tag_mentions_normalized.jsonl;
создан tags_raw.csv;
создан auto_clusters.jsonl;
создан auto_clusters.csv;
создан normalization_n1_report.json;
создан normalization_n1_manifest.json;
создан failed_documents_snapshot.jsonl;
создан quote_issue_mentions.jsonl;
deterministic normalization работает по типам;
auto-clustering не объединяет разные entity types;
auto-clustering не делает опасные semantic merges;
tests проходят;
feedback-файл создан.
21. Feedback исполнителя

В конце работы создать:

docs/normalization_n1_feedback.md

В feedback указать:

что сделано;
какие файлы изменены;
какие команды запускались;
какие тесты прошли;
сколько mentions собрано;
сколько unique raw tags;
сколько unique normalized tags;
сколько auto-clusters;
сколько clusters review_required;
топ-20 entity types;
топ-50 raw tags;
топ-50 normalized tags;
сколько quote issues;
сколько failed documents перенесено;
какие риски остались;
что нужно делать на N2.
22. Важное ограничение

Не начинать N2/N3 в этом этапе. N1 должен только подготовить данные и безопасно схлопнуть очевидные строковые дубли.

Следующий этап будет отдельно: candidate generation + LLM cluster validation.


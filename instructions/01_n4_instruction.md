# N4. Final canonical layer: полный финальный список тегов, aliases и замена всех document-tag links

## 0. Критически важное уточнение

N3 accepted clusters — это НЕ полный список финальных тегов.

N3 accepted clusters — это только validated merge decisions, то есть правила вида:

```text
эти несколько уже существующих tag nodes являются одной сущностью

Полный финальный список тегов должен строиться из ВСЕХ N1/N1.1 auto_clusters.

Если auto_cluster не участвовал ни в одном N3 accepted merge, он всё равно должен стать отдельным final canonical tag.

Иными словами:

каждый N1/N1.1 auto_cluster обязан попасть в финальный canonical layer

либо:

как самостоятельный final tag

либо:

как часть компоненты, объединённой через N3 accepted clusters

Нельзя создавать финальный список только из data/normalization/n3/accepted_clusters.jsonl.

1. Контекст

Этап tagging завершён:

documents_requested = 16181
documents_tagged = 16161
documents_failed = 20

20 failed документов не участвуют в текущем N4, но должны быть сохранены для recovery-трека.

Этап N1/N1.1 собрал полный слой mentions и auto-clusters:

mentions_total = 42324
documents_with_tags = 16161
unique_raw_values = 22710
unique_normalized_values = 22116
auto_clusters_total ≈ 22-23k

Эти mentions и auto_clusters являются основой полного финального canonical layer.

Этап N3 обработал только candidate groups из N2.2:

groups_total = 363
accepted_clusters_total = 333

Это только слой дополнительных объединений, а не весь список тегов.

2. Главная цель N4

Создать полный финальный слой нормализации:

каждая исходная mention → final tag_id

и полный список финальных canonical tags:

каждый N1/N1.1 auto_cluster → final tag_id

Итоговые артефакты:

data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv
data/normalization/final/document_tag_links_normalized.jsonl
data/normalization/final/document_tag_links_normalized.csv
data/normalization/final/document_tags_normalized_by_doc.jsonl
data/normalization/final/final_canonical_tag_names.csv
data/normalization/final/specialist_review_full.csv
data/normalization/final/specialist_review_sample.csv
data/normalization/final/final_normalization_report.json
data/normalization/final/final_normalization_manifest.json
3. Не цели N4

На N4 запрещено:

вызывать LLM;
делать новые semantic merges;
удалять standalone tags;
менять N1/N2/N3 artifacts;
менять data/tagging/*;
менять data/parsed/*;
создавать статьи;
извлекать evidence;
строить папки;
строить граф знаний.

N4 только собирает финальную canonical-таблицу и заменяет связи документов с raw tags на final tag_id.

4. Основной принцип

N4 должен работать по формуле:

Base nodes = все auto_clusters из N1/N1.1
Merge edges = все безопасные N3 accepted clusters
Final components = connected components графа
Final canonical tags = one tag per final component

Если auto_cluster не входит ни в один N3 accepted cluster:

он остаётся отдельным final canonical tag
5. Входные файлы

Обязательные входы:

data/normalization/auto_clusters.jsonl
data/normalization/tag_mentions_normalized.jsonl
data/normalization/tag_mentions_raw.jsonl
data/normalization/normalization_n1_manifest.json
data/normalization/normalization_n1_report.json

data/normalization/n2/candidate_nodes.jsonl
data/normalization/n2/candidate_generation_manifest.json
data/normalization/n2/candidate_generation_report.json

data/normalization/n3/accepted_clusters.jsonl
data/normalization/n3/rejected_groups.jsonl
data/normalization/n3/split_groups.jsonl
data/normalization/n3/web_or_human_review_groups.jsonl
data/normalization/n3/llm_group_decisions.jsonl
data/normalization/n3/n3_report.json
data/normalization/n3/n3_manifest.json
data/normalization/n3/n3_quality_diagnostics.json

N4 должен проверять:

N3 manifest stage_version = n3.0
N3 quality passed = true
N1 mentions_total > 0
auto_clusters_total > 0
candidate_nodes exists
accepted_clusters exists
6. Выходные файлы

Создать директорию:

data/normalization/final/

Обязательные outputs:

tags_canonical.csv
tag_aliases.csv
document_tag_links_normalized.jsonl
document_tag_links_normalized.csv
document_tags_normalized_by_doc.jsonl

final_canonical_tag_names.csv
specialist_review_full.csv
specialist_review_sample.csv
canonical_review_detailed.csv

coverage_audit.json
coverage_audit_missing_mentions.csv
coverage_audit_missing_aliases.csv

alias_conflicts.csv
merge_conflicts.jsonl
drug_policy_review.csv
unresolved_review_groups.jsonl

final_normalization_report.json
final_normalization_manifest.json
7. Полный список финальных тегов без aliases

Создать файл:

data/normalization/final/final_canonical_tag_names.csv

Это полный список финальных тегов-сущностей без aliases.

Поля:

tag_id
canonical_tag_ru
canonical_tag_latin
entity_type
need_review

Важно:

число строк в final_canonical_tag_names.csv должно равняться числу финальных canonical tags

Этот файл нужен для быстрой проверки специалистом: “какие сущности вообще есть в финальной базе”.

8. Specialist review CSV

Создать два review-файла.

8.1 Полный review
data/normalization/final/specialist_review_full.csv

Ровно 4 колонки:

canonical_tag_ru
canonical_tag_latin
aliases
need_review

Где:

canonical_tag_ru

Русское финальное название.

canonical_tag_latin

Латинское/английское название или null.

aliases

JSON-list строк:

["Болезнь Аддисона", "Аддисонова болезнь"]
need_review

true или false.

Этот файл должен содержать ВСЕ финальные canonical tags.

8.2 Репрезентативная выборка
data/normalization/final/specialist_review_sample.csv

Тоже ровно 4 колонки:

canonical_tag_ru
canonical_tag_latin
aliases
need_review

Размер задаётся параметром:

--review-sample-size 500

Логика отбора:

Включить все need_review=true, если их меньше лимита.
Если их больше лимита, взять самые важные по:
drug_policy_review;
alias_conflict;
merge_conflict;
high mentions_count;
high documents_count.
Добавить top frequent tags по каждому entity_type.
Добавить deterministic random sample по hash.
Сохранить разнообразие по entity_type.
9. Graph construction
9.1 Base graph nodes

Каждый auto_cluster из N1/N1.1 — отдельная вершина:

auto_cluster_id

Каждая такая вершина должна попасть в final graph.

9.2 Mapping node_id → auto_cluster_id

Из N2 candidate_nodes.jsonl построить:

node_id → auto_cluster_id
9.3 Accepted merge edges

Каждый N3 accepted cluster содержит node_ids.

N4 должен:

взять node_ids;
найти соответствующие auto_cluster_id;
добавить edges между этими auto_cluster_id;
сохранить provenance:
n3_cluster_id;
source_candidate_group_id;
confidence;
reason;
labels.
9.4 Standalone components

Если auto_cluster не имеет accepted merge edges:

component = [auto_cluster_id]

и создаётся standalone final tag.

10. Connected components

После построения graph:

connected component = final canonical tag candidate

Но N4 должен проверить:

entity_type внутри component один;
нет rejected constraint conflict;
нет drug policy conflict;
нет alias conflict;
нет unknown node_id;
нет пустого canonical_tag_ru.

Если конфликт не критический:

need_review=true

Если конфликт критический:

не применять merge edge

и записать в:

merge_conflicts.jsonl
11. N3 rejected/review constraints
11.1 rejected_groups

rejected_groups.jsonl означает:

эти node_ids/labels не должны быть объединены в одну сущность

Если rejected nodes оказались в одной final component, N4 должен:

need_review=true
review_reason=rejected_constraint_conflict

Если конфликт прямой и merge пришёл только через слабый N3 accepted cluster:

разорвать merge edge
11.2 web_or_human_review_groups

Не применять как merge.

Добавить в:

unresolved_review_groups.jsonl
11.3 split_groups

Использовать как provenance.

Accepted subclusters из split уже должны быть в accepted_clusters.jsonl.

Singleton/rejected части split не объединять.

12. Drug policy guard

Для entity_type=drug_trade_name действует правило:

финальная сущность лекарства = торговое название

Торговое название и действующее вещество / соль / МНН не должны автоматически становиться обычными aliases одного final tag.

Примеры:

Бетасерк | Бетагистина дигидрохлорид
Амикацин | Амикацина сульфат
Бусерелин | Бусерелина ацетат
Амловас | Амлодипин
Страттера | Атомоксетин

Если такой merge найден:

Не применять merge автоматически, если это возможно.

Если component уже создана, пометить:

need_review=true
review_reason=drug_trade_name_active_substance_conflict

Alias действующего вещества пометить:

alias_status=blocked_active_substance_candidate

Записать строку в:

drug_policy_review.csv
13. Canonical selection

Для каждой final component выбрать:

canonical_tag_ru
canonical_tag_latin
13.1 Приоритет canonical_tag_ru
N3 accepted canonical с высоким confidence.
Если несколько N3 canonical конфликтуют — выбрать лучший, но need_review=true.
Если N3 нет — canonical_display_candidate из auto_cluster.
Для drug_trade_name / supplement — чистое название без дозировки.
Для disease subtype — не терять subtype marker.
Не выбирать слишком широкий generic alias, если есть более точное название.
13.2 canonical_tag_latin
N3 canonical_tag_latin.
N1/N2 latin candidate.
Иначе null.
14. tag_id

Создать стабильный deterministic tag_id.

Формат:

{entity_type}_{hash10}

Hash от:

entity_type
canonical_tag_ru_norm
canonical_tag_latin_norm
sorted normalized aliases

Пример:

disease_a1b2c3d4e5
drug_trade_name_f9e8d7c6b5
15. tags_canonical.csv

Поля:

tag_id
canonical_tag_ru
canonical_tag_latin
entity_type
primary_role
article_candidate
status
need_review
review_reasons
aliases_count
mentions_count
documents_count
confidence
normalization_source
merge_method
auto_cluster_ids
n3_cluster_ids
source_candidate_group_ids
created_from_stage
status
active
needs_review
context_only
folder_candidate
normalization_source
n1_auto_cluster
n3_accepted
n3_split_accepted
n4_drug_policy_review
n4_conflict_review
merge_method
single_auto_cluster
deterministic
llm_validated
llm_split_validated
review_required
16. tag_aliases.csv

Одна строка = один alias.

Поля:

alias_id
tag_id
alias
alias_norm
alias_latin
entity_type
alias_source
alias_status
mention_count
document_count
confidence
need_review
review_reasons
alias_source
n1_surface
n1_canonical_candidate_ru
n1_canonical_candidate_latin
n1_auto_cluster_alias
n3_label
n3_canonical
n4_generated
alias_status
active
needs_review
blocked_active_substance_candidate
conflict_alias
17. Железная проверка покрытия aliases

Это обязательное условие N4.

Каждый исходный tag/mention из 16 161 успешно протегированных документов должен распознаваться через:

canonical names + aliases

Проверять по данным:

data/normalization/tag_mentions_normalized.jsonl

Для каждой mention проверить:

surface
canonical_candidate_ru
canonical_candidate_latin
normalized.primary_norm
normalized.surface_norm
normalized.candidate_ru_norm
normalized.candidate_latin_norm

Если непустое значение есть в исходной mention, оно должно быть найдено в alias index:

(entity_type, normalized_name) → tag_id

Где alias index строится из:

tags_canonical.canonical_tag_ru
tags_canonical.canonical_tag_latin
tag_aliases.alias
tag_aliases.alias_latin

Если что-то не найдено:

coverage_audit_missing_aliases.csv

и:

coverage_audit.quality.passed = false
coverage_audit_missing_aliases.csv

Поля:

mention_id
doc_id
document_name
entity_type
missing_value
missing_value_norm
source_field
raw_surface
raw_canonical_candidate_ru
raw_canonical_candidate_latin
expected_tag_id
reason
Требование

Для acceptance:

missing_aliases_count = 0

Исключение допускается только для пустых значений.

18. document_tag_links_normalized.jsonl

Одна строка = одна исходная mention.

Количество строк должно быть равно:

mentions_total из N1/N1.1

Формат:

{
  "doc_id": "doc_000001_xxxxxxxx",
  "document_name": "...",
  "mention_id": "m_0000001_00",

  "raw_surface": "...",
  "raw_canonical_candidate_ru": "...",
  "raw_canonical_candidate_latin": "...",

  "entity_type": "disease",
  "tag_role": "article_candidate",
  "article_candidate": true,
  "confidence": 0.95,

  "tag_id": "disease_a1b2c3d4e5",
  "canonical_tag_ru": "Болезнь Аддисона",
  "canonical_tag_latin": "Addison disease",

  "normalization_source": "n3_accepted",
  "need_review": false,
  "review_reasons": []
}
19. document_tag_links_normalized.csv

CSV mirror:

doc_id
document_name
mention_id
entity_type
raw_surface
raw_canonical_candidate_ru
raw_canonical_candidate_latin
tag_id
canonical_tag_ru
canonical_tag_latin
tag_role
article_candidate
confidence
normalization_source
need_review
review_reasons
20. document_tags_normalized_by_doc.jsonl

Одна строка = один документ.

{
  "doc_id": "...",
  "document_name": "...",
  "tags": [
    {
      "tag_id": "...",
      "canonical_tag_ru": "...",
      "canonical_tag_latin": "...",
      "entity_type": "...",
      "tag_role": "...",
      "article_candidate": true,
      "need_review": false
    }
  ]
}

Внутри документа убрать дубли tag_id.

Количество документов должно быть равно числу документов с mentions:

documents_with_tags = 16161
21. Полная проверка покрытия document links

Создать:

coverage_audit.json

Структура:

{
  "mentions_total": 42324,
  "document_tag_links_total": 42324,
  "mentions_without_tag_id": 0,
  "links_to_missing_tag_id": 0,
  "aliases_missing_for_original_mentions": 0,
  "documents_with_mentions": 16161,
  "documents_with_normalized_tags": 16161,
  "all_mentions_have_tag_id": true,
  "all_original_tag_names_recognized": true,
  "passed": true
}

Acceptance:

mentions_without_tag_id = 0
links_to_missing_tag_id = 0
aliases_missing_for_original_mentions = 0
all_mentions_have_tag_id = true
all_original_tag_names_recognized = true
passed = true
22. final_normalization_report.json

Добавить обязательные counts:

{
  "counts": {
    "mentions_total": 0,
    "document_tag_links_total": 0,
    "documents_with_tags": 0,
    "documents_with_normalized_tags": 0,

    "auto_clusters_total": 0,
    "n3_accepted_clusters_total": 0,
    "final_canonical_tags_total": 0,

    "standalone_auto_cluster_tags": 0,
    "merged_n3_tags": 0,

    "aliases_total": 0,
    "need_review_tags": 0,
    "alias_conflicts": 0,
    "merge_conflicts": 0,
    "drug_policy_review_items": 0,
    "unresolved_review_groups": 0
  },

  "quality": {
    "all_mentions_have_tag_id": true,
    "all_original_tag_names_recognized": true,
    "no_empty_canonical_tag_ru": true,
    "no_missing_tag_ids_in_links": true,
    "no_alias_without_tag_id": true,
    "no_duplicate_tag_ids": true,
    "final_canonical_tag_names_created": true,
    "specialist_review_full_created": true,
    "specialist_review_sample_created": true,
    "passed": true
  }
}
23. final_normalization_manifest.json

Обязательные outputs:

{
  "outputs": {
    "tags_canonical_csv": "data/normalization/final/tags_canonical.csv",
    "tag_aliases_csv": "data/normalization/final/tag_aliases.csv",
    "document_tag_links_normalized_jsonl": "data/normalization/final/document_tag_links_normalized.jsonl",
    "document_tag_links_normalized_csv": "data/normalization/final/document_tag_links_normalized.csv",
    "document_tags_normalized_by_doc_jsonl": "data/normalization/final/document_tags_normalized_by_doc.jsonl",
    "final_canonical_tag_names_csv": "data/normalization/final/final_canonical_tag_names.csv",
    "specialist_review_full_csv": "data/normalization/final/specialist_review_full.csv",
    "specialist_review_sample_csv": "data/normalization/final/specialist_review_sample.csv",
    "coverage_audit_json": "data/normalization/final/coverage_audit.json",
    "coverage_audit_missing_aliases_csv": "data/normalization/final/coverage_audit_missing_aliases.csv",
    "coverage_audit_missing_mentions_csv": "data/normalization/final/coverage_audit_missing_mentions.csv",
    "final_report": "data/normalization/final/final_normalization_report.json"
  }
}
24. Tests

Добавить/обновить tests:

tests/test_normalization_n4_graph.py
tests/test_normalization_n4_canonical.py
tests/test_normalization_n4_aliases.py
tests/test_normalization_n4_links.py
tests/test_normalization_n4_coverage.py
tests/test_normalization_n4_review.py
tests/test_normalization_n4_runner.py
24.1 Graph tests
every auto_cluster becomes final tag if no N3 merge;
N3 accepted cluster merges auto_clusters;
overlapping accepted clusters deduplicate into one component;
rejected constraint marks review;
unknown node_id goes to merge_conflicts.
24.2 Full coverage tests
every mention gets tag_id;
document_tag_links count equals mentions count;
every raw surface is in canonical+aliases index;
every canonical_candidate_ru is in canonical+aliases index;
every canonical_candidate_latin is in canonical+aliases index if non-empty;
coverage audit fails if alias missing.
24.3 Final names tests
final_canonical_tag_names.csv exists;
contains all final tags;
contains no aliases column;
no empty canonical_tag_ru;
tag_id unique.
24.4 Specialist review tests

specialist_review_full.csv has exactly 4 columns:

canonical_tag_ru
canonical_tag_latin
aliases
need_review
specialist_review_sample.csv has exactly same 4 columns;
aliases is JSON-list;
canonical_tag_latin is null if empty;
need_review is true/false.
24.5 Drug policy tests
trade name + active substance triggers review/block;
dosage variants of same trade name allowed;
blocked active substance aliases are not normal active aliases.
25. Команда запуска
.venv/bin/python -m kb_rebuild normalize-n4 \
  --data data \
  --normalization-dir data/normalization \
  --n2-dir data/normalization/n2 \
  --n3-dir data/normalization/n3 \
  --out data/normalization/final \
  --review-sample-size 500
26. Acceptance criteria

N4 принимается, если:

tags_canonical.csv создан;
tag_aliases.csv создан;
document_tag_links_normalized.jsonl создан;
document_tag_links_normalized.csv создан;
document_tags_normalized_by_doc.jsonl создан;
final_canonical_tag_names.csv создан;
specialist_review_full.csv создан;
specialist_review_sample.csv создан;
coverage_audit.json создан;
coverage_audit.passed = true;
coverage_audit_missing_aliases.csv пустой кроме header;
coverage_audit_missing_mentions.csv пустой кроме header;
каждый mention получил tag_id;
каждый исходный tag распознаётся через canonical+aliases;
каждый tag_id в links существует в tags_canonical;
каждый alias указывает на существующий tag_id;
final report quality.passed = true;
tests passed;
feedback создан.
27. Feedback после N4

Создать:

docs/normalization_n4_feedback.md

Feedback должен содержать:

1. Что сделано.
2. Какие файлы изменены.
3. Какие команды запускались.
4. Сколько tests passed.
5. Сколько mentions_total.
6. Сколько document_tag_links_total.
7. Сколько final canonical tags.
8. Сколько standalone auto_cluster tags.
9. Сколько merged N3 tags.
10. Сколько aliases.
11. Сколько documents_with_normalized_tags.
12. Coverage audit:
    - mentions_without_tag_id
    - aliases_missing_for_original_mentions
    - all_original_tag_names_recognized
    - passed
13. Сколько need_review tags.
14. Сколько alias conflicts.
15. Сколько merge conflicts.
16. Сколько drug policy review items.
17. Путь к final_canonical_tag_names.csv.
18. Путь к specialist_review_full.csv.
19. Путь к specialist_review_sample.csv.
20. Что не сделано.
21. Риски.
22. Что передать следующему этапу.

Обязательно указать:

Все N1/N1.1 auto_clusters покрыты: yes/no
Все mentions получили tag_id: yes/no
Все исходные raw tag names распознаются через canonical+aliases: yes/no
28. Главное напоминание

N4 не должен “применить только 333 N3 clusters”.

N4 должен применить 333 N3 clusters как merge-rules поверх полного множества N1/N1.1 auto_clusters.

Итоговый финальный список тегов должен быть полным:

все standalone теги
+
все merged теги
=
полный canonical layer

И коротко по сути: **ничего из остальных ~22k normalized сущностей не должно потеряться**.  
Они просто не были объединены N3 и поэтому должны попасть в финальный список как самостоятельные canonical tags.
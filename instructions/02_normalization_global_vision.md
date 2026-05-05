# 02_normalization_global_vision.md

# Общее видение этапа нормализации тегов

## 0. Зачем нужен этап нормализации

После LLM-тегирования у нас есть множество документов, и у каждого документа есть набор извлечённых сущностей. Но эти сущности пока являются сырыми представлениями. Одна и та же реальная сущность может называться по-разному:

```text
болезнь альцгеймера
Альцгеймер
болезнь Альцгеймера
Alzheimer disease

Или:

ИФА
иммуноферментный анализ
ELISA
enzyme-linked immunosorbent assay

Если не провести нормализацию, downstream-этапы создадут несколько документов для одной сущности. Это разрушит цель пересборки базы знаний.
Цель нормализации:

одна реальная сущность = один canonical tag = один tag_id

Все варианты написания должны стать aliases этой сущности.

1. Что должно получиться в конце всей нормализации

Финальные артефакты полного этапа нормализации:

data/normalization/tags_canonical.csv
data/normalization/tag_aliases.csv
data/normalization/document_tag_links_normalized.jsonl
data/normalization/clusters_for_review.csv
data/normalization/clusters_for_review.jsonl
data/normalization/normalization_report.json

Главные таблицы:

tags_canonical.csv

Одна строка = одна финальная сущность.

tag_id
canonical_tag_ru
canonical_tag_latin
entity_type
primary_role
article_candidate
aliases_count
mentions_count
documents_count
normalization_confidence
review_status
tag_aliases.csv

Одна строка = один alias.

alias
normalized_alias
tag_id
canonical_tag_ru
canonical_tag_latin
entity_type
source
confidence
review_status
document_tag_links_normalized.jsonl

Одна строка = связь документа с финальным canonical tag.

{
  "doc_id": "doc_000123_xxxxxxxx",
  "raw_surface": "Альцгеймер",
  "raw_canonical_candidate_ru": "болезнь Альцгеймера",
  "entity_type": "disease",
  "tag_id": "disease_000045",
  "canonical_tag_ru": "Болезнь Альцгеймера",
  "canonical_tag_latin": "Alzheimer disease",
  "tag_role": "article_candidate",
  "article_candidate": true,
  "normalization_method": "llm_cluster",
  "normalization_confidence": 0.96
}
2. Главный архитектурный принцип

Нормализация — это отдельный слой.

Tagging-output не редактируется и не удаляется.

Нужно хранить:

raw LLM entity
normalized mention
cluster decision
final canonical tag
document link to canonical tag

Это позволит откатывать решения, проверять кластеры вручную и улучшать нормализацию без повторного LLM-тегирования всего корпуса.

3. Почему нельзя сразу отдать всё LLM

В корпусе десятки тысяч mentions. Если отправить всё в LLM одним большим списком, будут проблемы:

высокая стоимость;
большой риск ошибки;
смешение разных типов сущностей;
схлопывание широких и узких понятий;
невозможность проверить решения;
плохая воспроизводимость;
трудно понять, почему конкретный alias попал в cluster.

Правильный подход:

deterministic cleanup → candidate clusters → LLM validation only for candidates → human review → final canonical map

LLM должна быть арбитром в сложных случаях, а не единственным механизмом нормализации.

4. Этапы нормализации
N1. Подготовка и deterministic normalization

Цель:

собрать все mentions;
нормализовать строки;
схлопнуть очевидные дубли;
подготовить auto-clusters;
собрать статистику;
выделить suspicious mentions;
не вызывать LLM.

Выход:

tag_mentions_raw.jsonl
tag_mentions_normalized.jsonl
auto_clusters.jsonl
auto_clusters.csv
normalization_n1_report.json
N2. Candidate generation

Цель:

построить candidate pairs/groups для возможного merge;
работать только внутри одного entity_type;
использовать edit distance, token similarity, abbreviations, latin candidates, product-name cleanup, co-occurrence;
не утверждать merge, а только предложить.

Выход:

candidate_pairs.jsonl
candidate_groups.jsonl
candidate_generation_report.json
N3. LLM cluster validation

Цель:

отправить в Gemini только candidate groups;
получить решение: merge / do not merge / parent-child / needs_review;
выбрать canonical tag;
сохранить aliases;
сохранить причины решений.

Выход:

llm_cluster_decisions.jsonl
clusters_for_review.jsonl
clusters_for_review.csv
N4. Final canonical layer

Цель:

объединить auto-clusters + LLM decisions + manual overrides;
создать финальные canonical tags;
создать alias mapping;
заменить raw tags в document links на tag_id.

Выход:

tags_canonical.csv
tag_aliases.csv
document_tag_links_normalized.jsonl
normalization_report.json
5. Что считать одной сущностью

Одна сущность — это самостоятельный объект знания, вокруг которого потенциально можно собрать документ, графовую вершину или устойчивый alias.

Примеры одной сущности:

Ахондроплазия
Achondroplasia
→ Ахондроплазия
ИФА
иммуноферментный анализ
ELISA
→ Иммуноферментный анализ
Вольтарен эмульгель гель для наружного применения 2%
Вольтарен Эмульгель
Вольтарен эмульгель
→ Вольтарен Эмульгель
6. Что НЕ считать одной сущностью

Не объединять автоматически:

сердце
порок сердца
врожденный порок сердца
митральный стеноз
гастрит
хронический гастрит
острый гастрит
атрофический гастрит
антибиотики
макролиды
тетрациклины
аминогликозиды
Escherichia
Escherichia coli
E. coli

E. coli и Escherichia coli можно объединить.

Escherichia и Escherichia coli нельзя автоматически объединять, потому что это род и вид.

7. Роль entity_type

Нормализация должна идти внутри entity_type.

По умолчанию нельзя объединять разные типы:

drug_trade_name + drug_class
drug_trade_name + biological_substance
disease + symptom
diagnostic_method + procedure
organ_or_body_system + disease
microorganism + disease

Исключения возможны только через LLM + review, но не на deterministic этапах.

8. Роль tag_role и article_candidate

Tagging-output содержит:

tag_role = article_candidate | folder_candidate | context_only
article_candidate = true | false

Нормализация должна учитывать эти поля.

Предлагаемая логика:

article_candidate=true
  → кандидат на будущий документ-сущность

folder_candidate
  → кандидат на папку, раздел или высокий уровень иерархии

context_only
  → полезно для графа и связей, но не должно автоматически создавать статью

Важно: нормализовать нужно все роли, но финальные документы-сущности создавать прежде всего из article_candidate.

9. Риски parent-child merge

Самая опасная ошибка нормализации — схлопнуть родительскую и дочернюю сущность.

Пример:

диабет
сахарный диабет
сахарный диабет 1 типа

Наивный алгоритм может решить, что всё похоже, и объединить в один cluster. Это неправильно.

Нужно различать:

same_entity
alias_of_same_entity
parent_child
related_but_distinct
not_related

LLM validation на N3 должна возвращать такие решения.

10. Риски transitive merge

Нельзя строить кластеры только по connected components:

A похож на B
B похож на C
A не равен C

Если без проверки объединить A, B, C, получится ложный cluster.

Поэтому после candidate generation нужна cluster validation.

11. Типовые правила по entity_type
disease

Схлопывать:

Ахондроплазия
Achondroplasia
→ Ахондроплазия

Осторожно:

острый
хронический
врожденный
приобретенный
первичный
вторичный
наследственный
метастатический

Эти слова часто означают отдельную сущность или подтип.

drug_trade_name

Торговое название — это не действующее вещество.

Нурофен ≠ Ибупрофен
Вольтарен ≠ Диклофенак

Формы выпуска и упаковки можно убрать:

таблетки
капсулы
гель
мазь
раствор
спрей
60 шт
500 мг
2%
supplement

Похоже на drug trade names, но коммерческое название БАД часто важно.

Vitamax(бад)
Витамакс
Vitamax
→ Vitamax / Витамакс

Не объединять БАД с ингредиентом без отдельной причины.

drug_class

Не объединять широкий класс и подкласс:

антибиотики ≠ макролиды
антибиотики ≠ тетрациклины
diagnostic_method

Часто есть аббревиатуры:

ИФА = иммуноферментный анализ = ELISA
ПЦР = полимеразная цепная реакция = PCR

Но аббревиатуры лучше подтверждать через candidates + LLM.

microorganism

Сохранять различие taxonomic levels:

род ≠ вид ≠ штамм
biological_substance

Гены/белки/медиаторы могут иметь латинские aliases:

FGFR3
IL-2
TNF
ФНО

Нужно осторожно выбирать canonical.

organ_or_body_system

Часто это folder/context entities. Не раздувать документы на общие сущности, если они не являются темой.

12. Human review

Нормализация должна сохранять clusters для ручной проверки.

Особенно review_required для:

кластеров с высоким mention count;
коротких aliases;
аббревиатур;
parent-child подозрений;
разных ролей;
низкой confidence;
quote issues;
лекарств с дозировками;
болезней с модификаторами;
biological substances с латинскими aliases.
13. Как downstream должен использовать нормализацию

После нормализации downstream должен читать:

document_tag_links_normalized.jsonl

А не raw tagging-output.

Но raw tagging-output всегда должен оставаться доступным для audit.

Финальные статьи будут строиться по:

tag_id
canonical_tag_ru
entity_type
article_candidate=true
source document links
evidence extraction
14. Текущий ближайший шаг

Сейчас нужен только N1.

N1 должен:

собрать mentions;
нормализовать строки;
auto-merge obvious duplicates;
создать отчёты;
подготовить почву для N2.

LLM не использовать.
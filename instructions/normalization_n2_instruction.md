# N2. Candidate generation для нормализации тегов
10.6 Product variants

Для drug_trade_name и supplement использовать:

product_name_norm;
trailing numeric variants;
dosage/form stripped aliases;
N1.1 possible_numeric_dosage_variant.

Примеры candidate pairs:

Берлиприл
Берлиприл 20
Берлиприл 20 мг
Вольтарен Эмульгель
Вольтарен эмульгель 2%

Но это должны быть candidate, не final merge.

10.7 Disease aliases

Для disease можно находить:

болезнь Альцгеймера
Альцгеймер
синдром Ли-Фраумени
Li-Fraumeni syndrome

Но осторожно с:

острый
хронический
врожденный
приобретенный
первичный
вторичный
тип 1
тип 2

Если есть subtype/type conflict, pair должен быть blocked.

10.8 Microorganism aliases

Candidate examples:

E. coli
Escherichia coli
кишечная палочка

Blocked examples:

Escherichia
Escherichia coli

Genus/species не объединять автоматически.

Если один label состоит из одного латинского слова, а другой из двух латинских слов с тем же первым словом, это parent_child_suspect или taxonomic_level_conflict.

11. Blocking rules

Создать blocking.py.

Blocking rules должны помечать pair как blocked, если есть небезопасное совпадение.

11.1 Different entity type
different_entity_type

Хотя pair generation и так должен работать внутри типа.

11.2 Disease subtype conflict

Blocked, если:

оба entity_type=disease;
один label содержит subtype/type marker, другой нет;
или оба содержат subtype/type marker, но subtype_signature различается.

Причина:

disease_subtype_conflict
11.3 Parent-child suspect

Blocked или marked high-risk, если:

один normalized label полностью содержит другой;
difference состоит из specificity modifier;
example:
диабет vs сахарный диабет;
гастрит vs хронический гастрит;
антибиотики vs макролиды;
сердце vs порок сердца.

Для N2 можно не полностью блокировать все contains cases, но обязательно выставлять:

parent_child_suspect

и снижать score / переводить в blocked для некоторых типов.

11.4 Drug trade name vs substance

Если внутри drug_trade_name label явно похож на действующее вещество, а другой — торговое название, N2 не должен решать это сам. Лучше candidate group помечать:

possible_brand_substance_conflict

Но поскольку тип один и тот же, не всегда можно определить. Оставить как risk reason.

11.5 Microorganism taxonomic conflict

Blocked, если:

single latin genus
species with same genus

Пример:

Escherichia
Escherichia coli

Причина:

taxonomic_level_conflict
11.6 Short abbreviation conflict

Если оба labels короткие, например <= 4 символов, и нет strong evidence:

АР
AR
ARX

Не создавать strong candidate только по похожести. Требовать abbreviation expansion / shared latin / same document cooccurrence.

Причина:

short_alias_ambiguous
12. Pair scoring

Реализовать детерминированный score от 0 до 1.

Примерная логика:

Сильные сигналы
shared_latin_candidate: +0.35
abbreviation_match: +0.35
parenthetical_alias_match: +0.30
product_variant_match: +0.30
high_token_similarity: +0.25
high_sequence_similarity: +0.20
same_document_cooccurrence: +0.05 to +0.15
Штрафы
blocking flag: pair_status=blocked
parent_child_suspect: -0.30
both context_only: -0.15
quote issue: -0.10
low confidence: -0.15
short alias ambiguous: -0.25
disease modifier mismatch: -0.30

Score должен быть объяснимым. В candidate_reason и blocking_reasons записывать причины.

Минимальный порог:

min_score = 0.72

Но пары с сильным правилом, например abbreviation/parenthetical/product variant, можно включать даже если string similarity низкая.

13. Candidate pair statuses

pair_status:

candidate
high_priority_candidate
blocked
rejected_low_score
high_priority_candidate

Если:

score >= high_priority_score

или есть сильные правила:

abbreviation_match
parenthetical_alias_match
shared_latin_candidate
product_variant_match

и нет blocking reasons.

candidate

Если score >= min_score и нет blocking reasons.

blocked

Если есть hard blocking reason.

rejected_low_score

Если features посчитаны, но score ниже порога.

14. Candidate groups

После candidate pairs создать candidate groups.

Важно: не делать опасный transitive merge.

Нельзя просто брать connected components без ограничений.

Пример опасности:

A похож на B
B похож на C
A не равен C

Поэтому group builder должен:

Собирать группы из candidate pairs.
Проверять pairwise compatibility внутри группы.
Если внутри группы есть конфликтующие pairs, разбивать группу.
Ограничивать размер группы.
Добавлять group_risk_flags.

Формат candidate_groups.jsonl:

{
  "candidate_group_id": "cg_000001",
  "entity_type": "diagnostic_method",

  "group_labels": [
    "Иммуноферментный анализ",
    "ИФА",
    "ELISA"
  ],

  "node_ids": [
    "n_000001",
    "n_000145",
    "n_000987"
  ],

  "pair_ids": [
    "p_000000001",
    "p_000000002"
  ],

  "group_score": 0.94,
  "group_priority": "high",

  "candidate_reasons": [
    "abbreviation_match",
    "shared_latin_candidate"
  ],

  "group_risk_flags": [
    "contains_short_alias"
  ],

  "requires_llm_validation": true,
  "recommended_for_n3": true,

  "mentions_count": 52,
  "documents_count": 31,
  "article_candidate_count": 40,
  "context_only_count": 12,

  "sample_documents": [
    {
      "doc_id": "...",
      "document_name": "..."
    }
  ]
}
15. Group priority

group_priority:

high
medium
low
blocked_review
high
high score;
article candidates involved;
many mentions/docs;
strong candidate reason;
no hard blocking.
medium
plausible but less frequent;
score around threshold;
some risk flags.
low
mostly context_only;
low frequency;
weak lexical similarity.
blocked_review
useful to inspect, but hard blocking exists;
should not go to automatic LLM merge unless explicitly requested.
16. Ограничение объёма

N2 может сгенерировать слишком много pairs, особенно для disease.

Нужно ограничивать candidate generation:

Для каждого entity_type
не сравнивать все со всеми, если узлов много;
сначала индексировать по blocking keys:
first token;
normalized prefix;
latin candidate;
abbreviation candidate;
product key;
parenthetical alias;
token signatures.
Maximum candidates

Флаг:

--max-pairs-per-type 50000

Если превышено, оставить самые сильные пары по preliminary score и записать warning.

17. Entity-type-specific priorities
disease

Приоритет:

aliases with same latin candidate;
eponym variants;
disease name with/without “болезнь”;
syndrome Russian/Latin variants.

Строго защищать:

тип, типа, type;
острый/хронический;
первичный/вторичный;
врожденный/приобретенный.
diagnostic_method

Приоритет:

abbreviations;
Russian/Latin method aliases;
method name variants;
“метод X” vs “X”.
drug_trade_name / supplement

Приоритет:

product variants;
dosage/form variants;
punctuation/case variants;
Latin/Russian spelling variants.

Не объединять с substances.

drug_class

Приоритет:

spelling variants;
Greek beta/literal beta;
abbreviation only with strong evidence.

Не объединять broad class with subclass.

microorganism

Приоритет:

Latin abbreviation vs full species;
Russian common name vs Latin species.

Не объединять genus/species.

biological_substance

Приоритет:

Latin/Russian aliases;
gene/protein abbreviations;
cytokine/interleukin abbreviations.

Short aliases требуют N3 validation.

procedure / instruction

Приоритет:

“порядок проведения X” vs “X”;
“инструкция по X” vs “X”.

Но parent/procedure distinction нужно помечать.

18. Singleton fast path

N2 должен не принимать решение, но должен перенести и дополнить singleton report.

Использовать вход:

data/normalization/singleton_entity_candidates.jsonl

Создать:

data/normalization/n2/singleton_fast_path_candidates.csv

Разделить:

recommended_fast_path=true
recommended_fast_path=false

Для recommended true добавить поля:

fast_path_reason
expected_downstream_action

Например:

expected_downstream_action = single_document_article_generation_without_multi_doc_extraction

Важно: singleton fast path — это не финальная нормализация. Это оптимизация будущего evidence/article этапа.

19. CSV для ручной проверки

candidate_groups.csv должен быть удобен для человека.

Поля:

candidate_group_id
entity_type
group_priority
group_score
group_labels
node_ids
mentions_count
documents_count
article_candidate_count
context_only_count
candidate_reasons
group_risk_flags
requires_llm_validation
recommended_for_n3
sample_documents

high_priority_candidate_groups.csv:

То же, но только:

group_priority=high
20. Reports

Создать candidate_generation_report.json.

Минимальная структура:

{
  "stage": "normalization_n2_candidate_generation",
  "created_at": "...",
  "source_stage": "normalization_n1",
  "source_stage_version": "n1.1",

  "counts": {
    "nodes_total": 0,
    "candidate_pairs_total": 0,
    "high_priority_pairs": 0,
    "blocked_pairs": 0,
    "rejected_low_score_pairs": 0,
    "candidate_groups_total": 0,
    "high_priority_groups": 0,
    "medium_priority_groups": 0,
    "low_priority_groups": 0,
    "blocked_review_groups": 0,
    "singleton_fast_path_candidates": 0
  },

  "counts_by_entity_type": {},
  "candidate_reason_counts": {},
  "blocking_reason_counts": {},
  "group_risk_flag_counts": {},

  "warnings": []
}

Создать candidate_generation_manifest.json:

{
  "stage": "normalization_n2_candidate_generation",
  "created_at": "...",
  "source_normalization_manifest": "data/normalization/normalization_n1_manifest.json",
  "source_stage_version": "n1.1",

  "inputs": {
    "auto_clusters": "data/normalization/auto_clusters.jsonl",
    "tag_mentions_normalized": "data/normalization/tag_mentions_normalized.jsonl",
    "singleton_entity_candidates": "data/normalization/singleton_entity_candidates.jsonl"
  },

  "outputs": {
    "candidate_nodes": "data/normalization/n2/candidate_nodes.jsonl",
    "candidate_pairs": "data/normalization/n2/candidate_pairs.jsonl",
    "candidate_groups": "data/normalization/n2/candidate_groups.jsonl",
    "candidate_groups_csv": "data/normalization/n2/candidate_groups.csv",
    "candidate_generation_report": "data/normalization/n2/candidate_generation_report.json"
  }
}
21. Валидация N2

Перед записью outputs проверить:

все input files существуют;
N1 manifest stage_version=n1.1;
duplicate diagnostics пустой;
все node_ids уникальны;
все pair_ids уникальны;
все group_ids уникальны;
pair не содержит разные entity_type;
group не содержит разные entity_type;
blocked pairs не попадают в обычные candidate groups;
candidate groups имеют хотя бы 2 nodes;
candidate_groups.csv не содержит дублирующихся group ids;
no final canonical tags are produced.

Если sanity check не проходит, N2 должен завершиться ошибкой.

22. Unit tests

Добавить тесты:

tests/test_normalization_n2_features.py
tests/test_normalization_n2_blocking.py
tests/test_normalization_n2_pair_generation.py
tests/test_normalization_n2_grouping.py
tests/test_normalization_n2_runner.py
Feature tests
exact normalized labels score high;
typo/edit-distance labels score moderate;
abbreviation detection works:
иммуноферментный анализ ↔ ИФА;
полимеразная цепная реакция ↔ ПЦР;
магнитно-резонансная томография ↔ МРТ;
parenthetical alias works:
Вирус папилломы человека (ВПЧ) ↔ ВПЧ;
shared latin candidate works;
product variant match works.
Blocking tests
disease type 1 vs type 2 blocked;
disease base vs type blocked;
chronic disease vs base disease parent-child suspect;
genus vs species microorganism blocked;
different entity types not paired;
short alias ambiguous without expansion rejected/blocked.
Pair generation tests
pairs only inside entity_type;
high priority pairs created for abbreviations;
low score pairs rejected;
blocked pairs written separately.
Grouping tests
A-B and B-C with A-C conflict does not create unsafe transitive group;
high priority groups are generated;
groups contain one entity_type;
blocked pairs do not enter normal groups.
Runner tests
creates all required outputs;
refuses to run if N1 manifest not n1.1;
refuses to run if duplicate diagnostics non-empty;
report counts consistent.

Запуск:

.venv/bin/python -m unittest discover -s tests

Compile check:

.venv/bin/python -m py_compile \
  kb_rebuild/normalization/n2/features.py \
  kb_rebuild/normalization/n2/blocking.py \
  kb_rebuild/normalization/n2/pair_generation.py \
  kb_rebuild/normalization/n2/grouping.py \
  kb_rebuild/normalization/n2/report.py \
  kb_rebuild/normalization/n2/runner.py \
  kb_rebuild/cli.py
23. Команда запуска N2

После реализации:

.venv/bin/python -m kb_rebuild normalize-n2 \
  --data data \
  --normalization-dir data/normalization \
  --out data/normalization/n2 \
  --min-score 0.72 \
  --high-priority-score 0.88 \
  --max-pairs-per-type 50000
24. Acceptance criteria

N2 считается выполненным, если:

добавлена CLI-команда normalize-n2;
создан пакет kb_rebuild/normalization/n2;
N2 читает только N1.1 outputs;
N2 не меняет data/tagging/*;
N2 не меняет N1.1 outputs;
создан candidate_nodes.jsonl;
создан candidate_pairs.jsonl;
создан candidate_groups.jsonl;
создан candidate_groups.csv;
создан rejected_pairs.jsonl;
создан blocked_pairs.jsonl;
создан candidate_generation_report.json;
создан candidate_generation_manifest.json;
пары строятся только внутри entity_type;
disease subtype conflicts блокируются;
microorganism genus/species conflicts блокируются;
product variants попадают в candidates;
abbreviations попадают в candidates;
singleton fast path перенесён в отдельный report;
tests проходят;
feedback создан.
25. Feedback исполнителя

Создать:

docs/normalization_n2_feedback.md

В feedback указать:

что сделано;
какие файлы изменены;
какие команды запускались;
сколько tests passed;
сколько nodes;
сколько candidate pairs;
сколько blocked pairs;
сколько rejected pairs;
сколько candidate groups;
сколько high priority groups;
counts by entity_type;
top candidate reasons;
top blocking reasons;
примеры хороших candidate groups:
abbreviation;
latin alias;
product variant;
disease alias;
microorganism alias;
примеры blocked groups:
disease type conflict;
genus/species conflict;
parent-child suspect;
сколько singleton fast path candidates;
что передать в N3;
риски.
26. Важное напоминание

N2 не должен решать, какие tags окончательно объединять.

N2 должен подготовить качественный, объяснимый, ограниченный список candidate groups для N3.

Если есть сомнение, pair/group лучше пометить как blocked_review или requires_llm_validation, чем сделать опасный merge.
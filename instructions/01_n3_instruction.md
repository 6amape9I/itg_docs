# N3. LLM validation candidate groups для финальной нормализации тегов

## 0. Контекст

Этапы N1/N1.1/N2/N2.1/N2.2 уже выполнены.

N2.2 подготовил строгий список candidate groups для LLM-валидации. Главный вход N3:

```text
data/normalization/n2/n3_candidate_groups.jsonl

По актуальному N2.2 report:

n3_candidate_groups = 363
candidate_groups_total = 6878
subtype_conflict_groups = 3969
location_scope_conflict_groups = 1097
quality_score_rejected_groups = 1201
known_bad_n3_matches = 0
quality_gate.passed = true

N2.2 уже сильно сократил пространство кандидатов, но часть N3-candidate groups всё ещё может быть ложноположительной. Поэтому N3 должен быть не “автоматической склейкой”, а строгим LLM-валидатором.

Главный принцип N3:

accept only when clearly same entity;
reject when distinct;
split when group contains both true aliases and unrelated items;
send to web/human review only when uncertain.
1. Цель N3

Цель N3 — валидировать candidate groups из N2.2 и подготовить решения для финального canonical layer.

N3 должен для каждой группы принять одно из решений:

accept_same_entity
reject_distinct_entities
split_into_subclusters
needs_web_or_human_review

N3 НЕ должен сразу создавать финальные tags_canonical.csv и tag_aliases.csv. Это будет N4.

N3 должен создать валидированные решения:

data/normalization/n3/llm_group_decisions.jsonl
data/normalization/n3/accepted_clusters.jsonl
data/normalization/n3/rejected_groups.jsonl
data/normalization/n3/split_groups.jsonl
data/normalization/n3/web_or_human_review_groups.jsonl
data/normalization/n3/n3_report.json
data/normalization/n3/n3_manifest.json
2. Не цели N3

На N3 запрещено:

создавать финальный canonical layer;
создавать tags_canonical.csv;
создавать tag_aliases.csv;
создавать document_tag_links_normalized.jsonl;
менять N1/N2 артефакты;
менять data/tagging/*;
менять data/parsed/*;
добавлять внешние медицинские факты в базу;
писать статьи;
извлекать evidence по документам;
запускать N4.

N3 только валидирует, какие candidate groups действительно являются одной сущностью, какие нужно разбить, какие отклонить.

3. Главный принцип безопасности

LLM должна быть строгим судьёй, а не помощником, который старается объединить всё похожее.

Если внутри группы есть хотя бы одна сущность, которая явно отличается от остальных, нельзя возвращать accept_same_entity.

Пример:

Мерцательная аритмия
Фибрилляция предсердий
Мегалобластная анемия

Правильное решение:

split_into_subclusters

с subclusters:

[Мерцательная аритмия, Фибрилляция предсердий]
[Мегалобластная анемия]

Пример:

Вирус гепатита A
Вирус гепатита B
Вирус гепатита C

Правильное решение:

reject_distinct_entities

или split на одиночные subclusters, но не accept_same_entity.

4. Входные артефакты

Основной вход:

data/normalization/n2/n3_candidate_groups.jsonl

Дополнительные входы:

data/normalization/n2/candidate_generation_report.json
data/normalization/n2/candidate_generation_manifest.json
data/normalization/n2/group_quality_diagnostics.json
data/normalization/n2/candidate_nodes.jsonl
data/normalization/n2/candidate_pairs.jsonl
data/normalization/auto_clusters.jsonl
data/normalization/tag_mentions_normalized.jsonl

N3 runner должен проверять:

candidate_generation_manifest.stage_version == "n2.2"
candidate_generation_report.stage_version == "n2.2"
quality_gate.passed == true
n3_candidate_groups_jsonl exists

Если проверка не проходит, N3 должен завершиться ошибкой.

5. Выходные артефакты

Создать директорию:

data/normalization/n3/

Обязательные outputs:

data/normalization/n3/llm_group_decisions.jsonl
data/normalization/n3/accepted_clusters.jsonl
data/normalization/n3/rejected_groups.jsonl
data/normalization/n3/split_groups.jsonl
data/normalization/n3/web_or_human_review_groups.jsonl
data/normalization/n3/n3_report.json
data/normalization/n3/n3_manifest.json

Дополнительные outputs:

data/normalization/n3/llm_group_decisions.csv
data/normalization/n3/accepted_clusters.csv
data/normalization/n3/split_groups.csv
data/normalization/n3/rejected_groups.csv
data/normalization/n3/review_groups.csv
data/normalization/n3/validation_failures.jsonl
data/normalization/n3/known_bad_decision_checks.csv
data/normalization/n3/n3_quality_diagnostics.json
6. Рекомендуемая структура кода

Создать пакет:

kb_rebuild/normalization/n3/

Файлы:

kb_rebuild/normalization/n3/__init__.py
kb_rebuild/normalization/n3/models.py
kb_rebuild/normalization/n3/prompt.py
kb_rebuild/normalization/n3/schema.py
kb_rebuild/normalization/n3/runner.py
kb_rebuild/normalization/n3/report.py
kb_rebuild/normalization/n3/quality.py

Назначение:

models.py   — dataclasses для group input, decision, subcluster
prompt.py   — prompt builder для Gemini
schema.py   — Gemini response schema + local validation schema
runner.py   — orchestration, cache, Gemini calls, retries
report.py   — CSV/JSON reports
quality.py  — sanity checks after LLM decisions

Добавить CLI-команду:

python -m kb_rebuild normalize-n3 --data data

Флаги:

--normalization-dir data/normalization
--n2-dir data/normalization/n2
--out data/normalization/n3
--model gemini-3-flash-preview
--provider gemini_direct
--batch-size 1
--max-inflight 8
--max-retries 3
--max-cost-usd 20
--structured-output-mode gemini_schema
--enable-web-review
--web-review-model gemini-2.5-flash
--web-review-limit 50
--no-overwrite

По умолчанию:

enable_web_review = false
batch_size = 1
model = gemini-3-flash-preview
7. Почему batch-size по умолчанию 1

На N3 каждая group требует смыслового решения и часто split. Ошибка на одном group не должна портить соседние groups.

Поэтому default:

one candidate group = one LLM request

Допускается batch mode, но только если он сохраняет независимые решения по каждой candidate_group_id и строго валидирует все ответы.

8. Модельная стратегия
8.1 Основной проход

Основная модель:

gemini-3-flash-preview

Режим:

structured output
no web search
temperature = 0
8.2 Web/human review pass

Web search не использовать по умолчанию.

Опционально, если включён флаг:

--enable-web-review

то только группы с решением:

needs_web_or_human_review

могут быть отправлены на второй проход.

Для web-review использовать модель, которая поддерживает Google Search grounding. Начальный вариант:

gemini-2.5-flash

или другая доступная direct Gemini модель, подтверждённая discovery.

Важно: web-review не должен автоматически принимать merge. Он должен вернуть либо:

accept_same_entity
reject_distinct_entities
split_into_subclusters
human_review_required

и сохранить grounding metadata, если API возвращает его.

9. Input format для LLM

Для каждой candidate group в prompt передавать:

candidate_group_id
entity_type
group_labels
candidate_reasons
clean_candidate_reasons
weak_candidate_reasons
group_risk_flags
group_score
mentions_count
documents_count
article_candidate_count
context_only_count
sample_documents
node_ids

Если есть доступ к candidate_nodes.jsonl, дополнительно передать по каждому node:

node_id
label
normalized_label
aliases
normalized_aliases
latin_label
mentions_count
documents_count
risk_flags
routing_flags

Не передавать огромные исходные документы.

N3 валидирует labels/entities, а не извлекает evidence из текста.

10. Prompt requirements

Создать файл:

kb_rebuild/normalization/n3/prompts/validate_group_v1.md

Prompt должен быть на русском.

Смысл prompt:

Ты валидируешь, являются ли несколько тегов одной и той же медицинской сущностью.
Твоя задача — быть строгим.
Не объединяй разные подтипы, разные локализации, разные процедуры, разные препараты, разные вирусы/серотипы/группы.
Если внутри группы есть частично правильные aliases и частично мусор — верни split_into_subclusters.
Если все элементы разные — reject_distinct_entities.
Если все элементы действительно обозначают одну сущность — accept_same_entity.
Если не уверен — needs_web_or_human_review.

Обязательные правила в prompt:

10.1 Общие правила

Не объединять:

родительскую и дочернюю сущность;
базовый метод и метод с локализацией;
болезни с разной локализацией;
болезни с разными типами/подтипами;
разные группы/серотипы микроорганизмов;
разные торговые продукты;
разные БАДы одной линейки/бренда;
процедуры с разным объектом применения;
лекарство и класс лекарств;
торговое название и действующее вещество.
10.2 Разрешать объединение

Разрешать:

русское и латинское название одной сущности;
синонимы;
эпонимические варианты;
аббревиатура и полное название, если это именно одно и то же;
орфографические варианты;
варианты регистра;
варианты с/без скобочного alias;
торговое название с дозировкой и без дозировки, если это тот же продукт;
БАД с дозировкой и без дозировки, если это тот же продукт.
10.3 Split examples

Prompt должен содержать примеры:

[Мерцательная аритмия, Фибрилляция предсердий, Мегалобластная анемия]
→ split:
  [Мерцательная аритмия, Фибрилляция предсердий]
  [Мегалобластная анемия]
[Гемофилия A, Гемофилия А, Гемолитическая анемия]
→ split:
  [Гемофилия A, Гемофилия А]
  [Гемолитическая анемия]
[Вирус гепатита A, Вирус гепатита B, Вирус гепатита C]
→ reject_distinct_entities
[Жевательный кальций RBC, Железо RBC, Люцерна RBC]
→ reject_distinct_entities
[Аддисонова болезнь, Болезнь Аддисона]
→ accept_same_entity
11. Structured output schema

Ответ LLM должен быть строгим JSON.

Минимальная схема:

{
  "candidate_group_id": "cg_000001",
  "decision": "accept_same_entity | reject_distinct_entities | split_into_subclusters | needs_web_or_human_review",
  "confidence": 0.0,
  "canonical_tag_ru": "",
  "canonical_tag_latin": "",
  "entity_type": "disease",
  "subclusters": [
    {
      "subcluster_id": "sc_001",
      "decision": "same_entity | singleton | reject",
      "canonical_tag_ru": "",
      "canonical_tag_latin": "",
      "labels": [],
      "node_ids": [],
      "confidence": 0.0,
      "reason": ""
    }
  ],
  "rejected_labels": [
    {
      "label": "",
      "node_id": "",
      "reason": ""
    }
  ],
  "reason": "",
  "risk_flags": [],
  "requires_human_review": false
}
11.1 Decision meanings
accept_same_entity

Все labels/nodes в группе являются одной сущностью.

Требования:

subclusters содержит ровно один subcluster;
в subcluster входят все node_ids;
canonical_tag_ru заполнен;
confidence >= 0.8 желательно, но не обязательно для schema.
reject_distinct_entities

Группа не содержит полезного merge.

Использовать, если все labels обозначают разные сущности или общее сходство слишком слабое.

split_into_subclusters

Группа содержит хотя бы один полезный alias-subcluster и хотя бы один лишний/отдельный элемент.

Использовать, если внутри группы есть частичные правильные объединения.

needs_web_or_human_review

Использовать, если без внешнего знания или ручной проверки нельзя уверенно решить.

12. Local validation после LLM

После каждого ответа код должен проверить:

candidate_group_id совпадает;
decision в enum;
confidence в [0, 1];
entity_type совпадает с input;
все node_ids из ответа существуют в input group;
нет неизвестных labels;
для accept_same_entity все input node_ids покрыты ровно одним subcluster;
для split_into_subclusters каждый node_id либо в subcluster, либо rejected;
subclusters не пересекаются по node_id;
canonical_tag_ru не пустой для accepted/same_entity subclusters;
reject_distinct_entities не создаёт accepted cluster;
needs_web_or_human_review не создаёт final accepted cluster.

Если ответ невалиден:

retry с repair prompt;
максимум max_retries;
если всё равно невалидно, записать в validation_failures.jsonl;
decision для группы считать needs_human_review_due_to_invalid_llm_response.
13. N3 output: llm_group_decisions.jsonl

Одна строка = одно решение по group.

Формат:

{
  "candidate_group_id": "cg_000001",
  "entity_type": "disease",
  "input_group_labels": [],
  "input_node_ids": [],

  "decision": "split_into_subclusters",
  "confidence": 0.92,

  "canonical_tag_ru": "",
  "canonical_tag_latin": "",

  "subclusters": [],
  "rejected_labels": [],

  "reason": "",
  "risk_flags": [],
  "requires_human_review": false,

  "model": "gemini-3-flash-preview",
  "provider": "gemini_direct",
  "prompt_version": "n3_validate_group_v1",
  "schema_version": "n3_group_decision_v1",

  "usage": {},
  "estimated_cost_usd": 0.0,
  "latency_ms": 0,
  "cache_key": "",
  "from_cache": false,
  "created_at": ""
}
14. Accepted clusters output

accepted_clusters.jsonl содержит только фактически принятые same-entity clusters.

Если group decision = accept_same_entity, создать один accepted cluster.

Если group decision = split_into_subclusters, создать accepted clusters только для subclusters с:

decision = same_entity
len(node_ids) >= 2
confidence >= threshold

Формат:

{
  "n3_cluster_id": "n3c_000001",
  "source_candidate_group_id": "cg_000001",
  "entity_type": "disease",
  "canonical_tag_ru": "Болезнь Аддисона",
  "canonical_tag_latin": "Addison disease",
  "labels": [
    "Аддисонова болезнь",
    "Болезнь Аддисона"
  ],
  "node_ids": [],
  "confidence": 0.96,
  "decision_source": "llm_n3",
  "reason": ""
}
15. Rejected groups output

rejected_groups.jsonl содержит:

decision = reject_distinct_entities

и группы, где LLM решила, что useful merge нет.

16. Split groups output

split_groups.jsonl содержит исходную group и все subclusters.

Важно: split groups — самые ценные для N3, потому что они спасают частично правильные кандидаты.

17. Review groups output

web_or_human_review_groups.jsonl содержит:

needs_web_or_human_review
invalid_llm_response
low_confidence_accept
schema_validation_failed

Эти группы можно будет отправить на web-review или ручную проверку.

18. Web review optional pass

Опционально реализовать, но не включать по умолчанию.

Флаг:

--enable-web-review

Если включён:

Взять только группы из web_or_human_review_groups.jsonl.

Ограничить число через:

--web-review-limit 50

Использовать модель:

--web-review-model gemini-2.5-flash
Включить Google Search grounding.

Сохранить:

data/normalization/n3/web_review_decisions.jsonl
data/normalization/n3/web_review_sources.jsonl

Web-review должен быть отдельным secondary decision layer.

Если web-review принят, в decision record указать:

{
  "decision_source": "llm_n3_web_grounded"
}
19. Cache

Использовать LLM cache.

Cache key должен учитывать:

stage = normalization_n3
provider
model
prompt_version
schema_version
candidate_group_id
input_group_hash
web_review_enabled

Нельзя использовать N2 cache или tagging cache.

20. Report

Создать n3_report.json.

Минимальная структура:

{
  "stage": "normalization_n3_llm_validation",
  "stage_version": "n3.0",
  "created_at": "...",

  "input": {
    "n3_candidate_groups": "data/normalization/n2/n3_candidate_groups.jsonl",
    "n2_manifest": "data/normalization/n2/candidate_generation_manifest.json"
  },

  "counts": {
    "groups_total": 0,
    "groups_processed": 0,
    "accepted_same_entity": 0,
    "rejected_distinct_entities": 0,
    "split_into_subclusters": 0,
    "needs_web_or_human_review": 0,
    "invalid_llm_responses": 0,
    "accepted_clusters_total": 0,
    "accepted_clusters_from_split": 0,
    "review_groups_total": 0
  },

  "by_entity_type": {},

  "cost": {
    "estimated_cost_usd": 0.0,
    "requests": 0,
    "cache_hits": 0,
    "cache_misses": 0
  },

  "quality": {
    "accepted_clusters_with_single_node": 0,
    "accepted_clusters_with_empty_canonical": 0,
    "split_groups_with_uncovered_nodes": 0,
    "known_bad_accepted_clusters": 0,
    "passed": true
  },

  "warnings": []
}
21. Manifest

Создать n3_manifest.json:

{
  "stage": "normalization_n3_llm_validation",
  "stage_version": "n3.0",
  "created_at": "...",

  "source_n2_manifest": "data/normalization/n2/candidate_generation_manifest.json",
  "source_n2_stage_version": "n2.2",

  "inputs": {
    "n3_candidate_groups": "data/normalization/n2/n3_candidate_groups.jsonl"
  },

  "outputs": {
    "llm_group_decisions": "data/normalization/n3/llm_group_decisions.jsonl",
    "accepted_clusters": "data/normalization/n3/accepted_clusters.jsonl",
    "rejected_groups": "data/normalization/n3/rejected_groups.jsonl",
    "split_groups": "data/normalization/n3/split_groups.jsonl",
    "web_or_human_review_groups": "data/normalization/n3/web_or_human_review_groups.jsonl",
    "n3_report": "data/normalization/n3/n3_report.json"
  },

  "model": "gemini-3-flash-preview",
  "provider": "gemini_direct",
  "prompt_version": "n3_validate_group_v1",
  "schema_version": "n3_group_decision_v1"
}
22. Quality checks после N3

Создать n3_quality_diagnostics.json.

Проверки:

accepted cluster не должен содержать known bad combinations;
accepted cluster не должен содержать labels с разными вирусами A/B/C/D/E;
accepted cluster не должен содержать разные streptococcus groups A/B;
accepted cluster не должен содержать разные БАДы одной линейки, например RBC;
accepted cluster не должен содержать разные локализации процедур;
accepted cluster не должен содержать разные локализации болезней;
split subclusters не должны пересекаться;
all node_ids covered or explicitly rejected;
canonical_tag_ru filled for accepted clusters.

Known bad examples:

Вирус гепатита A + Вирус гепатита B
Стрептококк группы A + Стрептококки группы B
Жевательный кальций RBC + Железо RBC
Аллергические реакции + Аллергический ринит + Лекарственная аллергия
Андрогенетическая алопеция у женщин + Апластическая анемия
Мегалобластная анемия + Мерцательная аритмия
Гемолитическая анемия + Гемофилия A
Стеноз гортани + Стеноз пищевода
Лазерная коагуляция сетчатки + Лазерная коагуляция шейки матки
Цистэктомия печени + Цистэктомия яичника

Если LLM всё равно принимает known bad cluster:

quality.passed = false

и записать в:

data/normalization/n3/known_bad_accepted_clusters.csv
23. Важные примеры expected decisions
23.1 Accept
Аддисонова болезнь
Болезнь Аддисона
→ accept_same_entity
Акне
Угревая сыпь
→ accept_same_entity
Ингибиторы АПФ
Ингибиторы ангиотензинпревращающего фермента
→ accept_same_entity
Bacillus anthracis
Сибиреязвенная палочка
→ accept_same_entity
HVP
HVP (Эйч Ви Пи)
→ accept_same_entity
23.2 Reject
Вирус гепатита A
Вирус гепатита B
Вирус гепатита C
→ reject_distinct_entities
Стеноз гортани
Стеноз пищевода
→ reject_distinct_entities
Лазерная коагуляция сетчатки
Лазерная коагуляция шейки матки
→ reject_distinct_entities
23.3 Split
Мерцательная аритмия
Фибрилляция предсердий
Мегалобластная анемия
→ split_into_subclusters:
   [Мерцательная аритмия, Фибрилляция предсердий]
   [Мегалобластная анемия]
Гемофилия A
Гемофилия А
Гемолитическая анемия
→ split_into_subclusters:
   [Гемофилия A, Гемофилия А]
   [Гемолитическая анемия]
24. Tests

Добавить tests:

tests/test_normalization_n3_schema.py
tests/test_normalization_n3_validation.py
tests/test_normalization_n3_runner.py
tests/test_normalization_n3_quality.py
tests/test_normalization_n3_prompt.py
24.1 Schema tests
valid accept response passes;
valid reject response passes;
valid split response passes;
unknown decision fails;
unknown node_id fails;
accept without canonical_tag_ru fails;
split with overlapping node_ids fails;
split with uncovered node_ids fails unless rejected.
24.2 Quality tests
known bad accepted cluster fails quality;
hepatitis A/B/C accepted cluster fails;
streptococcus A/B accepted cluster fails;
RBC supplement mixed accepted cluster fails;
split with correct subcluster passes;
reject passes.
24.3 Runner tests
refuses to run if N2 manifest not n2.2;
creates all required outputs;
handles invalid LLM response with retry/failure;
writes accepted clusters from accept;
writes accepted clusters from split;
writes review groups.
24.4 Prompt tests
prompt contains strict “do not merge distinct entities” rules;
prompt contains split examples;
prompt contains reject examples;
prompt says web search is not default;
prompt does not request chain-of-thought.

Запуск:

.venv/bin/python -m unittest discover -s tests

Compile check:

.venv/bin/python -m py_compile \
  kb_rebuild/normalization/n3/models.py \
  kb_rebuild/normalization/n3/prompt.py \
  kb_rebuild/normalization/n3/schema.py \
  kb_rebuild/normalization/n3/quality.py \
  kb_rebuild/normalization/n3/report.py \
  kb_rebuild/normalization/n3/runner.py \
  kb_rebuild/cli.py
25. Команда запуска N3

Основной запуск:

.venv/bin/python -m kb_rebuild normalize-n3 \
  --data data \
  --normalization-dir data/normalization \
  --n2-dir data/normalization/n2 \
  --out data/normalization/n3 \
  --provider gemini_direct \
  --model gemini-3-flash-preview \
  --structured-output-mode gemini_schema \
  --batch-size 1 \
  --max-inflight 8 \
  --max-retries 3 \
  --max-cost-usd 20

Опциональный web-review pass:

.venv/bin/python -m kb_rebuild normalize-n3-web-review \
  --data data \
  --normalization-dir data/normalization \
  --n3-dir data/normalization/n3 \
  --model gemini-2.5-flash \
  --limit 50 \
  --max-cost-usd 20

Если web-review команда не реализована в этом этапе, указать это в feedback как не сделано. Основной N3 без web-review обязателен.

26. Acceptance criteria

N3 считается выполненным, если:

добавлена CLI-команда normalize-n3;
создан пакет kb_rebuild/normalization/n3;
N3 читает data/normalization/n2/n3_candidate_groups.jsonl;
N3 проверяет N2 manifest stage_version=n2.2;
используется direct Gemini provider;
используется structured output schema;
создан llm_group_decisions.jsonl;
создан accepted_clusters.jsonl;
создан rejected_groups.jsonl;
создан split_groups.jsonl;
создан web_or_human_review_groups.jsonl;
создан n3_report.json;
создан n3_manifest.json;
local validation работает;
invalid LLM responses не ломают весь run;
known bad accepted clusters ловятся quality check;
tests проходят;
feedback создан.
27. Feedback после N3

Создать:

docs/normalization_n3_feedback.md

Feedback должен содержать:

1. Что сделано.
2. Какие файлы изменены.
3. Какие команды запускались.
4. Сколько tests passed.
5. Сколько groups обработано.
6. Сколько accept/reject/split/review.
7. Сколько accepted clusters создано.
8. Сколько accepted clusters пришло из split.
9. Сколько invalid LLM responses.
10. Стоимость и число запросов.
11. Примеры accept.
12. Примеры reject.
13. Примеры split.
14. Примеры needs review.
15. Quality diagnostics.
16. Known bad accepted clusters count.
17. Что не сделано.
18. Риски.
19. Что передать в N4.
28. Инструкция по поведению агента

Перед началом работы агент обязан создать план:

docs/normalization_n3_plan.md

В плане указать:

что понял;
какие файлы изменит;
какие outputs создаст;
какую schema реализует;
какие tests добавит;
какие риски видит;
чего делать не будет;
чеклист.

Агент обязан перечитать это ТЗ:

после плана;
после реализации schema;
после реализации runner;
после tests;
перед production run;
перед feedback.

В feedback добавить строку:

ТЗ перечитано на этапах: after_plan, after_schema, after_runner, after_tests, before_run, before_feedback

Если память агента очищена, сначала перечитать:

instructions/current_n3_instruction.md
docs/normalization_n2_2_feedback.md
data/normalization/n2/candidate_generation_report.json
data/normalization/n2/candidate_generation_manifest.json
data/normalization/n2/n3_candidate_groups.jsonl

и только потом продолжать.

29. Главное напоминание

N3 не должен стараться принять максимум групп.

N3 должен максимально безопасно отфильтровать true aliases.

Правильное поведение:

сомневаешься → split или review;
видишь разные сущности → reject;
видишь частично правильную группу → split;
видишь очевидные synonyms → accept.

Главный output для N4:

data/normalization/n3/accepted_clusters.jsonl
::contentReference[oaicite:4]{index=4}
# 03_normalization_engineer_agent_guide.md

# Инструкция для Codex-агента: Normalization Engineer

## 0. Твоя роль

Ты Normalization Engineer.

Твоя задача — построить первый слой нормализации тегов после завершённого LLM-тегирования.

Ты не занимаешься Gemini API.

Ты не занимаешься OpenRouter.

Ты не занимаешься извлечением тегов.

Ты не занимаешься evidence extraction.

Ты не занимаешься созданием статей.

Ты работаешь только с уже готовым tagging-output и создаёшь deterministic normalization слой.

## 1. Что уже сделано до тебя

В проекте уже есть этап tagging.

Актуальный production tagging-output находится в:

```text
data/tagging/document_tags_raw_active.jsonl

Также могут быть:

data/tagging/document_tagging_failures_active.jsonl
data/tagging/empty_documents_name_candidates.jsonl
data/tagging/tagging_active_manifest.json

Эти файлы являются input для твоего этапа.

Ты не должен их менять.

2. Какие документы нужно прочитать перед началом

Перед началом работы обязательно прочитай:

instructions/01_n1_deterministic_normalization_requirements.md
instructions/02_normalization_global_vision.md
instructions/03_normalization_engineer_agent_guide.md

Также посмотри текущую структуру проекта:

kb_rebuild/cli.py
kb_rebuild/io/jsonl.py
kb_rebuild/llm/tagging_batch.py
data/tagging/tagging_active_manifest.json

tagging_batch.py читать нужно не для изменения, а чтобы понять формат tagging-output и active/history подход.

3. Как поддерживать контекст

После каждого крупного шага перечитывай:

instructions/01_n1_deterministic_normalization_requirements.md

Минимально перечитать нужно после:

создания плана;
реализации flatten mentions;
реализации text normalization;
реализации auto-clustering;
перед написанием feedback.

Это нужно, чтобы не уйти в N2/N3 и не начать делать лишнюю semantic normalization.

4. Перед началом работы создай план

Перед изменением кода создай:

docs/normalization_n1_plan.md

В плане укажи:

что ты понял;
какие файлы планируешь создать;
какие файлы планируешь изменить;
какие артефакты создаст команда;
какие deterministic правила реализуешь;
какие риски видишь;
что точно не будешь делать;
чеклист выполнения.

План должен быть достаточно конкретным, чтобы архитектор мог понять, куда ты движешься.

5. Твои основные задачи
5.1 Создать пакет нормализации

Создай:

kb_rebuild/normalization/

Минимальные модули:

__init__.py
models.py
text.py
mentions.py
auto_cluster.py
report.py
n1_runner.py
5.2 Добавить CLI-команду

Добавь команду:

python -m kb_rebuild normalize-n1 --data data

Она должна читать tagging-output и писать артефакты в:

data/normalization/
5.3 Flatten mentions

Из каждого tagging record извлечь все entities.

Одна entity = одна mention.

Создать:

data/normalization/tag_mentions_raw.jsonl
5.4 Normalize mentions

Для каждой mention создать normalized forms:

surface_norm
candidate_ru_norm
candidate_latin_norm
primary_norm
display_candidate_ru
display_candidate_latin

Создать:

data/normalization/tag_mentions_normalized.jsonl
5.5 Deterministic auto-clusters

Создать безопасные кластеры очевидных дублей.

Создать:

data/normalization/auto_clusters.jsonl
data/normalization/auto_clusters.csv
5.6 Reports

Создать:

data/normalization/normalization_n1_report.json
data/normalization/normalization_n1_manifest.json
data/normalization/type_role_stats.csv
data/normalization/tags_raw.csv
data/normalization/suspicious_mentions.jsonl
data/normalization/failed_documents_snapshot.jsonl
data/normalization/quote_issue_mentions.jsonl
6. Чего нельзя делать

Запрещено:

вызывать LLM;
использовать Gemini API;
использовать OpenRouter;
менять data/tagging/*;
менять parsed artifacts;
запускать полный pipeline downstream;
делать semantic merge;
объединять разные entity_type;
создавать финальные tags_canonical.csv;
создавать финальные document_tag_links_normalized.jsonl;
исправлять failed documents;
генерировать теги из document_name.
7. Важные архитектурные правила
7.1 Raw tagging-output immutable

Старые файлы tagging — это audit trail.

Ты только читаешь их.

Все новые файлы — в data/normalization/.

7.2 N1 не финальная нормализация

N1 только подготавливает данные.

Не надо пытаться решить всю задачу.

Если сомневаешься, помечай review_required или suspicious_flags, а не делай опасное объединение.

7.3 Entity type boundary

Нельзя auto-merge разные типы.

Пример:

drug_trade_name ≠ drug_class
disease ≠ symptom
diagnostic_method ≠ procedure
microorganism ≠ disease
7.4 Parent-child осторожность

Не объединяй:

гастрит
хронический гастрит
острый гастрит

Не объединяй:

антибиотики
макролиды
тетрациклины

Не объединяй:

сердце
порок сердца
врожденный порок сердца
7.5 Context-only не мусор

context_only не надо удалять.

Но его нужно учитывать отдельно, чтобы downstream не создавал лишние статьи.

8. На что смотреть в первую очередь

Сначала проверь формат входного файла:

data/tagging/document_tags_raw_active.jsonl

Посмотри:

есть ли doc_id;
есть ли document_name;
есть ли entities;
какие поля есть у entities;
какие встречаются entity_type;
какие встречаются tag_role;
как выглядят quote validation поля.

Затем проверь manifest:

data/tagging/tagging_active_manifest.json

Он поможет записать source metadata в normalization manifest.

9. Реализация text normalization

В text.py реализуй чистые функции без side effects.

Примеры функций:

normalize_basic_text(value: str) -> str
normalize_latin_text(value: str) -> str
normalize_greek_letters(value: str) -> str
normalize_drug_trade_name(value: str) -> str
normalize_supplement_name(value: str) -> str
has_specificity_modifier(value: str) -> bool
detect_suspicious_flags(...) -> list[str]

Тестировать их отдельно.

10. Реализация mentions flattening

В mentions.py сделай функции:

load_tagging_records(path: Path) -> Iterator[dict]
flatten_mentions(records: Iterable[dict]) -> list[TagMention]

Обработка ошибок:

malformed JSONL line → invalid records file;
missing doc_id → invalid record;
missing entities → warning;
entity не dict → invalid mention;
пустой surface/candidate → suspicious, но не падать.
11. Реализация auto-clustering

В auto_cluster.py сделай:

build_auto_cluster_key(mention: NormalizedMention) -> str
build_auto_clusters(mentions: list[NormalizedMention]) -> list[AutoCluster]

Кластеры строить только по безопасному ключу.

Не использовать fuzzy matching на N1 для автоматического merge, кроме совсем безопасных нормализованных совпадений.

Edit distance — это N2, не N1.

12. Tests

Добавь тесты:

tests/test_normalization_text.py
tests/test_normalization_mentions.py
tests/test_normalization_auto_cluster.py
tests/test_normalization_n1_runner.py

Тесты должны запускаться стандартно:

.venv/bin/python -m unittest discover -s tests

Не использовать внешние API.

Не использовать реальные большие данные в unit tests.

Сделать маленькие fixtures внутри tests.

13. Как проверять вручную

После реализации запусти:

.venv/bin/python -m kb_rebuild normalize-n1 --data data

Потом проверь:

ls -lah data/normalization
cat data/normalization/normalization_n1_report.json
head -n 3 data/normalization/tag_mentions_raw.jsonl
head -n 3 data/normalization/tag_mentions_normalized.jsonl
head -n 3 data/normalization/auto_clusters.jsonl

Проверить, что tagging files не изменились:

git status

Если data/ игнорируется git, хотя бы не перезаписывай tagging-файлы кодом.

14. Feedback после завершения

В конце создай:

docs/normalization_n1_feedback.md

В feedback обязательно укажи:

Что сделано

Кратко описать реализованный функционал.

Какие файлы изменены

Список файлов кода и docs.

Какие артефакты созданы

Список файлов в data/normalization/.

Как запустить

Команда запуска N1.

Как проверить

Команды проверки.

Результаты

Обязательно указать:

mentions_total
unique_raw_values
unique_normalized_values
auto_clusters_total
auto_clusters_review_required
suspicious_mentions
quote_issue_mentions
failed_documents_count
Топы

Указать:

top entity types;
top tag roles;
top raw tags;
top normalized tags.
Что не сделано

Например:

LLM merge не реализован
candidate pairs не реализованы
final canonical tags не созданы
document_tag_links_normalized не созданы
Риски

Например:

drug form cleanup может быть слишком агрессивным
abbreviations требуют N2/N3
parent-child terms требуют LLM validation
Вопросы архитектору

Задать вопросы, если есть.

15. Критерий хорошей работы

Хороший N1 — это не тот, который схлопнул максимальное количество тегов.

Хороший N1 — это тот, который:

не потерял raw data;
не сделал опасных merge;
подготовил чистую таблицу mentions;
дал reproducible normalized forms;
безопасно объединил очевидные дубли;
вынес спорные случаи в suspicious/review;
дал понятный report;
подготовил основу для N2/N3.
16. Финальное напоминание

Не пытайся решить всю нормализацию сразу.

Твоя задача — deterministic foundation.

Следующий агент или следующий этап будет заниматься candidate generation и LLM cluster validation.
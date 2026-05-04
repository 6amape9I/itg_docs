# Порядок запуска агентов — этап 1

## Общая логика

На первом этапе нужно не пытаться сразу пересобрать всю базу, а создать надёжный фундамент:

1. распарсить `documents.csv`;
2. получить `parsed_documents.jsonl` и `document_blocks.jsonl`;
3. подготовить контролируемые LLM-вызовы через OpenRouter;
4. сделать calibration run на 50–200 документах;
5. проверить артефакты, кэш, схемы, бюджет и отчёты.

Рекомендуется работать в отдельных ветках или хотя бы с аккуратным разделением зон ответственности, чтобы агенты не перетирали файлы друг друга.

## Рекомендуемый порядок

### 1. Сначала запустить Pipeline Engineer

Файл инструкции:

```text
instructions/01_pipeline_engineer_stage1.md
```

Почему он первый:

- он создаёт базовую структуру проекта;
- он определяет формат `parsed_documents.jsonl` и `document_blocks.jsonl`;
- без этих файлов LLM Orchestrator не имеет нормального входа;
- QA потом сможет проверять конкретные артефакты, а не абстрактные ожидания.

Что попросить агента сделать первым:

```text
Прочитай instructions/01_pipeline_engineer_stage1.md, создай docs/stage1_pipeline_engineer_plan.md, затем реализуй этап парсинга и feedback.
```

Ожидаемый промежуточный результат:

```text
docs/stage1_pipeline_engineer_plan.md
kb_rebuild/... базовая структура
data/parsed/parsed_documents.jsonl
data/parsed/document_blocks.jsonl
data/reports/run_report.json
docs/stage1_pipeline_engineer_feedback.md
```

Если реального `documents.csv` ещё нет в ожидаемом месте, агент должен работать на фикстурах и описать это в feedback.

### 2. Затем запустить LLM Orchestrator Engineer

Файл инструкции:

```text
instructions/02_llm_orchestrator_engineer_stage1.md
```

Почему он второй:

- он зависит от формата parsed artifacts;
- он должен использовать `doc_id`, `name`, `clean_text`;
- он не должен дублировать парсер;
- он должен подключить OpenRouter, кэш, JSON Schema и calibration run.

Что попросить агента сделать:

```text
Прочитай instructions/02_llm_orchestrator_engineer_stage1.md и feedback Pipeline Engineer, создай docs/stage1_llm_orchestrator_plan.md, затем реализуй OpenRouter-клиент, кэш, schema/prompt и calibration tagging CLI.
```

Ожидаемый результат:

```text
docs/stage1_llm_orchestrator_plan.md
kb_rebuild/llm/...
data/llm_cache/...
data/tagging/document_tags_raw.jsonl
data/tagging/document_tagging_failures.jsonl
data/reports/tagging_report.json
docs/stage1_llm_orchestrator_feedback.md
```

Для первого запуска использовать маленький лимит:

```bash
python -m kb_rebuild tag --data data --limit 50 --model deepseek/deepseek-v4-flash --max-cost-usd 3
```

Если всё стабильно, можно увеличить до 100–200 документов:

```bash
python -m kb_rebuild tag --data data --limit 200 --model deepseek/deepseek-v4-flash --max-cost-usd 10
```

Не запускать 16 000 документов на этом этапе.

### 3. QA / Test Engineer запустить третьим, но можно дать ему ранний старт после плана Pipeline Engineer

Файл инструкции:

```text
instructions/03_qa_test_engineer_stage1.md
```

Идеальный порядок — запускать QA после того, как Pipeline Engineer и LLM Orchestrator создали первые результаты. Но QA можно подключить раньше, когда Pipeline Engineer уже написал план и начал создавать структуру: QA сможет подготовить фикстуры и тестовые ожидания.

Что попросить агента сделать:

```text
Прочитай instructions/03_qa_test_engineer_stage1.md, планы и feedback других агентов, создай docs/stage1_qa_test_engineer_plan.md, затем реализуй фикстуры, валидаторы, тесты и QA-отчёт.
```

Ожидаемый результат:

```text
docs/stage1_qa_test_engineer_plan.md
tests/fixtures/...
tests/test_parsed_artifacts_validation.py
tests/test_llm_orchestrator_contract.py
kb_rebuild/validation/...
docs/stage1_qa_report.md
docs/stage1_qa_test_engineer_feedback.md
```

## Практический режим запуска на сегодня

Рекомендуемый сценарий:

1. Положить все четыре файла инструкции в папку `instructions`.
2. Запустить Pipeline Engineer.
3. Дождаться его плана. Если план разумный, пусть продолжает реализацию.
4. Когда Pipeline Engineer создаст базовую структуру и формат parsed artifacts, запустить LLM Orchestrator Engineer.
5. Когда LLM Orchestrator создаст план и skeleton клиента, запустить QA / Test Engineer.
6. После завершения всех трёх агентов дать архитектору доступ к репозиторию, feedback-файлам и QA-отчёту.

## Как разделить зоны ответственности, чтобы не было конфликтов

Pipeline Engineer может менять:

```text
kb_rebuild/cli.py
kb_rebuild/parsing/...
kb_rebuild/io/...
kb_rebuild/schemas/parsed_documents.py
kb_rebuild/reports/...
tests/test_editorjs_parser.py
tests/test_doc_id_generation.py
```

LLM Orchestrator Engineer может менять:

```text
kb_rebuild/llm/...
kb_rebuild/cli.py только для добавления команды tag
kb_rebuild/schemas/ если нужны LLM-схемы
data/tagging/ только при запуске calibration
data/llm_cache/ только при запуске calibration
```

QA / Test Engineer может менять:

```text
kb_rebuild/validation/...
tests/fixtures/...
tests/test_*validation*.py
tests/test_llm_orchestrator_contract.py
docs/stage1_qa_report.md
```

Если двум агентам нужно менять один и тот же файл, например `kb_rebuild/cli.py`, второй агент обязан сделать минимальное изменение и описать его в feedback.

## Что считать успешным окончанием этапа 1

Этап 1 можно считать успешным, если:

- Pipeline Engineer создал рабочий парсинг документов;
- LLM Orchestrator создал контролируемый OpenRouter-клиент и test tagging run;
- QA проверил артефакты и не нашёл критичных ошибок;
- есть документация в `docs` от каждого агента;
- есть понятный список нерешённых вопросов для архитектора.

## Что делать после этапа 1

После проверки архитектором следующий этап будет посвящён первичному тегированию уже не на 50–200, а на всём корпусе, затем нормализации тегов и построению `document_tag_links`.

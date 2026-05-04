# Stage 1 Pipeline Engineer Plan

## Что я понял

Нужно создать технический фундамент первого этапа: CLI, чтение `documents.csv`, детерминированную генерацию `doc_id`, устойчивый парсинг Editor.js, сохранение `parsed_documents.jsonl` и `document_blocks.jsonl`, базовый report/logging и проверку распарсенных артефактов.

Моя зона ответственности не включает LLM-вызовы, тегирование, нормализацию, evidence extraction, генерацию статей и миграцию.

## Файлы, которые планирую создать или изменить

- `kb_rebuild/__init__.py`
- `kb_rebuild/__main__.py`
- `kb_rebuild/cli.py`
- `kb_rebuild/parsing/editorjs.py`
- `kb_rebuild/io/jsonl.py`
- `kb_rebuild/schemas/parsed_documents.py`
- `kb_rebuild/reports/run_report.py`
- `tests/test_editorjs_parser.py`
- `tests/test_doc_id_generation.py`
- `tests/fixtures/editorjs_simple.json`
- `tests/fixtures/editorjs_mixed_blocks.json`
- `tests/fixtures/documents_sample.csv`
- `docs/stage1_pipeline_engineer_feedback.md`

Если понадобится, добавлю небольшие служебные `__init__.py`.

## Допущения

- Основной вход по умолчанию: `data/input/documents.csv`, но путь всегда задаётся через `--input`.
- Реального `data/input/documents.csv` сейчас может не быть; в этом случае тестирование выполняется на фикстурах.
- `doc_id` генерируется как `doc_{row_index_1_based:06d}_{content_hash_8}`.
- `row_index` в выходных документах считается с 1 и соответствует строке данных CSV без заголовка.
- Парсер не исполняет содержимое `code`/`raw`, а только сохраняет текст.
- Неизвестные блоки сохраняются в статистике и попадают в `document_blocks.jsonl`, если из них удалось извлечь текст; если текста нет, они учитываются в документе как `empty_or_unhandled_block`.

## Как буду проверять результат

- Unit tests на:
  - `header` + `paragraph`;
  - `list`;
  - `table`;
  - unknown-блок с вложенным текстом;
  - битый JSON без падения;
  - уникальность `doc_id`;
  - связь блоков с `doc_id`.
- CLI smoke test:
  - `python -m kb_rebuild parse --input tests/fixtures/documents_sample.csv --out /tmp/itg_docs_stage1 --limit 10`;
  - `python -m kb_rebuild validate-parsed --data /tmp/itg_docs_stage1 --expected-docs 4`.

## Риски

- В реальном CSV могут встретиться нестандартные Editor.js-блоки и HTML-фрагменты, поэтому unknown extraction должен быть рекурсивным.
- Битый JSON и пустой `content` не должны выбрасывать документ из артефактов.
- Повторные запуски должны перезаписывать stage artifacts атомарно, чтобы не смешивать старые и новые строки.
- `pytest` может быть не установлен; тесты сделаю на стандартном `unittest`, чтобы они запускались без новых зависимостей.

## Чеклист

- [x] Прочитать актуальные инструкции.
- [x] Создать stage-1 план.
- [x] Создать структуру `kb_rebuild`.
- [x] Реализовать `parse`.
- [x] Реализовать `validate-parsed`.
- [x] Реализовать report и logging.
- [x] Добавить тестовые фикстуры.
- [x] Добавить unit tests.
- [x] Запустить tests и CLI smoke test.
- [x] Создать feedback.

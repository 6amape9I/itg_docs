# Stage 1 Pipeline Engineer Feedback

## Что сделано

- Создан пакет `kb_rebuild` с entrypoint `python -m kb_rebuild`.
- Реализована команда парсинга:
  - `python -m kb_rebuild parse --input data/input/documents.csv --out data`;
  - `python -m kb_rebuild parse --input data/input/documents.csv --out data --limit 100`.
- Реализована команда проверки:
  - `python -m kb_rebuild validate-parsed --data data`;
  - дополнительно поддерживаются `--input` и `--expected-docs`.
- Реализована детерминированная генерация `doc_id` в формате `doc_{row_index:06d}_{content_hash_8}`.
- Реализован устойчивый парсинг Editor.js для `paragraph`, `header`, `list`, `table`, `quote`, `warning`, `checklist`, `delimiter`, `image`, `embed`, `code`, `raw` и unknown-блоков.
- Битый JSON, пустой `content` и unknown-блоки не останавливают весь прогон.
- Для реального большого CSV поднят `csv.field_size_limit`, иначе документы с крупным `content` ломают стандартный Python CSV reader.
- Добавлены JSONL IO, dataclass-схемы, run report и логирование в `data/logs/pipeline.log`.
- Добавлены тестовые фикстуры и unit tests на стандартном `unittest`.
- `.gitignore` дополнен исключениями для Python bytecode caches; `data/` сейчас также игнорируется и не попадёт в git status.

## Какие файлы изменены

- `.gitignore`
- `docs/stage1_pipeline_engineer_plan.md`
- `docs/stage1_pipeline_engineer_feedback.md`
- `kb_rebuild/__init__.py`
- `kb_rebuild/__main__.py`
- `kb_rebuild/cli.py`
- `kb_rebuild/io/__init__.py`
- `kb_rebuild/io/jsonl.py`
- `kb_rebuild/parsing/__init__.py`
- `kb_rebuild/parsing/documents.py`
- `kb_rebuild/parsing/editorjs.py`
- `kb_rebuild/parsing/validate.py`
- `kb_rebuild/reports/__init__.py`
- `kb_rebuild/reports/run_report.py`
- `kb_rebuild/schemas/__init__.py`
- `kb_rebuild/schemas/parsed_documents.py`
- `tests/fixtures/documents_sample.csv`
- `tests/fixtures/editorjs_simple.json`
- `tests/fixtures/editorjs_mixed_blocks.json`
- `tests/test_doc_id_generation.py`
- `tests/test_editorjs_parser.py`

## Как запустить парсинг

Для реального корпуса:

```bash
python -m kb_rebuild parse --input data/input/documents.csv --out data
```

Dry-run:

```bash
python -m kb_rebuild parse --input data/input/documents.csv --out data --limit 100
```

Проверка артефактов:

```bash
python -m kb_rebuild validate-parsed --data data
```

Если нужно сверить количество документов с исходным CSV:

```bash
python -m kb_rebuild validate-parsed --data data --input data/input/documents.csv
```

Если парсинг был с `--limit`:

```bash
python -m kb_rebuild validate-parsed --data data --expected-docs 100
```

## Как запустить тесты

```bash
python -m unittest discover -s tests
```

В текущей среде команда запускалась через `.venv`:

```bash
.venv/bin/python -m unittest discover -s tests
```

Результат: `Ran 9 tests ... OK`.

Дополнительно запускалась компиляционная проверка:

```bash
.venv/bin/python -m py_compile kb_rebuild/__main__.py kb_rebuild/cli.py kb_rebuild/io/jsonl.py kb_rebuild/parsing/editorjs.py kb_rebuild/parsing/documents.py kb_rebuild/parsing/validate.py kb_rebuild/reports/run_report.py kb_rebuild/schemas/parsed_documents.py
```

Результат: успешно.

## Какие форматы данных получаются

`data/parsed/parsed_documents.jsonl` содержит один JSON-объект на документ:

- `doc_id`
- `row_index`
- `name`
- `description`
- `content_hash`
- `parse_status`
- `parse_errors`
- `clean_text`
- `text_length_chars`
- `blocks_count`
- `non_empty_blocks_count`
- `block_types`
- `block_parse_statuses`
- `empty_or_unhandled_blocks_count`

`data/parsed/document_blocks.jsonl` содержит один JSON-объект на блок:

- `doc_id`
- `block_id`
- `block_index`
- `block_type`
- `text`
- `text_length_chars`
- `metadata`
- `raw_block_hash`
- `parse_status`

`data/reports/run_report.json` содержит summary по parse stage:

- количество документов по статусам;
- общее количество блоков;
- типы блоков;
- количество duplicate `doc_id`;
- список ошибок;
- input/output пути и `limit`.

## Проверка на фикстуре

Первичный smoke test выполнен на фикстуре:

```bash
.venv/bin/python -m kb_rebuild parse --input tests/fixtures/documents_sample.csv --out /tmp/itg_docs_stage1 --limit 4
.venv/bin/python -m kb_rebuild validate-parsed --data /tmp/itg_docs_stage1 --expected-docs 4
```

Результат:

- `documents=4`;
- `blocks=5`;
- validation `ok`;
- один документ с битым JSON сохранён со статусом `failed`;
- один документ с пустым `content` сохранён со статусом `empty`.

## Проверка на реальном корпусе

После добавления `data/input/documents.csv` выполнен полный parse:

```bash
.venv/bin/python -m kb_rebuild parse --input data/input/documents.csv --out data
.venv/bin/python -m kb_rebuild validate-parsed --data data --input data/input/documents.csv
```

Результат:

- `documents_total`: 16181;
- `documents_parsed_ok`: 16152;
- `documents_parse_partial`: 9;
- `documents_parse_failed`: 0;
- `documents_empty`: 20;
- `blocks_total`: 427015;
- `duplicate_doc_ids`: 0;
- `errors_count`: 29;
- validation: `ok`.

Созданы реальные артефакты:

- `data/parsed/parsed_documents.jsonl` - около 195 MB;
- `data/parsed/document_blocks.jsonl` - около 308 MB;
- `data/reports/run_report.json`;
- `data/logs/pipeline.log`.

Типы блоков по полному корпусу:

```json
{
  "delimiter": 59,
  "header": 176284,
  "image": 1835,
  "list": 33181,
  "paragraph": 210013,
  "raw": 1,
  "table": 5641,
  "unknown": 1
}
```

## Что не сделано

- Не реализованы LLM-вызовы, tagging, normalization, evidence extraction и article compilation, так как это вне зоны Pipeline Engineer на этом этапе.

## Риски и вопросы архитектору

- Нужно посмотреть неизвестные `block_type` из реального корпуса и при необходимости добавить специализированные extractors.
- В корпусе есть 20 документов с пустыми Editor.js `blocks`; они сохранены как `empty`, не потеряны.
- В корпусе есть 9 документов `partial`; в основном это пустые текстовые блоки. Они сохранены и отражены в `run_report.json`.
- В корпусе встретился 1 `unknown` block type; нужно решить, нужен ли для него отдельный extractor после просмотра downstream-командой.
- При запуске с `--limit` в `run_report.json` `documents_total` означает количество обработанных строк, а не полный размер исходного CSV.

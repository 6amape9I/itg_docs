# План ревью Gemini 4000 эксперимента

Дата: 2026-05-05 10:29 MSK

Роль: LLM Orchestrator Engineer

## Что понял

Нужно найти последний эксперимент Gemini на 4000 документов, проверить его `tagging_report.json`, файл ошибок и активные результаты, затем дать обратную связь по стабильности, скорости, стоимости и характеру ошибок.

## Артефакты

Проверяемые артефакты:

- `data/tagging/experiments/gemini_flash_4000_batch5_inflight4_v1/tagging_report.json`
- `data/tagging/experiments/gemini_flash_4000_batch5_inflight4_v1/tagging_active_manifest.json`
- `data/tagging/experiments/gemini_flash_4000_batch5_inflight4_v1/document_tags_raw_active.jsonl`
- `data/tagging/experiments/gemini_flash_4000_batch5_inflight4_v1/document_tagging_failures.jsonl`

Создаваемые артефакты:

- `docs/gemini_4000_experiment_llm_orchestrator_plan.md`
- `docs/gemini_4000_experiment_llm_orchestrator_feedback.md`

## Планируемые изменения

Код и данные эксперимента не изменяются. Добавляются только документы ревью в `docs`.

## Риски

- Ревью не заменяет медицинскую QA-проверку семантической корректности тегов.
- Метрики качества цитат основаны на текущей автоматической валидации строк, а не на ручной проверке каждой сущности.
- `batch_documents_requested` в report учитывает документы в ретраях и поэтому отличается от `documents_requested`.

## Чеклист

- [x] Найти актуальный эксперимент на 4000 документов.
- [x] Прочитать `tagging_report.json`.
- [x] Проверить manifest и наличие активных/failure-файлов.
- [x] Разобрать причины failures.
- [x] Проверить активный JSONL на дубли, пустые сущности и статусы quote validation.
- [x] Сформировать итоговую обратную связь.

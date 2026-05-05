# Feedback по Gemini 4000 эксперименту

Дата: 2026-05-05 10:29 MSK

Роль: LLM Orchestrator Engineer

## Что сделано

Найден и проверен эксперимент:

`data/tagging/experiments/gemini_flash_4000_batch5_inflight4_v1`

Запуск завершился 2026-05-04 19:24:55 MSK. Использовались `google/gemini-3-flash-preview` / `google/gemini-3-flash-preview-20251217`, `batch_size=5`, `max_inflight=4`, `structured_output_mode=schema_lite`.

Ключевые метрики:

- запрошено документов: 4000;
- успешно размечено: 3993;
- failures: 7;
- успешность от всех документов: 99.825%;
- успешность от непустых документов: 100%;
- wall clock: 2676 секунд, примерно 44 минуты 36 секунд;
- скорость: примерно 5371.749 документов/час;
- API requests/hour: 1111.211;
- средняя latency: 12.789 секунды;
- estimated cost: 9.5935455 USD;
- стоимость на документ: примерно 0.002403 USD;
- прогноз на 16181 документ: примерно 38.88 USD и 3.01 часа при той же скорости.

Стабильность LLM:

- `http_429_count=0`;
- `rate_limit_count=0`;
- `cooldown_events_count=0`;
- `llm_error_count=0`;
- `http_status_counts={}`;
- `llm_success_count=826` из `llm_requests_count=826`;
- `invalid_json_count=3`, но все случаи восстановились ретраями;
- `llm_retries_count=3`.

Качество активного JSONL:

- active rows: 3993;
- unique `doc_id`: 3993;
- дублей нет;
- документов с нулевым числом сущностей нет;
- всего сущностей: 10647;
- среднее число сущностей на документ: 2.666.

Quote validation по report:

- exact found: 10446;
- fuzzy: 118;
- normalized found: 152;
- not found: 62;
- доля `not_found`: примерно 0.575%;
- accepted quote matches с учетом exact/normalized/fuzzy: примерно 99.425%.

## Ошибки

Все 7 failures имеют причину `empty_clean_text` и `attempts=0`. Это не ошибки Gemini/OpenRouter: документы не отправлялись в LLM, потому что после парсинга у них нет текста для проверки цитат.

Список failed документов:

- `doc_000001_a2bc407d` - `!метастатический опухолевый субклон`;
- `doc_000166_a2bc407d` - `Vitamax(бад)`;
- `doc_000174_a2bc407d` - ``` ``макротромбоцитопения, связанная с геном tubb1, с аутосомно-доминантным наследованием``.`` ```;
- `doc_000264_a2bc407d` - `Агнукастон таблетки, покрытые оболочкой 60 шт`;
- `doc_001197_a2bc407d` - `Антистин-привин`;
- `doc_003013_a2bc407d` - `Витрум`;
- `doc_003139_a2bc407d` - `Вольтарен эмульгель гель для наружного применения 2%`.

## Файлы изменены

- `docs/gemini_4000_experiment_llm_orchestrator_plan.md`
- `docs/gemini_4000_experiment_llm_orchestrator_feedback.md`

Код, данные эксперимента и исходные документы не изменялись.

## Как запустить

Для повторения такого эксперимента нужно запускать текущий tagging batch pipeline с Gemini Flash, `batch_size=5`, `max_inflight=4`, лимитом 4000 и включенным кэшем LLM. Точную команду из shell history не восстанавливал, потому что в артефактах сохранены только manifest/report, а не CLI invocation.

## Как проверить

Проверенные файлы:

- `tagging_report.json`;
- `tagging_active_manifest.json`;
- `document_tagging_failures.jsonl`;
- `document_tags_raw_active.jsonl`.

Проверки:

- line count active/failures/history;
- причины failures;
- уникальность `doc_id`;
- наличие документов с пустым списком entities;
- распределение статусов quote validation;
- расчет стоимости, скорости и долей ошибок.

## Что не сделано

- Не выполнялась ручная медицинская оценка корректности выбранных сущностей.
- Не сравнивалась семантика с предыдущими OpenRouter/DeepSeek результатами документ к документу.
- Не исправлялись 62 `not_found` цитаты, только зафиксирован масштаб проблемы.

## Риски

- 62 `not_found` цитаты нужно отдельно отдать в QA, даже если доля низкая.
- Высокая доля `context_only` сущностей, 4685 из 10647, может быть нормальной для источников, но стоит проверить, не размечает ли модель слишком много контекстных сущностей.
- `batch_documents_requested=4006` при `documents_requested=4000` может путать в отчетности: это похоже на учет документов внутри batch retries после `invalid_json`.

## Вопросы архитектору

- Считать ли `empty_clean_text` допустимыми input failures или нужно генерировать fallback-тег из `name` для таких документов?
- Нужен ли отдельный QA-этап для 62 `not_found` цитат перед запуском на весь корпус?
- Принимать ли текущую долю `context_only` или ужесточить prompt/фильтр ролей перед нормализацией?

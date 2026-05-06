# Normalization N3 Plan

## Что понял

N3 должен прочитать строгий N2.2 handoff:

```text
data/normalization/n2/n3_candidate_groups.jsonl
```

и для каждой candidate group получить LLM-решение:

- `accept_same_entity`
- `reject_distinct_entities`
- `split_into_subclusters`
- `needs_web_or_human_review`

N3 не делает финальный merge и не создаёт `tags_canonical.csv`, `tag_aliases.csv`, `document_tag_links_normalized.jsonl`. Главный output для N4: `data/normalization/n3/accepted_clusters.jsonl`.

## Прочитанные инструкции и контекст

- `instructions/normaalization_agent_instruction.md`
- `instructions/01_n3_instruction.md`
- `instructions/02_normalization_global_vision.md`
- `instructions/03_normalization_engineer_agent_guide.md`
- `docs/normalization_n1_feedback.md`
- `docs/normalization_n1_1_feedback.md`
- `docs/normalization_n2_feedback.md`
- `docs/normalization_n2_1_feedback.md`
- `docs/normalization_n2_2_feedback.md`
- `data/normalization/n2/candidate_generation_report.json`
- `data/normalization/n2/candidate_generation_manifest.json`
- `data/normalization/n2/n3_candidate_groups.jsonl`

Note: `03_normalization_engineer_agent_guide.md` is mostly N1-oriented and says not to use Gemini for N1. For this task, the explicit N3 instruction overrides that because it requires direct Gemini structured-output validation.

## Входные проверки

Runner должен отказать, если:

- `candidate_generation_manifest.stage_version != n2.2`
- `candidate_generation_report.stage_version != n2.2`
- `candidate_generation_report.quality_gate.passed != true`
- `data/normalization/n2/n3_candidate_groups.jsonl` отсутствует

## Файлы, которые планирую изменить

- `kb_rebuild/cli.py`

## Новые файлы кода

- `kb_rebuild/normalization/n3/__init__.py`
- `kb_rebuild/normalization/n3/models.py`
- `kb_rebuild/normalization/n3/prompt.py`
- `kb_rebuild/normalization/n3/schema.py`
- `kb_rebuild/normalization/n3/quality.py`
- `kb_rebuild/normalization/n3/report.py`
- `kb_rebuild/normalization/n3/runner.py`
- `kb_rebuild/normalization/n3/prompts/validate_group_v1.md`

## Outputs

Обязательные:

- `data/normalization/n3/llm_group_decisions.jsonl`
- `data/normalization/n3/accepted_clusters.jsonl`
- `data/normalization/n3/rejected_groups.jsonl`
- `data/normalization/n3/split_groups.jsonl`
- `data/normalization/n3/web_or_human_review_groups.jsonl`
- `data/normalization/n3/n3_report.json`
- `data/normalization/n3/n3_manifest.json`

Дополнительные:

- `data/normalization/n3/llm_group_decisions.csv`
- `data/normalization/n3/accepted_clusters.csv`
- `data/normalization/n3/split_groups.csv`
- `data/normalization/n3/rejected_groups.csv`
- `data/normalization/n3/review_groups.csv`
- `data/normalization/n3/validation_failures.jsonl`
- `data/normalization/n3/known_bad_decision_checks.csv`
- `data/normalization/n3/known_bad_accepted_clusters.csv`
- `data/normalization/n3/n3_quality_diagnostics.json`

## Schema

Реализую локальную schema validation без внешних зависимостей:

- decision enum validation
- confidence in `[0, 1]`
- matching `candidate_group_id`
- matching `entity_type`
- no unknown labels/node_ids
- accepted group covers all input node_ids in one subcluster
- split covers every node_id either in subclusters or rejected labels
- no overlapping subcluster node_ids
- canonical is required for accepted/same_entity subclusters
- reject/review do not produce accepted clusters

Gemini payload will use `generationConfig.responseMimeType=application/json` and `responseJsonSchema` for `gemini_schema`.

## Runner

- Direct Gemini provider only for primary N3.
- `batch_size=1` default and implementation.
- Disk cache under `data/normalization/n3/llm_cache/`.
- Cache key includes stage, provider, model, prompt version, schema version, candidate group id, input hash, web-review flag and request params.
- Retries use repair prompt on invalid JSON/schema response.
- Invalid final responses go to `validation_failures.jsonl` and become `needs_web_or_human_review`.
- Budget preflight uses configured Gemini pricing and `max_cost_usd`.
- `--no-overwrite` refuses to overwrite existing N3 outputs.

## Tests

Add:

- `tests/test_normalization_n3_schema.py`
- `tests/test_normalization_n3_validation.py`
- `tests/test_normalization_n3_quality.py`
- `tests/test_normalization_n3_prompt.py`
- `tests/test_normalization_n3_runner.py`

Test coverage:

- valid accept/reject/split/review
- unknown decision fails
- unknown node_id fails
- accept without canonical fails
- split overlapping/uncovered node_ids fails
- accepted clusters from accept and split
- invalid LLM response becomes review/failure
- known bad accepted cluster fails quality
- prompt contains strict no-merge, split, reject and no-web-by-default rules
- runner refuses non-`n2.2` manifest
- runner creates required outputs with a fake client

## Что не буду делать

- Не создавать N4 artifacts.
- Не менять `data/tagging/*`, `data/parsed/*`, N1/N2 input artifacts.
- Не запускать evidence/article pipeline.
- Не включать web-review по умолчанию.
- Не реализовывать отдельную `normalize-n3-web-review` команду в этом проходе, если primary N3 acceptance закрыт без неё. Укажу это в feedback как not done.

## Риски

- Live Gemini run может быть заблокирован отсутствием ключа, сетью или provider rate limits.
- 363 отдельных запроса могут занять заметное время.
- Gemini structured output может вернуть JSON, который локальная schema отвергнет; такие группы должны уйти в review, а не ломать весь run.
- В N2.2 остаются hard-exact группы с raw risk flags, поэтому prompt должен быть строгим и не доверять N2 blindly.
- Production LLM stages must use real parallelism when `--max-inflight > 1`; sequential full-corpus/group runs waste time and are not acceptable operationally.

## Изменения плана по ходу работы

- При возобновлении обнаружен уже созданный skeleton `kb_rebuild/normalization/n3/` с models/schema/prompt/runner/report/quality и валидным compile check.
- Оставшиеся обязательные части: подключить CLI `normalize-n3`, добавить N3 unit tests, проверить runner на fake Gemini client, запустить production command или явно зафиксировать внешний блокер.
- `normalize-n3-web-review` остаётся вне primary acceptance этого прохода; основной N3 должен писать review layer без web pass.
- После production run выявлено `57` invalid LLM responses, в основном из-за `MAX_TOKENS`; runner доработан: реальный `max_inflight`, `max_output_tokens=6000`, `repair_max_output_tokens=12000`, `thinkingLevel=minimal`.
- Выполнен filtered retry только по invalid groups; итоговый N3 report пересобран без повторного full run.

## Чеклист

- [x] Перечитать N3 ТЗ после плана.
- [x] Реализовать models/schema/prompt.
- [x] Перечитать N3 ТЗ after_schema.
- [x] Реализовать runner/report/quality.
- [x] Перечитать N3 ТЗ after_runner.
- [x] Добавить CLI `normalize-n3`.
- [x] Добавить tests.
- [x] Перечитать N3 ТЗ after_tests.
- [x] Запустить compile check.
- [x] Запустить unittest discover.
- [x] Перечитать N3 ТЗ before_run.
- [x] Запустить production command из ТЗ.
- [x] Проверить outputs/report/manifest/quality/known bad.
- [x] Перечитать N3 ТЗ before_feedback.
- [x] Создать `docs/normalization_n3_feedback.md`.

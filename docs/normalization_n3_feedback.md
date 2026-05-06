# Normalization N3 Feedback

ТЗ перечитано на этапах: after_plan, after_schema, after_runner, after_tests, before_run, before_feedback

## 1. Что сделано

- Добавлен N3 LLM validation stage для строгой проверки N2.2 candidate groups.
- Добавлена CLI-команда `normalize-n3`.
- Реализованы prompt, Gemini structured output schema, local response validation, retries, cache, report/manifest/CSV/JSONL outputs и quality diagnostics.
- Production run выполнен на `363` группах из `data/normalization/n2/n3_candidate_groups.jsonl`.
- После первичного run исправлена runtime-проблема: `max_output_tokens=1800` и default thinking приводили к `MAX_TOKENS` и truncated JSON на retries.
- Добавлены реальные parallel requests через `--max-inflight`, `thinkingLevel=minimal`, `--max-output-tokens`, `--repair-max-output-tokens`.
- Выполнен filtered retry только по `57` invalid groups; итоговые N3 outputs пересобраны без повторного full run.

## 2. Какие файлы изменены

Код:

- `kb_rebuild/cli.py`
- `kb_rebuild/normalization/n3/__init__.py`
- `kb_rebuild/normalization/n3/models.py`
- `kb_rebuild/normalization/n3/prompt.py`
- `kb_rebuild/normalization/n3/schema.py`
- `kb_rebuild/normalization/n3/quality.py`
- `kb_rebuild/normalization/n3/report.py`
- `kb_rebuild/normalization/n3/runner.py`
- `kb_rebuild/normalization/n3/prompts/validate_group_v1.md`

Tests:

- `tests/test_normalization_n3_schema.py`
- `tests/test_normalization_n3_validation.py`
- `tests/test_normalization_n3_quality.py`
- `tests/test_normalization_n3_prompt.py`
- `tests/test_normalization_n3_runner.py`

Docs:

- `docs/normalization_n3_plan.md`
- `docs/normalization_n3_feedback.md`

## 3. Какие команды запускались

```bash
.venv/bin/python -m py_compile kb_rebuild/normalization/n3/models.py kb_rebuild/normalization/n3/prompt.py kb_rebuild/normalization/n3/schema.py kb_rebuild/normalization/n3/quality.py kb_rebuild/normalization/n3/report.py kb_rebuild/normalization/n3/runner.py kb_rebuild/cli.py
.venv/bin/python -m unittest tests/test_normalization_n3_schema.py tests/test_normalization_n3_validation.py tests/test_normalization_n3_quality.py tests/test_normalization_n3_prompt.py tests/test_normalization_n3_runner.py
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m kb_rebuild normalize-n3 --data data --normalization-dir data/normalization --n2-dir data/normalization/n2 --out data/normalization/n3 --provider gemini_direct --model gemini-3-flash-preview --structured-output-mode gemini_schema --batch-size 1 --max-inflight 8 --max-retries 3 --max-cost-usd 20
```

Также выполнен filtered retry только по invalid groups с:

- `max_inflight=8`
- `max_output_tokens=6000`
- `repair_max_output_tokens=12000`
- `thinkingLevel=minimal`

## 4. Tests

- Targeted N3 tests: `27` passed.
- Full suite: `147` tests passed.
- Compile check: passed.

## 5. Groups обработано

- `groups_total`: 363
- `groups_processed`: 363

## 6. Decisions

- `accepted_same_entity`: 294
- `rejected_distinct_entities`: 38
- `split_into_subclusters`: 20
- `needs_web_or_human_review`: 11

## 7. Accepted clusters

- `accepted_clusters_total`: 333
- `accepted_clusters_from_split`: 39

Главный output для N4:

```text
data/normalization/n3/accepted_clusters.jsonl
```

## 8. Invalid LLM responses

- Initial production run: `57`
- After filtered retry: `11`

Root cause for the initial failures:

- many cache records had `finish_reason=MAX_TOKENS`;
- visible JSON was truncated;
- Gemini also spent output budget on reasoning tokens.

Fix applied:

- default N3 `max_output_tokens` raised to `6000`;
- repair attempts can use up to `12000`;
- Gemini `thinkingConfig.thinkingLevel=minimal`;
- retry run used real `max_inflight=8`.

Remaining `11` invalid groups were kept as `needs_web_or_human_review`, mostly because LLM returned `split_into_subclusters` without any useful `same_entity` subcluster. This is intentionally not auto-converted to accept/reject by code.

## 9. Стоимость и число запросов

Final combined cost:

- `estimated_cost_usd`: 3.337914
- `requests`: 695
- `cache_hits`: 0
- `cache_misses`: 695

The request count includes initial run attempts plus filtered retry attempts.

## 10. Примеры accept

- `Простатический специфический антиген | Простатоспецифический антиген | Простатспецифический антиген` -> accepted cluster `n3c_000001`
- `NK-клетки | Натуральные киллеры` -> accepted cluster `n3c_000002`
- `МРТ головного мозга | Магнитно-резонансная томография головного мозга` -> accepted cluster `n3c_000004`

## 11. Примеры reject

- `Недержание мочи у женщин | Недержание мочи у мужчин` -> `reject_distinct_entities`
- `Азоксимера бромид | Полиоксидоний` -> `reject_distinct_entities`
- `Амловас | Амлодипин` -> `reject_distinct_entities`
- `Атомоксетин | Страттера` -> `reject_distinct_entities`

## 12. Примеры split

- `Мегалобластная анемия | Мерцательная аритмия | Фибрилляция предсердий`
  - accepted subcluster: `Мерцательная аритмия | Фибрилляция предсердий`
  - singleton: `Мегалобластная анемия`
- `Акустическая невринома | Вестибулярная шваннома | Невринома головного мозга | Невринома слухового нерва`
  - accepted subcluster: `Акустическая невринома | Вестибулярная шваннома | Невринома слухового нерва`
  - singleton: `Невринома головного мозга`
- `Анти-VEGF препараты | Ингибиторы VEGF | Ингибиторы ангиогенеза | Ингибиторы фактора роста эндотелия сосудов`
  - accepted subcluster: anti-VEGF / VEGF aliases
  - singleton: broader `Ингибиторы ангиогенеза`

## 13. Примеры needs review

- `ИНТАЛ | Кромоглициевая кислота`
- `Диротон | Лизиноприл | Синоприл`
- `Скинорен | Скинорен гель | Скинорен крем`
- `Диабетическая нейропатия | Диабетическая полинейропатия`
- `Гастроэзофагеальная рефлюксная болезнь | Гастроэзофагеальный рефлюкс`

## 14. Quality diagnostics

Final `data/normalization/n3/n3_quality_diagnostics.json`:

- `accepted_clusters_with_single_node`: 0
- `accepted_clusters_with_empty_canonical`: 0
- `split_groups_with_uncovered_nodes`: 0
- `known_bad_accepted_clusters`: 0
- `passed`: true

## 15. Known bad accepted clusters

- `known_bad_accepted_clusters`: 0
- `data/normalization/n3/known_bad_accepted_clusters.csv` contains only the header.

Quality scanner was corrected to avoid false positives for:

- same-product RBC punctuation variants such as `Железо rbc | Железо(RBC)`;
- `Вирус гепатита D | Вирус гепатита дельта`.

It still catches actual mixed RBC products and hepatitis A/B/C/D/E conflicts.

## 16. Outputs

Main outputs:

- `data/normalization/n3/llm_group_decisions.jsonl`
- `data/normalization/n3/accepted_clusters.jsonl`
- `data/normalization/n3/rejected_groups.jsonl`
- `data/normalization/n3/split_groups.jsonl`
- `data/normalization/n3/web_or_human_review_groups.jsonl`
- `data/normalization/n3/validation_failures.jsonl`
- `data/normalization/n3/n3_report.json`
- `data/normalization/n3/n3_manifest.json`
- `data/normalization/n3/n3_quality_diagnostics.json`
- CSV mirrors for decisions/clusters/groups

Audit outputs:

- `data/normalization/n3/validation_failures_initial_run.jsonl`
- `data/normalization/n3/retry_invalid_groups/`

## 17. Что не сделано

- `normalize-n3-web-review` command не реализована.
- Web grounding не запускался.
- N4 artifacts не создавались:
  - `tags_canonical.csv`
  - `tag_aliases.csv`
  - `document_tag_links_normalized.jsonl`
- N1/N2 artifacts, `data/tagging/*`, `data/parsed/*` не изменялись кодом N3.

## 18. Риски

- Остались `11` review groups из-за invalid schema after retry; они безопасно исключены из accepted clusters.
- Часть `reject_distinct_entities` для drug trade name vs active substance отражает strict N3 policy. N4 не должен автоматически превращать эти rejected pairs в aliases.
- `accepted_clusters.jsonl` может содержать duplicate node coverage across clusters from different source groups; N4 должен deduplicate/resolve canonical layer globally.
- Runtime policy: дальнейшие production LLM stages должны использовать real parallelism by default when `max_inflight > 1`.

## 19. Что передать в N4

Передавать:

```text
data/normalization/n3/accepted_clusters.jsonl
```

Также учитывать:

- `data/normalization/n3/rejected_groups.jsonl` для hard negative decisions;
- `data/normalization/n3/split_groups.jsonl` для provenance частичных merges;
- `data/normalization/n3/web_or_human_review_groups.jsonl` для ручной/web review очереди;
- `data/normalization/n3/n3_report.json` и `n3_quality_diagnostics.json` как gates.

# A5. Final Article Export Assembly

## 0. Контекст

A5 — финальный deterministic export stage для документов-сущностей.

К этому моменту есть несколько путей, по которым прошли теги:

```text
A1 direct_copy_article: 6 806
A4 compiled articles: 9 748
A1 stub_only: 3 839
A1 review_stub: 2 017
A3 insufficient_evidence_review: 103

В сумме все эти пути должны покрыть:

final_tags_total = 22 513

A4 production уже принят:

tasks_processed = 9 748
article_drafts_total = 9 748
compiled_articles = 2 960
compiled_with_review_flag = 6 788
tasks_failed = 0
article_quality_issues = 0
quality.passed = true

Источник A4 production:

data/articles/a4/production_v1/

A1 уже создал полный entity JSON слой:

data/articles/entities/{entity_type}/{tag_id}.json

A5 должен собрать из этих слоёв два экспортных контура:

for_n8n
for_docs
1. Главная цель A5

Создать финальные article JSON файлы для всех 22 513 tag_id.

Нужно сохранить файлы в двух разных видах:

1.1 Flat export для n8n
data/articles/final_exports/for_n8n/

В этой папке все документы должны лежать в одной директории:

data/articles/final_exports/for_n8n/{tag_id}.json

Никакой иерархии внутри for_n8n быть не должно.

Эти файлы будут использоваться для отдельных n8n-пайплайнов.

1.2 Structured export для docs
data/articles/final_exports/for_docs/

Минимальная иерархия по entity_type:

data/articles/final_exports/for_docs/disease/{tag_id}.json
data/articles/final_exports/for_docs/disease/{tag_id}_quotes.json

data/articles/final_exports/for_docs/drug_trade_name/{tag_id}.json
data/articles/final_exports/for_docs/drug_trade_name/{tag_id}_quotes.json

data/articles/final_exports/for_docs/diagnostic_method/{tag_id}.json
data/articles/final_exports/for_docs/diagnostic_method/{tag_id}_quotes.json

for_docs позже будет дополнительно организовываться в иерархию папок, а companion-файлы {tag_id}_quotes.json будут использоваться для вопросов, цитат и последующей миграции evidence.

2. Не цели A5

На A5 запрещено:

вызывать LLM;
делать web search;
перегенерировать статьи;
изменять A1/A2/A3/A4 artifacts;
изменять normalization artifacts;
создавать новые медицинские факты;
переписывать content;
строить папочную медицинскую иерархию глубже entity_type;
генерировать полноценные 30+ вопросов на документ через LLM;
строить graph.

A5 — это сборка, нормализация формата, экспорт, проверка покрытия и подготовка companion quotes/questions files.

3. Входные файлы A5

Обязательные:

data/articles/a1/article_status_index.jsonl
data/articles/a1/a1_report.json
data/articles/a1/a1_manifest.json
data/articles/entities/

data/articles/a3/a4_compilation_input.jsonl
data/articles/a3/fact_groups.jsonl
data/articles/a3/tag_fact_group_index.jsonl
data/articles/a3/a3_report.json
data/articles/a3/a3_manifest.json

data/articles/a4/production_v1/article_drafts.jsonl
data/articles/a4/production_v1/a4_report.json
data/articles/a4/production_v1/a4_manifest.json
data/articles/a4/production_v1/article_quality_diagnostics.json

data/normalization/final/tags_canonical.csv
data/normalization/final/tag_aliases.csv
data/normalization/final/final_normalization_report.json
data/normalization/final/final_normalization_manifest.json

Опциональные, но полезные:

data/articles/a4/production_v1/article_compilation_review.jsonl
data/articles/a4/production_v1/manual_qa_articles_sample.csv
data/articles/a3/tags_without_usable_evidence.jsonl
data/articles/a3/tag_evidence_coverage.jsonl
data/articles/a1/direct_copy_articles.jsonl
data/articles/a1/stub_articles.jsonl
data/articles/a1/review_stub_articles.jsonl
4. Input validation

A5 runner должен отказаться запускаться, если:

A1 report quality.passed != true
A3 report quality.passed != true
A4 report quality.passed != true
A4 tasks_failed > 0
A4 article_quality_issues > 0
A1 final_tags_total != 22 513 или article_status_index_rows != final_tags_total
A4 article_drafts_total != 9 748
articles/entities directory отсутствует

Если exact counts немного отличаются из-за будущего перезапуска, runner не должен hardcode 22 513/9 748, но должен проверять consistency:

final_tags_total из A1 = число строк article_status_index
A4 article_drafts_total = число строк article_drafts.jsonl
5. Выходные файлы A5

Создать директорию:

data/articles/final_exports/

Основные export folders:

data/articles/final_exports/for_n8n/
data/articles/final_exports/for_docs/

Служебные outputs:

data/articles/final_exports/article_export_index.jsonl
data/articles/final_exports/article_export_index.csv

data/articles/final_exports/export_coverage_audit.json
data/articles/final_exports/export_missing_tags.csv
data/articles/final_exports/export_duplicate_filenames.csv
data/articles/final_exports/export_quality_issues.jsonl

data/articles/final_exports/quotes_index.jsonl
data/articles/final_exports/quotes_index.csv

data/articles/final_exports/a5_report.json
data/articles/final_exports/a5_manifest.json

Дополнительные QA outputs:

data/articles/final_exports/manual_qa_export_sample.csv
data/articles/final_exports/status_distribution.csv
data/articles/final_exports/entity_type_distribution.csv
6. Source selection policy

Для каждого tag_id выбрать финальный article source.

Приоритет:

6.1 A4 compiled article

Если tag_id есть в:

data/articles/a4/production_v1/article_drafts.jsonl

и статус:

compiled_article
compiled_with_review_flag

то использовать A4 draft.

Итоговый статус:

compiled_article
compiled_with_review_flag
6.2 A1 direct-copy article

Если A4 draft отсутствует, но A1 article_status=direct_copy_article, использовать:

data/articles/entities/{entity_type}/{tag_id}.json

Итоговый статус:

direct_copy_article
6.3 A1 stub_only

Если A1 article_status=stub_only, использовать A1 entity JSON как итоговый stub.

Итоговый статус:

stub_only
6.4 A1 review_stub

Если A1 article_status=review_stub, использовать A1 entity JSON как итоговый review stub.

Итоговый статус:

review_stub
6.5 A3 insufficient_evidence_review

Если tag находится в A3:

a4_strategy=insufficient_evidence_review

и A4 draft отсутствует, использовать A1 entity JSON, но итоговый статус:

insufficient_evidence_review
6.6 Fallback

Если ни один source не найден:

final_status = missing_article_source
need_review = true

Записать в:

export_missing_tags.csv
export_quality_issues.jsonl

Quality gate должен fail.

7. Финальный article JSON формат

Каждый файл в for_n8n и for_docs должен иметь одинаковый JSON формат.

Файл:

{tag_id}.json

Схема:

{
  "tag_id": "disease_...",
  "canonical_tag_ru": "Астма",
  "canonical_tag_latin": null,
  "entity_type": "disease",

  "article_status": "compiled_article",
  "source_article_status": "compiled_article",
  "source_stage": "A4",

  "needs_review_before_publication": false,
  "review_reasons": [],

  "content_format": "editorjs",
  "content": {
    "time": 0,
    "version": "2.28.0",
    "blocks": []
  },

  "sources": {
    "source_doc_ids": [],
    "source_documents_count": 0,
    "fact_group_ids": [],
    "used_fact_group_ids": []
  },

  "export": {
    "stage": "A5",
    "exported_at": "...",
    "for_n8n_path": "data/articles/final_exports/for_n8n/disease_x.json",
    "for_docs_path": "data/articles/final_exports/for_docs/disease/disease_x.json",
    "quotes_path": "data/articles/final_exports/for_docs/disease/disease_x_quotes.json"
  },

  "provenance": {
    "a1_entity_json": "data/articles/entities/disease/disease_x.json",
    "a3_fact_groups": "data/articles/a3/fact_groups.jsonl",
    "a4_article_draft": "data/articles/a4/production_v1/article_drafts.jsonl"
  }
}
8. Editor.js requirements

A5 must validate content for every exported article.

Required:

content is object
content.blocks is list
content.version exists or defaulted
all blocks have type and data
header blocks have non-empty text
paragraph blocks have non-empty text
list blocks have non-empty items
table blocks have non-empty content

For stub/review_stub, minimal content is allowed, but it must still be valid Editor.js.

If an input content is malformed, A5 should not invent medical content. It should create a safe review stub:

article_status = export_repair_stub
needs_review_before_publication = true
review_reasons includes malformed_source_editorjs

and record issue in export_quality_issues.jsonl.

9. File naming

Use stable tag_id filenames.

for_n8n
data/articles/final_exports/for_n8n/{tag_id}.json

Example:

data/articles/final_exports/for_n8n/disease_a1b2c3d4e5.json
for_docs
data/articles/final_exports/for_docs/{entity_type}/{tag_id}.json
data/articles/final_exports/for_docs/{entity_type}/{tag_id}_quotes.json

Example:

data/articles/final_exports/for_docs/disease/disease_a1b2c3d4e5.json
data/articles/final_exports/for_docs/disease/disease_a1b2c3d4e5_quotes.json

Do not use canonical title in filename. It can contain slashes, quotes, Latin symbols, duplicates and unsafe characters.

10. for_n8n export policy

for_n8n must be flat.

Allowed:

for_n8n/{tag_id}.json

Not allowed:

for_n8n/disease/{tag_id}.json
for_n8n/index/{...}
for_n8n/{tag_id}_quotes.json

No hierarchy inside for_n8n.

Service reports and indexes must stay outside:

data/articles/final_exports/article_export_index.csv

not inside for_n8n.

11. for_docs export policy

for_docs uses minimal hierarchy:

for_docs/{entity_type}/

Inside each entity type folder:

{tag_id}.json
{tag_id}_quotes.json

No deeper hierarchy at A5.

Future hierarchy stage may reorganize for_docs, but A5 should not attempt it.

12. Companion quotes/questions file

For each article in for_docs, create companion file:

{tag_id}_quotes.json

This file must exist for every tag.

12.1 Companion file schema
{
  "tag_id": "disease_...",
  "canonical_tag_ru": "Астма",
  "canonical_tag_latin": null,
  "entity_type": "disease",

  "article_status": "compiled_article",
  "needs_review_before_publication": false,
  "review_reasons": [],

  "questions_generation_status": "deterministic_draft",
  "quotes_source_status": "from_a3_fact_groups",

  "questions": [
    {
      "question_id": "q_disease_x_001",
      "question": "Что такое Астма?",
      "answer_quote": "...",
      "fact_group_id": "fg_...",
      "fact_type": "definition",
      "source_doc_ids": [],
      "quote_validation_status": "exact",
      "needs_review": false
    }
  ],

  "quotes": [
    {
      "quote_id": "quote_disease_x_001",
      "fact_group_id": "fg_...",
      "fact_type": "definition",
      "claim": "...",
      "quote": "...",
      "source_doc_ids": [],
      "source_window_ids": [],
      "quote_validation_status": "exact",
      "used_in_article": true,
      "needs_review": false
    }
  ],

  "provenance": {
    "source_fact_groups": "data/articles/a3/fact_groups.jsonl",
    "source_article": "data/articles/final_exports/for_docs/disease/disease_x.json"
  }
}
12.2 Important

A5 does not generate final LLM-quality question sets.

A5 should create deterministic draft questions from available fact groups.

This is not the postponed “30+ questions per document” stage.

The deterministic questions are only a useful initial companion layer for quotes/evidence.

13. Quote extraction for companion files

For A4 compiled articles:

Read used_fact_group_ids from article draft.

Map fact_group_id → fact group from:

data/articles/a3/fact_groups.jsonl

For each used fact group, create a quote object from:

representative_claim
representative_quote
representative_quote_validation_status
source_doc_ids
source_window_ids
fact_type

Include only fact groups with:

usable_for_a4=true
representative_quote_validation_status in {exact, normalized_exact}
If article uses no fact groups, companion quotes should be empty and quotes_source_status=empty_or_unavailable.

For direct-copy articles:

quotes_source_status = direct_copy_no_fact_groups
questions_generation_status = pending_fact_extraction_or_manual
questions = []
quotes = []

For stub/review/insufficient evidence:

quotes_source_status = no_usable_evidence
questions_generation_status = not_applicable_or_pending
questions = []
quotes = []
14. Deterministic question generation

For fact groups with valid quotes, generate one simple question per fact group.

No LLM.

Question templates by fact_type:

definition → Что такое {canonical_tag_ru}?
description → Что известно о {canonical_tag_ru}?
classification → Как классифицируется {canonical_tag_ru}?
mechanism → Каков механизм или принцип действия для {canonical_tag_ru}?
cause_or_risk_factor → Какие причины или факторы риска связаны с {canonical_tag_ru}?
symptom → Какие симптомы описаны для {canonical_tag_ru}?
diagnostics → Как диагностируют или оценивают {canonical_tag_ru}?
treatment → Какие подходы к лечению описаны для {canonical_tag_ru}?
prevention → Какие меры профилактики описаны для {canonical_tag_ru}?
complication → Какие осложнения связаны с {canonical_tag_ru}?
indication → Для чего применяется {canonical_tag_ru}?
contraindication → Какие противопоказания описаны для {canonical_tag_ru}?
side_effect → Какие побочные эффекты описаны для {canonical_tag_ru}?
usage_or_dosage → Как применяется {canonical_tag_ru}?
procedure_step → Какие этапы выполнения описаны для {canonical_tag_ru}?
preparation → Какая подготовка описана для {canonical_tag_ru}?
interpretation → Как интерпретируются результаты, связанные с {canonical_tag_ru}?
composition → Каков состав или компоненты {canonical_tag_ru}?
safety_warning → Какие меры безопасности описаны для {canonical_tag_ru}?
other → Что сказано о {canonical_tag_ru}?

If multiple fact groups have the same question text, add suffix based on section/fact type:

Что сказано о {canonical_tag_ru} в разделе «Диагностика»?

Do not generate questions for rejected/review-only quotes.

15. Article export index

Create:

data/articles/final_exports/article_export_index.jsonl
data/articles/final_exports/article_export_index.csv

One row per tag_id.

Fields:

tag_id
canonical_tag_ru
canonical_tag_latin
entity_type
article_status
source_stage
source_article_status
needs_review_before_publication
review_reasons
for_n8n_path
for_docs_path
for_docs_quotes_path
content_blocks_count
quotes_count
questions_count
source_documents_count
used_fact_groups_count
export_quality_status

Expected row count:

22 513
16. Quotes index

Create:

data/articles/final_exports/quotes_index.jsonl
data/articles/final_exports/quotes_index.csv

One row per companion file.

Fields:

tag_id
canonical_tag_ru
entity_type
quotes_path
questions_count
quotes_count
questions_generation_status
quotes_source_status
needs_review_before_publication

Expected row count:

22 513
17. Coverage audit

Create:

data/articles/final_exports/export_coverage_audit.json

Structure:

{
  "stage": "article_a5_final_export_assembly",
  "stage_version": "a5.0",

  "counts": {
    "final_tags_total": 22513,
    "for_n8n_article_files": 22513,
    "for_docs_article_files": 22513,
    "for_docs_quotes_files": 22513,

    "compiled_article": 2960,
    "compiled_with_review_flag": 6788,
    "direct_copy_article": 6806,
    "stub_only": 3839,
    "review_stub": 2017,
    "insufficient_evidence_review": 103,

    "missing_article_source": 0,
    "malformed_editorjs_repaired": 0
  },

  "quality": {
    "all_tags_exported_to_for_n8n": true,
    "all_tags_exported_to_for_docs": true,
    "all_for_docs_have_quotes_file": true,
    "no_duplicate_filenames": true,
    "all_articles_valid_editorjs": true,
    "article_export_index_complete": true,
    "quotes_index_complete": true,
    "passed": true
  }
}
18. Status distribution

Create:

data/articles/final_exports/status_distribution.csv

Fields:

article_status
count

Create:

data/articles/final_exports/entity_type_distribution.csv

Fields:

entity_type
article_status
count
19. Quality gates

A5 passes only if:

for_n8n contains exactly one article JSON per final tag_id
for_n8n has no subdirectories
for_docs contains exactly one article JSON per final tag_id
for_docs contains exactly one quotes JSON per final tag_id
article_export_index rows = final_tags_total
quotes_index rows = final_tags_total
no duplicate filenames
no missing tag_id
all exported article JSON are valid
all content_format = editorjs
all content.blocks exists
all for_docs quotes files valid JSON
export_coverage_audit.quality.passed = true

If any fail:

a5_report.quality.passed=false
runner exits non-zero
20. Important handling of review

A5 should not block export because of:

needs_review_before_publication=true
compiled_with_review_flag
review_stub
insufficient_evidence_review

These statuses must be exported.

The goal is not to hide review documents, but to keep them clearly marked.

For review documents:

needs_review_before_publication=true
review_reasons preserved
article_status preserved
21. Recommended code structure

Create package:

kb_rebuild/articles/a5/

Files:

kb_rebuild/articles/a5/__init__.py
kb_rebuild/articles/a5/models.py
kb_rebuild/articles/a5/loaders.py
kb_rebuild/articles/a5/source_selection.py
kb_rebuild/articles/a5/editorjs.py
kb_rebuild/articles/a5/quotes.py
kb_rebuild/articles/a5/exporter.py
kb_rebuild/articles/a5/report.py
kb_rebuild/articles/a5/runner.py

Purpose:

models.py           — constants/config/dataclasses
loaders.py          — load A1/A3/A4/final normalization artifacts
source_selection.py — choose final article source per tag_id
editorjs.py         — Editor.js validation and safe repair stub
quotes.py           — companion quotes/questions builder
exporter.py         — write for_n8n and for_docs files
report.py           — indexes/reports/audits
runner.py           — orchestration

Add CLI:

python -m kb_rebuild article-a5-export --data data

Flags:

--a1-dir data/articles/a1
--a3-dir data/articles/a3
--a4-dir data/articles/a4/production_v1
--entities-dir data/articles/entities
--normalization-final-dir data/normalization/final
--out data/articles/final_exports
--overwrite
--no-overwrite

Default:

out = data/articles/final_exports
22. Command to run A5

A5 is deterministic. It may run full production after tests.

.venv/bin/python -m kb_rebuild article-a5-export \
  --data data \
  --a1-dir data/articles/a1 \
  --a3-dir data/articles/a3 \
  --a4-dir data/articles/a4/production_v1 \
  --entities-dir data/articles/entities \
  --normalization-final-dir data/normalization/final \
  --out data/articles/final_exports \
  --overwrite
23. Tests

Add tests:

tests/test_article_a5_source_selection.py
tests/test_article_a5_editorjs.py
tests/test_article_a5_quotes.py
tests/test_article_a5_exporter.py
tests/test_article_a5_runner.py
tests/test_article_a5_report.py
23.1 Source selection tests
A4 compiled article wins over A1 source.
A1 direct_copy used when no A4 draft.
stub_only preserved.
review_stub preserved.
insufficient_evidence_review preserved.
missing source creates quality issue.
23.2 Editor.js tests
valid compiled Editor.js passes.
valid stub Editor.js passes.
malformed content creates safe repair stub.
no medical content invented during repair.
23.3 Quotes tests
compiled article creates quotes from used fact groups.
not_found/review_only fact groups not included.
direct copy creates empty companion with correct status.
stub creates empty companion with correct status.
deterministic questions generated from fact_type.
duplicate question text handled.
23.4 Exporter tests
for_n8n is flat.
for_docs grouped by entity_type.
every for_docs article has quotes companion.
filenames use tag_id.
no duplicate filenames.
23.5 Runner/report tests
creates all required outputs.
export index complete.
quotes index complete.
coverage audit passes.
quality fails when a tag is missing.
quality fails when for_n8n has subdirectories.

Run:

.venv/bin/python -m unittest discover -s tests

Compile:

.venv/bin/python -m py_compile \
  kb_rebuild/articles/a5/models.py \
  kb_rebuild/articles/a5/loaders.py \
  kb_rebuild/articles/a5/source_selection.py \
  kb_rebuild/articles/a5/editorjs.py \
  kb_rebuild/articles/a5/quotes.py \
  kb_rebuild/articles/a5/exporter.py \
  kb_rebuild/articles/a5/report.py \
  kb_rebuild/articles/a5/runner.py \
  kb_rebuild/cli.py
24. A5 report

Create:

data/articles/final_exports/a5_report.json

Structure:

{
  "stage": "article_a5_final_export_assembly",
  "stage_version": "a5.0",
  "created_at": "...",

  "input": {
    "a1_report": "data/articles/a1/a1_report.json",
    "a3_report": "data/articles/a3/a3_report.json",
    "a4_report": "data/articles/a4/production_v1/a4_report.json"
  },

  "counts": {
    "final_tags_total": 0,
    "for_n8n_article_files": 0,
    "for_docs_article_files": 0,
    "for_docs_quotes_files": 0,

    "compiled_article": 0,
    "compiled_with_review_flag": 0,
    "direct_copy_article": 0,
    "stub_only": 0,
    "review_stub": 0,
    "insufficient_evidence_review": 0,

    "questions_total": 0,
    "quotes_total": 0,

    "missing_article_source": 0,
    "malformed_editorjs_repaired": 0,
    "export_quality_issues": 0
  },

  "by_entity_type": {},
  "quality": {
    "all_tags_exported_to_for_n8n": true,
    "all_tags_exported_to_for_docs": true,
    "all_for_docs_have_quotes_file": true,
    "no_duplicate_filenames": true,
    "all_articles_valid_editorjs": true,
    "article_export_index_complete": true,
    "quotes_index_complete": true,
    "passed": true
  },

  "warnings": []
}
25. A5 manifest

Create:

data/articles/final_exports/a5_manifest.json

Must include:

{
  "stage": "article_a5_final_export_assembly",
  "stage_version": "a5.0",
  "created_at": "...",

  "inputs": {},
  "outputs": {
    "for_n8n_dir": "data/articles/final_exports/for_n8n",
    "for_docs_dir": "data/articles/final_exports/for_docs",
    "article_export_index_jsonl": "data/articles/final_exports/article_export_index.jsonl",
    "article_export_index_csv": "data/articles/final_exports/article_export_index.csv",
    "quotes_index_jsonl": "data/articles/final_exports/quotes_index.jsonl",
    "quotes_index_csv": "data/articles/final_exports/quotes_index.csv",
    "export_coverage_audit_json": "data/articles/final_exports/export_coverage_audit.json",
    "a5_report_json": "data/articles/final_exports/a5_report.json"
  }
}
26. Manual QA sample

Create:

data/articles/final_exports/manual_qa_export_sample.csv

Fields:

tag_id
canonical_tag_ru
entity_type
article_status
needs_review_before_publication
for_n8n_path
for_docs_path
quotes_path
content_blocks_count
questions_count
quotes_count
qa_excerpt

Include representative sample:

20 compiled_article
20 compiled_with_review_flag
20 direct_copy_article
20 stub_only
20 review_stub
all insufficient_evidence_review if <= 120
27. Feedback after A5

Create:

docs/article_a5_feedback.md

Feedback must include:

1. Что сделано.
2. Какие файлы изменены.
3. Какие команды запускались.
4. Tests passed.
5. final_tags_total.
6. for_n8n files count.
7. for_docs article files count.
8. for_docs quotes files count.
9. Counts by article_status.
10. Counts by entity_type.
11. questions_total.
12. quotes_total.
13. Coverage audit result.
14. Examples of for_n8n files.
15. Examples of for_docs files.
16. Examples of quotes companion files.
17. Any repaired malformed Editor.js.
18. Missing/quality issues.
19. What to pass to n8n.
20. What to pass to docs hierarchy stage.

Required lines:

Главный output для n8n:
data/articles/final_exports/for_n8n/

Главный output для docs:
data/articles/final_exports/for_docs/

Все 22 513 tag_id экспортированы: yes/no
28. Agent behavior

Before coding, create:

docs/article_a5_plan.md

Plan must include:

what was understood;
input layers;
source selection policy;
output folder design;
quotes companion design;
Editor.js validation;
coverage strategy;
tests;
risks;
checklist.

Agent must reread this instruction at:

after_plan
after_source_selection
after_editorjs_validation
after_quotes_builder
after_exporter
after_tests
before_production_run
before_feedback

Feedback must include:

ТЗ перечитано на этапах: after_plan, after_source_selection, after_editorjs_validation, after_quotes_builder, after_exporter, after_tests, before_production_run, before_feedback

If context is lost, reread:

instructions/current_a5_instruction.md
docs/article_a4_production_feedback.md
data/articles/a4/production_v1/a4_report.json
data/articles/a4/production_v1/a4_manifest.json
data/articles/a3/a3_report.json
data/articles/a1/a1_report.json
29. Главное напоминание

A5 must export everything.

A5 is not only about A4 compiled articles.

A5 must include:

A4 compiled articles
A1 direct-copy articles
A1 stubs
A1 review stubs
A3 insufficient evidence review entities

Final expected shape:

for_n8n/
  22 513 flat JSON files

for_docs/
  {entity_type}/
    {tag_id}.json
    {tag_id}_quotes.json

A5 should not hide review or stub documents. It should export them with clear status and review metadata.
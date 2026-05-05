# Normalization N1 Plan

## What I Understood

N1 is a deterministic normalization layer over the immutable tagging output. It reads active tagging artifacts, flattens entity mentions, creates reproducible normalized forms, builds only safe exact normalization auto-clusters, and writes reports under `data/normalization/`.

N1 must not call any LLM, alter `data/tagging/*`, create final canonical tags, create normalized document links, or perform fuzzy/semantic merge.

## Files To Create

- `kb_rebuild/normalization/__init__.py`
- `kb_rebuild/normalization/models.py`
- `kb_rebuild/normalization/text.py`
- `kb_rebuild/normalization/mentions.py`
- `kb_rebuild/normalization/auto_cluster.py`
- `kb_rebuild/normalization/report.py`
- `kb_rebuild/normalization/n1_runner.py`
- `tests/test_normalization_text.py`
- `tests/test_normalization_mentions.py`
- `tests/test_normalization_auto_cluster.py`
- `tests/test_normalization_n1_runner.py`
- `docs/normalization_n1_feedback.md`

## Files To Modify

- `kb_rebuild/cli.py` to add `normalize-n1`.

## Command Artifacts

The command will write these artifacts to `data/normalization/` by default:

- `tag_mentions_raw.jsonl`
- `tag_mentions_normalized.jsonl`
- `tags_raw.csv`
- `auto_clusters.jsonl`
- `auto_clusters.csv`
- `normalization_n1_report.json`
- `normalization_n1_manifest.json`
- `type_role_stats.csv`
- `suspicious_mentions.jsonl`
- `failed_documents_snapshot.jsonl`
- `quote_issue_mentions.jsonl`
- `article_candidate_mentions.jsonl`
- `context_only_mentions.jsonl`
- `top_aliases_by_type.csv`
- `top_canonical_candidates.csv`
- `invalid_tagging_records.jsonl`

## Deterministic Rules

- Basic text cleanup: NFKC, HTML unescape, trim, lowercase, `ё` to `е`, Greek symbols to Russian words, dash normalization, repeated whitespace collapse, spacing around hyphen and slash, outer quotes/brackets removal, trailing punctuation cleanup.
- `primary_norm`: use `canonical_candidate_ru` when present, otherwise `surface`; mark empty mentions suspicious.
- `drug_trade_name`: additionally compute `product_name_norm` by removing obvious dosage, package, and dosage-form tokens only when the remaining value stays usable.
- `supplement`: same conservative product cleanup for BAA/package markers.
- `drug_class`: normalize beta-lactam spelling through explicit rules only.
- `diagnostic_method`: add abbreviation candidates for known deterministic expansions but do not auto-merge abbreviation variants.
- `microorganism`: normalize common punctuation and flag latin genus-only strings.
- `disease`: keep specificity modifiers and flag them to avoid unsafe parent-child merges.

## Auto-Clustering Rules

- Cluster only inside the same `entity_type`.
- Use `entity_type::primary_norm` for most types.
- Use valid `product_name_norm` for `drug_trade_name` and `supplement`.
- Exclude or mark review for critical suspicious cases such as low confidence, quote issues, very short abbreviations, genus-only microorganism values, and disease specificity modifiers.
- Do not use fuzzy matching, edit distance, embeddings, or semantic synonym rules.

## Risks

- Product-name cleanup can be too aggressive for names that include form words as part of the brand.
- Abbreviations like `ИФА` and `ELISA` need N2/N3 validation before merge.
- Parent-child terms and disease modifiers require later candidate generation and validation.
- Quote validation issues should reduce automatic confidence but should not remove raw mentions.

## Explicit Non-Goals

- No Gemini/OpenRouter/LLM calls.
- No changes to `data/tagging/*`.
- No N2 candidate-pair generation.
- No N3 LLM cluster validation.
- No final `tags_canonical.csv`.
- No `document_tag_links_normalized.jsonl`.
- No recovery from `document_name` for empty documents.

## Checklist

- [x] Re-read N1 requirements after this plan.
- [x] Implement data models.
- [x] Implement deterministic text normalization.
- [x] Implement mention flattening and invalid-record capture.
- [x] Implement safe auto-clustering.
- [x] Implement report and CSV writers.
- [x] Add CLI command.
- [x] Add unit tests.
- [x] Run unit tests and py_compile.
- [x] Run N1 on `data`.
- [x] Verify generated artifacts and tagging input status.
- [x] Write feedback with metrics and risks.

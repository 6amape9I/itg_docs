from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Sequence

from kb_rebuild.articles.a1.models import A1Config
from kb_rebuild.articles.a1.runner import run_article_a1_bootstrap
from kb_rebuild.articles.a2.models import A2Config
from kb_rebuild.articles.a2.runner import run_article_a2_extraction
from kb_rebuild.articles.a3.models import A3Config
from kb_rebuild.articles.a3.runner import run_article_a3_grouping
from kb_rebuild.articles.planning.models import A0Config
from kb_rebuild.articles.planning.runner import run_article_planning_a0
from kb_rebuild.io.jsonl import write_jsonl
from kb_rebuild.llm.gemini_client import GeminiClient, GeminiError, load_dotenv_gemini_keys
from kb_rebuild.llm.models import (
    GEMINI_FLASH_TAGGING_MODEL,
    MODEL_ROLE_MAPPING,
    OPENROUTER_DEEPSEEK_FLASH,
    OPENROUTER_GEMINI_FLASH_TAGGING_MODEL,
    PRIMARY_TAGGING_MODEL,
    model_from_preset,
    model_from_role,
)
from kb_rebuild.llm.openrouter_client import OpenRouterClient, load_dotenv_openrouter_key
from kb_rebuild.llm.tagging_batch import BatchTaggingConfig, run_batch_tagging_calibration
from kb_rebuild.llm.tagging import TaggingConfig, run_tagging_calibration
from kb_rebuild.normalization.n1_runner import N1Config, run_normalization_n1
from kb_rebuild.normalization.n2.runner import N2Config, run_normalization_n2
from kb_rebuild.normalization.n3.runner import N3Config, run_normalization_n3
from kb_rebuild.normalization.n4.runner import N4Config, run_normalization_n4
from kb_rebuild.parsing.documents import parse_csv_documents
from kb_rebuild.parsing.validate import validate_parsed_artifacts
from kb_rebuild.reports.run_report import RunReport, write_run_report


LOGGER_NAME = "kb_rebuild"


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kb_rebuild")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_parser = subparsers.add_parser("parse", help="Parse documents.csv into JSONL artifacts")
    parse_parser.add_argument("--input", required=True, help="Path to documents.csv")
    parse_parser.add_argument("--out", default="data", help="Output data directory")
    parse_parser.add_argument("--limit", type=_positive_int, default=None, help="Limit documents for dry-run")
    parse_parser.set_defaults(func=run_parse)

    validate_parser = subparsers.add_parser("validate-parsed", help="Validate parsed JSONL artifacts")
    validate_parser.add_argument("--data", default="data", help="Data directory with parsed artifacts")
    validate_parser.add_argument("--input", default=None, help="Optional source CSV for row count validation")
    validate_parser.add_argument("--expected-docs", type=_non_negative_int, default=None)
    validate_parser.set_defaults(func=run_validate_parsed)

    tag_parser = subparsers.add_parser("tag", help="Run controlled LLM document tagging calibration")
    tag_parser.add_argument("--data", default="data", help="Data directory with parsed artifacts")
    tag_parser.add_argument("--limit", type=_positive_int, default=100, help="Limit documents for calibration")
    tag_parser.add_argument("--model", default=OPENROUTER_DEEPSEEK_FLASH, help="Stable OpenRouter legacy model id")
    tag_parser.add_argument("--primary-model", default=None, help="Alias for --model in Gemini/hybrid commands")
    tag_parser.add_argument("--model-preset", choices=("deepseek-flash", "gemini-flash"), default=None)
    tag_parser.add_argument("--fallback-model", default="none", help="Stable fallback OpenRouter model id, or none")
    tag_parser.add_argument("--max-cost-usd", type=_non_negative_float, default=5.0, help="Hard calibration budget limit")
    tag_parser.add_argument("--max-retries", type=_non_negative_int, default=2, help="Retries per model")
    tag_parser.add_argument("--prompt-char-limit", type=_positive_int, default=16000, help="Max clean_text chars sent to LLM")
    tag_parser.add_argument("--max-output-tokens", type=_positive_int, default=3200)
    tag_parser.add_argument("--provider-sort", choices=("throughput", "price"), default="throughput")
    tag_parser.add_argument("--timeout-seconds", type=_positive_int, default=120)
    tag_parser.add_argument("--request-delay-seconds", type=_non_negative_float, default=2.0)
    tag_parser.add_argument("--rate-limit-backoff-seconds", type=_non_negative_float, default=30.0)
    tag_parser.add_argument("--experiment-name", default=None, help="Write isolated outputs under data/tagging/experiments/{name}")
    tag_parser.add_argument("--structured-output-mode", choices=("strict", "schema_lite", "prompt_json"), default="strict")
    tag_parser.add_argument("--schema-version", choices=("document_tagging_v2", "compact_tagging_v2"), default="document_tagging_v2")
    tag_parser.add_argument("--prompt-version", choices=("tagging_v2", "tagging_v2_compact"), default="tagging_v2")
    tag_parser.add_argument("--tagging-text-mode", choices=("full", "compact"), default="full")
    tag_parser.add_argument("--tagging-char-limit", type=_positive_int, default=8000)
    tag_parser.add_argument("--routing-strategy", choices=("single", "manual_fallback", "openrouter_models"), default="single")
    tag_parser.add_argument("--fallback-on-status", default="429")
    tag_parser.add_argument("--primary-max-retries", type=_non_negative_int, default=None)
    tag_parser.add_argument("--fallback-max-retries", type=_non_negative_int, default=None)
    tag_parser.add_argument("--primary-cooldown-after-429-seconds", type=_non_negative_float, default=300.0)
    tag_parser.add_argument("--primary-timeout-seconds", type=_positive_int, default=None)
    tag_parser.add_argument("--fallback-timeout-seconds", type=_positive_int, default=None)
    tag_parser.add_argument("--retry-failures", action="store_true", help="Resume successes but retry previous failures")
    tag_parser.add_argument("--use-api-key-list", action="store_true", help="Rotate keys from OPENROUTER_API_KEY_LIST")
    tag_parser.add_argument(
        "--parallel-workers",
        type=_positive_int,
        default=1,
        help="Run several sequential workers in parallel; intended for OPENROUTER_API_KEY_LIST",
    )
    tag_parser.add_argument("--no-resume", action="store_true", help="Do not skip already written tagging records")
    tag_parser.set_defaults(func=run_tag)

    tag_batch_parser = subparsers.add_parser("tag-batch", help="Run active-only batch LLM document tagging calibration")
    tag_batch_parser.add_argument("--data", default="data", help="Data directory with parsed artifacts")
    tag_batch_parser.add_argument("--limit", type=_positive_int, default=100, help="Limit documents for calibration")
    tag_batch_parser.add_argument("--provider", choices=("gemini_direct", "openrouter"), default="gemini_direct")
    tag_batch_parser.add_argument("--batch-size", type=_positive_int, default=5)
    tag_batch_parser.add_argument("--batch-char-limit", type=_positive_int, default=50000)
    tag_batch_parser.add_argument("--prompt-char-limit-per-doc", type=_positive_int, default=16000)
    tag_batch_parser.add_argument("--model", default=GEMINI_FLASH_TAGGING_MODEL, help="Stable model id for selected provider")
    tag_batch_parser.add_argument("--primary-model", default=None, help="Alias for --model in Gemini/hybrid commands")
    tag_batch_parser.add_argument("--model-role", choices=tuple(sorted(MODEL_ROLE_MAPPING)), default=None)
    tag_batch_parser.add_argument("--model-preset", choices=("deepseek-flash", "gemini-flash"), default=None)
    tag_batch_parser.add_argument("--fallback-model", default="none", help="Stable fallback OpenRouter model id, or none")
    tag_batch_parser.add_argument("--max-cost-usd", type=_non_negative_float, default=5.0, help="Hard calibration budget limit")
    tag_batch_parser.add_argument("--max-retries", type=_non_negative_int, default=3, help="Retries per batch/model")
    tag_batch_parser.add_argument("--max-output-tokens", type=_positive_int, default=6000)
    tag_batch_parser.add_argument("--provider-sort", choices=("throughput", "price"), default="throughput")
    tag_batch_parser.add_argument("--timeout-seconds", type=_non_negative_int, default=0, help="0 disables urllib timeout")
    tag_batch_parser.add_argument("--max-inflight", type=_positive_int, default=1)
    tag_batch_parser.add_argument("--min-request-interval-seconds", type=_non_negative_float, default=5.0)
    tag_batch_parser.add_argument("--rate-limit-backoff-seconds", type=_non_negative_float, default=120.0)
    tag_batch_parser.add_argument("--max-rate-limit-backoff-seconds", type=_non_negative_float, default=300.0)
    tag_batch_parser.add_argument("--retry-failures", action="store_true", help="Resume successes but retry previous failures")
    tag_batch_parser.add_argument("--experiment-name", default=None, help="Write isolated outputs under data/experiments/{name}")
    tag_batch_parser.add_argument(
        "--structured-output-mode",
        choices=("strict", "schema_lite", "prompt_json", "gemini_schema", "gemini_schema_lite"),
        default="gemini_schema",
    )
    tag_batch_parser.add_argument("--schema-version", choices=("document_tagging_v2", "compact_tagging_v2"), default="document_tagging_v2")
    tag_batch_parser.add_argument(
        "--prompt-version",
        choices=("tagging_v2", "tagging_v2_compact", "tagging_v2_gemini"),
        default="tagging_v2_gemini",
    )
    tag_batch_parser.add_argument("--tagging-text-mode", choices=("full", "compact"), default="full")
    tag_batch_parser.add_argument("--tagging-char-limit", type=_positive_int, default=8000)
    tag_batch_parser.add_argument("--thinking-level", choices=("minimal", "low", "medium", "high"), default=None)
    tag_batch_parser.add_argument("--thinking-budget", type=int, default=None)
    tag_batch_parser.add_argument("--routing-strategy", choices=("single", "manual_fallback", "openrouter_models"), default="single")
    tag_batch_parser.add_argument("--fallback-on-status", default="429")
    tag_batch_parser.add_argument("--primary-max-retries", type=_non_negative_int, default=None)
    tag_batch_parser.add_argument("--fallback-max-retries", type=_non_negative_int, default=None)
    tag_batch_parser.add_argument("--primary-cooldown-after-429-seconds", type=_non_negative_float, default=300.0)
    tag_batch_parser.add_argument("--primary-timeout-seconds", type=_positive_int, default=None)
    tag_batch_parser.add_argument("--fallback-timeout-seconds", type=_positive_int, default=None)
    tag_batch_parser.add_argument("--use-api-key-list", action="store_true", help="Rotate keys from OPENROUTER_API_KEY_LIST")
    tag_batch_parser.add_argument("--no-resume", action="store_true", help="Do not skip already written active records")
    tag_batch_parser.set_defaults(func=run_tag_batch)

    gemini_models_parser = subparsers.add_parser("gemini-list-models", help="Discover direct Gemini models")
    gemini_models_parser.add_argument("--data", default="data", help="Data directory for report artifacts")
    gemini_models_parser.add_argument("--timeout-seconds", type=_non_negative_int, default=0, help="0 disables urllib timeout")
    gemini_models_parser.set_defaults(func=run_gemini_list_models)

    normalize_n1_parser = subparsers.add_parser("normalize-n1", help="Run deterministic N1 tag normalization")
    normalize_n1_parser.add_argument("--data", default="data", help="Data directory with tagging artifacts")
    normalize_n1_parser.add_argument("--tagging-active-path", default=None, help="Path to active tagging success JSONL")
    normalize_n1_parser.add_argument("--failures-path", default=None, help="Path to active tagging failures JSONL")
    normalize_n1_parser.add_argument("--empty-candidates-path", default=None, help="Path to empty document candidates JSONL")
    normalize_n1_parser.add_argument("--out", default=None, help="Output normalization directory")
    normalize_n1_parser.add_argument("--min-mentions-for-report", type=_positive_int, default=1)
    normalize_n1_parser.add_argument("--no-overwrite", action="store_true", help="Fail if any N1 output already exists")
    normalize_n1_parser.set_defaults(func=run_normalize_n1)

    normalize_n2_parser = subparsers.add_parser("normalize-n2", help="Run N2 normalization candidate generation")
    normalize_n2_parser.add_argument("--data", default="data", help="Data directory")
    normalize_n2_parser.add_argument("--normalization-dir", default=None, help="N1.1 normalization output directory")
    normalize_n2_parser.add_argument("--out", default=None, help="N2 output directory")
    normalize_n2_parser.add_argument("--min-score", type=_score_float, default=0.72)
    normalize_n2_parser.add_argument("--high-priority-score", type=_score_float, default=0.88)
    normalize_n2_parser.add_argument("--max-pairs-per-type", type=_positive_int, default=50000)
    normalize_n2_parser.set_defaults(func=run_normalize_n2)

    normalize_n3_parser = subparsers.add_parser("normalize-n3", help="Run N3 LLM validation for N2 candidate groups")
    normalize_n3_parser.add_argument("--data", default="data", help="Data directory")
    normalize_n3_parser.add_argument("--normalization-dir", default=None, help="Normalization output directory")
    normalize_n3_parser.add_argument("--n2-dir", default=None, help="N2 candidate-generation output directory")
    normalize_n3_parser.add_argument("--out", default=None, help="N3 output directory")
    normalize_n3_parser.add_argument("--provider", choices=("gemini_direct",), default="gemini_direct")
    normalize_n3_parser.add_argument("--model", default="gemini-3-flash-preview")
    normalize_n3_parser.add_argument("--batch-size", type=_positive_int, default=1)
    normalize_n3_parser.add_argument("--max-inflight", type=_positive_int, default=8)
    normalize_n3_parser.add_argument("--max-retries", type=_non_negative_int, default=3)
    normalize_n3_parser.add_argument("--max-cost-usd", type=_non_negative_float, default=20.0)
    normalize_n3_parser.add_argument(
        "--structured-output-mode",
        choices=("gemini_schema", "gemini_schema_lite", "prompt_json"),
        default="gemini_schema",
    )
    normalize_n3_parser.add_argument("--enable-web-review", action="store_true")
    normalize_n3_parser.add_argument("--web-review-model", default="gemini-2.5-flash")
    normalize_n3_parser.add_argument("--web-review-limit", type=_positive_int, default=50)
    normalize_n3_parser.add_argument("--max-output-tokens", type=_positive_int, default=6000)
    normalize_n3_parser.add_argument("--repair-max-output-tokens", type=_positive_int, default=12000)
    normalize_n3_parser.add_argument("--thinking-level", choices=("minimal", "low", "medium", "high", "none"), default="minimal")
    normalize_n3_parser.add_argument("--no-overwrite", action="store_true")
    normalize_n3_parser.set_defaults(func=run_normalize_n3)

    normalize_n4_parser = subparsers.add_parser("normalize-n4", help="Run N4 final canonical normalization layer")
    normalize_n4_parser.add_argument("--data", default="data", help="Data directory")
    normalize_n4_parser.add_argument("--normalization-dir", default=None, help="Normalization output directory")
    normalize_n4_parser.add_argument("--n2-dir", default=None, help="N2 candidate-generation output directory")
    normalize_n4_parser.add_argument("--n3-dir", default=None, help="N3 LLM-validation output directory")
    normalize_n4_parser.add_argument("--out", default=None, help="N4 final output directory")
    normalize_n4_parser.add_argument("--review-sample-size", type=_non_negative_int, default=500)
    normalize_n4_parser.set_defaults(func=run_normalize_n4)

    article_plan_a0_parser = subparsers.add_parser("article-plan-a0", help="Build deterministic article source windows and work plan")
    article_plan_a0_parser.add_argument("--data", default="data", help="Data directory")
    article_plan_a0_parser.add_argument("--normalization-final-dir", default=None, help="N4 final normalization directory")
    article_plan_a0_parser.add_argument("--parsed-dir", default=None, help="Parsed document artifacts directory")
    article_plan_a0_parser.add_argument("--normalization-dir", default=None, help="Normalization directory with mention context")
    article_plan_a0_parser.add_argument("--out", default=None, help="Article planning output directory")
    article_plan_a0_parser.add_argument("--max-neighbor-blocks", type=_non_negative_int, default=2)
    article_plan_a0_parser.add_argument("--max-window-chars", type=_positive_int, default=12000)
    article_plan_a0_parser.add_argument("--short-document-char-limit", type=_positive_int, default=12000)
    article_plan_a0_parser.add_argument("--high-frequency-doc-threshold", type=_positive_int, default=20)
    article_plan_a0_parser.add_argument("--low-count-doc-threshold", type=_positive_int, default=3)
    article_plan_a0_parser.add_argument("--review-sample-size", type=_non_negative_int, default=500)
    article_plan_a0_parser.add_argument("--no-overwrite", action="store_true")
    article_plan_a0_parser.set_defaults(func=run_article_plan_a0)

    article_a1_parser = subparsers.add_parser("article-a1-bootstrap", help="Build A1 entity JSON/status layer and A2 task queue")
    article_a1_parser.add_argument("--data", default="data", help="Data directory")
    article_a1_parser.add_argument("--articles-planning-dir", default=None, help="A0 article planning output directory")
    article_a1_parser.add_argument("--normalization-final-dir", default=None, help="N4 final normalization directory")
    article_a1_parser.add_argument("--parsed-dir", default=None, help="Parsed document artifacts directory")
    article_a1_parser.add_argument("--out", default=None, help="A1 output directory")
    article_a1_parser.add_argument("--entities-out", default=None, help="Entity JSON output directory")
    article_a1_parser.add_argument("--review-sample-size", type=_non_negative_int, default=500)
    article_a1_parser.add_argument("--low-count-doc-threshold", type=_positive_int, default=3)
    article_a1_parser.add_argument("--high-frequency-doc-threshold", type=_positive_int, default=20)
    article_a1_parser.add_argument("--no-overwrite", action="store_true")
    article_a1_parser.set_defaults(func=run_article_a1)

    article_a2_parser = subparsers.add_parser("article-a2-extract", help="Extract A2 evidence items from A1 source windows")
    article_a2_parser.add_argument("--data", default="data", help="Data directory")
    article_a2_parser.add_argument("--a1-dir", default=None, help="A1 output directory")
    article_a2_parser.add_argument("--planning-dir", default=None, help="A0 article planning output directory")
    article_a2_parser.add_argument("--normalization-final-dir", default=None, help="N4 final normalization directory")
    article_a2_parser.add_argument("--out", default=None, help="A2 output directory")
    article_a2_parser.add_argument("--provider", choices=("gemini_direct",), default="gemini_direct")
    article_a2_parser.add_argument("--model", default="gemini-3-flash-preview")
    article_a2_parser.add_argument(
        "--structured-output-mode",
        choices=("gemini_schema", "gemini_schema_lite", "prompt_json"),
        default="gemini_schema",
    )
    article_a2_parser.add_argument("--limit", type=_positive_int, default=None)
    article_a2_parser.add_argument("--task-filter", choices=("all", "pending_review"), default="all")
    article_a2_parser.add_argument(
        "--strategy-filter",
        default="single_doc_extract,low_count_batch_extract,multi_doc_map_reduce,high_frequency_map_reduce",
    )
    article_a2_parser.add_argument("--priority-filter", default="high,medium,low")
    article_a2_parser.add_argument("--max-tasks-per-batch", type=_positive_int, default=8)
    article_a2_parser.add_argument("--batch-char-limit", type=_positive_int, default=60000)
    article_a2_parser.add_argument("--max-inflight", type=_positive_int, default=8)
    article_a2_parser.add_argument("--max-retries", type=_non_negative_int, default=3)
    article_a2_parser.add_argument("--max-output-tokens", type=_positive_int, default=12000)
    article_a2_parser.add_argument("--repair-max-output-tokens", type=_positive_int, default=24000)
    article_a2_parser.add_argument("--thinking-level", choices=("minimal", "low", "medium", "high", "none"), default="minimal")
    article_a2_parser.add_argument("--max-cost-usd", type=_non_negative_float, default=20.0)
    article_a2_parser.add_argument("--retry-failures", action="store_true")
    article_a2_parser.add_argument("--no-resume", action="store_true")
    article_a2_parser.add_argument("--experiment-name", default=None)
    article_a2_parser.set_defaults(func=run_article_a2)

    article_a3_parser = subparsers.add_parser("article-a3-group-evidence", help="Group A2 evidence items into A3 fact groups")
    article_a3_parser.add_argument("--data", default="data", help="Data directory")
    article_a3_parser.add_argument("--a2-dir", default=None, help="A2 production output directory")
    article_a3_parser.add_argument("--a1-dir", default=None, help="A1 output directory")
    article_a3_parser.add_argument("--normalization-final-dir", default=None, help="N4 final normalization directory")
    article_a3_parser.add_argument("--out", default=None, help="A3 output directory")
    article_a3_parser.add_argument("--min-confidence", type=_score_float, default=0.5)
    article_a3_parser.add_argument("--allow-fuzzy-for-review", action="store_true", default=True)
    article_a3_parser.add_argument("--max-quotes-per-fact-group", type=_positive_int, default=8)
    article_a3_parser.add_argument("--max-fact-groups-per-tag", type=_positive_int, default=200)
    article_a3_parser.add_argument("--no-overwrite", action="store_true")
    article_a3_parser.set_defaults(func=run_article_a3)

    return parser


def run_parse(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    out_dir = Path(args.out)
    logger = configure_logging(out_dir)
    logger.info("parse stage started")
    logger.info("input_file=%s output_dir=%s limit=%s", input_path, out_dir, args.limit)

    if not input_path.exists():
        logger.error("input CSV not found: %s", input_path)
        print(f"Input CSV not found: {input_path}")
        return 2

    try:
        documents, blocks, duplicate_doc_ids, errors = parse_csv_documents(input_path, limit=args.limit)
    except Exception as exc:
        logger.exception("parse stage failed before artifact write")
        print(f"Parse failed: {exc}")
        return 1

    parsed_dir = out_dir / "parsed"
    reports_dir = out_dir / "reports"
    parsed_documents_path = parsed_dir / "parsed_documents.jsonl"
    document_blocks_path = parsed_dir / "document_blocks.jsonl"
    run_report_path = reports_dir / "run_report.json"

    write_jsonl(parsed_documents_path, (document.to_dict() for document in documents))
    write_jsonl(document_blocks_path, (block.to_dict() for block in blocks))

    report = RunReport.from_documents(
        documents=documents,
        duplicate_doc_ids=duplicate_doc_ids,
        errors=errors,
        input_file=input_path,
        output_dir=out_dir,
        limit=args.limit,
    )
    write_run_report(run_report_path, report)

    logger.info("parsed_documents=%s document_blocks=%s", len(documents), len(blocks))
    logger.info("parse_errors=%s duplicate_doc_ids=%s", len(errors), duplicate_doc_ids)
    logger.info("parsed output=%s blocks output=%s report=%s", parsed_documents_path, document_blocks_path, run_report_path)
    logger.info("parse stage finished")

    print(
        "Parse complete: "
        f"documents={len(documents)} blocks={len(blocks)} "
        f"errors={len(errors)} out={out_dir}"
    )
    return 0


def run_validate_parsed(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    input_path = Path(args.input) if args.input else None
    result = validate_parsed_artifacts(
        data_dir=data_dir,
        input_path=input_path,
        expected_docs=args.expected_docs,
    )

    print(
        "Parsed artifact validation: "
        f"{'ok' if result.ok else 'failed'} "
        f"documents={result.stats.get('documents_count', 0)} "
        f"blocks={result.stats.get('blocks_count', 0)}"
    )
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")
    return 0 if result.ok else 1


def run_tag(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    logger = configure_logging(data_dir)
    logger.info("tagging calibration started")
    logger.info(
        "data_dir=%s limit=%s model=%s fallback_model=%s max_cost_usd=%s",
        data_dir,
        args.limit,
        args.model,
        args.fallback_model,
        args.max_cost_usd,
    )

    load_dotenv_openrouter_key(Path(".env"))
    model = model_from_preset(args.model_preset, args.primary_model or args.model)
    fallback_model = _parse_optional_model(args.fallback_model)
    if args.experiment_name:
        config = BatchTaggingConfig(
            data_dir=data_dir,
            limit=args.limit,
            model=model,
            fallback_model=fallback_model,
            max_cost_usd=args.max_cost_usd,
            max_retries=args.max_retries,
            batch_size=1,
            batch_char_limit=args.prompt_char_limit,
            prompt_char_limit_per_doc=args.prompt_char_limit,
            max_output_tokens=args.max_output_tokens,
            provider_sort=args.provider_sort,
            resume=not args.no_resume,
            retry_failures=args.retry_failures,
            max_inflight=1,
            min_request_interval_seconds=args.request_delay_seconds,
            rate_limit_backoff_seconds=args.rate_limit_backoff_seconds,
            max_rate_limit_backoff_seconds=max(args.rate_limit_backoff_seconds, args.rate_limit_backoff_seconds * 2),
            structured_output_mode=args.structured_output_mode,
            experiment_name=args.experiment_name,
            prompt_version=args.prompt_version,
            output_schema_version=args.schema_version,
            tagging_text_mode=args.tagging_text_mode,
            tagging_char_limit=args.tagging_char_limit,
        )
        try:
            client = OpenRouterClient(
                timeout_seconds=args.timeout_seconds,
                use_api_key_list=args.use_api_key_list,
            )
            report = run_batch_tagging_calibration(config=config, client=client, logger=logger)
        except Exception as exc:
            logger.exception("one-doc experiment tagging failed before report write")
            print(f"Tagging failed: {exc}")
            return 1
        print(
            "Tagging calibration complete: "
            f"tagged={report.get('documents_tagged', 0)} "
            f"failed={report.get('documents_failed', 0)} "
            f"cost=${report.get('estimated_cost_usd', 0.0)} "
            f"api_attempts={report.get('llm_api_attempts_total', 0)} "
            f"cache_hits={report.get('cache_hits', 0)} "
            f"cache_misses={report.get('cache_misses', 0)}"
        )
        return 0

    config = TaggingConfig(
        data_dir=data_dir,
        limit=args.limit,
        model=model,
        fallback_model=fallback_model,
        max_cost_usd=args.max_cost_usd,
        max_retries=args.max_retries,
        prompt_char_limit=args.prompt_char_limit,
        max_output_tokens=args.max_output_tokens,
        provider_sort=args.provider_sort,
        resume=not args.no_resume,
        retry_failures=args.retry_failures,
        request_delay_seconds=args.request_delay_seconds,
        rate_limit_backoff_seconds=args.rate_limit_backoff_seconds,
        parallel_workers=args.parallel_workers,
    )
    try:
        client = OpenRouterClient(
            timeout_seconds=args.timeout_seconds,
            use_api_key_list=args.use_api_key_list or args.parallel_workers > 1,
        )
        if args.parallel_workers > 1 and client.api_keys_count < 2:
            raise ValueError("--parallel-workers > 1 requires OPENROUTER_API_KEY_LIST with at least two keys")
        if args.use_api_key_list:
            logger.info("OpenRouter key rotation enabled key_count=%s", client.api_keys_count)
        if args.parallel_workers > 1:
            logger.info("OpenRouter parallel workers requested=%s key_count=%s", args.parallel_workers, client.api_keys_count)
        report = run_tagging_calibration(
            config=config,
            client=client,
            logger=logger,
        )
    except Exception as exc:
        logger.exception("tagging calibration failed before report write")
        print(f"Tagging failed: {exc}")
        return 1

    logger.info(
        "tagging calibration finished documents_tagged=%s documents_failed=%s cost=%s",
        report.get("documents_tagged", 0),
        report.get("documents_failed", 0),
        report.get("estimated_cost_usd", 0.0),
    )
    print(
        "Tagging calibration complete: "
        f"tagged={report.get('documents_tagged', 0)} "
        f"failed={report.get('documents_failed', 0)} "
        f"cost=${report.get('estimated_cost_usd', 0.0)} "
        f"cache_hits={report.get('cache_hits', 0)} "
        f"cache_misses={report.get('cache_misses', 0)}"
    )
    if report.get("stop_reason"):
        print(f"Stopped: {report['stop_reason']}")
    return 0


def run_tag_batch(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    logger = configure_logging(data_dir)
    logger.info("batch tagging calibration started")
    logger.info(
        "data_dir=%s limit=%s provider=%s batch_size=%s model=%s fallback_model=%s max_cost_usd=%s experiment=%s mode=%s",
        data_dir,
        args.limit,
        args.provider,
        args.batch_size,
        args.model,
        args.fallback_model,
        args.max_cost_usd,
        args.experiment_name,
        args.structured_output_mode,
    )

    if args.provider == "gemini_direct":
        load_dotenv_gemini_keys(Path(".env"))
    else:
        load_dotenv_openrouter_key(Path(".env"))
    model = model_from_preset(args.model_preset, args.primary_model or args.model)
    model = model_from_role(args.model_role, model)
    structured_output_mode = args.structured_output_mode
    prompt_version = args.prompt_version
    if args.provider == "openrouter":
        if model == GEMINI_FLASH_TAGGING_MODEL:
            model = OPENROUTER_GEMINI_FLASH_TAGGING_MODEL
        if structured_output_mode in {"gemini_schema", "gemini_schema_lite"}:
            structured_output_mode = "strict"
        if prompt_version == "tagging_v2_gemini":
            prompt_version = "tagging_v2"
    config = BatchTaggingConfig(
        data_dir=data_dir,
        limit=args.limit,
        provider=args.provider,
        model=model,
        model_role=args.model_role,
        fallback_model=_parse_optional_model(args.fallback_model),
        max_cost_usd=args.max_cost_usd,
        max_retries=args.max_retries,
        batch_size=args.batch_size,
        batch_char_limit=args.batch_char_limit,
        prompt_char_limit_per_doc=args.prompt_char_limit_per_doc,
        max_output_tokens=args.max_output_tokens,
        provider_sort=args.provider_sort,
        resume=not args.no_resume,
        retry_failures=args.retry_failures,
        max_inflight=args.max_inflight,
        min_request_interval_seconds=args.min_request_interval_seconds,
        rate_limit_backoff_seconds=args.rate_limit_backoff_seconds,
        max_rate_limit_backoff_seconds=args.max_rate_limit_backoff_seconds,
        structured_output_mode=structured_output_mode,
        experiment_name=args.experiment_name,
        prompt_version=prompt_version,
        output_schema_version=args.schema_version,
        tagging_text_mode=args.tagging_text_mode,
        tagging_char_limit=args.tagging_char_limit,
        thinking_level=args.thinking_level,
        thinking_budget=args.thinking_budget,
    )
    try:
        if args.provider == "gemini_direct":
            client = GeminiClient(
                timeout_seconds=_optional_timeout_seconds(args.timeout_seconds),
                rate_limit_backoff_seconds=args.rate_limit_backoff_seconds,
                max_rate_limit_backoff_seconds=args.max_rate_limit_backoff_seconds,
            )
            logger.info("Gemini direct key rotation enabled key_count=%s", client.api_keys_count)
        else:
            client = OpenRouterClient(
                timeout_seconds=args.timeout_seconds,
                use_api_key_list=args.use_api_key_list,
            )
            if args.use_api_key_list:
                logger.info("OpenRouter key rotation enabled key_count=%s", client.api_keys_count)
        report = run_batch_tagging_calibration(
            config=config,
            client=client,
            logger=logger,
        )
    except Exception as exc:
        logger.exception("batch tagging calibration failed before report write")
        print(f"Batch tagging failed: {exc}")
        return 1

    logger.info(
        "batch tagging calibration finished documents_tagged=%s documents_failed=%s cost=%s status_counts=%s",
        report.get("documents_tagged", 0),
        report.get("documents_failed", 0),
        report.get("estimated_cost_usd", 0.0),
        report.get("http_status_counts", {}),
    )
    print(
        "Batch tagging calibration complete: "
        f"tagged={report.get('documents_tagged', 0)} "
        f"failed={report.get('documents_failed', 0)} "
        f"cost=${report.get('estimated_cost_usd', 0.0)} "
        f"api_attempts={report.get('llm_api_attempts_total', 0)} "
        f"cache_hits={report.get('cache_hits', 0)} "
        f"cache_misses={report.get('cache_misses', 0)}"
    )
    if report.get("stop_reason"):
        print(f"Stopped: {report['stop_reason']}")
    return 0


def run_gemini_list_models(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    logger = configure_logging(data_dir)
    logger.info("Gemini model discovery started")
    load_dotenv_gemini_keys(Path(".env"))
    client = GeminiClient(timeout_seconds=_optional_timeout_seconds(args.timeout_seconds))
    try:
        raw = client.list_models()
    except GeminiError as exc:
        logger.exception("Gemini model discovery failed")
        print(f"Gemini model discovery failed: {exc}")
        return 1

    reports_dir = data_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    raw_path = reports_dir / "gemini_models.json"
    with raw_path.open("w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    docs_dir = Path("docs")
    docs_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = docs_dir / "gemini_available_models.md"
    markdown_path.write_text(_gemini_models_markdown(raw, client), encoding="utf-8")

    models = raw.get("models", [])
    models_count = len(models) if isinstance(models, list) else 0
    logger.info("Gemini model discovery finished models=%s raw=%s markdown=%s", models_count, raw_path, markdown_path)
    print(f"Gemini model discovery complete: models={models_count} raw={raw_path} report={markdown_path}")
    return 0


def run_normalize_n1(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    logger = configure_logging(data_dir)
    config = N1Config.from_data_dir(
        data_dir,
        tagging_active_path=Path(args.tagging_active_path) if args.tagging_active_path else None,
        failures_path=Path(args.failures_path) if args.failures_path else None,
        empty_candidates_path=Path(args.empty_candidates_path) if args.empty_candidates_path else None,
        out_dir=Path(args.out) if args.out else None,
        min_mentions_for_report=args.min_mentions_for_report,
        overwrite=not args.no_overwrite,
    )
    logger.info(
        "normalization N1 started data_dir=%s tagging_active=%s failures=%s empty_candidates=%s out=%s",
        config.data_dir,
        config.tagging_active_path,
        config.failures_path,
        config.empty_candidates_path,
        config.out_dir,
    )
    try:
        report = run_normalization_n1(config)
    except Exception as exc:
        logger.exception("normalization N1 failed")
        print(f"Normalization N1 failed: {exc}")
        return 1

    counts = report.get("counts", {})
    logger.info("normalization N1 finished counts=%s", counts)
    print(
        "Normalization N1 complete: "
        f"mentions={counts.get('mentions_total', 0)} "
        f"unique_norm={counts.get('unique_normalized_values', 0)} "
        f"auto_clusters={counts.get('auto_clusters_total', 0)} "
        f"review_required={counts.get('auto_clusters_review_required', 0)} "
        f"suspicious={counts.get('suspicious_mentions', 0)} "
        f"out={config.out_dir}"
    )
    warnings = report.get("warnings", [])
    for warning in warnings[:10]:
        print(f"WARNING: {warning}")
    if len(warnings) > 10:
        print(f"WARNING: {len(warnings) - 10} more warnings in normalization_n1_report.json")
    return 0


def run_normalize_n2(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    logger = configure_logging(data_dir)
    config = N2Config.from_data_dir(
        data_dir,
        normalization_dir=Path(args.normalization_dir) if args.normalization_dir else None,
        out_dir=Path(args.out) if args.out else None,
        min_score=args.min_score,
        high_priority_score=args.high_priority_score,
        max_pairs_per_type=args.max_pairs_per_type,
    )
    logger.info(
        "normalization N2 started data_dir=%s normalization_dir=%s out=%s min_score=%s high_priority_score=%s max_pairs_per_type=%s",
        config.data_dir,
        config.normalization_dir,
        config.out_dir,
        config.min_score,
        config.high_priority_score,
        config.max_pairs_per_type,
    )
    try:
        report = run_normalization_n2(config)
    except Exception as exc:
        logger.exception("normalization N2 failed")
        print(f"Normalization N2 failed: {exc}")
        return 1

    counts = report.get("counts", {})
    logger.info("normalization N2 finished counts=%s", counts)
    print(
        "Normalization N2 complete: "
        f"nodes={counts.get('nodes_total', 0)} "
        f"candidate_pairs={counts.get('candidate_pairs_total', 0)} "
        f"blocked_pairs={counts.get('blocked_pairs', 0)} "
        f"rejected_pairs={counts.get('rejected_low_score_pairs', 0)} "
        f"groups={counts.get('candidate_groups_total', 0)} "
        f"n3_groups={counts.get('n3_candidate_groups', 0)} "
        f"high_groups={counts.get('high_priority_groups', 0)} "
        f"out={config.out_dir}"
    )
    warnings = report.get("warnings", [])
    for warning in warnings[:10]:
        print(f"WARNING: {warning}")
    if len(warnings) > 10:
        print(f"WARNING: {len(warnings) - 10} more warnings in candidate_generation_report.json")
    return 0


def run_normalize_n3(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    logger = configure_logging(data_dir)
    load_dotenv_gemini_keys(Path(".env"))
    config = N3Config.from_data_dir(
        data_dir,
        normalization_dir=Path(args.normalization_dir) if args.normalization_dir else None,
        n2_dir=Path(args.n2_dir) if args.n2_dir else None,
        out_dir=Path(args.out) if args.out else None,
        provider=args.provider,
        model=args.model,
        batch_size=args.batch_size,
        max_inflight=args.max_inflight,
        max_retries=args.max_retries,
        max_cost_usd=args.max_cost_usd,
        structured_output_mode=args.structured_output_mode,
        enable_web_review=args.enable_web_review,
        web_review_model=args.web_review_model,
        web_review_limit=args.web_review_limit,
        no_overwrite=args.no_overwrite,
        max_output_tokens=args.max_output_tokens,
        repair_max_output_tokens=args.repair_max_output_tokens,
        thinking_level=None if args.thinking_level == "none" else args.thinking_level,
    )
    logger.info(
        "normalization N3 started data_dir=%s normalization_dir=%s n2_dir=%s out=%s provider=%s model=%s batch_size=%s max_inflight=%s max_cost_usd=%s web_review=%s",
        config.data_dir,
        config.normalization_dir,
        config.n2_dir,
        config.out_dir,
        config.provider,
        config.model,
        config.batch_size,
        config.max_inflight,
        config.max_cost_usd,
        config.enable_web_review,
    )
    try:
        client = GeminiClient()
        logger.info("Gemini direct key rotation enabled key_count=%s", client.api_keys_count)
        report = run_normalization_n3(config, client=client)
    except Exception as exc:
        logger.exception("normalization N3 failed")
        print(f"Normalization N3 failed: {exc}")
        return 1

    counts = report.get("counts", {})
    cost = report.get("cost", {})
    quality = report.get("quality", {})
    logger.info("normalization N3 finished counts=%s cost=%s quality=%s", counts, cost, quality)
    print(
        "Normalization N3 complete: "
        f"groups={counts.get('groups_processed', 0)} "
        f"accept={counts.get('accepted_same_entity', 0)} "
        f"reject={counts.get('rejected_distinct_entities', 0)} "
        f"split={counts.get('split_into_subclusters', 0)} "
        f"review={counts.get('review_groups_total', 0)} "
        f"accepted_clusters={counts.get('accepted_clusters_total', 0)} "
        f"invalid={counts.get('invalid_llm_responses', 0)} "
        f"cost=${cost.get('estimated_cost_usd', 0.0)} "
        f"quality_passed={quality.get('passed')} "
        f"out={config.out_dir}"
    )
    warnings = report.get("warnings", [])
    for warning in warnings[:10]:
        print(f"WARNING: {warning}")
    if len(warnings) > 10:
        print(f"WARNING: {len(warnings) - 10} more warnings in n3_report.json")
    return 0


def run_normalize_n4(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    logger = configure_logging(data_dir)
    config = N4Config.from_data_dir(
        data_dir,
        normalization_dir=Path(args.normalization_dir) if args.normalization_dir else None,
        n2_dir=Path(args.n2_dir) if args.n2_dir else None,
        n3_dir=Path(args.n3_dir) if args.n3_dir else None,
        out_dir=Path(args.out) if args.out else None,
        review_sample_size=args.review_sample_size,
    )
    logger.info(
        "normalization N4 started data_dir=%s normalization_dir=%s n2_dir=%s n3_dir=%s out=%s review_sample_size=%s",
        config.data_dir,
        config.normalization_dir,
        config.n2_dir,
        config.n3_dir,
        config.out_dir,
        config.review_sample_size,
    )
    try:
        report = run_normalization_n4(config)
    except Exception as exc:
        logger.exception("normalization N4 failed")
        print(f"Normalization N4 failed: {exc}")
        return 1

    counts = report.get("counts", {})
    quality = report.get("quality", {})
    logger.info("normalization N4 finished counts=%s quality=%s", counts, quality)
    print(
        "Normalization N4 complete: "
        f"mentions={counts.get('mentions_total', 0)} "
        f"links={counts.get('document_tag_links_total', 0)} "
        f"final_tags={counts.get('final_canonical_tags_total', 0)} "
        f"standalone={counts.get('standalone_auto_cluster_tags', 0)} "
        f"merged={counts.get('merged_n3_tags', 0)} "
        f"aliases={counts.get('aliases_total', 0)} "
        f"quality_passed={quality.get('passed')} "
        f"out={config.out_dir}"
    )
    return 0


def run_article_plan_a0(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    logger = configure_logging(data_dir)
    config = A0Config.from_data_dir(
        data_dir,
        normalization_final_dir=Path(args.normalization_final_dir) if args.normalization_final_dir else None,
        parsed_dir=Path(args.parsed_dir) if args.parsed_dir else None,
        normalization_dir=Path(args.normalization_dir) if args.normalization_dir else None,
        out_dir=Path(args.out) if args.out else None,
        max_neighbor_blocks=args.max_neighbor_blocks,
        max_window_chars=args.max_window_chars,
        short_document_char_limit=args.short_document_char_limit,
        high_frequency_doc_threshold=args.high_frequency_doc_threshold,
        low_count_doc_threshold=args.low_count_doc_threshold,
        review_sample_size=args.review_sample_size,
        overwrite=not args.no_overwrite,
    )
    logger.info(
        "article planning A0 started data_dir=%s normalization_final_dir=%s parsed_dir=%s normalization_dir=%s out=%s",
        config.data_dir,
        config.normalization_final_dir,
        config.parsed_dir,
        config.normalization_dir,
        config.out_dir,
    )
    try:
        report = run_article_planning_a0(config)
    except Exception as exc:
        logger.exception("article planning A0 failed")
        print(f"Article planning A0 failed: {exc}")
        return 1

    counts = report.get("counts", {})
    logger.info("article planning A0 finished counts=%s", counts)
    print(
        "Article planning A0 complete: "
        f"final_tags={counts.get('final_tags_total', 0)} "
        f"source_windows={counts.get('source_windows_total', 0)} "
        f"direct_copy={counts.get('direct_copy_candidates', 0)} "
        f"singleton={counts.get('singleton_candidates', 0)} "
        f"stub_only={counts.get('stub_only_tags', 0)} "
        f"review_stub={counts.get('review_stub_tags', 0)} "
        f"no_source={counts.get('no_source_window_tags', 0)} "
        f"out={config.out_dir}"
    )
    warnings = report.get("warnings", [])
    for warning in warnings[:10]:
        print(f"WARNING: {warning}")
    if len(warnings) > 10:
        print(f"WARNING: {len(warnings) - 10} more warnings in article_planning_report.json")
    return 0


def run_article_a1(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    logger = configure_logging(data_dir)
    config = A1Config.from_data_dir(
        data_dir,
        articles_planning_dir=Path(args.articles_planning_dir) if args.articles_planning_dir else None,
        normalization_final_dir=Path(args.normalization_final_dir) if args.normalization_final_dir else None,
        parsed_dir=Path(args.parsed_dir) if args.parsed_dir else None,
        out_dir=Path(args.out) if args.out else None,
        entities_out_dir=Path(args.entities_out) if args.entities_out else None,
        review_sample_size=args.review_sample_size,
        low_count_doc_threshold=args.low_count_doc_threshold,
        high_frequency_doc_threshold=args.high_frequency_doc_threshold,
        overwrite=not args.no_overwrite,
    )
    logger.info(
        "article A1 started data_dir=%s articles_planning_dir=%s normalization_final_dir=%s parsed_dir=%s out=%s entities_out=%s",
        config.data_dir,
        config.articles_planning_dir,
        config.normalization_final_dir,
        config.parsed_dir,
        config.out_dir,
        config.entities_out_dir,
    )
    try:
        report = run_article_a1_bootstrap(config)
    except Exception as exc:
        logger.exception("article A1 failed")
        print(f"Article A1 failed: {exc}")
        return 1

    counts = report.get("counts", {})
    logger.info("article A1 finished counts=%s quality=%s", counts, report.get("quality", {}))
    print(
        "Article A1 complete: "
        f"final_tags={counts.get('final_tags_total', 0)} "
        f"entity_json={counts.get('entity_json_files_created', 0)} "
        f"rerouted={counts.get('a0_1_rerouted_from_review_stub', 0)} "
        f"direct_copy={counts.get('direct_copy_articles', 0)} "
        f"direct_rejected={counts.get('direct_copy_rejected', 0)} "
        f"review_stub={counts.get('review_stub_articles', 0)} "
        f"a2_tasks={counts.get('a2_extraction_tasks_total', 0)} "
        f"out={config.out_dir}"
    )
    warnings = report.get("warnings", [])
    for warning in warnings[:10]:
        print(f"WARNING: {warning}")
    if len(warnings) > 10:
        print(f"WARNING: {len(warnings) - 10} more warnings in a1_report.json")
    return 0


def run_article_a2(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    logger = configure_logging(data_dir)
    load_dotenv_gemini_keys(Path(".env"))
    config = A2Config.from_data_dir(
        data_dir,
        a1_dir=Path(args.a1_dir) if args.a1_dir else None,
        planning_dir=Path(args.planning_dir) if args.planning_dir else None,
        normalization_final_dir=Path(args.normalization_final_dir) if args.normalization_final_dir else None,
        out_dir=Path(args.out) if args.out else None,
        provider=args.provider,
        model=args.model,
        structured_output_mode=args.structured_output_mode,
        limit=args.limit,
        task_filter=args.task_filter,
        strategy_filter=_split_csv_arg(args.strategy_filter),
        priority_filter=_split_csv_arg(args.priority_filter),
        max_tasks_per_batch=args.max_tasks_per_batch,
        batch_char_limit=args.batch_char_limit,
        max_inflight=args.max_inflight,
        max_retries=args.max_retries,
        max_output_tokens=args.max_output_tokens,
        repair_max_output_tokens=args.repair_max_output_tokens,
        thinking_level=None if args.thinking_level == "none" else args.thinking_level,
        max_cost_usd=args.max_cost_usd,
        retry_failures=args.retry_failures,
        resume=not args.no_resume,
        experiment_name=args.experiment_name,
    )
    logger.info(
        "article A2 started data_dir=%s a1_dir=%s planning_dir=%s out=%s provider=%s model=%s limit=%s max_inflight=%s experiment=%s",
        config.data_dir,
        config.a1_dir,
        config.planning_dir,
        config.out_dir,
        config.provider,
        config.model,
        config.limit,
        config.max_inflight,
        config.experiment_name,
    )
    try:
        client = GeminiClient()
        logger.info("Gemini direct key rotation enabled key_count=%s", client.api_keys_count)
        report = run_article_a2_extraction(config, client=client)
    except Exception as exc:
        logger.exception("article A2 failed")
        print(f"Article A2 failed: {exc}")
        return 1

    counts = report.get("counts", {})
    llm = report.get("llm", {})
    quality = report.get("quality", {})
    logger.info("article A2 finished counts=%s llm=%s quality=%s", counts, llm, quality)
    print(
        "Article A2 complete: "
        f"tasks={counts.get('tasks_processed', 0)} "
        f"evidence_items={counts.get('evidence_items_total', 0)} "
        f"no_evidence={counts.get('tasks_no_evidence', 0)} "
        f"review={counts.get('tasks_review', 0)} "
        f"failed={counts.get('tasks_failed', 0)} "
        f"quote_not_found={counts.get('evidence_items_quote_not_found', 0)} "
        f"cost=${llm.get('estimated_cost_usd', 0.0)} "
        f"quality_passed={quality.get('passed')} "
        f"out={config.out_dir}"
    )
    if report.get("stop_reason"):
        print(f"Stopped: {report['stop_reason']}")
    warnings = report.get("warnings", [])
    for warning in warnings[:10]:
        print(f"WARNING: {warning}")
    if len(warnings) > 10:
        print(f"WARNING: {len(warnings) - 10} more warnings in a2_report.json")
    return 0


def run_article_a3(args: argparse.Namespace) -> int:
    data_dir = Path(args.data)
    logger = configure_logging(data_dir)
    config = A3Config.from_data_dir(
        data_dir,
        a2_dir=Path(args.a2_dir) if args.a2_dir else None,
        a1_dir=Path(args.a1_dir) if args.a1_dir else None,
        normalization_final_dir=Path(args.normalization_final_dir) if args.normalization_final_dir else None,
        out_dir=Path(args.out) if args.out else None,
        min_confidence=args.min_confidence,
        allow_fuzzy_for_review=args.allow_fuzzy_for_review,
        max_quotes_per_fact_group=args.max_quotes_per_fact_group,
        max_fact_groups_per_tag=args.max_fact_groups_per_tag,
        overwrite=not args.no_overwrite,
    )
    logger.info(
        "article A3 started data_dir=%s a2_dir=%s a1_dir=%s normalization_final_dir=%s out=%s min_confidence=%s",
        config.data_dir,
        config.a2_dir,
        config.a1_dir,
        config.normalization_final_dir,
        config.out_dir,
        config.min_confidence,
    )
    try:
        report = run_article_a3_grouping(config)
    except Exception as exc:
        logger.exception("article A3 failed")
        print(f"Article A3 failed: {exc}")
        return 1

    counts = report.get("counts", {})
    quality = report.get("quality", {})
    logger.info("article A3 finished counts=%s quality=%s", counts, quality)
    print(
        "Article A3 complete: "
        f"evidence={counts.get('a2_evidence_items_total', 0)} "
        f"valid={counts.get('valid_evidence_items', 0)} "
        f"review={counts.get('review_evidence_items', 0)} "
        f"rejected={counts.get('rejected_evidence_items', 0)} "
        f"fact_groups={counts.get('fact_groups_total', 0)} "
        f"usable_groups={counts.get('usable_fact_groups', 0)} "
        f"ready_for_a4={counts.get('ready_for_a4_tags', 0)} "
        f"quality_passed={quality.get('passed')} "
        f"out={config.out_dir}"
    )
    warnings = report.get("warnings", [])
    for warning in warnings[:10]:
        print(f"WARNING: {warning}")
    if len(warnings) > 10:
        print(f"WARNING: {len(warnings) - 10} more warnings in a3_report.json")
    return 0


def configure_logging(out_dir: Path) -> logging.Logger:
    logs_dir = out_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "pipeline.log"

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)
    return logger


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def _score_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0.0 or parsed > 1.0:
        raise argparse.ArgumentTypeError("score must be between 0 and 1")
    return parsed


def _optional_timeout_seconds(value: int) -> int | None:
    return None if value == 0 else value


def _parse_optional_model(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.lower() in {"none", "null", "off"}:
        return None
    return stripped


def _split_csv_arg(value: str | None) -> tuple[str, ...]:
    if value is None:
        return tuple()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _gemini_models_markdown(raw: dict[str, Any], client: GeminiClient) -> str:
    models = raw.get("models", [])
    if not isinstance(models, list):
        models = []
    lines = [
        "# Gemini Available Models",
        "",
        f"Generated at: {__import__('datetime').datetime.utcnow().isoformat(timespec='seconds')}Z",
        "",
        "## Recommended mapping",
        "",
        "TAGGING_PRIMARY = gemini-3-flash-preview",
        "EVIDENCE_EXTRACTION_PRIMARY = gemini-3-flash-preview",
        "TAG_NORMALIZATION_PRIMARY = gemini-3-pro-preview",
        "ARTICLE_COMPILATION_PRIMARY = gemini-3-pro-preview",
        "FOLDER_HIERARCHY_PRIMARY = gemini-3-flash-preview",
        "QA_AUDIT_PRIMARY = gemini-3-flash-preview",
        "",
        f"Discovered with key_count={client.api_keys_count}; keys are not stored in this report.",
        "",
        "## Raw available models",
        "",
        "| name | baseModelId | version | displayName | input | output | methods | recommended_role |",
        "|---|---|---|---|---:|---:|---|---|",
    ]
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        base_model_id = str(item.get("baseModelId", ""))
        version = str(item.get("version", ""))
        display_name = str(item.get("displayName", ""))
        input_limit = item.get("inputTokenLimit", "")
        output_limit = item.get("outputTokenLimit", "")
        methods = item.get("supportedGenerationMethods", [])
        methods_text = ", ".join(str(method) for method in methods) if isinstance(methods, list) else ""
        role = _recommended_gemini_role(item)
        lines.append(
            "| "
            + " | ".join(
                _md_cell(value)
                for value in (
                    name,
                    base_model_id,
                    version,
                    display_name,
                    input_limit,
                    output_limit,
                    methods_text,
                    role,
                )
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _recommended_gemini_role(model: dict[str, Any]) -> str:
    model_id = str(model.get("baseModelId") or model.get("name") or "").removeprefix("models/")
    methods = model.get("supportedGenerationMethods", [])
    supports_generate = isinstance(methods, list) and "generateContent" in methods
    if not supports_generate:
        return "not_for_pipeline"
    if model_id == "gemini-3-flash-preview":
        return "TAGGING_PRIMARY,EVIDENCE_EXTRACTION_PRIMARY,FOLDER_HIERARCHY_PRIMARY,QA_AUDIT_PRIMARY"
    if model_id == "gemini-3-pro-preview":
        return "TAG_NORMALIZATION_PRIMARY,ARTICLE_COMPILATION_PRIMARY,QA_AUDIT_HARD"
    if model_id == "gemini-2.5-flash-lite":
        return "cheap_fallback_candidate"
    if model_id == "gemini-2.5-pro":
        return "stable_pro_fallback_candidate"
    if model_id == "gemini-2.0-flash":
        return "stable_flash_fallback_candidate"
    return "available_generateContent_candidate"


def _md_cell(value: Any) -> str:
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")

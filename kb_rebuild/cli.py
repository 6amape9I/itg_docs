from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from kb_rebuild.io.jsonl import write_jsonl
from kb_rebuild.llm.models import FALLBACK_TAGGING_MODEL, PRIMARY_TAGGING_MODEL
from kb_rebuild.llm.openrouter_client import OpenRouterClient, load_dotenv_openrouter_key
from kb_rebuild.llm.tagging import TaggingConfig, run_tagging_calibration
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
    tag_parser.add_argument("--model", default=PRIMARY_TAGGING_MODEL, help="Stable OpenRouter model id")
    tag_parser.add_argument("--fallback-model", default=FALLBACK_TAGGING_MODEL, help="Stable fallback OpenRouter model id")
    tag_parser.add_argument("--max-cost-usd", type=_non_negative_float, default=5.0, help="Hard calibration budget limit")
    tag_parser.add_argument("--max-retries", type=_non_negative_int, default=2, help="Retries per model")
    tag_parser.add_argument("--prompt-char-limit", type=_positive_int, default=16000, help="Max clean_text chars sent to LLM")
    tag_parser.add_argument("--max-output-tokens", type=_positive_int, default=3200)
    tag_parser.add_argument("--provider-sort", choices=("throughput", "price"), default="throughput")
    tag_parser.add_argument("--timeout-seconds", type=_positive_int, default=120)
    tag_parser.add_argument("--request-delay-seconds", type=_non_negative_float, default=2.0)
    tag_parser.add_argument("--rate-limit-backoff-seconds", type=_non_negative_float, default=30.0)
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
    config = TaggingConfig(
        data_dir=data_dir,
        limit=args.limit,
        model=args.model,
        fallback_model=args.fallback_model or None,
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

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kb_rebuild.articles.a4.models import A4Config
from kb_rebuild.articles.a4.runner import run_article_a4_compilation
from kb_rebuild.io.jsonl import read_jsonl, write_jsonl


@dataclass(frozen=True)
class FakeCompletion:
    raw: dict[str, Any]
    content: str
    usage: dict[str, int]
    model: str = "gemini-3-flash-preview"
    finish_reason: str = "STOP"
    latency_ms: int = 50
    api_key_index: int = 0
    usage_source: str = "api"


class FakeGeminiClient:
    provider_name = "gemini_direct"

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = list(responses or [])
        self.payloads: list[dict[str, Any]] = []
        self.api_keys_count = 1

    def chat_completion(self, payload: dict[str, Any]) -> FakeCompletion:
        self.payloads.append(payload)
        if self.responses:
            response = self.responses.pop(0)
        else:
            batch = _batch_from_payload(payload)
            response = _valid_response(batch)
        return FakeCompletion(
            raw={"candidates": []},
            content=json.dumps(response, ensure_ascii=False),
            usage={"prompt_tokens": 100, "completion_tokens": 50, "reasoning_tokens": 0},
        )


class ArticleA4RunnerTests(unittest.TestCase):
    def test_fake_gemini_client_compiles_valid_article(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root)
            config = _config(root, limit=1, max_inflight=1)

            report = run_article_a4_compilation(config, client=FakeGeminiClient())

            self.assertEqual(report["counts"]["tasks_processed"], 1)
            self.assertEqual(report["counts"]["compiled_articles"], 1)
            self.assertTrue((config.out_dir / "article_drafts.jsonl").exists())
            self.assertTrue((config.out_dir / "compiled_articles" / "disease" / "tag_1.json").exists())

    def test_invalid_response_triggers_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root)
            config = _config(root, limit=1, max_inflight=1, max_retries=1)
            client = FakeGeminiClient(responses=[{"batch_id": "a4batch_000001", "articles": []}])

            report = run_article_a4_compilation(config, client=client)

            self.assertEqual(len(client.payloads), 2)
            self.assertEqual(report["counts"]["compiled_articles"], 1)
            self.assertGreaterEqual(report["llm"]["schema_validation_failures"], 1)

    def test_unrepaired_invalid_response_goes_to_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root)
            config = _config(root, limit=1, max_inflight=1, max_retries=0)
            client = FakeGeminiClient(responses=[{"batch_id": "a4batch_000001", "articles": []}])

            report = run_article_a4_compilation(config, client=client)

            self.assertEqual(report["counts"]["tasks_failed"], 1)
            failures = read_jsonl(config.out_dir / "article_compilation_failures.jsonl")
            self.assertEqual(failures[0]["status"], "failed")

    def test_cache_hit_skips_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root)
            config = _config(root, limit=1, max_inflight=1, resume=False)
            first_client = FakeGeminiClient()
            run_article_a4_compilation(config, client=first_client)
            self.assertEqual(len(first_client.payloads), 1)

            second_client = FakeGeminiClient()
            report = run_article_a4_compilation(config, client=second_client)

            self.assertEqual(len(second_client.payloads), 0)
            self.assertEqual(report["llm"]["cache_hits"], 1)

    def test_resume_skips_completed_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root)
            config = _config(root, limit=1, max_inflight=1, resume=True)
            run_article_a4_compilation(config, client=FakeGeminiClient())

            second_client = FakeGeminiClient()
            report = run_article_a4_compilation(config, client=second_client)

            self.assertEqual(len(second_client.payloads), 0)
            self.assertEqual(report["counts"]["tasks_requested"], 0)

    def test_smoke_limit_respected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root, tags_count=3)
            config = _config(root, limit=1, max_inflight=1)

            report = run_article_a4_compilation(config, client=FakeGeminiClient())

            self.assertEqual(report["counts"]["tasks_requested"], 1)
            tasks = read_jsonl(config.out_dir / "article_compilation_tasks.jsonl")
            self.assertEqual(len(tasks), 1)

    def test_production_without_limit_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_inputs(root)
            config = _config(root, limit=None, max_inflight=1)

            with self.assertRaises(ValueError):
                run_article_a4_compilation(config, client=FakeGeminiClient())


def _config(root: Path, **kwargs: Any) -> A4Config:
    return A4Config.from_data_dir(
        root,
        a3_dir=root / "articles" / "a3",
        a1_dir=root / "articles" / "a1",
        entities_dir=root / "articles" / "entities",
        normalization_final_dir=root / "normalization" / "final",
        out_dir=root / "articles" / "a4" / "experiments" / "smoke_test",
        structured_output_mode="prompt_json",
        max_output_tokens=1200,
        repair_max_output_tokens=2400,
        **kwargs,
    )


def _write_inputs(root: Path, *, tags_count: int = 1) -> None:
    a3_dir = root / "articles" / "a3"
    a1_dir = root / "articles" / "a1"
    entities_dir = root / "articles" / "entities"
    final_dir = root / "normalization" / "final"
    a3_dir.mkdir(parents=True, exist_ok=True)
    a1_dir.mkdir(parents=True, exist_ok=True)
    entities_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)
    a4_inputs = []
    fact_groups = []
    tag_index = []
    for index in range(1, tags_count + 1):
        tag_id = f"tag_{index}"
        fact_id = f"fg_{index}"
        strategy = "compile_with_review_flag" if index % 2 == 0 else "compile_from_fact_groups"
        review = strategy == "compile_with_review_flag"
        a4_inputs.append(_a4_input(tag_id, fact_id, strategy=strategy, review=review))
        fact_groups.append(_fact(fact_id, tag_id, review=review))
        tag_index.append({"tag_id": tag_id, "ready_for_a4": True, "a4_strategy": strategy})
    write_jsonl(a3_dir / "a4_compilation_input.jsonl", a4_inputs)
    write_jsonl(a3_dir / "fact_groups.jsonl", fact_groups)
    write_jsonl(a3_dir / "tag_fact_group_index.jsonl", tag_index)
    write_jsonl(a1_dir / "article_status_index.jsonl", [])
    _write_json(
        a3_dir / "a3_report.json",
        {
            "stage": "article_a3_evidence_dedupe_fact_grouping",
            "counts": {"ready_for_a4_tags": tags_count},
            "quality": {"passed": True},
        },
    )
    _write_json(a3_dir / "a3_manifest.json", {"stage_version": "a3.0"})
    _write_json(a1_dir / "a1_report.json", {"stage": "article_a1_entity_json_bootstrap", "quality": {"passed": True}})
    _write_json(a1_dir / "a1_manifest.json", {"stage_version": "a1.0"})
    (final_dir / "tags_canonical.csv").write_text("tag_id,canonical_tag_ru\n", encoding="utf-8")
    (final_dir / "tag_aliases.csv").write_text("tag_id,alias\n", encoding="utf-8")


def _a4_input(tag_id: str, fact_id: str, *, strategy: str, review: bool) -> dict[str, Any]:
    return {
        "tag_id": tag_id,
        "canonical_tag_ru": "Тестовый тег",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "a4_strategy": strategy,
        "article_status_from_a1": "pending",
        "ready_for_a4": True,
        "needs_review_before_publication": review,
        "review_reasons": ["publication_review_required"] if review else [],
        "fact_group_ids": [fact_id],
        "source_documents_count": 1,
    }


def _fact(fact_id: str, tag_id: str, *, review: bool) -> dict[str, Any]:
    return {
        "fact_group_id": fact_id,
        "tag_id": tag_id,
        "canonical_tag_ru": "Тестовый тег",
        "canonical_tag_latin": None,
        "entity_type": "disease",
        "fact_type": "definition",
        "section_hint": "Что это",
        "representative_claim": "Тестовый тег является примером.",
        "representative_quote": "Тестовый тег является примером.",
        "representative_quote_validation_status": "exact",
        "source_doc_ids": ["doc_1"],
        "source_documents_count": 1,
        "confidence": 0.9,
        "importance": "high",
        "a4_usage": "core_fact",
        "usable_for_a4": True,
        "needs_review_before_publication": review,
        "review_reasons": ["publication_review_required"] if review else [],
    }


def _valid_response(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        "batch_id": batch["batch_id"],
        "articles": [_article(task) for task in batch["tasks"]],
    }


def _article(task: dict[str, Any]) -> dict[str, Any]:
    fact_id = task["fact_group_ids"][0]
    review = bool(task.get("needs_review_before_publication"))
    return {
        "task_id": task["task_id"],
        "tag_id": task["tag_id"],
        "article_status": "compiled_with_review_flag" if task["a4_strategy"] == "compile_with_review_flag" else "compiled_article",
        "title": task["canonical_tag_ru"],
        "summary": "Краткое описание.",
        "content": {
            "time": 0,
            "version": "2.28.0",
            "blocks": [
                {"id": "block_001", "type": "header", "data": {"text": "Что это", "level": 2}, "metadata": {"source_fact_group_ids": []}},
                {
                    "id": "block_002",
                    "type": "paragraph",
                    "data": {"text": "Тестовый тег является примером."},
                    "metadata": {"source_fact_group_ids": [fact_id]},
                },
            ],
        },
        "used_fact_group_ids": [fact_id],
        "unused_fact_group_ids": [],
        "needs_review_before_publication": review,
        "review_reasons": ["publication_review_required"] if review else [],
        "confidence": 0.9,
        "reason": "",
    }


def _batch_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload["contents"][0]["parts"][0]["text"]
    marker = "Входные задачи A4:\n```json\n"
    json_text = text.split(marker, 1)[1].split("\n```", 1)[0]
    return json.loads(json_text)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

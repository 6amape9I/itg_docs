from __future__ import annotations

import json
import unittest

from kb_rebuild.articles.a2.schema import parse_response_json, validate_batch_response


class ArticleA2SchemaTests(unittest.TestCase):
    def test_valid_batch_response_passes(self) -> None:
        parsed = _response("a2batch_000001", "a2task_000000001", "tag_1")
        normalized, errors = validate_batch_response(parsed, _batch())

        self.assertFalse(errors)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["task_results"][0]["decision"], "evidence_extracted")

    def test_unknown_task_id_fails(self) -> None:
        parsed = _response("a2batch_000001", "unknown", "tag_1")
        normalized, errors = validate_batch_response(parsed, _batch())

        self.assertIsNone(normalized)
        self.assertTrue(any("unknown task_id" in error for error in errors))

    def test_missing_task_result_fails(self) -> None:
        parsed = {"batch_id": "a2batch_000001", "task_results": []}
        normalized, errors = validate_batch_response(parsed, _batch())

        self.assertIsNone(normalized)
        self.assertTrue(any("missing task_id" in error for error in errors))

    def test_invalid_decision_fails(self) -> None:
        parsed = _response("a2batch_000001", "a2task_000000001", "tag_1")
        parsed["task_results"][0]["decision"] = "write_article"
        normalized, errors = validate_batch_response(parsed, _batch())

        self.assertIsNone(normalized)
        self.assertTrue(any("invalid decision" in error for error in errors))

    def test_invalid_fact_type_fails(self) -> None:
        parsed = _response("a2batch_000001", "a2task_000000001", "tag_1")
        parsed["task_results"][0]["evidence_items"][0]["fact_type"] = "fantasy"
        normalized, errors = validate_batch_response(parsed, _batch())

        self.assertIsNone(normalized)
        self.assertTrue(any("invalid fact_type" in error for error in errors))

    def test_evidence_extracted_without_quote_fails(self) -> None:
        parsed = _response("a2batch_000001", "a2task_000000001", "tag_1")
        parsed["task_results"][0]["evidence_items"][0]["quote"] = ""
        normalized, errors = validate_batch_response(parsed, _batch())

        self.assertIsNone(normalized)
        self.assertTrue(any("quote must be non-empty" in error for error in errors))

    def test_parse_response_json_strips_code_fence(self) -> None:
        parsed, errors = parse_response_json("```json\n" + json.dumps({"batch_id": "b", "task_results": []}) + "\n```")

        self.assertFalse(errors)
        self.assertEqual(parsed["batch_id"], "b")


def _batch() -> dict[str, object]:
    return {
        "batch_id": "a2batch_000001",
        "tasks": [{"task_id": "a2task_000000001", "tag_id": "tag_1"}],
    }


def _response(batch_id: str, task_id: str, tag_id: str) -> dict[str, object]:
    return {
        "batch_id": batch_id,
        "task_results": [
            {
                "task_id": task_id,
                "tag_id": tag_id,
                "decision": "evidence_extracted",
                "relevance": "direct",
                "confidence": 0.9,
                "evidence_items": [
                    {
                        "fact_type": "definition",
                        "section_hint": "Что это",
                        "claim": "Короткий факт",
                        "quote": "Дословная цитата",
                        "importance": "high",
                        "confidence": 0.9,
                    }
                ],
                "reason": "",
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()


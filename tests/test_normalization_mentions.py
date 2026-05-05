from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kb_rebuild.normalization.mentions import flatten_mentions, load_tagging_records, normalize_mention


class NormalizationMentionsTests(unittest.TestCase):
    def test_flatten_one_document_with_multiple_entities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "document_tags_raw_active.jsonl"
            path.write_text(
                '{"doc_id":"doc_1","document_name":"Гастрит","provider":"gemini_direct",'
                '"model":"gemini-3-flash-preview","prompt_version":"tagging_v2_gemini",'
                '"schema_version":"document_tagging_v2","entities":['
                '{"surface":"Гастрит","canonical_candidate_ru":"Гастрит","canonical_candidate_latin":"Gastritis",'
                '"entity_type":"disease","article_candidate":true,"tag_role":"article_candidate",'
                '"is_primary":true,"confidence":0.94,"evidence_quotes":["Гастрит"],'
                '"quote_validation_status":"all_exact","quote_validation_details":[]},'
                '{"surface":"желудок","canonical_candidate_ru":"Желудок","canonical_candidate_latin":"",'
                '"entity_type":"organ_or_body_system","article_candidate":false,"tag_role":"context_only",'
                '"is_primary":false,"confidence":0.8,"evidence_quotes":["желудок"],'
                '"quote_validation_status":"all_exact","quote_validation_details":[]}'
                "]}\n",
                encoding="utf-8",
            )

            records, invalid, warnings = load_tagging_records(path)
            mentions, flatten_invalid, flatten_warnings = flatten_mentions(records, source_file=path)

        self.assertEqual(invalid, [])
        self.assertEqual(warnings, [])
        self.assertEqual(flatten_invalid, [])
        self.assertEqual(flatten_warnings, [])
        self.assertEqual(len(mentions), 2)
        self.assertEqual(mentions[0].mention_id, "m_0000001_00")
        self.assertEqual(mentions[1].tag_role, "context_only")

    def test_missing_entities_warns_but_does_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.jsonl"
            path.write_text('{"doc_id":"doc_1","document_name":"Empty"}\n', encoding="utf-8")
            records, _, _ = load_tagging_records(path)
            mentions, invalid, warnings = flatten_mentions(records, source_file=path)

        self.assertEqual(mentions, [])
        self.assertEqual(invalid, [])
        self.assertTrue(warnings)

    def test_invalid_records_are_collected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.jsonl"
            path.write_text(
                '{"doc_id":"doc_1","entities":[]}\n'
                "{bad json}\n"
                '{"document_name":"missing doc","entities":[]}\n'
                '{"doc_id":"doc_2","entities":[42]}\n',
                encoding="utf-8",
            )
            records, invalid_load, _ = load_tagging_records(path)
            mentions, invalid_flatten, _ = flatten_mentions(records, source_file=path)

        self.assertEqual(mentions, [])
        self.assertEqual(len(invalid_load), 1)
        self.assertEqual(len(invalid_flatten), 2)

    def test_normalized_mentions_include_suspicious_quote_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.jsonl"
            path.write_text(
                '{"doc_id":"doc_1","document_name":"ИФА","entities":['
                '{"surface":"ИФА","canonical_candidate_ru":"","canonical_candidate_latin":"ELISA",'
                '"entity_type":"diagnostic_method","article_candidate":true,"tag_role":"article_candidate",'
                '"is_primary":true,"confidence":0.7,"evidence_quotes":["..."],'
                '"quote_validation_status":"not_found","quote_validation_details":[{"status":"not_found"}]}'
                "]}\n",
                encoding="utf-8",
            )
            records, _, _ = load_tagging_records(path)
            mentions, _, _ = flatten_mentions(records, source_file=path)
            normalized = normalize_mention(mentions[0])

        self.assertEqual(normalized.normalized["primary_norm"], "ифа")
        self.assertIn("empty_canonical_candidate_ru", normalized.suspicious_flags)
        self.assertIn("quote_not_found", normalized.suspicious_flags)
        self.assertIn("quote_not_found", normalized.risk_flags)
        self.assertIn("article_candidate", normalized.routing_flags)

    def test_context_only_is_routing_not_risk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.jsonl"
            path.write_text(
                '{"doc_id":"doc_1","document_name":"Желудок","entities":['
                '{"surface":"Желудок","canonical_candidate_ru":"Желудок","canonical_candidate_latin":"",'
                '"entity_type":"organ_or_body_system","article_candidate":false,"tag_role":"context_only",'
                '"is_primary":false,"confidence":0.95,"evidence_quotes":["Желудок"],'
                '"quote_validation_status":"all_exact","quote_validation_details":[{"status":"exact"}]}'
                "]}\n",
                encoding="utf-8",
            )
            records, _, _ = load_tagging_records(path)
            mentions, _, _ = flatten_mentions(records, source_file=path)
            normalized = normalize_mention(mentions[0])

        self.assertEqual(normalized.risk_flags, [])
        self.assertEqual(normalized.suspicious_flags, [])
        self.assertIn("context_only", normalized.routing_flags)


if __name__ == "__main__":
    unittest.main()

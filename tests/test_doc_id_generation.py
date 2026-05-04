from __future__ import annotations

import unittest

from kb_rebuild.parsing.documents import generate_doc_id
from kb_rebuild.parsing.editorjs import content_sha256


class DocIdGenerationTests(unittest.TestCase):
    def test_doc_id_is_deterministic_and_contains_hash_prefix(self) -> None:
        content = '{"blocks":[]}'
        doc_id, duplicate = generate_doc_id(1, content)

        self.assertFalse(duplicate)
        self.assertEqual(doc_id, f"doc_000001_{content_sha256(content)[:8]}")

    def test_duplicate_doc_id_gets_safe_suffix(self) -> None:
        content = '{"blocks":[]}'
        base_doc_id, _ = generate_doc_id(7, content)
        doc_id, duplicate = generate_doc_id(7, content, {base_doc_id})

        self.assertTrue(duplicate)
        self.assertEqual(doc_id, f"{base_doc_id}_dup2")


if __name__ == "__main__":
    unittest.main()

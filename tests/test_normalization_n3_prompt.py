import unittest

from tests.test_normalization_n3_schema import _group
from kb_rebuild.normalization.n3.prompt import build_group_prompt, load_prompt_template


class NormalizationN3PromptTests(unittest.TestCase):
    def test_prompt_contains_strict_no_merge_rules(self) -> None:
        prompt = load_prompt_template()

        self.assertIn("Будь строгим", prompt)
        self.assertIn("Не объединяй", prompt)
        self.assertIn("торговое название и действующее вещество", prompt)
        self.assertIn("разные вирусы", prompt)

    def test_prompt_contains_split_and_reject_examples(self) -> None:
        prompt = load_prompt_template()

        self.assertIn("Мерцательная аритмия", prompt)
        self.assertIn("split_into_subclusters", prompt)
        self.assertIn("Вирус гепатита A", prompt)
        self.assertIn("reject_distinct_entities", prompt)

    def test_prompt_says_web_search_is_not_default(self) -> None:
        prompt = load_prompt_template()

        self.assertIn("Web search по умолчанию не используется", prompt)

    def test_prompt_does_not_request_chain_of_thought(self) -> None:
        prompt = load_prompt_template()

        self.assertIn("Не объясняй ход рассуждений", prompt)
        self.assertNotIn("chain-of-thought", prompt.lower())

    def test_group_prompt_contains_payload_and_repair_errors(self) -> None:
        prompt = build_group_prompt(_group(), repair_errors=["unknown node_id"])

        self.assertIn("## Candidate group input", prompt)
        self.assertIn('"candidate_group_id": "cg_test"', prompt)
        self.assertIn("unknown node_id", prompt)


if __name__ == "__main__":
    unittest.main()

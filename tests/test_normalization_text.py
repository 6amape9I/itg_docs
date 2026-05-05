from __future__ import annotations

import unittest

from kb_rebuild.normalization.text import (
    detect_suspicious_flags,
    diagnostic_abbreviation_candidate,
    has_specificity_modifier,
    normalize_basic_text,
    normalize_drug_class,
    normalize_drug_trade_name,
    normalize_microorganism_text,
    normalize_supplement_name,
)


class NormalizationTextTests(unittest.TestCase):
    def test_basic_cleanup(self) -> None:
        self.assertEqual(normalize_basic_text(" Болезнь Альцгеймера. "), "болезнь альцгеймера")
        self.assertEqual(normalize_basic_text("Вольтарен — эмульгель"), "вольтарен-эмульгель")
        self.assertEqual(normalize_basic_text("«Ахондроплазия»"), "ахондроплазия")
        self.assertEqual(normalize_basic_text("β-лактамные антибиотики"), "бета-лактамные антибиотики")

    def test_drug_trade_name_cleanup(self) -> None:
        self.assertEqual(
            normalize_drug_trade_name("Вольтарен эмульгель гель для наружного применения 2%"),
            "вольтарен эмульгель",
        )
        self.assertEqual(
            normalize_drug_trade_name("Агнукастон таблетки, покрытые оболочкой 60 шт"),
            "агнукастон",
        )
        self.assertEqual(normalize_drug_trade_name("Антистин-привин"), "антистин-привин")

    def test_supplement_cleanup(self) -> None:
        self.assertEqual(normalize_supplement_name("Vitamax(бад)"), "vitamax")

    def test_type_specific_helpers(self) -> None:
        self.assertEqual(normalize_drug_class("бета лактамные антибиотики"), "бета-лактамные антибиотики")
        self.assertEqual(normalize_drug_class("бета-лактамы"), "бета-лактамные антибиотики")
        self.assertEqual(normalize_microorganism_text("E. coli"), "e coli")
        self.assertEqual(diagnostic_abbreviation_candidate("иммуноферментный анализ"), "ифа")
        self.assertTrue(has_specificity_modifier("Хронический гастрит"))

    def test_suspicious_flags(self) -> None:
        flags = detect_suspicious_flags(
            surface="ИФА",
            canonical_candidate_ru="",
            primary_norm="ифа",
            entity_type="diagnostic_method",
            tag_role="context_only",
            confidence=0.7,
            quote_validation_status="not_found",
            quote_validation_details=[],
            evidence_quotes=[],
        )
        self.assertIn("empty_canonical_candidate_ru", flags)
        self.assertIn("possible_abbreviation", flags)
        self.assertIn("quote_not_found", flags)
        self.assertIn("low_confidence", flags)
        self.assertIn("context_only", flags)


if __name__ == "__main__":
    unittest.main()

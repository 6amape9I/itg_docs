from __future__ import annotations

import unittest

from kb_rebuild.normalization.text import (
    detect_suspicious_flags,
    diagnostic_abbreviation_candidate,
    has_specificity_modifier,
    has_type_subtype_marker,
    normalize_basic_text,
    normalize_drug_class,
    normalize_drug_trade_name,
    normalize_microorganism_text,
    normalize_product_name,
    normalize_supplement_name,
    strip_trailing_numeric_product_variant,
    subtype_signature,
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
        self.assertEqual(normalize_drug_trade_name("Берлиприл 20 мг"), "берлиприл")
        self.assertEqual(normalize_drug_trade_name("Берлиприл 20"), "берлиприл")
        self.assertEqual(normalize_drug_trade_name("Гепатромбин Г"), "гепатромбин г")

    def test_trailing_numeric_product_variant_protection(self) -> None:
        self.assertEqual(strip_trailing_numeric_product_variant("Берлиприл 20"), ("берлиприл", True))
        self.assertEqual(strip_trailing_numeric_product_variant("CoQ10"), ("coq10", False))
        self.assertEqual(strip_trailing_numeric_product_variant("Q10"), ("q10", False))
        self.assertEqual(strip_trailing_numeric_product_variant("Витамин B12"), ("витамин b12", False))
        self.assertEqual(strip_trailing_numeric_product_variant("IL-2"), ("il-2", False))
        self.assertEqual(strip_trailing_numeric_product_variant("FGFR3"), ("fgfr3", False))
        self.assertEqual(strip_trailing_numeric_product_variant("COVID-19"), ("covid-19", False))

        product = normalize_product_name("Берлиприл 20", "drug_trade_name")
        self.assertTrue(product.numeric_variant_changed)
        self.assertEqual(product.value, "берлиприл")

    def test_supplement_cleanup(self) -> None:
        self.assertEqual(normalize_supplement_name("Vitamax(бад)"), "vitamax")

    def test_type_specific_helpers(self) -> None:
        self.assertEqual(normalize_drug_class("бета лактамные антибиотики"), "бета-лактамные антибиотики")
        self.assertEqual(normalize_drug_class("бета-лактамы"), "бета-лактамные антибиотики")
        self.assertEqual(normalize_microorganism_text("E. coli"), "e coli")
        self.assertEqual(diagnostic_abbreviation_candidate("иммуноферментный анализ"), "ифа")
        self.assertTrue(has_specificity_modifier("Хронический гастрит"))
        self.assertTrue(has_type_subtype_marker("GM1 ганглиозидоз тип 1"))
        self.assertEqual(subtype_signature("GM1 ганглиозидоз тип 1"), "type_1")
        self.assertEqual(subtype_signature("GM1 ганглиозидоз тип 2"), "type_2")
        self.assertEqual(subtype_signature("сахарный диабет I типа"), "type_i")

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

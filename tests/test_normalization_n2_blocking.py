from __future__ import annotations

import unittest

from kb_rebuild.normalization.n2.blocking import blocking_reasons
from tests.test_normalization_n2_features import _node


class NormalizationN2BlockingTests(unittest.TestCase):
    def test_different_entity_types_blocked(self) -> None:
        reasons = blocking_reasons(_node("n1", "disease", "Гастрит"), _node("n2", "symptom", "Гастрит"), [])

        self.assertIn("different_entity_type", reasons)

    def test_disease_type_conflicts_blocked(self) -> None:
        reasons = blocking_reasons(
            _node("n1", "disease", "Сахарный диабет 1 типа", subtype_signature="type_1"),
            _node("n2", "disease", "Сахарный диабет 2 типа", subtype_signature="type_2"),
            [],
        )

        self.assertIn("disease_subtype_conflict", reasons)

    def test_disease_base_vs_type_blocked(self) -> None:
        reasons = blocking_reasons(
            _node("n1", "disease", "Сахарный диабет", subtype_signature="none"),
            _node("n2", "disease", "Сахарный диабет 1 типа", subtype_signature="type_1"),
            [],
        )

        self.assertIn("disease_subtype_conflict", reasons)

    def test_chronic_disease_parent_child_blocked(self) -> None:
        reasons = blocking_reasons(_node("n1", "disease", "Гастрит"), _node("n2", "disease", "Хронический гастрит"), [])

        self.assertIn("parent_child_suspect", reasons)
        self.assertIn("parent_child_blocked", reasons)

    def test_genus_species_microorganism_blocked(self) -> None:
        reasons = blocking_reasons(
            _node("n1", "microorganism", "Escherichia"),
            _node("n2", "microorganism", "Escherichia coli"),
            [],
        )

        self.assertIn("taxonomic_level_conflict", reasons)

    def test_short_alias_without_expansion_blocked(self) -> None:
        reasons = blocking_reasons(_node("n1", "biological_substance", "AR"), _node("n2", "biological_substance", "ARX"), [])

        self.assertIn("short_alias_ambiguous", reasons)

    def test_diagnostic_method_scope_conflict_blocked(self) -> None:
        reasons = blocking_reasons(_node("n1", "diagnostic_method", "МРТ"), _node("n2", "diagnostic_method", "МРТ гипофиза"), [])

        self.assertIn("diagnostic_method_scope_conflict", reasons)
        self.assertIn("parent_child_blocked", reasons)

    def test_procedure_object_scope_conflict_blocked(self) -> None:
        reasons = blocking_reasons(
            _node("n1", "procedure", "Вакцинация против гепатита А"),
            _node("n2", "procedure", "Вакцинация против желтой лихорадки"),
            [],
        )

        self.assertIn("procedure_object_scope_conflict", reasons)

    def test_disease_location_scope_conflict_blocked(self) -> None:
        reasons = blocking_reasons(_node("n1", "disease", "Полип матки"), _node("n2", "disease", "Полип носа"), [])

        self.assertIn("disease_location_conflict", reasons)


if __name__ == "__main__":
    unittest.main()

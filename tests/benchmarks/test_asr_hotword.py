import unittest

from benchmarks.suites.asr_hotword import (
    EXPECTED_TERM_COUNT,
    REQUIREMENT_ID,
    contains_term,
    evaluate,
    load_dataset,
)


class AsrHotwordBenchmarkTest(unittest.TestCase):
    def test_dataset_contains_fifty_terms_mapped_to_requirement(self):
        terms = load_dataset()

        self.assertEqual(len(terms), EXPECTED_TERM_COUNT)
        self.assertEqual(EXPECTED_TERM_COUNT, 50)
        self.assertEqual(REQUIREMENT_ID, "FR-ASR-09")
        self.assertEqual(len({term.id for term in terms}), len(terms))

    def test_matching_normalizes_case_punctuation_and_yo(self):
        terms = {term.id: term for term in load_dataset()}

        self.assertTrue(
            contains_term(
                "Клиенту выдана ВЫПИСКА ПО СЧЕТУ.",
                terms["bank-050"],
            )
        )
        self.assertTrue(
            contains_term(
                "Назовите си-ви-ви код карты",
                terms["bank-024"],
            )
        )

    def test_reports_term_accuracy_with_and_without_boost(self):
        terms = load_dataset()
        without_boost = {
            term.id: term.term if index % 2 == 0 else "не распознано"
            for index, term in enumerate(terms)
        }
        with_boost = {
            term.id: f"распознано: {term.term}"
            for term in terms
        }

        report = evaluate(terms, without_boost, with_boost)

        self.assertEqual(
            report["without_hotword_boost"]["term_accuracy_percent"],
            50.0,
        )
        self.assertEqual(
            report["with_hotword_boost"]["term_accuracy_percent"],
            100.0,
        )
        self.assertEqual(report["improvement_percentage_points"], 50.0)
        self.assertEqual(report["requirement"], "FR-ASR-09")


if __name__ == "__main__":
    unittest.main()

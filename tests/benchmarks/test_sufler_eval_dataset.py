import json
import unittest
from collections import Counter
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPOSITORY_ROOT / "benchmarks" / "datasets" / "sufler_eval_100.json"


class SuflerEvaluationDatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        cls.cases = cls.dataset["samples"]

    def test_dataset_has_exact_frozen_distribution(self):
        self.assertEqual(len(self.cases), 100)
        self.assertEqual(
            Counter(case["bucket"] for case in self.cases),
            {"no_hint": 25, "scenario": 35, "kb": 40},
        )
        self.assertEqual(
            Counter(
                case["case_type"]
                for case in self.cases
                if case["bucket"] == "no_hint"
            ),
            {"phatic": 20, "personal_question_control": 5},
        )
        self.assertEqual(
            Counter(
                case["case_type"]
                for case in self.cases
                if case["bucket"] == "scenario"
            ),
            {"start": 10, "branch": 20, "off_topic": 5},
        )

    def test_every_case_is_versioned_and_uses_common_schema(self):
        required = {"id", "version", "bucket", "case_type", "input", "expected"}
        ids = []
        for case in self.cases:
            self.assertEqual(set(case), required, case.get("id"))
            self.assertRegex(case["version"], r"^\d+\.\d+\.\d+$")
            self.assertIsInstance(case["input"]["text"], str)
            self.assertTrue(case["input"]["text"].strip())
            self.assertEqual(case["input"]["language"], "ru")
            self.assertIn(
                case["expected"]["route"],
                {"no_hint", "scenario", "knowledge_base"},
            )
            if "prior_turns" in case["input"]:
                self.assertIsInstance(case["input"]["prior_turns"], list)
                self.assertTrue(case["input"]["prior_turns"])
            ids.append(case["id"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_grounding_and_scenario_labels_are_present(self):
        for case in self.cases:
            if case["bucket"] == "kb":
                self.assertTrue(case["expected"].get("source_titles"), case["id"])
                self.assertTrue(
                    case["expected"].get("required_concepts"),
                    case["id"],
                )
            if case["case_type"] in {"start", "branch"}:
                self.assertRegex(
                    case["expected"].get("scenario_code", ""),
                    r"^CC-SCR-\d{3}$",
                )
                self.assertTrue(case["expected"].get("node_id"))


if __name__ == "__main__":
    unittest.main()

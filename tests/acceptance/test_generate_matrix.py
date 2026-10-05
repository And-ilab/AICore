import json
import tempfile
import unittest
from pathlib import Path

from tests.acceptance.generate_matrix import (
    DEFAULT_SOURCE,
    extract_test_cases,
    generate_matrix,
)


class AcceptanceMatrixGeneratorTest(unittest.TestCase):
    def test_finds_at_least_five_ids_in_unified_specification(self):
        source = DEFAULT_SOURCE.read_text(encoding="utf-8")

        test_cases = extract_test_cases(source)

        self.assertGreaterEqual(len(test_cases), 5)
        self.assertTrue(
            all(case["status"] == "pending" for case in test_cases)
        )
        self.assertEqual(
            len({case["id"] for case in test_cases}),
            len(test_cases),
        )

    def test_writes_json_and_markdown_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            json_output = output_directory / "matrix.json"
            markdown_output = output_directory / "matrix.md"

            test_cases = generate_matrix(
                DEFAULT_SOURCE,
                json_output,
                markdown_output,
            )

            self.assertEqual(
                json.loads(json_output.read_text(encoding="utf-8")),
                test_cases,
            )
            markdown = markdown_output.read_text(encoding="utf-8")
            self.assertIn("| id | module | status |", markdown)
            self.assertIn("| pending |", markdown)


if __name__ == "__main__":
    unittest.main()

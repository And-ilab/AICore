import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.acceptance.generate_matrix import (
    DEFAULT_SOURCE,
    REPOSITORY_ROOT,
    extract_test_cases,
    generate_matrix,
)

# Markdown export is gitignored. CI checks the tracked Word specification.
TRACKED_DOCX = (
    REPOSITORY_ROOT / "docs" / "modules" / "ai-hub" / "TZ-unified-v1.8 (МИХ).docx"
)


def docx_plain_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", " ", xml)


def read_specification(source: Path = DEFAULT_SOURCE) -> str:
    if source.is_file():
        return source.read_text(encoding="utf-8")
    if not TRACKED_DOCX.is_file():
        raise FileNotFoundError(
            f"Neither {source} nor {TRACKED_DOCX} is available"
        )
    return docx_plain_text(TRACKED_DOCX)


def specification_path(directory: Path) -> Path:
    if DEFAULT_SOURCE.is_file():
        return DEFAULT_SOURCE
    target = directory / "tz-unified.md"
    target.write_text(read_specification(DEFAULT_SOURCE), encoding="utf-8")
    return target


class AcceptanceMatrixGeneratorTest(unittest.TestCase):
    def test_finds_at_least_five_ids_in_unified_specification(self):
        source = read_specification()

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
                specification_path(output_directory),
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

    def test_missing_markdown_falls_back_to_tracked_docx(self):
        source = read_specification(Path("missing-tz-unified-v1.4.md"))

        test_cases = extract_test_cases(source)

        self.assertGreaterEqual(len(test_cases), 5)
        self.assertIn("SUF-T-01", {case["id"] for case in test_cases})


if __name__ == "__main__":
    unittest.main()

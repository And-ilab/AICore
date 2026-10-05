"""Generate an acceptance-test matrix from the unified specification."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = (
    REPOSITORY_ROOT / "docs" / "modules" / "ai-hub" / "tz-unified-v1.4.md"
)
DEFAULT_JSON_OUTPUT = Path(__file__).with_name("matrix.json")
DEFAULT_MARKDOWN_OUTPUT = Path(__file__).with_name("matrix.md")

TEST_ID_PATTERN = re.compile(
    r"\b(?P<prefix>SUF|CHAT|ASS|DOC|INT)-T-"
    r"(?P<suffix>[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\b"
)

MODULE_BY_PREFIX = {
    "SUF": "sufler",
    "CHAT": "chat",
    "ASS": "assistant",
    "DOC": "documents",
    "INT": "integration",
}


def extract_test_cases(source: str) -> list[dict[str, str]]:
    """Return sorted unique acceptance cases found in Markdown text."""
    test_ids = {
        match.group(0)
        for match in TEST_ID_PATTERN.finditer(source)
    }
    return [
        {
            "id": test_id,
            "module": MODULE_BY_PREFIX[test_id.split("-", maxsplit=1)[0]],
            "status": "pending",
        }
        for test_id in sorted(test_ids)
    ]


def render_markdown(test_cases: list[dict[str, str]]) -> str:
    """Render acceptance cases as a Markdown checklist table."""
    lines = [
        "# Acceptance matrix",
        "",
        "| id | module | status |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| {case['id']} | {case['module']} | {case['status']} |"
        for case in test_cases
    )
    return "\n".join(lines) + "\n"


def generate_matrix(
    source_path: Path = DEFAULT_SOURCE,
    json_output: Path = DEFAULT_JSON_OUTPUT,
    markdown_output: Path = DEFAULT_MARKDOWN_OUTPUT,
) -> list[dict[str, str]]:
    """Parse the specification and write JSON and Markdown matrices."""
    source = source_path.read_text(encoding="utf-8")
    test_cases = extract_test_cases(source)

    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(test_cases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_output.write_text(
        render_markdown(test_cases),
        encoding="utf-8",
    )
    return test_cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the Sufler acceptance matrix from the unified TZ.",
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    test_cases = generate_matrix(args.source, args.json, args.markdown)
    print(f"Generated {len(test_cases)} acceptance cases.")


if __name__ == "__main__":
    main()

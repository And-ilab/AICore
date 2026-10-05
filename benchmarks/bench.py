"""Unified command-line entry point for AI Model Layer benchmarks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.suites import asr, embedding, llm, ocr, qu  # noqa: E402


SuiteRunner = Callable[[], dict[str, Any]]
RUNNERS: dict[str, SuiteRunner] = {
    "asr": asr.run,
    "embedding": embedding.run,
    "qu": qu.run,
    "llm": llm.run,
    "ocr": ocr.run,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bench",
        description="Run Sufler AI Model Layer benchmark suites.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser(
        "run",
        help="Run one benchmark suite and write a JSON report.",
    )
    run_parser.add_argument(
        "--suite",
        choices=tuple(RUNNERS),
        required=True,
        help="Suite to run.",
    )
    run_parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports"),
        help="Report directory (default: reports/).",
    )
    return parser


def write_report(report: dict[str, Any], output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / f"{report['report_id']}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_path


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "run":
        raise RuntimeError(f"Unsupported command: {args.command}")

    report = RUNNERS[args.suite]()
    report_path = write_report(report, args.output)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

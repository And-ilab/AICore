"""Tests for acceptance protocol generator."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tests.acceptance.generate_protocol import (
    generate_protocol,
    load_matrix,
    render_protocol,
    summarize,
    verdict,
)


class GenerateProtocolTest(unittest.TestCase):
    def test_summarize_and_verdict_from_mixed_statuses(self):
        cases = [
            {"id": "SUF-T-01", "module": "sufler", "status": "pass"},
            {"id": "CHAT-T-04", "module": "chat", "status": "fail"},
            {"id": "ASS-T-01", "module": "assistant", "status": "pending"},
            {"id": "DOC-T-01", "module": "documents", "status": "skip"},
        ]
        summary = summarize(cases)
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["by_status"]["pass"], 1)
        self.assertEqual(summary["by_status"]["fail"], 1)
        code, label = verdict(summary)
        self.assertEqual(code, "fail")
        self.assertIn("не пройдена", label)

    def test_verdict_pass_when_only_pass_and_skip(self):
        cases = [
            {"id": "SUF-T-01", "module": "sufler", "status": "pass"},
            {"id": "CHAT-T-04", "module": "chat", "status": "skip"},
        ]
        code, label = verdict(summarize(cases))
        self.assertEqual(code, "pass")
        self.assertIn("пройдена", label)

    def test_render_includes_summary_and_signature_blocks(self):
        cases = [
            {"id": "SUF-T-01", "module": "sufler", "status": "pass"},
            {"id": "CHAT-T-04", "module": "chat", "status": "fail"},
        ]
        markdown = render_protocol(
            cases,
            generated_on=date(2026, 7, 27),
            matrix_path=Path("matrix.json"),
        )
        self.assertIn("# Протокол приёмки программного обеспечения", markdown)
        self.assertIn("## 1. Сводка результатов (pass / fail)", markdown)
        self.assertIn("| pass (пройден) | 1 |", markdown)
        self.assertIn("| fail (не пройден) | 1 |", markdown)
        self.assertIn("SUF-T-01", markdown)
        self.assertIn("CHAT-T-04", markdown)
        self.assertIn("## 5. Подписи сторон", markdown)
        self.assertIn("ОАО «АСБ Беларусбанк»", markdown)
        self.assertIn("ООО «ГС Ритейл»", markdown)
        self.assertIn("| Представитель заказчика |", markdown)
        self.assertIn("| Представитель исполнителя |", markdown)
        self.assertIn("2026-07-27", markdown)

    def test_generate_protocol_writes_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrix_path = root / "matrix.json"
            output_path = root / "protocol.md"
            matrix_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "SUF-T-01",
                            "module": "sufler",
                            "status": "pass",
                        },
                        {
                            "id": "INT-T-AUD-01",
                            "module": "integration",
                            "status": "pending",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = generate_protocol(
                matrix_path,
                output_path,
                generated_on=date(2026, 7, 27),
            )

            self.assertEqual(result["cases"], 2)
            self.assertEqual(result["verdict"], "in_progress")
            text = output_path.read_text(encoding="utf-8")
            self.assertIn("pending (не выполнен)", text)
            self.assertEqual(load_matrix(matrix_path)[0]["id"], "SUF-T-01")


if __name__ == "__main__":
    unittest.main()

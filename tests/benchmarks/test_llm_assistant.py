import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.suites.llm_assistant import main, run


class LlmAssistantBenchmarkTest(unittest.TestCase):
    def test_stub_validates_sse_context_and_tool_call_contracts(self):
        report = run()
        details = report["suite_details"]

        self.assertEqual(report["runner_status"], "stub")
        self.assertEqual(details["profile"], "assistant_bank")
        self.assertTrue(details["contract_passed"])
        self.assertFalse(details["kpi_evidence"])

        context = details["context"]
        self.assertEqual(context["requested_tokens"], 8000)
        self.assertEqual(context["constructed_whitespace_tokens"], 8000)
        self.assertTrue(context["accepted"])

        sse = details["sse"]
        self.assertTrue(sse["valid"])
        self.assertTrue(sse["done_received"])
        self.assertGreater(sse["frames"], 2)
        self.assertGreater(sse["content_chunks"], 0)
        self.assertEqual(sse["status"], "placeholder")

        tool_call = details["tool_call"]
        self.assertTrue(tool_call["valid"])
        self.assertEqual(tool_call["tool_name"], "get_exchange_rate")
        self.assertEqual(tool_call["arguments"], {"currency": "USD"})
        self.assertEqual(tool_call["finish_reason"], "tool_calls")
        self.assertFalse(tool_call["execution_performed"])

    def test_cli_exits_zero_and_writes_json_report(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "reports"
            exit_code = main(["--mode", "stub", "--output", str(output)])
            reports = list(output.glob("llm-assistant-*.json"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(reports), 1)
            payload = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertTrue(payload["suite_details"]["contract_passed"])


if __name__ == "__main__":
    unittest.main()

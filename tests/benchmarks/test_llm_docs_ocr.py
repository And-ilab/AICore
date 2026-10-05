import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.suites.llm_docs_ocr import (
    DEFAULT_DATASET_PATH,
    load_dataset,
    main,
    run,
)
from core.model_gateway import ModelGateway


class PerfectDocsOcrGateway:
    def __init__(self):
        self._profile = ModelGateway.from_registry().get_profile("docs_ocr")

    def get_profile(self, profile):
        if profile != "docs_ocr":
            raise AssertionError(f"Unexpected profile: {profile}")
        return self._profile.__class__(
            profile=self._profile.profile,
            slot_name=self._profile.slot_name,
            model="measured-docs-ocr",
            gateway_mode="openai",
            api_compatibility="openai",
            kpi=self._profile.kpi,
        )

    def chat(self, profile, messages):
        self.get_profile(profile)
        prompt = messages[-1]["content"]
        lines = prompt.splitlines()
        document_type = lines[0].split(": ", 1)[1]
        fields = lines[1].split(": ", 1)[1].split(", ")
        content = json.dumps(
            {
                "document_type": document_type,
                "fields": {field: f"value-{field}" for field in fields},
                "validation": {
                    "status": "valid",
                    "missing_required_fields": [],
                    "anomalies": [],
                },
            },
            ensure_ascii=False,
        )
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ]
        }


class LlmDocsOcrBenchmarkTest(unittest.TestCase):
    def test_dataset_contains_ocr_text_and_field_templates(self):
        samples = load_dataset(DEFAULT_DATASET_PATH)

        self.assertEqual(len(samples), 5)
        self.assertTrue(samples[0]["input"]["ocr_text"])
        self.assertTrue(samples[0]["expected"]["fields"])

    def test_stub_outputs_placeholder_field_accuracy(self):
        report = run()
        details = report["suite_details"]

        self.assertEqual(report["runner_status"], "stub")
        self.assertEqual(details["profile"], "docs_ocr")
        self.assertFalse(details["kpi_evidence"])
        self.assertEqual(
            details["structured_json_validity_percent"],
            100.0,
        )
        self.assertEqual(
            details["field_extraction"]["accuracy_percent"],
            0.0,
        )
        self.assertEqual(
            report["metrics"]["accuracy_percent"]["status"],
            "placeholder",
        )

    def test_measured_gateway_scores_required_field_names(self):
        report = run(gateway=PerfectDocsOcrGateway())
        details = report["suite_details"]

        self.assertEqual(report["runner_status"], "ready")
        self.assertTrue(details["kpi_evidence"])
        self.assertEqual(
            details["field_extraction"]["accuracy_percent"],
            100.0,
        )
        self.assertEqual(
            details["field_extraction"]["precision_percent"],
            100.0,
        )
        self.assertEqual(
            details["document_type_accuracy_percent"],
            100.0,
        )

    def test_cli_writes_json_report(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "reports"
            exit_code = main(["--mode", "stub", "--output", str(output)])
            reports = list(output.glob("llm-docs-ocr-*.json"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(reports), 1)
            payload = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["suite_details"]["profile"], "docs_ocr")


if __name__ == "__main__":
    unittest.main()

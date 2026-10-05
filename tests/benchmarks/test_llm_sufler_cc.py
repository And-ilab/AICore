import json
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from benchmarks.suites.llm_sufler_cc import (  # noqa: E402
    EXPECTED_PROMPT_COUNT,
    run,
)
from core.model_gateway import (  # noqa: E402
    GatewayProfile,
    ModelGateway,
)


class FakeMeasuredGateway:
    def __init__(self):
        stub_profile = ModelGateway.from_registry().get_profile("sufler_cc")
        self.profile = GatewayProfile(
            profile=stub_profile.profile,
            slot_name=stub_profile.slot_name,
            model="measured-test-model",
            gateway_mode="openai",
            api_compatibility="openai",
            kpi=stub_profile.kpi,
        )

    def get_profile(self, _profile):
        return self.profile

    def chat(self, _profile, _messages):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Краткий ответ только по фрагменту СУЗ.",
                    }
                }
            ]
        }


class LlmSuflerCcBenchmarkTest(unittest.TestCase):
    def test_dev_stub_runs_twenty_prompts_without_claiming_kpi(self):
        report = run()
        details = report["suite_details"]

        self.assertEqual(report["runner_status"], "stub")
        self.assertEqual(details["profile"], "sufler_cc")
        self.assertEqual(details["prompt_count"], EXPECTED_PROMPT_COUNT)
        self.assertEqual(EXPECTED_PROMPT_COUNT, 20)
        self.assertEqual(details["characters"]["passed"], 20)
        self.assertEqual(
            report["metrics"]["latency_ms"]["status"],
            "placeholder",
        )
        self.assertIsNone(details["hallucination"]["rate_percent"])
        self.assertFalse(details["kpi_evidence"])

    def test_measured_gateway_and_manual_rubric_produce_kpi_fields(self):
        gateway = FakeMeasuredGateway()
        first_report = run(gateway=gateway)

        with tempfile.TemporaryDirectory() as temporary_directory:
            rubric_path = Path(temporary_directory) / "rubric.json"
            rubric_path.write_text(
                json.dumps(
                    {
                        "reviews": [
                            {
                                "id": result["id"],
                                "response_sha256": result[
                                    "response_sha256"
                                ],
                                "hallucinated": False,
                                "notes": "Grounded in supplied fragment.",
                            }
                            for result in first_report["suite_details"][
                                "results"
                            ]
                        ]
                    }
                ),
                encoding="utf-8",
            )
            report = run(
                gateway=gateway,
                rubric_path=rubric_path,
            )

        details = report["suite_details"]
        self.assertEqual(report["runner_status"], "ready")
        self.assertTrue(details["kpi_evidence"])
        self.assertEqual(details["hallucination"]["rate_percent"], 0)
        self.assertTrue(details["hallucination"]["target_passed"])
        self.assertEqual(
            report["metrics"]["latency_ms"]["status"],
            "measured",
        )


if __name__ == "__main__":
    unittest.main()

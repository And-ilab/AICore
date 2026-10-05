import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from core.model_registry import (  # noqa: E402
    ModelRegistry,
    REQUIRED_DEPLOYMENT_PROFILES,
    REQUIRED_PROFILES,
    REQUIRED_SLOTS,
)


class ModelRegistryTest(unittest.TestCase):
    def test_loads_all_slots_and_gets_asr(self):
        registry = ModelRegistry.load()

        self.assertEqual(set(registry.slots), set(REQUIRED_SLOTS))
        self.assertEqual(set(registry.profiles), set(REQUIRED_PROFILES))
        self.assertEqual(
            set(registry.deployment_profiles),
            set(REQUIRED_DEPLOYMENT_PROFILES),
        )

        asr = registry.get_slot("asr")
        self.assertEqual(asr.name, "asr")
        self.assertEqual(asr.dev_model, "vosk-model-small-ru-0.22")
        self.assertEqual(asr.status, "approved_dev")
        self.assertEqual(asr.kpi["word_accuracy_percent_min"], 90)
        self.assertEqual(asr.kpi["wer_percent_max"], 10)
        self.assertEqual(asr.kpi["latency_p95_ms_max"], 1000)
        approved_dev_slots = {
            "asr",
            "embedding",
            "llm_sufler_cc",
            "llm_assistant_bank",
            "llm_docs_ocr",
        }
        self.assertTrue(
            all(
                slot.status
                == (
                    "approved_dev"
                    if name in approved_dev_slots
                    else "evaluating"
                )
                and slot.prod_candidate is None
                and slot.kpi
                for name, slot in registry.slots.items()
            )
        )

        embedding = registry.get_slot("embedding")
        self.assertEqual(
            embedding.dev_model,
            "intfloat/multilingual-e5-large",
        )
        self.assertIn("recall_at_5_percent_min", embedding.kpi)
        self.assertIsNone(embedding.kpi["recall_at_5_percent_min"])
        self.assertEqual(
            embedding.kpi["chunk_size_candidates_tokens"],
            [256, 512, 1024],
        )
        self.assertEqual(
            embedding.kpi["chunk_overlap_candidates_tokens"],
            [50, 100, 200],
        )
        self.assertEqual(embedding.kpi["optimal_chunk_size_tokens"], 512)
        self.assertEqual(embedding.kpi["optimal_chunk_overlap_tokens"], 100)
        self.assertEqual(
            embedding.kpi["context_inclusion_threshold"],
            0.6,
        )
        self.assertEqual(
            embedding.kpi["deterministic_answer_threshold"],
            0.85,
        )
        self.assertEqual(
            embedding.kpi["retrieval_threshold_status"],
            "dev_frozen",
        )

        profile = registry.get_profile("kb_cc_production")
        self.assertEqual(profile.status, "dev_frozen")
        self.assertEqual(profile.embedding_slot, "embedding")
        self.assertEqual(profile.embedding_model, embedding.dev_model)
        self.assertEqual(profile.chunk_size_tokens, 512)
        self.assertEqual(profile.chunk_overlap_tokens, 100)
        self.assertEqual(profile.context_inclusion_threshold, 0.6)
        self.assertEqual(profile.deterministic_answer_threshold, 0.85)
        self.assertTrue(profile.change_control["benchmark_required"])
        self.assertTrue(profile.change_control["sign_off_required"])

        llm = registry.get_slot("llm_sufler_cc")
        self.assertEqual(llm.kpi["response_chars_max"], 500)
        self.assertEqual(llm.kpi["latency_p95_ms_max"], 2000)
        self.assertEqual(llm.kpi["hallucination_percent_max"], 3)

        deploy = registry.get_deployment_profile("test")
        self.assertEqual(deploy.name, "test")
        self.assertEqual(deploy.status, "approved_dev")
        self.assertFalse(deploy.gpu_required)
        self.assertEqual(deploy.asr_mode, "stub")
        self.assertEqual(deploy.llm_gateway_mode, "stub")
        self.assertIn("sufler_cc", deploy.llm_profiles)


if __name__ == "__main__":
    unittest.main()

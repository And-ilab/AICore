import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.test import TestCase  # noqa: E402

from core.model_gateway import ModelGateway  # noqa: E402
from ingest.models import AssistantProductionChunk, CCProductionChunk  # noqa: E402
from ingest.pipeline import deterministic_embedding  # noqa: E402
from orchestrator.sufler import suggest  # noqa: E402
from qu.models import QuReferenceExample  # noqa: E402


class SuflerKbSlugsTest(TestCase):
    def setUp(self):
        env = patch.dict(
            os.environ,
            {
                "SUFLER_ALLOW_UNGROUNDED": "0",
                "SUFLER_LLM_BASE_URL": "",
                "MODEL_GATEWAY_MODE": "stub",
                "OPENAI_BASE_URL": "",
                "EMBEDDING_MODE": "stub",
            },
            clear=False,
        )
        env.start()
        self.addCleanup(env.stop)

    def test_selected_assistant_kb_grounds_hints(self):
        AssistantProductionChunk.objects.create(
            kb_slug="assistant_cards",
            article_id=3_000_000_101,
            version_id=1,
            chunk_index=0,
            title="Оформление карты",
            content="как оформить карту. Карту Беларусбанка оформляют в отделении с паспортом.",
            permalink="https://kb.local/cards",
            locale="ru",
            visibility_scope=["assistant"],
            checksum="sha256:cards",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(
                "как оформить карту. Карту Беларусбанка оформляют в отделении с паспортом."
            ),
        )
        result = suggest(
            "как оформить карту",
            limit=3,
            gateway=ModelGateway.from_registry(),
            kb_slugs=["assistant_cards"],
        )
        self.assertTrue(result["hints"])
        self.assertEqual(result["kb_slugs"], ["assistant_cards"])
        self.assertIsNone(result["blocked_reason"])
        self.assertEqual(result["hints"][0]["citations"][0]["title"], "Оформление карты")

    def test_short_question_matches_selected_kb_lexically(self):
        AssistantProductionChunk.objects.create(
            kb_slug="assistant_cards",
            article_id=3_000_000_202,
            version_id=1,
            chunk_index=0,
            title="Отделения банка",
            content=(
                "Отделения Беларусбанка принимают клиентов по адресу "
                "проспект Дзержинского 18. Карту оформляют с 14 лет."
            ),
            permalink="https://kb.local/branches",
            locale="ru",
            visibility_scope=["assistant"],
            checksum="sha256:branches",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding("unrelated astronomy nebula"),
        )
        for query in (
            "По какому адресу находится банк?",
            "Со скольки лет?",
        ):
            result = suggest(
                query,
                limit=3,
                gateway=ModelGateway.from_registry(),
                kb_slugs=["assistant_cards"],
            )
            self.assertTrue(result["hints"], query)
            self.assertIsNone(result["blocked_reason"], query)
            self.assertIn("Отделения банка", result["hints"][0]["citations"][0]["title"])

    def test_empty_selection_does_not_invent(self):
        result = suggest(
            "как оформить карту",
            limit=3,
            gateway=ModelGateway.from_registry(),
            kb_slugs=[],
        )
        self.assertEqual(result["hints"], [])
        self.assertEqual(result["blocked_reason"], "sufler_unavailable")
        self.assertEqual(result["latency_ms"]["llm"], 0.0)

    def test_training_example_uses_full_document_not_header(self):
        header = "Заявление об оказании финансовой помощи. Шапка без возраста."
        clause = (
            "В списках на льготный кредит учитываются дети до 23 лет "
            "на дату утверждения списков."
        )
        CCProductionChunk.objects.create(
            article_id=701,
            version_id=1,
            chunk_index=0,
            title="zaiavlenie_ob_okazanii_fp040225.docx",
            content=header,
            permalink="https://kb.local/fp",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum="sha256:fp-h",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(header),
        )
        CCProductionChunk.objects.create(
            article_id=701,
            version_id=1,
            chunk_index=1,
            title="zaiavlenie_ob_okazanii_fp040225.docx",
            content=clause,
            permalink="https://kb.local/fp",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum="sha256:fp-c",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(clause),
        )
        CCProductionChunk.objects.create(
            article_id=702,
            version_id=1,
            chunk_index=0,
            title="08.04.2026_perechen_klienty.doc",
            content="Перечень административных процедур для клиентов банка.",
            permalink="https://kb.local/list",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum="sha256:list",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(
                "Перечень административных процедур для клиентов банка."
            ),
        )
        QuReferenceExample.objects.create(
            question="До скольки лет действует льготный кредит?",
            article_id=701,
            intent_id="Льготный кредит",
            is_active=True,
            status=QuReferenceExample.STATUS_ACTIVE,
        )
        captured: list[str] = []

        class CapturingGateway(ModelGateway):
            def chat(self, profile, messages, **kwargs):
                captured.append(str(messages[1]["content"]))
                raise RuntimeError("force snippet fallback")

        result = suggest(
            "До скольки лет действуют льготные кредиты?",
            limit=3,
            gateway=CapturingGateway.from_registry(),
        )
        self.assertTrue(result["hints"])
        self.assertEqual(
            result["hints"][0]["citations"][0]["title"],
            "zaiavlenie_ob_okazanii_fp040225.docx",
        )
        self.assertIn("23 лет", result["hints"][0]["text"])
        self.assertTrue(captured)
        self.assertIn("23 лет", captured[0])


if __name__ == "__main__":
    unittest.main()

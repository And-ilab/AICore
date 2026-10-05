import json
import logging
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

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client, TestCase  # noqa: E402

from auth.roles import ROLES_BY_CODE  # noqa: E402
from core.embeddings import EmbeddingError  # noqa: E402
from core.model_gateway import ModelGateway  # noqa: E402
from ingest.models import CCProductionChunk  # noqa: E402
from ingest.pipeline import deterministic_embedding  # noqa: E402
from orchestrator.sufler import (  # noqa: E402
    SuflerOrchestratorError,
    _document_supports_query,
    _kb_hint_payload,
    _looks_like_source_dump,
    _parse_llm_hint,
    _safe_ru_en_text,
    suggest,
)
from qu.service import _lexical_score  # noqa: E402


class SuflerSuggestPipelineTest(TestCase):
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

    @staticmethod
    def add_chunk(article_id, title, content):
        return CCProductionChunk.objects.create(
            article_id=article_id,
            version_id=1,
            chunk_index=0,
            title=title,
            content=content,
            permalink=f"https://suz.local/articles/{article_id}",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum=f"sha256:{article_id:064x}",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(content),
        )

    def test_pipeline_returns_hints_citations_and_latency(self):
        query = "как оформить банковскую карту"
        self.add_chunk(11, "Оформление карты", query)
        self.add_chunk(22, "Кредитный договор", "условия кредита")

        with self.assertLogs("orchestrator.sufler", level=logging.INFO) as logs:
            result = suggest(query, limit=3, gateway=ModelGateway.from_registry())

        self.assertEqual(result["profile"], "sufler_cc")
        self.assertEqual(result["kb_id"], "cc_production")
        self.assertGreaterEqual(len(result["hints"]), 1)
        hint = result["hints"][0]
        self.assertTrue(hint["text"].strip())
        self.assertEqual(hint["source_type"], "knowledge_base")
        self.assertTrue(str(hint.get("detail_text") or "").strip())
        self.assertNotIn("Подсказка оператору", hint["text"])
        self.assertIn("оформить", hint["text"].casefold())
        self.assertTrue(hint["citations"])
        self.assertEqual(hint["citations"][0]["title"], "Оформление карты")
        self.assertTrue(
            hint["citations"][0]["permalink"].startswith("https://suz.local/")
        )
        for key in ("qu", "rag", "llm", "total"):
            self.assertIn(key, result["latency_ms"])
            self.assertGreaterEqual(result["latency_ms"][key], 0)
        self.assertTrue(
            any("sufler_suggest_latency" in message for message in logs.output)
        )
        self.assertEqual(result["gateway_model"], "qwen2.5-1.5b-instruct")
        self.assertIsNone(result["blocked_reason"])

    def test_parse_llm_hint_keeps_longer_detail(self):
        answer, tip, detail = _parse_llm_hint(
            "ОТВЕТ:\n"
            "Для ребёнка 6 лет карта оформляется только как дополнительная.\n"
            "ПОДРОБНЕЕ:\n"
            "Для ребёнка 6 лет карта оформляется только как дополнительная "
            "к счёту законного представителя. Выпуск и обслуживание карты "
            "учащегося бесплатные. Оформить можно в отделении с паспортом.\n"
            "СОВЕТ:\n"
            "Сверьте возраст в статье."
        )
        self.assertIn("дополнительная", answer)
        self.assertIn("бесплатн", detail)
        self.assertGreater(len(detail), len(answer))
        self.assertIn("Сверьте", tip)

    def test_kb_detail_is_spoken_not_source_dump(self):
        raw = (
            "Дата сбора: 2026-08-26\n"
            "Источник: https://belarusbank.by/ru/cards/uchenik-belcart/\n"
            "karta-nesovershennoletnego-belarusbank.txt\n"
            "Для ребёнка 6 лет карта оформляется только как дополнительная "
            "к счёту законного представителя. В рамках продукта «Карта учащегося» "
            "выпуск и обслуживание карточки осуществляются бесплатно. "
            "Оформить можно в отделении с паспортом законного представителя."
        )
        self.assertTrue(_looks_like_source_dump(raw))
        payload = _kb_hint_payload(
            rank=1,
            text="Для ребёнка 6 лет карта оформляется только как дополнительная к счёту законного представителя.",
            operator_tip="",
            document={
                "title": "Карта учащегося",
                "content": raw,
                "snippet": raw,
            },
            relevance_score=0.85,
            relevance_percent=85,
            citations=[],
            query="обслуживание карты бесплатное?",
        )
        detail = payload["detail_text"]
        self.assertTrue(detail.strip())
        self.assertNotIn("Дата сбора", detail)
        self.assertNotIn("https://", detail)
        self.assertNotIn(".txt", detail)
        self.assertNotIn("belarusbank.by", detail.casefold())

    def test_empty_text_rejected(self):
        with self.assertRaises(SuflerOrchestratorError):
            suggest("   ")

    def test_limit_five_accepted_limit_six_rejected(self):
        query = "как оформить банковскую карту"
        self.add_chunk(11, "Оформление карты", query)
        result = suggest(query, limit=5, gateway=ModelGateway.from_registry())
        self.assertGreaterEqual(len(result["hints"]), 1)
        with self.assertRaises(SuflerOrchestratorError) as raised:
            suggest(query, limit=6, gateway=ModelGateway.from_registry())
        self.assertIn("between 1 and 5", str(raised.exception))

    def test_only_russian_and_english_letters_are_allowed_in_hints(self):
        self.assertEqual(
            _safe_ru_en_text("Карта Visa работает. Card is active."),
            "Карта Visa работает. Card is active.",
        )
        self.assertEqual(_safe_ru_en_text("Карта 拆康济沙"), "")

    def test_corrupted_cjk_source_never_reaches_hint(self):
        query = "как оформить банковскую карту"
        self.add_chunk(
            77,
            "Оформление карты",
            f"{query}. 拆康济沙壅轰合淋游玲漫蜒甄。",
        )
        result = suggest(query, limit=1, gateway=ModelGateway.from_registry())
        for hint in result["hints"]:
            self.assertNotRegex(hint["text"], r"[\u3400-\u9fff]")

    def test_no_relevant_documents_skip_llm(self):
        # Empty index → unavailable. Irrelevant seeded docs → no_relevant_knowledge.
        with patch(
            "orchestrator.sufler.ModelGateway.chat",
            side_effect=AssertionError("LLM must not be called"),
        ):
            empty = suggest(
                "астрология гороскоп",
                limit=3,
                gateway=ModelGateway.from_registry(),
            )
        self.assertEqual(empty["hints"], [])
        self.assertEqual(empty["blocked_reason"], "sufler_unavailable")
        self.assertEqual(empty["latency_ms"]["llm"], 0.0)

        self.add_chunk(99, "Кредитный договор", "условия потребительского кредита")
        with patch(
            "orchestrator.sufler.ModelGateway.chat",
            side_effect=AssertionError("LLM must not be called"),
        ):
            result = suggest(
                "астрология гороскоп",
                limit=3,
                gateway=ModelGateway.from_registry(),
            )
        self.assertEqual(result["hints"], [])
        self.assertEqual(result["blocked_reason"], "no_relevant_knowledge")
        self.assertEqual(result["latency_ms"]["llm"], 0.0)

    def test_inflected_ru_query_still_finds_article(self):
        self.add_chunk(
            44,
            "Блокировка карты",
            "Заблокировать карту можно в мобильном приложении или по телефону контакт-центра.",
        )
        result = suggest(
            "как заблокировать карту",
            limit=1,
            gateway=ModelGateway.from_registry(),
        )
        self.assertTrue(result["hints"], result.get("blocked_reason"))
        self.assertIsNone(result["blocked_reason"])
        self.assertIn("карт", result["hints"][0]["citations"][0]["title"].casefold())

    def test_lexical_score_matches_card_inflections(self):
        score = _lexical_score(
            "как заблокировать карту",
            "Блокировка карты",
            "Карту блокируют в приложении банка.",
        )
        self.assertGreaterEqual(score, 0.2)

    def test_ungrounded_empty_index_still_returns_hint(self):
        with patch.dict(os.environ, {"SUFLER_ALLOW_UNGROUNDED": "1"}, clear=False):
            result = suggest(
                "Как завести карту банка?",
                limit=3,
                gateway=ModelGateway.from_registry(),
            )
        self.assertTrue(result["hints"])
        self.assertTrue(result["hints"][0]["text"].strip())
        self.assertEqual(result["hints"][0]["citations"], [])
        self.assertIsNone(result["blocked_reason"])

    def test_unrelated_document_is_not_used_as_answer_source(self):
        document = {
            "title": "Комплект документов для физических лиц",
            "content": "Для открытия счёта клиент предъявляет паспорт.",
        }
        self.assertFalse(
            _document_supports_query(document, "Хочу купить биткоин")
        )

    def test_gibberish_with_generic_bank_words_returns_no_hint(self):
        document = {
            "rank": 1,
            "article_id": 8801,
            "chunk_index": 0,
            "title": "Перечень административных процедур Беларусбанка",
            "content": "Для работников банка действует перечень административных процедур.",
            "snippet": "Для работников банка действует перечень административных процедур.",
            "permalink": "https://suz.local/articles/8801",
            "relevance_score": 0.82,
            "relevance_percent": 82,
        }
        with (
            patch(
                "orchestrator.sufler._retrieve_documents",
                return_value=({"documents": [document]}, "cc_production"),
            ),
            patch.dict(os.environ, {"SUFLER_ALLOW_UNGROUNDED": "1"}, clear=False),
        ):
            for index, replica in enumerate(
                ("Хаолд из Беларусь банк", "а он с беларусь банк", "Можете хочу."),
                start=1,
            ):
                with self.subTest(replica=replica):
                    result = suggest(
                        replica,
                        limit=1,
                        session_id=f"gibberish-bank-{index}",
                        gateway=ModelGateway.from_registry(),
                    )
                    self.assertEqual(result["hints"], [])
                    self.assertEqual(result["blocked_reason"], "no_hint_needed")

    def test_meaningful_query_can_answer_without_unrelated_citation(self):
        document = {
            "rank": 1,
            "article_id": 8802,
            "chunk_index": 0,
            "title": "Комплект документов для физических лиц",
            "content": "Для открытия счёта клиент предъявляет паспорт.",
            "snippet": "Для открытия счёта клиент предъявляет паспорт.",
            "permalink": "https://suz.local/articles/8802",
            "relevance_score": 0.81,
            "relevance_percent": 81,
        }
        with (
            patch(
                "orchestrator.sufler._retrieve_documents",
                return_value=({"documents": [document]}, "cc_production"),
            ),
            patch.dict(os.environ, {"SUFLER_ALLOW_UNGROUNDED": "1"}, clear=False),
        ):
            result = suggest(
                "Хочу купить биткоин",
                limit=1,
                gateway=ModelGateway.from_registry(),
            )
        self.assertTrue(result["hints"])
        self.assertEqual(result["hints"][0]["citations"], [])

    def test_self_answer_does_not_attach_random_document(self):
        document = {
            "rank": 1,
            "article_id": 9901,
            "chunk_index": 0,
            "title": "zaiavlenie_ob_okazanii_fp040225.docx",
            "content": (
                "Заявление об оказании финансовой услуги подают в отделении "
                "по форме FP-04. При оформлении приложите паспорт."
            ),
            "snippet": "Заявление об оказании финансовой услуги подают в отделении.",
            "permalink": "https://suz.local/articles/9901",
            "relevance_score": 0.81,
            "relevance_percent": 81,
        }
        gateway = ModelGateway.from_registry()
        with (
            patch(
                "orchestrator.sufler._retrieve_documents",
                return_value=({"documents": [document]}, "cc_production"),
            ),
            patch.object(
                gateway,
                "chat",
                return_value={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "Понимаю, вы передумали оформлять автокредит. "
                                    "В таком случае никаких дополнительных действий "
                                    "не требуется, заявление на оформление не будет подано."
                                )
                            }
                        }
                    ]
                },
            ),
            patch.dict(os.environ, {"SUFLER_ALLOW_UNGROUNDED": "1"}, clear=False),
        ):
            result = suggest(
                "Нет, я передумал оформлять.",
                limit=1,
                gateway=gateway,
            )
        self.assertTrue(result["hints"])
        self.assertIn("передумали", result["hints"][0]["text"].casefold())
        self.assertEqual(result["hints"][0]["citations"], [])

    def test_int_07_accepted_sample_is_never_shown_as_source(self):
        self.add_chunk(
            7007,
            "INT-07 accepted sample",
            "Valid webhook body for INT-07 success check.",
        )
        with patch.dict(os.environ, {"SUFLER_ALLOW_UNGROUNDED": "1"}, clear=False):
            result = suggest(
                "Терминал не принимает карту",
                limit=1,
                gateway=ModelGateway.from_registry(),
            )
        citation_titles = [
            citation["title"]
            for hint in result["hints"]
            for citation in hint["citations"]
        ]
        self.assertNotIn("INT-07 accepted sample", citation_titles)

    def test_commission_fixtures_ignored_and_llm_answers(self):
        self.add_chunk(
            12845,
            "Komissiya za perevod3",
            "Komissiya za perevod mezhdu schetami banka "
            "sostavlyaet 0.5 procenta ot summy operacii.",
        )
        result = suggest(
            "Как оформить карту беларусбанка?",
            limit=3,
            gateway=ModelGateway.from_registry(),
        )
        titles = [
            citation["title"]
            for hint in result["hints"]
            for citation in hint["citations"]
        ]
        self.assertFalse(any("Komissiya" in title for title in titles))
        self.assertTrue(result["hints"])
        self.assertNotIn("0.5 procenta", result["hints"][0]["text"])
        self.assertIsNone(result["blocked_reason"])


class SuflerSuggestApiTest(TestCase):
    url = "/api/v1/sufler/suggest"

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"sufler-suggest-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    @staticmethod
    def add_chunk(article_id, title, content):
        return CCProductionChunk.objects.create(
            article_id=article_id,
            version_id=1,
            chunk_index=0,
            title=title,
            content=content,
            permalink=f"https://suz.local/articles/{article_id}",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum=f"sha256:{article_id:064x}",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(content),
        )

    def test_telephony_operator_receives_hints(self):
        query = "замена пин-кода карты"
        self.add_chunk(44, "Смена ПИН-кода", query)
        client = Client()
        client.force_login(
            self.user_for_role("contact_center_telephony_operator")
        )
        response = client.post(
            self.url,
            data=json.dumps({"text": query, "limit": 3}),
            content_type="application/json",
            HTTP_X_REQUEST_ID="test-suggest-1",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["profile"], "sufler_cc")
        self.assertGreaterEqual(len(body["hints"]), 1)
        self.assertTrue(body["hints"][0]["citations"])
        self.assertIn("latency_ms", body)
        self.assertEqual(response["X-Request-ID"], body["request_id"])

    def test_chat_operator_allowed(self):
        query = "открытие вклада"
        self.add_chunk(55, "Вклады", query)
        client = Client()
        client.force_login(
            self.user_for_role("contact_center_online_chat_operator")
        )
        response = client.post(
            self.url,
            data=json.dumps({"text": query}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kb_id"], "cc_production")

    def test_empty_text_is_rejected(self):
        client = Client()
        client.force_login(
            self.user_for_role("contact_center_telephony_operator")
        )
        response = client.post(
            self.url,
            data=json.dumps({"text": "  "}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "validation_error")

    def test_role_without_sufler_permission_is_rejected(self):
        client = Client()
        client.force_login(
            self.user_for_role("document_recognition_module_administrator")
        )
        response = client.post(
            self.url,
            data=json.dumps({"text": "карта"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "permission_denied")

    def test_http_embedding_outage_ranks_by_text_not_mixed_vectors(self):
        query = "Как оформить карту Беларусь банка?"
        self.add_chunk(
            12845,
            "Komissiya za perevod3",
            "Komissiya za perevod mezhdu schetami banka "
            "sostavlyaet 0.5 procenta ot summy operacii.",
        )
        self.add_chunk(
            91008,
            "Кредитная карта",
            "Как оформить кредитную карту Беларусбанка? "
            "Подайте заявку в отделении или онлайн.",
        )
        client = Client()
        client.force_login(
            self.user_for_role("contact_center_telephony_operator")
        )
        with patch.dict(
            os.environ,
            {
                "EMBEDDING_MODE": "http",
                "EMBEDDING_BASE_URL": "http://embedding:8090",
            },
            clear=False,
        ):
            with patch(
                "core.embeddings._http_embed",
                side_effect=EmbeddingError("down"),
            ):
                response = client.post(
                    self.url,
                    data=json.dumps({"text": query, "limit": 3}),
                    content_type="application/json",
                )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        titles = [
            citation["title"]
            for hint in body["hints"]
            for citation in hint["citations"]
        ]
        self.assertTrue(titles)
        self.assertTrue(any("карта" in title.casefold() for title in titles))
        self.assertFalse(any("Komissiya" in title for title in titles))


if __name__ == "__main__":
    unittest.main()

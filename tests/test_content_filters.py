import json
import os
import sys
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

from assistant.chat import NO_KB_ANSWER, iter_chat_sse  # noqa: E402
from auth.roles import ROLES_BY_CODE  # noqa: E402
from hub.content_filters import (  # noqa: E402
    apply_content_filter_instruction,
    match_content_filter,
    seed_default_content_filters,
)
from hub.models import AssistantContentFilter  # noqa: E402


def parse_sse_content(raw: bytes | str) -> str:
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    content = ""
    for block in text.split("\n\n"):
        block = block.strip("\n")
        if not block.startswith("data:"):
            continue
        payload = block[len("data:") :].strip()
        if payload == "[DONE]":
            continue
        chunk = json.loads(payload)
        delta = chunk["choices"][0]["delta"]
        content += delta.get("content") or ""
    return content


class ContentFilterMatchTest(TestCase):
    def setUp(self):
        seed_default_content_filters(username="test")

    def test_politics_and_religion_block_before_any_model(self):
        politics = match_content_filter("Расскажи про выборы и депутатов")
        religion = match_content_filter("Что такое ислам?")
        self.assertIsNotNone(politics)
        self.assertEqual(politics.code, "politics")
        self.assertIn("Политика", politics.refusal_text)
        self.assertIsNotNone(religion)
        self.assertEqual(religion.code, "religion")

    def test_bank_policy_phrases_are_exceptions(self):
        for question in (
            "Какова кредитная политика по картам?",
            "Расскажи про тарифную политику банка",
            "Нужна кадровая политика",
        ):
            self.assertIsNone(match_content_filter(question), question)

    def test_short_religion_word_does_not_match_inside_another_word(self):
        self.assertIsNone(match_content_filter("Какой богатый клиент получает карту?"))

    def test_disabled_category_is_not_a_hard_block(self):
        AssistantContentFilter.objects.filter(code="religion").update(enabled=False)
        self.assertIsNone(match_content_filter("Расскажи про ислам"))
        self.assertIsNotNone(match_content_filter("Расскажи про выборы"))

    def test_instruction_lists_enabled_topics_and_refusal(self):
        clause = apply_content_filter_instruction(
            [{"role": "system", "content": "Базовый промпт."}]
        )[0]["content"]
        self.assertIn("Базовый промпт.", clause)
        self.assertIn("Политика", clause)
        self.assertIn("Религия", clause)
        self.assertIn("фильтром контента «Религия»", clause)
        self.assertNotIn("ислам", clause)

    def test_instruction_is_absent_when_every_category_is_off(self):
        AssistantContentFilter.objects.update(enabled=False)
        messages = apply_content_filter_instruction(
            [{"role": "system", "content": "Базовый промпт."}]
        )
        self.assertEqual(messages[0]["content"], "Базовый промпт.")


class ContentFiltersApiTest(TestCase):
    url = "/api/admin/assistant/content-filters/"

    def setUp(self):
        seed_default_content_filters(username="test")

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"content-filter-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_module_admin_sees_seeded_categories(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_module_administrator"))
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        codes = [item["code"] for item in response.json()["items"]]
        self.assertEqual(codes, ["politics", "religion"])

    def test_put_roundtrip_disables_and_adds_a_category(self):
        client = Client()
        user = self.user_for_role("llm_knowledge_base_administrator")
        client.force_login(user)
        current = client.get(self.url).json()["items"]
        payload = []
        for item in current:
            payload.append(
                {
                    "code": item["code"],
                    "name": item["name"],
                    "enabled": item["code"] != "religion",
                    "keywords": item["keywords"],
                    "exceptions": item["exceptions"],
                    "refusal_text": item["refusal_text"],
                    "sort_order": item["sort_order"],
                }
            )
        payload.append(
            {
                "code": "violence",
                "name": "Насилие",
                "enabled": True,
                "keywords": ["насили"],
                "exceptions": [],
                "refusal_text": "Не могу обсуждать насилие.",
                "sort_order": 30,
            }
        )
        with patch("audit.service.emit") as emit:
            saved = client.put(
                self.url,
                data=json.dumps({"items": payload}),
                content_type="application/json",
            )
        self.assertEqual(saved.status_code, 200, saved.content)
        body = saved.json()
        self.assertEqual(
            [item["code"] for item in body["items"]],
            ["politics", "religion", "violence"],
        )
        religion = next(item for item in body["items"] if item["code"] == "religion")
        self.assertFalse(religion["enabled"])
        self.assertEqual(religion["updated_by"], user.username)
        self.assertIsNone(match_content_filter("Что такое ислам?"))
        details = emit.call_args.kwargs["details"]
        self.assertEqual(details["categories"], ["politics", "religion", "violence"])
        self.assertNotIn("насили", json.dumps(details))

    def test_enabled_category_without_keywords_is_rejected(self):
        client = Client()
        client.force_login(self.user_for_role("software_administrator"))
        response = client.put(
            self.url,
            data=json.dumps(
                {
                    "items": [
                        {
                            "code": "politics",
                            "name": "Политика",
                            "enabled": True,
                            "keywords": [],
                            "exceptions": [],
                            "refusal_text": "Нет.",
                            "sort_order": 10,
                        }
                    ]
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("items.0.keywords", response.json()["details"])
        self.assertTrue(
            AssistantContentFilter.objects.filter(code="religion").exists()
        )

    def test_analyst_and_contact_center_admin_are_forbidden(self):
        for role in (
            "ai_assistant_analyst",
            "contact_center_module_administrator",
            "document_recognition_module_administrator",
        ):
            client = Client()
            client.force_login(self.user_for_role(role))
            response = client.get(self.url)
            self.assertEqual(response.status_code, 403, role)

    def test_anonymous_request_is_rejected(self):
        response = Client().get(self.url)
        self.assertEqual(response.status_code, 401)


class ContentFilterChatTest(TestCase):
    url = "/api/v1/assistant/chat"

    def setUp(self):
        seed_default_content_filters(username="test")

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"content-chat-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def post_chat(self, message: str):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        return client.post(
            self.url,
            data=json.dumps({"message": message, "stream": True}),
            content_type="application/json",
        )

    def test_dictionary_hit_refuses_without_retrieval(self):
        with patch("audit.service.emit") as emit:
            response = self.post_chat("Расскажи про выборы и депутатов")
            self.assertEqual(response.status_code, 200)
            raw = b"".join(response.streaming_content)
        text = raw.decode("utf-8")
        self.assertNotIn("retrieving", text)
        content = parse_sse_content(raw)
        self.assertIn("фильтром контента «Политика»", content)
        self.assertNotIn("нет информации", content.casefold())
        details = emit.call_args.kwargs["details"]
        self.assertEqual(details, {"category": "politics"})
        self.assertEqual(
            emit.call_args.kwargs["subject"].user_login,
            "content-chat-ai_assistant_user",
        )
        self.assertNotIn("выборы", json.dumps(details))

    def test_bank_policy_question_still_uses_the_knowledge_base_path(self):
        response = self.post_chat("Какова кредитная политика по картам?")
        self.assertEqual(response.status_code, 200)
        content = parse_sse_content(b"".join(response.streaming_content))
        self.assertEqual(content, NO_KB_ANSWER)

    def test_silent_dictionary_adds_topics_to_the_model_prompt(self):
        captured: dict = {}

        def stream(profile, messages, **params):
            del profile, params
            captured["messages"] = messages
            yield (
                "data: "
                + json.dumps(
                    {
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": "Ответ по вкладу."},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )
            yield "data: [DONE]\n\n"

        document = {
            "rank": 1,
            "title": "Вклад",
            "kb_slug": "assistant_hr",
            "article_id": 1,
            "chunk_index": 0,
            "permalink": "https://example.test/deposit",
            "content": "Вклад открывается в отделении.",
            "snippet": "Вклад открывается в отделении.",
            "relevance_score": 0.9,
            "relevance_percent": 90,
        }
        gateway = type("Gateway", (), {"stream": staticmethod(stream)})()
        with patch(
            "assistant.chat.retrieve_assistant_context",
            return_value=([document], 0.2),
        ):
            frames = list(
                iter_chat_sse(
                    [{"role": "user", "content": "Как оформить вклад?"}],
                    gateway=gateway,
                    actor="tester",
                )
            )
        self.assertTrue(frames)
        system = next(
            item["content"]
            for item in captured["messages"]
            if item["role"] == "system"
        )
        self.assertIn("Политика", system)
        self.assertIn("Религия", system)
        self.assertIn("фильтром контента «Политика»", system)

    def test_document_prompt_is_refused(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        response = client.post(
            "/api/v1/assistant/content/from-prompt/",
            data=json.dumps({"message": "Подготовь справку о религии"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "content_filtered")
        self.assertEqual(body["details"]["category"], ["religion"])
        self.assertIn("Религия", body["details"]["request"][0])

    def test_bank_policy_document_is_not_a_content_filter_hit(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        response = client.post(
            "/api/v1/assistant/content/from-prompt/",
            data=json.dumps({"message": "Подготовь справку о кредитной политике"}),
            content_type="application/json",
        )
        if response.status_code == 422:
            self.assertNotEqual(response.json().get("error"), "content_filtered")

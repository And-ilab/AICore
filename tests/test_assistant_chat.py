import json
import os
import sys
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client, TestCase  # noqa: E402

from assistant.openapi import (  # noqa: E402
    SCHEMA_PATH,
    build_openapi_document,
    generate_openapi_yaml,
)
from auth.roles import ROLES_BY_CODE  # noqa: E402
from assistant.chat import (  # noqa: E402
    NO_KB_ANSWER,
    _effective_expand,
    _generation_parameters,
    parse_chat_request,
)
from hub.model_registry_store import get_model_settings  # noqa: E402
from assistant.idp import (  # noqa: E402
    build_attachment_prompt,
    split_fragments,
    wants_summary,
)
from core.model_gateway import STUB_RESPONSES  # noqa: E402


def parse_sse_content(raw: bytes | str) -> tuple[str, bool]:
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    content = ""
    done = False
    for block in text.split("\n\n"):
        block = block.strip("\n")
        if not block or block.startswith(":"):
            continue
        if not block.startswith("data:"):
            continue
        payload = block[len("data:") :].strip()
        if payload == "[DONE]":
            done = True
            continue
        chunk = json.loads(payload)
        delta = chunk["choices"][0]["delta"]
        content += delta.get("content") or ""
    return content, done


class AssistantChatApiTest(TestCase):
    url = "/api/v1/assistant/chat"

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"assistant-chat-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_chat_roundtrip_streams_assistant_bank_tokens(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))

        response = client.post(
            self.url,
            data=json.dumps(
                {
                    "message": "Нужна справка о вкладе",
                    "session_id": "sess-roundtrip-1",
                    "stream": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response["Content-Type"])
        self.assertEqual(response["X-Assistant-Profile"], "assistant_bank")
        self.assertEqual(response["X-Session-ID"], "sess-roundtrip-1")

        raw = b"".join(response.streaming_content)
        content, done = parse_sse_content(raw)
        self.assertTrue(done)
        self.assertEqual(content, NO_KB_ANSWER)
        self.assertIn("нет информации", content.casefold())
        self.assertIn('"sources": []', raw.decode("utf-8"))

    def test_messages_history_roundtrip(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        response = client.post(
            self.url,
            data=json.dumps(
                {
                    "messages": [
                        {"role": "user", "content": "Привет"},
                        {"role": "assistant", "content": "Здравствуйте"},
                        {"role": "user", "content": "Лимит перевода?"},
                    ]
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        content, done = parse_sse_content(b"".join(response.streaming_content))
        self.assertTrue(done)
        self.assertEqual(content, NO_KB_ANSWER)

    def test_parse_expand_flag(self):
        parsed = parse_chat_request({"message": "Автокредит", "stream": True})
        self.assertFalse(parsed["expand"])
        expanded = parse_chat_request(
            {"message": "Автокредит", "stream": True, "expand": True}
        )
        self.assertTrue(expanded["expand"])

    def test_attachment_only_defaults_to_summary(self):
        parsed = parse_chat_request(
            {
                "stream": True,
                "attachments": [
                    {
                        "type": "docx",
                        "name": "fx.docx",
                        "text": "Курс продажи USD 3,2500. Лимит 50 000 BYN в сутки.",
                    }
                ],
            }
        )
        user = parsed["messages"][-1]["content"]
        self.assertIn("Суммаризируй вложение", user)
        self.assertIn("Фрагмент", user)
        self.assertIn("3,2500", user)

    def test_question_uses_document_fragments_not_empty_summary_hint(self):
        prompt = build_attachment_prompt(
            [
                {
                    "name": "fx.docx",
                    "type": "docx",
                    "text": "Для наличного обмена резиденту нужен паспорт. "
                    "SWIFT — это перевод, а не обмен валюты. "
                    "Лимит безналичного обмена 50 000 BYN в сутки.",
                }
            ],
            "Какой лимит безналичного обмена?",
        )
        self.assertFalse(wants_summary("Какой лимит безналичного обмена?"))
        self.assertIn("только по фрагментам", prompt.casefold())
        self.assertIn("50 000", prompt)

    def test_idp_splits_long_document(self):
        words = " ".join(f"слово{index}" for index in range(500))
        fragments = split_fragments(words)
        self.assertGreater(len(fragments), 1)

    def test_expand_uses_higher_token_budget(self):
        short = _generation_parameters()
        long = _generation_parameters(expand=True)
        self.assertGreaterEqual(int(long["max_tokens"]), 2048)
        self.assertGreaterEqual(
            int(long["max_tokens"]), int(short["max_tokens"])
        )

    def test_default_token_budget_grows_eighteen_percent(self):

        with mock.patch.dict(os.environ, {"ASSISTANT_MAX_TOKENS": "256"}, clear=False):
            short = _generation_parameters()
            long = _generation_parameters(expand=True)
        self.assertEqual(int(short["max_tokens"]), 302)
        self.assertGreaterEqual(int(long["max_tokens"]), 4096)
        self.assertGreater(int(long["max_tokens"]), int(short["max_tokens"]))

    def test_default_answer_respects_max_response_chars(self):
        settings = get_model_settings("assistant_bank")
        settings.response_chars_max = 10
        settings.preset = "standard"
        settings.save(update_fields=("response_chars_max", "preset"))

        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        from assistant.chat import _clip_sse_stream, _iter_plain_sse

        long_text = STUB_RESPONSES["assistant_bank"]
        raw = "".join(_clip_sse_stream(_iter_plain_sse(long_text), 10))
        content, done = parse_sse_content(raw)
        self.assertTrue(done)
        self.assertEqual(len(content), 10)
        self.assertEqual(content, long_text[:10])

    def test_expand_ignores_short_char_cap(self):
        settings = get_model_settings("assistant_bank")
        settings.response_chars_max = 10
        settings.preset = "standard"
        settings.save(update_fields=("response_chars_max", "preset"))

        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        from assistant.chat import _iter_plain_sse

        long_text = STUB_RESPONSES["assistant_bank"]
        raw = "".join(_iter_plain_sse(long_text))
        content, done = parse_sse_content(raw)
        self.assertTrue(done)
        self.assertEqual(content, long_text)
        self.assertGreater(len(content), 10)

    def test_no_kb_hit_does_not_invent_answer(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        response = client.post(
            self.url,
            data=json.dumps({"message": "Какая погода на Марсе?", "stream": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        content, done = parse_sse_content(b"".join(response.streaming_content))
        self.assertTrue(done)
        self.assertEqual(content, NO_KB_ANSWER)
        self.assertIn("нет информации", content.casefold())

    def test_long_preset_uses_expand_mode_by_default(self):
        settings = get_model_settings("assistant_bank")
        settings.preset = "long"
        settings.response_chars_max = 10
        settings.save(update_fields=("preset", "response_chars_max"))
        self.assertTrue(_effective_expand(False))
        params = _generation_parameters(expand=_effective_expand(False))
        self.assertGreaterEqual(int(params["max_tokens"]), 4096)

    def test_validation_and_rbac(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        bad = client.post(
            self.url,
            data=json.dumps({"messages": []}),
            content_type="application/json",
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"], "validation_error")

        denied = Client()
        denied.force_login(
            self.user_for_role("contact_center_internal_user")
        )
        response = denied.post(
            self.url,
            data=json.dumps({"message": "hello"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_openapi_schema_generated_and_served(self):
        document = build_openapi_document()
        self.assertEqual(document["openapi"], "3.0.3")
        self.assertIn("/chat", document["paths"])
        self.assertEqual(
            document["paths"]["/chat"]["post"]["operationId"],
            "assistantChatStream",
        )

        written = generate_openapi_yaml()
        self.assertEqual(written, SCHEMA_PATH)
        self.assertTrue(SCHEMA_PATH.exists())
        self.assertIn("/chat", SCHEMA_PATH.read_text(encoding="utf-8"))

        client = Client()
        response = client.get("/api/v1/assistant/openapi.json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["info"]["title"], "AI Assistant API")
        self.assertIn("/chat", body["paths"])

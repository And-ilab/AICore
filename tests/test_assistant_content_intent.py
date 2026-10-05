import json
import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client, TestCase  # noqa: E402

from django.apps import apps  # noqa: E402

from assistant.content_intent import (  # noqa: E402
    classify_prompt,
    extract_topic,
    generate_from_prompt,
)
from assistant.docgen import _pptx_bytes, _split_slides  # noqa: E402
from auth.roles import ROLES_BY_CODE  # noqa: E402
from hub.models import AssistantDocumentTemplate  # noqa: E402


def _seed_assistant_templates() -> None:
    import importlib

    seed_leave = importlib.import_module(
        "hub.migrations.0018_assistant_document_template"
    )
    seed_content = importlib.import_module(
        "hub.migrations.0019_text_slides_diagram_templates"
    )
    seed_leave.seed_templates(apps, None)
    seed_content.seed(apps, None)


class AssistantContentIntentTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _seed_assistant_templates()

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"content-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_classify_and_topic(self):
        self.assertEqual(
            classify_prompt("Подготовьте служебную записку о переносе сроков"),
            "text",
        )
        self.assertEqual(classify_prompt("Нужна справка с места работы"), "text")
        self.assertEqual(
            classify_prompt("Сделай презентацию о запуске ассистента"),
            "slides",
        )
        self.assertEqual(classify_prompt("Нарисуй BPMN процесс выдачи карты"), "diagram")
        self.assertEqual(classify_prompt("ER-диаграмма клиент счёт"), "diagram")
        self.assertIsNone(classify_prompt("Какие ставки по вкладу?"))
        self.assertEqual(
            extract_topic("Подготовьте служебную записку о переносе сроков проекта"),
            "о переносе сроков проекта",
        )

    def test_text_draft_from_prompt(self):
        payload = generate_from_prompt(
            "Подготовьте служебную записку о переносе сроков проекта"
        )
        self.assertEqual(payload["kind"], "text")
        self.assertEqual(payload["output_format"], "txt")
        self.assertIn("переносе сроков проекта", payload["text"])
        self.assertIn("Служебная записка", payload["template_name"])

    def test_slides_and_diagram_files(self):
        slides = generate_from_prompt("Сделай презентацию о запуске ассистента")
        self.assertEqual(slides["kind"], "slides")
        self.assertEqual(slides["output_format"], "pptx")
        self.assertIn("## ", slides["text"])
        chunks = _split_slides(slides["text"])
        self.assertGreaterEqual(len(chunks), 3)
        data = _pptx_bytes(slides["text"])
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = archive.namelist()
            slide1 = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        self.assertIn("ppt/slides/slide1.xml", names)
        self.assertIn("ppt/slides/slide2.xml", names)
        self.assertIn("ppt/theme/theme1.xml", names)
        self.assertIn("ppt/slideLayouts/slideLayout1.xml", names)
        self.assertIn("ppt/slideMasters/slideMaster1.xml", names)
        self.assertIn("<a:off", slide1)
        self.assertIn("<a:t", slide1)
        self.assertTrue(
            any(token in slide1 for token in ("Введение", "Содержание", "Цель")),
            slide1[:500],
        )

        diagram = generate_from_prompt("Собери BPMN диаграмму выдачи карты")
        self.assertEqual(diagram["kind"], "diagram")
        self.assertEqual(diagram["output_format"], "bpmn")
        template = AssistantDocumentTemplate.objects.get(pk=diagram["template_id"])
        from assistant.docgen import build_document

        raw, filename, content_type = build_document(
            template, diagram["fields"], strict=False
        )
        self.assertTrue(filename.endswith(".bpmn"))
        self.assertIn(b"userTask", raw)
        self.assertIn(b"bpmndi:BPMNDiagram", raw)
        self.assertIn("xml", content_type)

    def test_chat_api(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        memo = client.post(
            "/api/v1/assistant/content/from-prompt/",
            data=json.dumps(
                {"message": "Нужна справка о доходах за последний год"}
            ),
            content_type="application/json",
        )
        self.assertEqual(memo.status_code, 200, memo.content)
        body = memo.json()
        self.assertEqual(body["kind"], "text")
        self.assertIn("справк", body["template_name"].casefold())

        skipped = client.post(
            "/api/v1/assistant/content/from-prompt/",
            data=json.dumps({"message": "Какие ставки по вкладу?"}),
            content_type="application/json",
        )
        self.assertEqual(skipped.status_code, 400)

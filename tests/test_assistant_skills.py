import json
import os
import sys
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

from assistant.chat import iter_chat_sse, parse_chat_request  # noqa: E402
from auth.roles import ROLES_BY_CODE  # noqa: E402
from hub.models import AssistantSkill  # noqa: E402
from hub.skill_store import (  # noqa: E402
    ORG_SKILL_PREFIX,
    apply_skill_layer,
    ensure_org_skill_seed,
    skill_instruction_layer,
)


class FakeGateway:
    def __init__(self):
        self.outbound = None

    def stream(self, _profile, outbound, **_kwargs):
        self.outbound = outbound
        yield (
            'data: {"choices":[{"index":0,"delta":{"content":"ok"},'
            '"finish_reason":null}]}\n\n'
        )
        yield "data: [DONE]\n\n"


class AssistantSkillsApiTest(TestCase):
    def user_for_role(self, role_code, username=None):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=username or f"skill-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_seed_has_eight_org_skills(self):
        ensure_org_skill_seed()
        codes = set(
            AssistantSkill.objects.filter(scope="org").values_list("code", flat=True)
        )
        self.assertTrue(
            {
                "SKL-01",
                "SKL-02",
                "SKL-03",
                "SKL-04",
                "SKL-05",
                "SKL-06",
                "SKL-07",
                "SKL-08",
                "SKL-09",
            }.issubset(codes)
        )

    def test_admin_lists_and_toggles_org_skill(self):
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )
        listed = client.get("/api/admin/assistant/skills/")
        self.assertEqual(listed.status_code, 200)
        items = listed.json()["items"]
        self.assertGreaterEqual(len(items), 8)
        zapiska = next(item for item in items if item["code"] == "SKL-01")
        self.assertEqual(zapiska["alias"], "записка")

        disabled = client.patch(
            f"/api/admin/assistant/skills/{zapiska['id']}/",
            data=json.dumps({"enabled": False}),
            content_type="application/json",
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertFalse(disabled.json()["enabled"])

    def test_org_alias_uniqueness(self):
        client = Client()
        client.force_login(
            self.user_for_role("ai_assistant_module_administrator")
        )
        client.get("/api/admin/assistant/skills/")
        created = client.post(
            "/api/admin/assistant/skills/",
            data=json.dumps(
                {
                    "name": "Дубль",
                    "alias": "записка",
                    "instruction": "Другой текст",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 400)

    def test_user_alias_may_collide_with_org(self):
        owner = self.user_for_role("ai_assistant_user", "skill-owner")
        client = Client()
        client.force_login(owner)
        created = client.post(
            "/api/v1/assistant/skills/",
            data=json.dumps(
                {
                    "name": "Моя записка",
                    "alias": "записка",
                    "instruction": "Личный тон",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["scope"], "user")
        self.assertEqual(created.json()["alias"], "записка")

        again = client.post(
            "/api/v1/assistant/skills/",
            data=json.dumps(
                {
                    "name": "Ещё записка",
                    "alias": "записка",
                    "instruction": "Повтор",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 400)

    def test_disabled_org_hidden_in_catalog(self):
        ensure_org_skill_seed()
        skill = AssistantSkill.objects.get(code="SKL-01")
        skill.enabled = False
        skill.save(update_fields=["enabled"])
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user", "catalog-user"))
        catalog = client.get("/api/v1/assistant/skills/")
        self.assertEqual(catalog.status_code, 200)
        aliases = {item["alias"] for item in catalog.json()["items"]}
        self.assertNotIn("записка", aliases)
        self.assertIn("справка", aliases)

    def test_foreign_user_skill_is_404(self):
        owner = self.user_for_role("ai_assistant_user", "skill-owner-a")
        other = self.user_for_role("ai_assistant_user", "skill-owner-b")
        owner_client = Client()
        owner_client.force_login(owner)
        created = owner_client.post(
            "/api/v1/assistant/skills/",
            data=json.dumps(
                {
                    "name": "Секрет",
                    "alias": "sekret",
                    "instruction": "Только мне",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        skill_id = created.json()["id"]

        other_client = Client()
        other_client.force_login(other)
        for method in ("get", "patch", "delete"):
            request = getattr(other_client, method)
            kwargs = {}
            if method == "patch":
                kwargs = {
                    "data": json.dumps({"name": "Хак"}),
                    "content_type": "application/json",
                }
            response = request(f"/api/v1/assistant/skills/{skill_id}/", **kwargs)
            self.assertEqual(response.status_code, 404, method)

        catalog = other_client.get("/api/v1/assistant/skills/")
        aliases = {item["alias"] for item in catalog.json()["items"]}
        self.assertNotIn("sekret", aliases)

    def test_operator_forbidden_admin_skills(self):
        client = Client()
        client.force_login(
            self.user_for_role("contact_center_telephony_operator")
        )
        response = client.get("/api/admin/assistant/skills/")
        self.assertIn(response.status_code, (401, 403))

    def test_alias_normalization_and_instruction_layer(self):
        ensure_org_skill_seed()
        skill = AssistantSkill.objects.get(code="SKL-01")
        layer = skill_instruction_layer(skill)
        self.assertTrue(layer.startswith(ORG_SKILL_PREFIX))
        self.assertIn("служебную записку", layer.casefold())
        messages = apply_skill_layer(
            [{"role": "system", "content": "assistant_bank"}],
            layer,
        )
        self.assertIn("Навык:", messages[0]["content"])
        self.assertIn("assistant_bank", messages[0]["content"])
        translate = skill_instruction_layer(AssistantSkill.objects.get(code="SKL-08"))
        self.assertNotIn("Отвечай по-русски", translate)
        self.assertIn("английском", translate.casefold())

    def test_parse_skill_id_and_inject_into_llm(self):
        parsed = parse_chat_request(
            {"message": "оформи", "stream": True, "skill_id": 12}
        )
        self.assertEqual(parsed["skill_id"], 12)
        with self.assertRaises(Exception):
            parse_chat_request(
                {"message": "оформи", "stream": True, "skill_id": "записка"}
            )

        ensure_org_skill_seed()
        skill = AssistantSkill.objects.get(code="SKL-01")
        gateway = FakeGateway()
        list(
            iter_chat_sse(
                [{"role": "user", "content": "нужна записка"}],
                gateway=gateway,
                skill_instruction=skill_instruction_layer(skill),
            )
        )
        self.assertIsNotNone(gateway.outbound)
        system = next(
            item["content"]
            for item in gateway.outbound
            if item.get("role") == "system"
        )
        self.assertIn(ORG_SKILL_PREFIX[:20], system)
        self.assertIn("служебную записку", system.casefold())

    def test_chat_rejects_foreign_skill(self):
        owner = self.user_for_role("ai_assistant_user", "chat-owner")
        other = self.user_for_role("ai_assistant_user", "chat-other")
        owner_client = Client()
        owner_client.force_login(owner)
        created = owner_client.post(
            "/api/v1/assistant/skills/",
            data=json.dumps(
                {
                    "name": "Личный",
                    "alias": "lichny",
                    "instruction": "Только автор",
                }
            ),
            content_type="application/json",
        )
        skill_id = created.json()["id"]
        other_client = Client()
        other_client.force_login(other)
        response = other_client.post(
            "/api/v1/assistant/chat",
            data=json.dumps(
                {
                    "message": "привет",
                    "stream": True,
                    "skill_id": skill_id,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("skill_not_available", response.json()["details"]["request"][0])

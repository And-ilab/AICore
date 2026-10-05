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

from auth.roles import ROLES_BY_CODE  # noqa: E402
from ingest.models import AssistantProductionChunk, CCProductionChunk  # noqa: E402
from ingest.pipeline import deterministic_embedding  # noqa: E402
from qu.models import QuReferenceExample  # noqa: E402
from qu.service import extractive_answer  # noqa: E402


class ExtractiveAnswerTest(TestCase):
    def test_calendar_days_beat_certificate_form_header(self):
        header = (
            "СПРАВКА для получения кредита в ОАО «АСБ Беларусбанк». "
            "Фамилия ________ Имя ________ Отчество ________ "
            "Место работы ________ должность ________ " + ("_____ " * 40)
        )
        clause = (
            "Срок действия справки для получения кредита составляет "
            "30 календарных дней после ее выдачи (оформления). "
            "Справка выдается администрацией юридического лица по месту "
            "работы (учебы, установления пенсии) кредитополучателя."
        )
        text = extractive_answer(
            f"{header} {clause}",
            "Сколько дней действует справка для получения кредита в Беларусбанке?",
        )
        self.assertIn("30", text)
        self.assertIn("календарных дней", text)
        self.assertNotIn("____", text)


class QuPreviewIntegrationTest(TestCase):
    url = "/api/admin/qu/preview/"

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"qu-preview-{role_code}",
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

    def test_admin_receives_ranked_percent_and_matched_example(self):
        query = "оформление отпуска сотруднику"
        self.add_chunk(101, "Положение об отпусках", query)
        self.add_chunk(202, "Регламент банковских карт", "замена банковской карты")
        example = QuReferenceExample.objects.create(
            question="Как оформить отпуск сотруднику?",
            article_id=101,
            intent_id="HR-LEAVE",
        )
        QuReferenceExample.objects.create(
            question="Как заменить банковскую карту?",
            article_id=202,
            intent_id="CARD-REPLACE",
        )
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )

        response = client.post(
            self.url,
            data=json.dumps({"query": query, "limit": 5}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["kb_id"], "all_knowledge_bases")
        self.assertEqual(body["documents"][0]["article_id"], 101)
        self.assertEqual(body["documents"][0]["relevance_percent"], 100)
        self.assertEqual(
            body["documents"][0]["matched_example"],
            example.question,
        )
        self.assertEqual(
            body["documents"][0]["matched_example_id"],
            example.pk,
        )
        scores = [
            document["relevance_score"] for document in body["documents"]
        ]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_training_example_pins_article_and_keeps_deep_clause(self):
        header = "Заявление об оказании финансовой помощи. Шапка бланка без возраста."
        clause = (
            "В списках на льготный кредит учитываются дети до 23 лет "
            "на дату утверждения списков."
        )
        CCProductionChunk.objects.create(
            article_id=501,
            version_id=1,
            chunk_index=0,
            title="zaiavlenie_ob_okazanii_fp040225.docx",
            content=header,
            permalink="https://kb.local/fp",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum="sha256:fp-0",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(header),
        )
        CCProductionChunk.objects.create(
            article_id=501,
            version_id=1,
            chunk_index=1,
            title="zaiavlenie_ob_okazanii_fp040225.docx",
            content=clause,
            permalink="https://kb.local/fp",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum="sha256:fp-1",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(clause),
        )
        self.add_chunk(
            502,
            "08.04.2026_perechen_klienty.doc",
            "Перечень административных процедур ОАО АСБ Беларусбанк для клиентов.",
        )
        QuReferenceExample.objects.create(
            question="До скольки лет действует льготный кредит?",
            article_id=501,
            intent_id="Льготный кредит",
            is_active=True,
            status=QuReferenceExample.STATUS_ACTIVE,
        )
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )
        response = client.post(
            self.url,
            data=json.dumps(
                {"query": "До скольки лет действуют льготные кредиты?", "limit": 5}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        top = body["documents"][0]
        self.assertEqual(top["article_id"], 501)
        self.assertGreaterEqual(top["relevance_percent"], 80)
        self.assertIn("23 лет", top["snippet"])
        self.assertIn("23 лет", top["content"])
        self.assertEqual(
            top["matched_example"],
            "До скольки лет действует льготный кредит?",
        )
        self.assertIsNotNone(body.get("hint"))
        self.assertIn("23 лет", body["hint"]["text"])

    def test_preview_hint_uses_answering_clause_not_form_header(self):
        header = (
            "________________ (наименование подразделения) ОАО «АСБ Беларусбанк» "
            "ЗАЯВЛЕНИЕ __.__.20__ Об оказании финансовой помощи. "
            "Прошу оказать финансовую помощь государства в погашении задолженности "
            "по льготному кредиту, выданному ________________. " + ("_____ " * 80)
        )
        clause = (
            "В списках на льготный кредит учитываются дети до 23 лет "
            "на дату утверждения списков."
        )
        CCProductionChunk.objects.create(
            article_id=511,
            version_id=1,
            chunk_index=0,
            title="zaiavlenie_ob_okazanii_fp040225.docx",
            content=header,
            permalink="https://kb.local/fp-header",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum="sha256:fp-header",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(header),
        )
        CCProductionChunk.objects.create(
            article_id=511,
            version_id=1,
            chunk_index=4,
            title="zaiavlenie_ob_okazanii_fp040225.docx",
            content=clause,
            permalink="https://kb.local/fp-clause",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum="sha256:fp-clause",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(clause),
        )
        QuReferenceExample.objects.create(
            question="До скольки лет учитываются дети по льготному кредиту?",
            article_id=511,
            intent_id="Льготный кредит",
            is_active=True,
            status=QuReferenceExample.STATUS_ACTIVE,
        )
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )
        response = client.post(
            self.url,
            data=json.dumps(
                {
                    "query": "До скольки лет учитываются дети по льготному кредиту?",
                    "limit": 5,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        hint = (body.get("hint") or {}).get("text") or ""
        self.assertIn("23 лет", hint)
        self.assertNotIn("ЗАЯВЛЕНИЕ", hint)

    def test_preview_hint_uses_calendar_days_not_certificate_header(self):
        header = (
            "СПРАВКА для получения кредита в ОАО «АСБ Беларусбанк». "
            "Фамилия ________ Имя ________ место работы ________ " + ("_____ " * 50)
        )
        filler = "Кредитополучатель заполняет шапку бланка справки для получения кредита."
        clause = (
            "Срок действия справки для получения кредита составляет "
            "30 календарных дней после ее выдачи (оформления). "
            "Справка выдается администрацией юридического лица по месту работы."
        )
        title = "spravka_dlya_polucheniya_kredita_oformleniya_v_oao_asb_belarusbank.doc"
        for index, content in enumerate([header, filler, filler, filler, clause]):
            CCProductionChunk.objects.create(
                article_id=701,
                version_id=1,
                chunk_index=index,
                title=title,
                content=content,
                permalink="https://kb.local/spravka",
                locale="ru",
                visibility_scope=["kc_operator"],
                checksum=f"sha256:spravka-{index}",
                embedding_model="deterministic-dev",
                embedding=deterministic_embedding(content),
            )
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )
        response = client.post(
            self.url,
            data=json.dumps(
                {
                    "query": "Сколько дней действует справка для получения кредита?",
                    "limit": 5,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        hint = (response.json().get("hint") or {}).get("text") or ""
        self.assertIn("30", hint)
        self.assertIn("календарных дней", hint)
        self.assertNotIn("____", hint)

    def test_unrelated_query_is_not_pinned_by_other_etalon(self):
        self.add_chunk(
            501,
            "zaiavlenie_ob_okazanii_fp040225.docx",
            "В списках на льготный кредит учитываются дети до 23 лет.",
        )
        self.add_chunk(
            601,
            "spravka_dlya_polucheniya_kredita_oformleniya_v_oao_asb_belarusbank.doc",
            "Справка для получения кредита в ОАО АСБ Беларусбанк действует 30 календарных дней после выдачи.",
        )
        QuReferenceExample.objects.create(
            question="До скольки лет действует льготный кредит?",
            article_id=501,
            intent_id="Льготный кредит",
            is_active=True,
            status=QuReferenceExample.STATUS_ACTIVE,
        )
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )
        response = client.post(
            self.url,
            data=json.dumps(
                {
                    "query": "Сколько дней действует справка для кредита в Беларусбанке?",
                    "limit": 5,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        top = body["documents"][0]
        self.assertEqual(top["article_id"], 601)
        self.assertIn("30", body["hint"]["text"])
        self.assertNotEqual(top["relevance_percent"], 86)

    def test_preview_pins_assistant_file_not_only_suz(self):
        self.add_chunk(
            80,
            "Пин-код карты",
            "Пин-код банковской карты выдают в отделении и меняют в банкомате.",
        )
        assistant_id = 3_000_000_414
        komplekt = (
            "Документом, удостоверяющим личность, является паспорт "
            "гражданина Республики Беларусь или вид на жительство."
        )
        AssistantProductionChunk.objects.create(
            kb_slug="assistant_komplekt_dokumentov",
            article_id=assistant_id,
            version_id=1,
            chunk_index=0,
            title="komplekt-dokumentov-fizicheskih-lic.txt",
            content=komplekt,
            permalink="https://kb.local/komplekt",
            locale="ru",
            visibility_scope=["assistant"],
            checksum="sha256:komplekt",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(komplekt),
        )
        QuReferenceExample.objects.create(
            question="Какой документ удостоверяет личность?",
            article_id=assistant_id,
            intent_id="Удостоверение личности",
            is_active=True,
            status=QuReferenceExample.STATUS_ACTIVE,
        )
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )
        response = client.post(
            self.url,
            data=json.dumps(
                {"query": "Какой документ удостоверяет личность?", "limit": 5}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["kb_id"], "all_knowledge_bases")
        top = body["documents"][0]
        self.assertEqual(top["article_id"], assistant_id)
        self.assertEqual(top["title"], "komplekt-dokumentov-fizicheskih-lic.txt")
        self.assertIn("паспорт", (body.get("hint") or {}).get("text", "").casefold())
        self.assertNotEqual(top["title"], "Пин-код карты")

    def test_empty_query_is_rejected(self):
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )
        response = client.post(
            self.url,
            data=json.dumps({"query": "   "}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "validation_error")

    def test_role_without_qu_permission_is_rejected(self):
        client = Client()
        client.force_login(
            self.user_for_role("contact_center_module_administrator")
        )
        response = client.post(
            self.url,
            data=json.dumps({"query": "отпуск"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_anonymous_request_is_rejected(self):
        response = Client().post(
            self.url,
            data=json.dumps({"query": "отпуск"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

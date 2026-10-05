import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import Client, TestCase, override_settings  # noqa: E402

from auth.roles import ROLES_BY_CODE  # noqa: E402
from ocr.engine import _ocr_text_quality, recognize_document  # noqa: E402
from ocr.extraction import extract_passport_fields, extract_fields  # noqa: E402
from ocr.structuring import structure_document  # noqa: E402
from ocr.page_templates import detect_page_kind, extract_from_pages  # noqa: E402
from ocr.models import OcrDocumentTemplate, OcrJob  # noqa: E402
from ocr.templates_registry import seed_templates_from_yaml  # noqa: E402


PASSPORT_TEXT = """\
ПАСПОРТ РЕСПУБЛИКИ БЕЛАРУСЬ
Фамилия: ИВАНОВ
Имя: ИВАН
Отчество: ИВАНОВИЧ
Серия: MP
Номер: 4123456
Дата выдачи: 12.03.2019
"""


class OcrExtractionUnitTest(TestCase):
    def test_passport_fields_and_confidence(self):
        fields = extract_passport_fields(PASSPORT_TEXT)
        self.assertEqual(fields["full_name"]["value"], "ИВАНОВ ИВАН ИВАНОВИЧ")
        self.assertGreaterEqual(fields["full_name"]["confidence"], 0.9)
        self.assertEqual(fields["series"]["value"], "MP")
        self.assertEqual(fields["number"]["value"], "4123456")
        self.assertEqual(fields["issue_date"]["value"], "12.03.2019")

    def test_registration_page_is_passport_with_address(self):
        text = (
            "МЕСТО ЖИТЕЛЬСТВА / ПРОПИСКА\n"
            "Зарегистрирован: г. Минск, ул. Ленина, д. 1, кв. 12\n"
        )
        self.assertEqual(detect_page_kind(text), "passport_registration")
        doc_type, fields = extract_fields(text, filename="passport_page3.jpg")
        self.assertEqual(doc_type, "passport")
        self.assertIn("минск", str(fields["address"]["value"]).casefold())

    def test_rf_registration_stamp_fills_address_not_fio(self):
        text = (
            "МЕСТО ЖИТЕЛЬСТВА\n"
            "ЗАРЕГИСТРИРОВАН\n"
            "16 Ноября 2010г.\n"
            "Рег-и: УДМУРТСКАЯ РЕСП.\n"
            "ГОР. ВОТКИНСК\n"
            "Улица: УЛ. 1905ГОДА\n"
            "дом : 26 Кор: — Кв: —\n"
            "ОТДЕЛ УФМС РОССИИ\n"
            "ПО УДМУРТСКОЙ РЕСПУБЛИКЕ\n"
            "В ГОРОДЕ ВОТКИНСКЕ\n"
            "94 11 207471\n"
        )
        self.assertEqual(detect_page_kind(text), "passport_registration")
        doc_type, fields = extract_fields(text)
        self.assertEqual(doc_type, "passport")
        self.assertNotIn("full_name", fields)
        self.assertIn("воткинск", str(fields["address"]["value"]).casefold())
        self.assertEqual(fields["registration_date"]["value"], "16.11.2010")
        self.assertEqual(fields["series"]["value"], "94 11")
        self.assertEqual(fields["number"]["value"], "207471")
        self.assertIn("УФМС", str(fields["issued_by"]["value"]).upper())

    def test_ocr_quality_prefers_readable_cyrillic(self):
        junk = "ссегисгрировн\nЧМРТСКая\nPECI\nBOгкИHCK"
        good = "МЕСТО ЖИТЕЛЬСТВА\nЗАРЕГИСТРИРОВАН\nУДМУРТСКАЯ РЕСП."
        self.assertGreater(_ocr_text_quality(good), _ocr_text_quality(junk))
        self.assertLess(_ocr_text_quality(junk), 0.45)

    def test_mixed_script_stamp_is_not_a_name(self):
        fields = extract_passport_fields("ЧМРТСКая\nPECI\nBOгкИHCK")
        self.assertNotIn("full_name", fields)

    def test_any_document_colon_pairs_become_fields(self):
        text = (
            "Выписка из Единого государственного реестра недвижимости\n"
            "Кадастровый номер: 77:01:0004014:2714\n"
            "Адрес: 123242 Москва, р-н Пресненский\n"
            "Площадь: 34\n"
            "Назначение: Жилое помещение\n"
        )
        doc_type, fields = extract_fields(text, filename="egrn.png")
        self.assertNotEqual(doc_type, "account_statement")
        self.assertEqual(fields["кадастровый_номер"]["value"], "77:01:0004014:2714")
        self.assertIn("москва", str(fields["address"]["value"]).casefold())
        self.assertEqual(fields["площадь"]["value"], "34")
        self.assertEqual(fields["purpose"]["value"], "Жилое помещение")

    def test_belarus_passport_header_duplicates_collapse(self):
        from ocr.page_templates import collapse_extracted_fields

        collapsed = collapse_extracted_fields(
            {
                "surname": {"value": "SAYAPIN", "confidence": 0.96, "label": "Фамилия"},
                "given_name": {"value": "ANDREI", "confidence": 0.96, "label": "Имя"},
                "document_number": {
                    "value": "MP2417879",
                    "confidence": 0.96,
                    "label": "Номер документа",
                },
                "expiry date": {
                    "value": "26.04.2028",
                    "confidence": 0.9,
                    "label": "expiry date",
                },
                "пашпарт_тип_type": {
                    "value": "P BLR MP2417879",
                    "confidence": 0.8,
                    "label": (
                        "ПАШПАРТ ТИП/TYPE — КОД ДЗЯРЖАВЫ/CODE OF ISSUING — "
                        "НУМАР ПАШПАРТА/PASSPORT No."
                    ),
                },
                "прэзвішча_surname": {
                    "value": "ЗАУАРТМ",
                    "confidence": 0.8,
                    "label": "ПРЭЗВІШЧА SURNAME",
                },
                "bougiven_names": {
                    "value": "ANDREI",
                    "confidence": 0.8,
                    "label": "BOUGIVEN NAMES",
                },
            }
        )
        self.assertEqual(collapsed["surname"]["value"], "SAYAPIN")
        self.assertEqual(collapsed["given_name"]["value"], "ANDREI")
        self.assertEqual(collapsed["expiry_date"]["value"], "26.04.2028")
        self.assertEqual(collapsed["expiry_date"]["label"], "Срок действия")
        self.assertNotIn("пашпарт_тип_type", collapsed)
        self.assertNotIn("bougiven_names", collapsed)
        self.assertEqual(collapsed["surname"]["label"], "Фамилия")

    def test_belarus_visual_zone_without_mrz(self):
        text = (
            "REPUBLIC OF BELARUS\n"
            "TYPE/TYP P\n"
            "CODE OF ISSUING STATE BLR\n"
            "PASSPORT NO. / НУМАР ПАШПАРТА\n"
            "KH2430485\n"
            "SURNAME / ПРОЗВІШЧА\n"
            "HUTSU\n"
            "GIVEN NAMES / ІМЯ\n"
            "ALEH\n"
            "NATIONALITY / ГРАМАДЗЯНСТВА\n"
            "BELARUS\n"
            "DATE OF BIRTH / ДАТА НАРАДЖЭННЯ\n"
            "23 02 1992\n"
            "SEX / ПОЛ M\n"
            "DATE OF ISSUE / ДАТА ВЫДАЧЫ\n"
            "07 03 2012\n"
            "DATE OF EXPIRY / ДАТА СКАНЧЭННЯ ТЭРМІНУ\n"
            "07 03 2022\n"
        )
        fields = extract_passport_fields(text, allow_name_guess=False)
        self.assertEqual(fields["series"]["value"], "KH")
        self.assertEqual(fields["number"]["value"], "2430485")
        self.assertEqual(fields["birth_date"]["value"], "23.02.1992")
        self.assertEqual(fields["issue_date"]["value"], "07.03.2012")
        self.assertEqual(fields["surname"]["value"].upper(), "HUTSU")
        self.assertEqual(fields["given_name"]["value"].upper(), "ALEH")

    def test_issue_date_on_same_line_as_bilingual_label(self):
        text = (
            "SURNAME / ПРОЗВІШЧА HUTSU\n"
            "GIVEN NAMES / ІМЯ ALEH\n"
            "PASSPORT NO. / НУМАР ПАШПАРТА KH2430485\n"
            "DATE OF BIRTH / ДАТА НАРАДЖЭННЯ 23 02 1992\n"
            "DATE OF ISSUE / ДАТА ВЫДАЧЫ 12 09 2014\n"
            "DATE OF EXPIRY / ДАТА СКАНЧЭННЯ 12 09 2024\n"
        )
        fields = extract_passport_fields(text, allow_name_guess=False)
        self.assertEqual(fields["issue_date"]["value"], "12.09.2014")
        self.assertEqual(fields["birth_date"]["value"], "23.02.1992")

    def test_issue_date_from_leftover_when_mrz_has_birth_and_expiry(self):
        text = (
            "HUTSU ALEH\n"
            "KH2430485\n"
            "12 09 2014\n"
            "P<BLRHUTSU<<ALEH<<<<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
            "KH24304857BLR9202231M24091233230292A012PB64<\n"
        )
        fields = extract_passport_fields(text, allow_name_guess=False)
        self.assertEqual(fields["birth_date"]["value"], "23.02.1992")
        self.assertEqual(fields["expiry_date"]["value"], "12.09.2024")
        self.assertEqual(fields["issue_date"]["value"], "12.09.2014")

    def test_chained_ocr_fragments_are_not_fields(self):
        text = (
            "слкд\n"
            "еспылика\n"
            "едруһ\n"
            "EeHUBiL\n"
            "or\n"
            "Ee\n"
            "ħ\n"
            "Refhli\n"
            "E\n"
            "ereeh\n"
        )
        _doc_type, fields = extract_fields(text, filename="97a49ec0.jpg")
        self.assertFalse(fields)

    def test_bank_statement_still_detected_with_account_signals(self):
        text = (
            "Выписка по счёту\n"
            "Счёт: BY13AKBB30141000015730000000\n"
            "Входящий остаток: 1 050.00\n"
        )
        doc_type, fields = extract_fields(text)
        self.assertEqual(doc_type, "account_statement")
        self.assertIn("1050", str(fields["opening_balance"]["value"]).replace(" ", ""))

    def test_generic_payment_fields_without_forced_type(self):
        text = (
            "Платёжное поручение № 42\n"
            "Плательщик: ООО Ромашка\n"
            "Получатель: ОАО Банк\n"
            "Сумма: 1500.00\n"
            "Валюта: BYN\n"
            "Назначение: Оплата по договору\n"
        )
        doc_type, fields = extract_fields(text)
        self.assertEqual(doc_type, "payment_order")
        self.assertEqual(fields["amount"]["value"], "1500.00")
        self.assertIn("Ромашка", str(fields["payer"]["value"]))

    def test_latin_filename_detects_payment_order(self):
        doc_type, _fields = extract_fields(
            "Номер: 184726\nДата: 02.09.2026\n",
            filename="09_platezhnoe_poruchenie.png",
        )
        self.assertEqual(doc_type, "payment_order")

    def test_multipage_merge_data_and_registration(self):
        data = "ПАСПОРТ\nФамилия: ИВАНОВ\nИмя: ИВАН\nСерия: MP\nНомер: 4123456\n"
        regist = "Прописка\nАдрес: г. Брест, ул. Советская, 5\n"
        doc_type, fields, kinds = extract_from_pages(
            [data, regist],
            filename="passport.pdf",
        )
        self.assertEqual(doc_type, "passport")
        self.assertIn("passport_registration", kinds)
        combined_type, combined = extract_fields(
            data + "\n" + regist,
            filename="passport.pdf",
            pages=[data, regist],
        )
        self.assertEqual(combined_type, "passport")
        self.assertEqual(combined["series"]["value"], "MP")
        self.assertIn("брест", str(combined["address"]["value"]).casefold())

    def test_recognize_keeps_embedded_text_and_page_list(self):
        result = recognize_document(
            "Платёжное поручение #42\nAmount: 1500.00 BYN\n".encode("utf-8"),
            filename="scan.png",
            content_type="image/png",
            document_id="doc-1",
            job_id="ocrjob-1",
            sha256="a" * 64,
        )
        self.assertGreaterEqual(result["ocr_engine"]["pages_processed"], 1)
        self.assertIn("1500.00", result["pages"][0]["text"])

    def test_detect_type_from_filename(self):
        doc_type, fields = extract_fields(
            "Фамилия: ПЕТРОВ\nИмя: ПЁТР\nСерия: AB\nНомер: 7654321\n"
            "Дата выдачи: 01.01.2020",
            filename="passport_scan.png",
        )
        self.assertEqual(doc_type, "passport")
        self.assertIn("full_name", fields)

    def test_passport_fields_without_labels(self):
        """Phone-photo OCR often drops labels — recover FIO / ID / date."""
        fields = extract_passport_fields(
            "РЕСПУБЛИКА БЕЛАРУСЬ\n"
            "ИВАНОВ ИВАН ИВАНОВИЧ\n"
            "PD 0000000\n"
            "12.03.2019\n"
        )
        self.assertEqual(fields["full_name"]["value"], "ИВАНОВ ИВАН ИВАНОВИЧ")
        self.assertEqual(fields["series"]["value"], "PD")
        self.assertEqual(fields["number"]["value"], "0000000")
        self.assertEqual(fields["issue_date"]["value"], "12.03.2019")

    def test_russian_passport_multiline_labels(self):
        """RF passport: labels on one line, values on the next; series 45 11."""
        fields = extract_passport_fields(
            "ПАСПОРТ\n"
            "Фамилия\n"
            "АНАНД\n"
            "Имя\n"
            "ОМКАР\n"
            "Отчество\n"
            "ВИКТОРОВИЧ\n"
            "Пол\n"
            "МУЖ.\n"
            "Дата рождения\n"
            "16.09.1988\n"
            "Место рождения\n"
            "ГОРОД МОСКВА\n"
            "45 11 532704\n"
        )
        self.assertEqual(fields["full_name"]["value"], "АНАНД ОМКАР ВИКТОРОВИЧ")
        self.assertEqual(fields["surname"]["value"], "АНАНД")
        self.assertEqual(fields["given_name"]["value"], "ОМКАР")
        self.assertEqual(fields["patronymic"]["value"], "ВИКТОРОВИЧ")
        self.assertEqual(fields["series"]["value"], "45 11")
        self.assertEqual(fields["number"]["value"], "532704")
        self.assertEqual(fields["birth_date"]["value"], "16.09.1988")
        self.assertNotEqual(fields["full_name"]["value"], "ГОРОД МОСКВА")

    def test_belarus_passport_mrz_not_header(self):
        """English header + MRZ: FIO from MRZ, not REPUBLIC OF BELARUS."""
        fields = extract_passport_fields(
            "REPUBLIC OF BELARUS\n"
            "PASSPORT\n"
            "Surname\nSAYAPIN\n"
            "Given names\nANDREI\n"
            "Nationality\nREPUBLIC OF BELARUS\n"
            "Passport No. MP2417879\n"
            "P<BLRSAYAPIN<<ANDREI<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
            "MP24178795BLR8304265M28042683260483A011PB648\n"
        )
        self.assertEqual(fields["full_name"]["value"], "SAYAPIN ANDREI")
        self.assertEqual(fields["surname"]["value"], "SAYAPIN")
        self.assertEqual(fields["given_name"]["value"], "ANDREI")
        self.assertEqual(fields["series"]["value"], "MP")
        self.assertEqual(fields["number"]["value"], "2417879")
        self.assertEqual(fields["document_number"]["value"], "MP2417879")
        self.assertEqual(fields["birth_date"]["value"], "26.04.1983")
        self.assertNotEqual(fields["full_name"]["value"], "REPUBLIC OF BELARUS")

    def test_noisy_english_header_without_labels(self):
        fields = extract_passport_fields(
            "REPUBLIC OF BELARUS\n"
            "PASSPORT\n"
            "P<BLRSAYAPIN<<ANDREI<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
            "MP24178795BLR8304265M28042683260483A011PB648\n"
        )
        self.assertEqual(fields["full_name"]["value"], "SAYAPIN ANDREI")
        self.assertEqual(fields["document_number"]["value"], "MP2417879")

    def test_icao_sample_us_passport_mrz(self):
        """Public ICAO TD3 example (Wikipedia / industry docs)."""
        fields = extract_passport_fields(
            "P<USASMITH<<JOHN<MICHAEL<<<<<<<<<<<<<<<<<<<<\n"
            "1234567897USA8501011M2501019<<<<<<<<<<<<<<06\n"
        )
        self.assertEqual(fields["full_name"]["value"], "SMITH JOHN MICHAEL")
        self.assertEqual(fields["document_number"]["value"], "123456789")
        self.assertEqual(fields["birth_date"]["value"], "01.01.1985")

    def test_azerbaijan_noisy_photo_ocr(self):
        """Real GitHub sample: Tesseract splits MRZ; recover FIO + number."""
        fields = extract_passport_fields(
            "C94630262\n"
            "QAQARIN\nQAQARIN\n"
            "FIDAN BƏŞİR QIZI\nFIDAN\n"
            "AZORBAYCAN/AZERBAIJAN\n"
            "PCAZEQA\n"
            "C94630262\n"
            "OAZE6707297F23031072W12IMJ <<<<<<<4O\n"
        )
        self.assertEqual(fields["full_name"]["value"], "QAQARIN FIDAN")
        self.assertEqual(fields["document_number"]["value"], "C94630262")
        self.assertEqual(fields["birth_date"]["value"], "29.07.1967")
        self.assertEqual(fields["expiry_date"]["value"], "10.03.2023")
        doc_type, detected = extract_fields(
            "C94630262\nQAQARIN\nQAQARIN\nFIDAN\nFIDAN\n"
            "AZORBAYCAN/AZERBAIJAN\n"
            "C946302620AZE67 (O7297F23031072W12IMJ\n",
            filename="scan.jpg",
        )
        self.assertEqual(doc_type, "passport")
        self.assertEqual(detected["full_name"]["value"], "QAQARIN FIDAN")
        self.assertEqual(detected["document_number"]["value"], "C94630262")

    def test_llm_fills_missing_receipt_fields_without_overwriting_type(self):
        receipt = (
            "КВИТАНЦИЯ\n"
            "Получатель: ПЕТРОВ ОЛЕГ ИГОРЕВИЧ\n"
            "Сумма: 250.00\n"
            "Валюта: BYN\n"
            "Статус: ВЫПОЛНЕНО\n"
        )
        llm_payload = {
            "document_type": "unknown",
            "fields": {
                "operation_id": "OP202609021145",
                "operation_date": {"value": "01.09.2026", "confidence": 0.9},
                "amount": {"value": "999.00", "confidence": 0.99},
            },
        }

        class FakeGateway:
            @classmethod
            def from_registry(cls):
                return cls()

            def chat(self, profile, messages, **_kwargs):
                self.profile = profile
                self.messages = messages
                return {
                    "choices": [
                        {"message": {"content": json.dumps(llm_payload, ensure_ascii=False)}}
                    ]
                }

        from unittest.mock import patch

        with patch("core.model_gateway.ModelGateway", FakeGateway):
            structured = structure_document(
                receipt,
                filename="05_kvitanciya_perevod.png",
                document_type_hint="payment_receipt",
            )

        self.assertEqual(structured["document_type"], "payment_receipt")
        self.assertEqual(structured["fields"]["amount"]["value"], "250.00")
        self.assertEqual(structured["fields"]["operation_id"]["value"], "OP202609021145")
        self.assertEqual(structured["fields"]["operation_date"]["value"], "01.09.2026")
        self.assertEqual(structured["fields"]["currency"]["value"], "BYN")

    def test_ml_hint_keeps_freeform_fields_and_type(self):
        from ocr.pipeline import _attach_structuring

        result = {
            "pages": [
                {
                    "text": (
                        "ВЫПИСКА ИЗ ЕГРН\n"
                        "Кадастровый номер: 77:01:0004014:2714\n"
                        "Кадастровая стоимость, руб: 9504493.62\n"
                        "Дата запроса: 11.12.2018\n"
                    )
                }
            ],
            "job_id": "ocrjob-ml",
            "document_id": "doc-ml",
        }
        attached = _attach_structuring(
            result,
            filename="egrn.png",
            document_type_hint="ml",
        )
        self.assertEqual(attached["document_type"], "ml")
        fields = attached["fields"]
        self.assertTrue(fields)
        serialized = json.dumps(fields, ensure_ascii=False)
        self.assertIn("77:01:0004014:2714", serialized)
        self.assertFalse(
            {"surname", "given_name", "series"}.issubset(set(fields))
            and len(fields) <= 8
        )

    def test_german_td3_adenauer_sample(self):
        """Wikimedia public-domain ICAO graphic (P<D<< + 9-digit number)."""
        fields = extract_passport_fields(
            "P<D<<ADENAUER<<KONRAD<HERMANN<JOSEPH<<<<<<<<\n"
            "1234567897D<<7601059M6704115<<<<<<<<<<<<<<<2\n"
        )
        self.assertEqual(fields["full_name"]["value"], "ADENAUER KONRAD HERMANN JOSEPH")
        self.assertEqual(fields["document_number"]["value"], "123456789")
        self.assertEqual(fields["birth_date"]["value"], "05.01.1976")


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    OCR_OBJECT_STORE_BACKEND="fs",
)
class OcrAssistantAndTemplatesTest(TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            OCR_OBJECT_STORE_ROOT=Path(self._tmpdir.name),
            MINIO_OCR_BUCKET="sufler-ocr-test",
        )
        self.settings_override.enable()
        seed_templates_from_yaml()

    def tearDown(self):
        self.settings_override.disable()
        self._tmpdir.cleanup()

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"ocr-asst-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_pipeline_structures_passport_fields(self):
        client = Client()
        client.force_login(self.user_for_role("document_recognition_user"))
        upload = SimpleUploadedFile(
            "passport_demo.png",
            PASSPORT_TEXT.encode("utf-8"),
            content_type="image/png",
        )
        response = client.post(
            "/api/v1/ocr/documents/",
            {"file": upload, "document_type": "passport", "sync": "1"},
        )
        self.assertIn(response.status_code, {200, 202}, response.content)
        body = response.json()
        job = OcrJob.objects.get(pk=body["job_id"])
        self.assertEqual(job.status, OcrJob.STATUS_COMPLETED)
        result = body.get("result")
        if result is None:
            result_resp = client.get(f"/api/v1/ocr/jobs/{job.job_id}/result/")
            self.assertEqual(result_resp.status_code, 200)
            result = result_resp.json()
        self.assertEqual(result["document_type"], "passport")
        self.assertEqual(result["fields"]["series"]["value"], "MP")
        self.assertEqual(result["fields"]["surname"]["value"], "ИВАНОВ")
        self.assertEqual(result["fields"]["given_name"]["value"], "ИВАН")
        self.assertIn("confidence", result["fields"]["surname"])
        self.assertEqual(result["validation_status"], "valid")

    def test_assistant_ocr_endpoint(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        upload = SimpleUploadedFile(
            "passport_ivanov.png",
            PASSPORT_TEXT.encode("utf-8"),
            content_type="image/png",
        )
        response = client.post(
            "/api/v1/assistant/attachments/ocr",
            {"file": upload, "document_type": "passport"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn("ocr", body)
        self.assertEqual(body["ocr"]["document_type"], "passport")
        self.assertEqual(body["ocr"]["fields"]["number"]["value"], "4123456")
        self.assertIn("ИВАНОВ", body["text"])

    def test_admin_template_publish_and_sample(self):
        client = Client()
        client.force_login(
            self.user_for_role("document_recognition_module_administrator")
        )
        response = client.get("/api/v1/ocr/templates/?seed=1")
        self.assertEqual(response.status_code, 200, response.content)
        items = response.json()["items"]
        self.assertTrue(any(item["doc_type"] == "passport" for item in items))

        put = client.put(
            "/api/v1/ocr/templates/passport/",
            data=json.dumps(
                {
                    "title": "Паспорт (обучение)",
                    "confidence_min": 0.55,
                    "publish": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(put.status_code, 200, put.content)
        template = OcrDocumentTemplate.objects.get(doc_type="passport")
        self.assertEqual(template.status, OcrDocumentTemplate.STATUS_PUBLISHED)
        self.assertGreaterEqual(template.template_version, 1)

        sample = client.post(
            "/api/v1/ocr/templates/passport/samples/",
            {
                "file": SimpleUploadedFile(
                    "train_passport.png",
                    PASSPORT_TEXT.encode("utf-8"),
                    content_type="image/png",
                )
            },
        )
        self.assertEqual(sample.status_code, 201, sample.content)
        payload = sample.json()
        self.assertEqual(payload["expected_fields"].get("series"), "MP")

    def test_doc_types_include_published_templates(self):
        client = Client()
        client.force_login(self.user_for_role("document_recognition_user"))
        response = client.get("/api/v1/ocr/doc-types/")
        self.assertEqual(response.status_code, 200, response.content)
        items = response.json()["items"]
        passport = next(item for item in items if item["doc_type"] == "passport")
        self.assertEqual(passport["title"], "Паспорт")
        self.assertIn("surname", passport["field_schema"])
        self.assertIn("given_name", passport["field_schema"])

    def test_trimmed_passport_template_keeps_name_fields(self):
        seed_templates_from_yaml()
        template = OcrDocumentTemplate.objects.get(doc_type="passport")
        template.field_schema = {
            "number": {},
            "series": {},
            "birth_date": {},
            "issue_date": {},
        }
        template.required_fields = ["number"]
        template.save()
        from ocr.templates_registry import template_schema_for

        schema = template_schema_for("passport")
        self.assertEqual(
            list(schema["fields"]),
            ["surname", "given_name", "series", "number", "birth_date", "issue_date"],
        )
        self.assertIn("number", schema["fields"])
        self.assertIn("surname", schema["required_fields"])
        self.assertIn("given_name", schema["required_fields"])
        self.assertNotIn("expiry_date", schema["fields"])
        self.assertNotIn("personal_number", schema["fields"])
        self.assertNotIn("nationality", schema["fields"])

    def test_zip_archive_creates_queue_jobs(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("passport_a.png", PASSPORT_TEXT.encode("utf-8"))
            archive.writestr("notes.txt", b"ignore me")
            archive.writestr("folder/passport_b.png", PASSPORT_TEXT.encode("utf-8"))
        client = Client()
        client.force_login(self.user_for_role("document_recognition_user"))
        upload = SimpleUploadedFile(
            "batch.zip",
            buffer.getvalue(),
            content_type="application/zip",
        )
        response = client.post(
            "/api/v1/ocr/documents/",
            {"file": upload, "document_type": "passport", "sync": "1"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(len(body["items"]), 2)
        self.assertTrue(body["batch_id"])
        self.assertEqual(body["archive"], "batch.zip")
        jobs = list(OcrJob.objects.filter(batch_id=body["batch_id"]))
        self.assertEqual(len(jobs), 2)
        self.assertTrue(all(job.source_archive == "batch.zip" for job in jobs))
        self.assertTrue(all(job.status == OcrJob.STATUS_COMPLETED for job in jobs))

    def test_zip_slip_is_rejected_and_safe_members_kept(self):
        from ocr.archives import extract_archive

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../evil.png", PASSPORT_TEXT.encode("utf-8"))
            archive.writestr("ok.png", PASSPORT_TEXT.encode("utf-8"))
        members = extract_archive(buffer.getvalue(), "pack.zip")
        self.assertEqual([item.filename for item in members], ["ok.png"])

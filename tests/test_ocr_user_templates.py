import json
import os
import sys
import tempfile
import uuid
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
from ocr.models import OcrJob, OcrUserTemplate  # noqa: E402
from ocr.storage import get_object_store  # noqa: E402


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    OCR_OBJECT_STORE_BACKEND="fs",
)
class OcrUserTemplatesApiTest(TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store_root = Path(self._tmpdir.name)
        self.settings_override = override_settings(
            OCR_OBJECT_STORE_ROOT=self.store_root,
            MINIO_OCR_BUCKET="sufler-ocr-test",
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self._tmpdir.cleanup()

    def user_for_role(self, role_code, username=None):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=username or f"ocr-tpl-{role_code}-{uuid.uuid4().hex[:8]}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def seed_job(self, user, fields, validation_status="valid"):
        store = get_object_store()
        job_id = f"ocrjob-{uuid.uuid4().hex}"
        document_id = f"doc-{uuid.uuid4().hex}"
        original_key = f"originals/{document_id}/scan.png"
        result_key = f"results/{job_id}/ocr_result.json"
        store.put_bytes(original_key, b"demo-scan", content_type="image/png")
        payload = {
            "job_id": job_id,
            "document_id": document_id,
            "fields": fields,
            "validation_status": validation_status,
            "document_type": "passport",
        }
        store.put_bytes(
            result_key,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )
        return OcrJob.objects.create(
            job_id=job_id,
            document_id=document_id,
            status=OcrJob.STATUS_COMPLETED,
            filename="scan.png",
            sha256="a" * 64,
            original_object_key=original_key,
            result_object_key=result_key,
            created_by=user.username,
            validation_status=validation_status,
            document_type="passport",
        )

    def test_owner_isolation_and_foreign_404(self):
        user_a = self.user_for_role("document_recognition_user", "ocr-owner-a")
        user_b = self.user_for_role("document_recognition_user", "ocr-owner-b")
        client_a = self.client_for(user_a)
        client_b = self.client_for(user_b)
        job = self.seed_job(
            user_a,
            {
                "full_name": {"value": "Иванов Иван", "confidence": 0.92},
                "series": {"value": "AB", "confidence": 0.88},
            },
        )
        created = client_a.post(
            "/api/v1/ocr/my-templates/",
            data=json.dumps({"job_id": job.job_id, "name": "Мой паспорт"}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        template_id = created.json()["id"]

        listed_a = client_a.get("/api/v1/ocr/my-templates/")
        self.assertEqual(listed_a.status_code, 200)
        self.assertEqual(len(listed_a.json()["items"]), 1)
        self.assertEqual(listed_a.json()["items"][0]["name"], "Мой паспорт")

        listed_b = client_b.get("/api/v1/ocr/my-templates/")
        self.assertEqual(listed_b.status_code, 200)
        self.assertEqual(listed_b.json()["items"], [])

        self.assertEqual(
            client_b.get(f"/api/v1/ocr/my-templates/{template_id}/").status_code,
            404,
        )
        self.assertEqual(
            client_b.patch(
                f"/api/v1/ocr/my-templates/{template_id}/",
                data=json.dumps({"name": "Чужой"}),
                content_type="application/json",
            ).status_code,
            404,
        )
        self.assertEqual(
            client_b.delete(f"/api/v1/ocr/my-templates/{template_id}/").status_code,
            404,
        )

        stolen = client_b.post(
            "/api/v1/ocr/documents/",
            {
                "file": SimpleUploadedFile(
                    "next.png",
                    b"Passport scan\nName: Petrov\n",
                    content_type="image/png",
                ),
                "user_template_id": str(template_id),
                "sync": "1",
            },
        )
        self.assertEqual(stolen.status_code, 404, stolen.content)

    def test_unique_name_in_user_layer(self):
        user = self.user_for_role("document_recognition_user")
        client = self.client_for(user)
        job = self.seed_job(
            user,
            {"full_name": {"value": "Петров", "confidence": 0.91}},
        )
        first = client.post(
            "/api/v1/ocr/my-templates/",
            data=json.dumps({"job_id": job.job_id, "name": "Мой паспорт"}),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 201, first.content)
        second = client.post(
            "/api/v1/ocr/my-templates/",
            data=json.dumps({"job_id": job.job_id, "name": "мой паспорт"}),
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 400, second.content)
        self.assertIn("такое имя уже есть", second.json()["details"]["request"][0])

        other = self.user_for_role("document_recognition_user", "ocr-other-name")
        other_job = self.seed_job(
            other,
            {"full_name": {"value": "Сидоров", "confidence": 0.9}},
        )
        other_ok = self.client_for(other).post(
            "/api/v1/ocr/my-templates/",
            data=json.dumps({"job_id": other_job.job_id, "name": "Мой паспорт"}),
            content_type="application/json",
        )
        self.assertEqual(other_ok.status_code, 201, other_ok.content)

    def test_second_upload_keeps_same_keys(self):
        user = self.user_for_role("document_recognition_user")
        client = self.client_for(user)
        job = self.seed_job(
            user,
            {
                "full_name": {"value": "Иванов Иван", "confidence": 0.93},
                "series": {"value": "MP", "confidence": 0.87},
                "number": {"value": "1234567", "confidence": 0.86},
            },
        )
        created = client.post(
            "/api/v1/ocr/my-templates/",
            data=json.dumps({"job_id": job.job_id, "name": "Паспорт · тест"}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        template_id = created.json()["id"]
        self.assertEqual(
            [item["key"] for item in created.json()["fields"]],
            ["full_name", "series", "number"],
        )

        upload = client.post(
            "/api/v1/ocr/documents/",
            {
                "file": SimpleUploadedFile(
                    "second.png",
                    b"Another scan without labels\n",
                    content_type="image/png",
                ),
                "user_template_id": str(template_id),
                "sync": "1",
            },
        )
        self.assertIn(upload.status_code, {200, 202}, upload.content)
        result = upload.json().get("result") or {}
        if not result.get("fields"):
            job_id = upload.json()["job_id"]
            fetched = client.get(f"/api/v1/ocr/jobs/{job_id}/result/")
            self.assertEqual(fetched.status_code, 200, fetched.content)
            result = fetched.json()
        self.assertEqual(
            set(result["fields"].keys()),
            {"full_name", "series", "number"},
        )
        self.assertEqual(result.get("user_template_id"), template_id)
        self.assertFalse(result.get("document_type"))
        self.assertFalse(
            OcrUserTemplate.objects.filter(owner=user).exclude(pk=template_id).exists()
        )

    def test_review_with_empty_fields_is_blocked(self):
        user = self.user_for_role("document_recognition_user")
        client = self.client_for(user)
        job = self.seed_job(
            user,
            {
                "full_name": {"value": "", "confidence": 0.2},
                "series": {"value": "AB", "confidence": 0.3},
            },
            validation_status="pending_review",
        )
        blocked = client.post(
            "/api/v1/ocr/my-templates/",
            data=json.dumps({"job_id": job.job_id, "name": "Черновик"}),
            content_type="application/json",
        )
        self.assertEqual(blocked.status_code, 400, blocked.content)
        self.assertIn(
            "сначала исправьте и утвердите",
            blocked.json()["details"]["request"][0],
        )

    def test_ocr_use_required(self):
        user = self.user_for_role("ai_assistant_user")
        client = self.client_for(user)
        response = client.get("/api/v1/ocr/my-templates/")
        self.assertEqual(response.status_code, 403)

    def test_patch_updates_name_and_fields(self):
        user = self.user_for_role("document_recognition_user")
        client = self.client_for(user)
        job = self.seed_job(
            user,
            {"full_name": {"value": "Иванов", "confidence": 0.9}},
        )
        created = client.post(
            "/api/v1/ocr/my-templates/",
            data=json.dumps({"job_id": job.job_id, "name": "Черновик"}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        template_id = created.json()["id"]
        updated = client.patch(
            f"/api/v1/ocr/my-templates/{template_id}/",
            data=json.dumps(
                {
                    "name": "Мой паспорт",
                    "fields": [
                        {
                            "key": "full_name",
                            "label": "ФИО",
                            "type": "string",
                            "pattern": "",
                        },
                        {
                            "key": "series",
                            "label": "Серия",
                            "type": "string",
                        },
                    ],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        body = updated.json()
        self.assertEqual(body["name"], "Мой паспорт")
        self.assertEqual(
            [item["key"] for item in body["fields"]],
            ["full_name", "series"],
        )
        self.assertEqual(body["fields"][0]["label"], "ФИО")

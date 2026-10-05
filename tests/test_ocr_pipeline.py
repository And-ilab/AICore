import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from celery import current_app  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client, TestCase, override_settings  # noqa: E402

from auth.roles import ROLES_BY_CODE  # noqa: E402
from core.model_registry import ModelRegistry  # noqa: E402
from ocr.models import OcrJob  # noqa: E402
from ocr.storage import get_object_store  # noqa: E402
from ocr.tasks import run_ocr_job  # noqa: E402


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    OCR_OBJECT_STORE_BACKEND="fs",
)
class OcrPipelineApiTest(TestCase):
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

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"ocr-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_celery_task_registered(self):
        self.assertIn(run_ocr_job.name, current_app.tasks)

    def test_model_registry_ocr_slot_is_auto_paddle(self):
        slot = ModelRegistry.load().get_slot("ocr")
        self.assertEqual(slot.dev_model, "auto:paddle+tesseract")
        self.assertEqual(slot.status, "evaluating")

    def test_upload_returns_job_id_and_celery_completes(self):
        client = Client()
        client.force_login(self.user_for_role("document_recognition_user"))
        from django.core.files.uploadedfile import SimpleUploadedFile

        payload = b"OCR demo payment order #42\nAmount: 1500.00 BYN\n"
        upload_file = SimpleUploadedFile(
            "scan.png",
            payload,
            content_type="image/png",
        )
        response = client.post(
            "/api/v1/ocr/documents/",
            {"file": upload_file},
        )
        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertTrue(body["job_id"].startswith("ocrjob-"))
        self.assertTrue(body["document_id"].startswith("doc-"))
        self.assertTrue(str(body["pipeline"]).startswith("IV.5"))

        job = OcrJob.objects.get(pk=body["job_id"])
        self.assertEqual(job.status, OcrJob.STATUS_COMPLETED)
        self.assertEqual(job.ocr_model, "auto:paddle+tesseract")
        self.assertTrue(job.result_object_key)

        store = get_object_store()
        self.assertTrue(store.exists(job.original_object_key))
        self.assertTrue(store.exists(job.result_object_key))
        result_raw = store.get_bytes(job.result_object_key)
        result = json.loads(result_raw.decode("utf-8"))
        self.assertEqual(result["job_id"], job.job_id)
        self.assertIn("payment order", result["pages"][0]["text"])
        # UTF-8 text-as-image fixtures use embedded_text mode (real engines optional).
        self.assertIn(result["ocr_engine"]["mode"], {"stub", "embedded_text"})
        self.assertIn("fields", result)

        status = client.get(f"/api/v1/ocr/jobs/{job.job_id}/")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "completed")
        self.assertEqual(status.json()["progress"], 100)
        self.assertIsNone(status.json()["error"])

        original = client.get(f"/api/v1/ocr/jobs/{job.job_id}/original/")
        self.assertEqual(original.status_code, 200)
        self.assertEqual(original.content, payload)

        fetched = client.get(f"/api/v1/ocr/jobs/{job.job_id}/result/")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["document_sha256"], job.sha256)
        self.assertEqual(
            fetched.json()["document_sha256"],
            hashlib.sha256(payload).hexdigest(),
        )

    def test_rejects_unsupported_extension(self):
        client = Client()
        client.force_login(self.user_for_role("document_recognition_user"))
        from django.core.files.uploadedfile import SimpleUploadedFile

        bad = SimpleUploadedFile("notes.docx", b"x", content_type="application/msword")
        response = client.post("/api/v1/ocr/documents/", {"file": bad})
        self.assertEqual(response.status_code, 400)

    def test_forbidden_without_ocr_permission(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("scan.png", b"abc", content_type="image/png")
        response = client.post("/api/v1/ocr/documents/", {"file": upload})
        self.assertIn(response.status_code, (401, 403))

    def test_jobs_post_returns_job_id_and_progress(self):
        client = Client()
        client.force_login(self.user_for_role("document_recognition_user"))
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile(
            "scan.png",
            b"OCR demo payment order #42\nAmount: 1500.00 BYN\n",
            content_type="image/png",
        )
        response = client.post(
            "/api/v1/ocr/jobs/",
            {"file": upload, "mode": "ml"},
        )
        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertTrue(body["job_id"].startswith("ocrjob-"))
        self.assertEqual(body["mode"], "ml")
        self.assertIn(body["progress"], (0, 50, 100))

        fetched = client.get(f"/api/v1/ocr/jobs/{body['job_id']}/result/")
        self.assertEqual(fetched.status_code, 200)
        result = fetched.json()
        self.assertIn("fields", result)

    def test_jobs_post_skips_csrf_for_integrators(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user_for_role("document_recognition_user"))
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile(
            "scan.png",
            b"OCR demo payment order #42\nAmount: 1500.00 BYN\n",
            content_type="image/png",
        )
        response = client.post(
            "/api/v1/ocr/jobs/",
            {"file": upload, "mode": "ml"},
        )
        self.assertEqual(response.status_code, 202, response.content)

    def test_template_mode_requires_doc_type(self):
        client = Client()
        client.force_login(self.user_for_role("document_recognition_user"))
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("scan.png", b"abc", content_type="image/png")
        response = client.post(
            "/api/v1/ocr/jobs/",
            {"file": upload, "mode": "template"},
        )
        self.assertEqual(response.status_code, 400)

    def test_result_not_ready_is_409(self):
        client = Client()
        client.force_login(self.user_for_role("document_recognition_user"))
        job = OcrJob.objects.create(
            job_id="ocrjob-not-ready",
            document_id="doc-not-ready",
            status=OcrJob.STATUS_QUEUED,
            filename="scan.png",
            sha256="a" * 64,
            original_object_key="originals/doc-not-ready/scan.png",
            result_object_key="results/ocrjob-not-ready/ocr_result.json",
        )
        status = client.get(f"/api/v1/ocr/jobs/{job.job_id}/")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["progress"], 0)
        self.assertEqual(status.json()["status"], "queued")
        fetched = client.get(f"/api/v1/ocr/jobs/{job.job_id}/result/")
        self.assertEqual(fetched.status_code, 409)
        self.assertEqual(fetched.json()["error"], "not_ready")

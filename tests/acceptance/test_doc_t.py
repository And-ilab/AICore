"""DOC-T acceptance harness (P0-04). Smoke: DOC-T-01, DOC-T-04."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import TestCase, override_settings  # noqa: E402

from tests.acceptance.fixtures import api_client_for, post_json  # noqa: E402
from tests.acceptance.harness import (  # noqa: E402
    expand_ids_for,
    mark_acceptance,
    smoke_ids_for,
)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    OCR_OBJECT_STORE_BACKEND="fs",
)
class DocTSmokeAcceptanceTest(TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._ocr_settings = override_settings(
            OCR_OBJECT_STORE_ROOT=Path(self._tmpdir.name),
        )
        self._ocr_settings.enable()
        self.addCleanup(self._ocr_settings.disable)

    @mark_acceptance("DOC-T-01")
    def test_doc_t_01_web_upload_returns_ocr_job(self):
        """Web PDF/JPEG upload creates OCR job (foundation for ≥95% set)."""
        client = api_client_for(
            "document_recognition_user",
            prefix="doc-t-01",
        )
        upload = SimpleUploadedFile(
            "sample.pdf",
            b"%PDF-1.4 acceptance smoke sample",
            content_type="application/pdf",
        )
        response = client.post(
            "/api/v1/ocr/documents/",
            data={"file": upload},
        )
        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertIn("job_id", body)
        job_id = body["job_id"]
        detail = client.get(f"/api/v1/ocr/jobs/{job_id}/")
        self.assertEqual(detail.status_code, 200)
        status = detail.json()["status"]
        self.assertIn(
            status,
            {"queued", "ocr_processing", "completed", "processing_error"},
        )

    @mark_acceptance("DOC-T-04")
    def test_doc_t_04_required_fields_validation(self):
        """Required fields by template + §6.1.14 validation via API."""
        client = api_client_for(
            "document_recognition_user",
            prefix="doc-t-04",
        )
        catalog = client.get("/api/v1/ocr/doc-types/")
        self.assertEqual(catalog.status_code, 200)
        types = catalog.json()
        self.assertTrue(types)

        response = post_json(
            client,
            "/api/v1/ocr/validate/",
            {
                "document_type": "payment_order",
                "fields": {
                    "document_number": "42",
                    "date": "2026-07-20",
                    "payer": "ООО Альфа",
                    "beneficiary": "ООО Бета",
                    "amount": "1500.00",
                    "purpose": "оплата услуг",
                },
                "job_id": "ocrjob-doc-t-04",
                "document_id": "doc-t-04",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["status"], "valid")
        acceptance = body.get("provenance", {}).get("acceptance") or []
        self.assertIn("DOC-T-04", acceptance)


class DocTExpandAcceptanceTest(TestCase):
    def test_expand_ids_are_registered(self):
        self.assertEqual(
            set(smoke_ids_for("documents")),
            {"DOC-T-01", "DOC-T-04"},
        )
        self.assertTrue(expand_ids_for("documents"))
        self.skipTest(
            "P0-04 expand: implement remaining DOC-T-* per "
            "tests/acceptance/EXPAND.md"
        )


if __name__ == "__main__":
    unittest.main()

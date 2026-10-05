"""Tests for OpenAPI schema endpoint and Postman export."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.test import Client, SimpleTestCase  # noqa: E402

from api_docs.export_postman import (  # noqa: E402
    export_postman_collection,
    openapi_to_postman,
)
from api_docs.openapi_v1 import build_openapi_v1  # noqa: E402


class OpenApiSchemaTest(SimpleTestCase):
    def test_schema_endpoint_lists_ocr_only(self):
        client = Client()
        response = client.get("/api/schema/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertTrue(str(schema.get("openapi", "")).startswith("3."))
        paths = schema.get("paths") or {}
        self.assertTrue(paths)
        self.assertTrue(all(path.startswith("/api/v1/ocr") for path in paths))
        self.assertNotIn("/api/v1/assistant/chat", paths)
        self.assertNotIn("/api/v1/sufler/suggest", paths)
        self.assertNotIn("/api/v1/knowledge/events", paths)
        self.assertIn("/api/v1/ocr/jobs/", paths)
        self.assertIn("post", paths["/api/v1/ocr/jobs/"])
        self.assertIn("/api/v1/ocr/jobs/{id}/", paths)
        self.assertIn("get", paths["/api/v1/ocr/jobs/{id}/"])
        self.assertIn("/api/v1/ocr/jobs/{id}/result/", paths)
        self.assertIn("get", paths["/api/v1/ocr/jobs/{id}/result/"])
        tag_names = {tag.get("name") for tag in (schema.get("tags") or [])}
        self.assertEqual(tag_names, {"ocr"})

    def test_swagger_ui_available_when_debug(self):
        client = Client()
        response = client.get("/api/docs/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"swagger", response.content.lower())


class PostmanExportTest(unittest.TestCase):
    def test_postman_collection_covers_four_api_groups(self):
        collection = openapi_to_postman(build_openapi_v1())
        folder_names = {item["name"] for item in collection["item"]}
        self.assertEqual(folder_names, {"assistant", "ingest", "ocr", "sufler", "telephony"})
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "postman_collection.json"
            export_postman_collection(out)
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("v2.1.0", loaded["info"]["schema"])

    def test_ocr_postman_collection_has_upload_poll_result(self):
        path = REPOSITORY_ROOT / "docs" / "api" / "ocr.postman_collection.json"
        loaded = json.loads(path.read_text(encoding="utf-8"))
        names = [item["name"] for item in loaded["item"]]
        self.assertTrue(any("Upload template" in name for name in names))
        self.assertTrue(any("Poll" in name for name in names))
        self.assertTrue(any("result" in name.lower() for name in names))
        self.assertTrue(any("ML" in name for name in names))
        keys = {item["key"] for item in loaded["variable"]}
        self.assertIn("base_url", keys)
        self.assertIn("access_token", keys)


if __name__ == "__main__":
    unittest.main()

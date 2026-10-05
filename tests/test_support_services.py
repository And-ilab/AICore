import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.test import override_settings  # noqa: E402
from io import StringIO  # noqa: E402

from ocr.storage import FilesystemObjectStore, get_object_store  # noqa: E402
from sufler.celery import ping  # noqa: E402


class ObjectStoreRoundTripTests(unittest.TestCase):
    def test_filesystem_upload_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FilesystemObjectStore(Path(tmp), "sufler-ocr-test")
            key = "probe/hello.txt"
            uri = store.put_bytes(key, b"hello-minio-probe", content_type="text/plain")
            self.assertTrue(uri.startswith("fs://"))
            self.assertTrue(store.exists(key))
            self.assertEqual(store.get_bytes(key), b"hello-minio-probe")


class VerifySupportServicesCommandTests(unittest.TestCase):
    def test_verify_with_fs_store_skips_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = StringIO()
            with override_settings(
                CELERY_BROKER_URL="redis://127.0.0.1:6399/0",
                OCR_OBJECT_STORE_BACKEND="fs",
                OCR_OBJECT_STORE_ROOT=Path(tmp),
                MINIO_OCR_BUCKET="sufler-ocr-test",
                MINIO_ACCESS_KEY="",
                MINIO_SECRET_KEY="",
            ):
                fake_redis = mock.MagicMock()
                fake_redis.ping.return_value = True
                with mock.patch("redis.Redis.from_url", return_value=fake_redis):
                    call_command(
                        "verify_support_services",
                        "--skip-celery-worker",
                        stdout=out,
                    )
            text = out.getvalue()
            self.assertIn("redis broker: ok", text)
            self.assertIn("object store: ok", text)
            self.assertIn("FilesystemObjectStore", text)
            self.assertIn("verify_support_services: OK", text)

    def test_celery_ping_task_registered(self):
        self.assertEqual(ping.name, "sufler.ping")
        self.assertEqual(ping(), "pong")

    def test_get_object_store_uses_minio_when_configured(self):
        fake = object()
        with override_settings(
            OCR_OBJECT_STORE_BACKEND="minio",
            MINIO_ENDPOINT="http://minio:9000",
            MINIO_ACCESS_KEY="sufler",
            MINIO_SECRET_KEY="secret",
            MINIO_OCR_BUCKET="sufler-ocr",
        ):
            with mock.patch(
                "ocr.storage.MinioObjectStore",
                return_value=fake,
            ) as ctor:
                store = get_object_store()
        self.assertIs(store, fake)
        ctor.assert_called_once()


class SupportVerifyScriptTests(unittest.TestCase):
    def test_script_exists_and_mentions_checks(self):
        script = (ROOT / "infra/test/verify-support-services.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("redis-cli", script)
        self.assertIn("minio/health/live", script)
        self.assertIn("verify_support_services", script)


if __name__ == "__main__":
    unittest.main()

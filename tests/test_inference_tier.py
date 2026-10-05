import json
import os
import sys
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import StringIO
from pathlib import Path
from threading import Thread
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.test import override_settings  # noqa: E402

from core.model_gateway import ModelGateway  # noqa: E402
from core.model_registry import ModelRegistry  # noqa: E402
from ingest.models import CCProductionChunk  # noqa: E402


class _OkHealth(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = json.dumps(
            {"status": "ok", "mode": "stub", "profile": "test"}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003
        return


class InferenceTierTests(unittest.TestCase):
    def test_deployment_profile_test_present(self):
        deploy = ModelRegistry.load().get_deployment_profile("test")
        self.assertEqual(deploy.llm_gateway_mode, "stub")
        self.assertFalse(deploy.gpu_required)

    def test_gateway_from_registry_uses_test_stub_mode(self):
        with mock.patch.dict(
            os.environ,
            {"AI_INFERENCE_PROFILE": "test", "MODEL_GATEWAY_MODE": ""},
            clear=False,
        ):
            gateway = ModelGateway.from_registry()
        profile = gateway.get_profile("sufler_cc")
        self.assertEqual(profile.gateway_mode, "stub")
        result = gateway.chat(
            "sufler_cc",
            [{"role": "user", "content": "test"}],
        )
        self.assertIn("СУЗ", result["choices"][0]["message"]["content"])
        self.assertIn("ОТВЕТ", result["choices"][0]["message"]["content"])

    def test_verify_inference_tier_command(self):
        server = HTTPServer(("127.0.0.1", 0), _OkHealth)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            CCProductionChunk.objects.filter(article_id=91001).delete()
            out = StringIO()
            with override_settings(
                AI_INFERENCE_PROFILE="test",
                ASR_HEALTH_URL=f"http://127.0.0.1:{port}/health",
            ):
                call_command("verify_inference_tier", stdout=out)
            text = out.getvalue()
            self.assertIn("deployment profile: test", text)
            self.assertIn("suggest smoke: ok", text)
            self.assertIn("verify_inference_tier: OK", text)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()

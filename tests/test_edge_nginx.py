import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NGINX = ROOT / "infra" / "test" / "nginx.conf"


class EdgeNginxConfigTests(unittest.TestCase):
    def setUp(self):
        self.text = NGINX.read_text(encoding="utf-8")

    def test_http_redirects_to_https(self):
        self.assertIn("listen 80", self.text)
        self.assertRegex(
            self.text,
            re.compile(r"return\s+301\s+https://\$host\$request_uri", re.M),
        )

    def test_tls_and_daphne_upstream(self):
        self.assertIn("listen 443 ssl", self.text)
        self.assertIn("ssl_certificate", self.text)
        self.assertIn("backend:8000", self.text)
        self.assertIn("proxy_pass $daphne", self.text)
        self.assertIn("location /ws", self.text)
        self.assertIn("location /api/", self.text)
        self.assertIn("location = /health/", self.text)
        self.assertIn("location = /metrics/", self.text)
        self.assertIn("resolver 127.0.0.11", self.text)

    def test_gen_cert_script_exists(self):
        script = ROOT / "infra" / "test" / "gen-self-signed-cert.sh"
        self.assertTrue(script.is_file())
        body = script.read_text(encoding="utf-8")
        self.assertIn("openssl", body)
        self.assertIn("fullchain.pem", body)
        self.assertIn("privkey.pem", body)


if __name__ == "__main__":
    unittest.main()

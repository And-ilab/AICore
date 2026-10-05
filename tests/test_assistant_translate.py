import os
import sys
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.test import SimpleTestCase  # noqa: E402

from assistant.translate import TranslateError, translate_text  # noqa: E402


class TranslateTextTests(SimpleTestCase):
    def test_ru_to_en_returns_model_text(self):
        payload = {
            "choices": [{"message": {"content": "  Card application  "}}],
        }
        with patch("core.model_gateway.ModelGateway.from_registry") as registry:
            registry.return_value.chat.return_value = payload
            result = translate_text("Заявка на карту", "ru-en")
        self.assertEqual(result["text"], "Card application")
        self.assertEqual(result["source_label"], "RU")
        self.assertEqual(result["target_label"], "EN")

    def test_direction_switch_asks_for_russian(self):
        payload = {"choices": [{"message": {"content": "Заявка на карту"}}]}
        with patch("core.model_gateway.ModelGateway.from_registry") as registry:
            registry.return_value.chat.return_value = payload
            result = translate_text("Card application", "en-ru")
        self.assertEqual(result["target_label"], "RU")
        messages = registry.return_value.chat.call_args.args[1]
        self.assertIn("русский", messages[0]["content"])

    def test_empty_text_is_rejected(self):
        with self.assertRaises(TranslateError):
            translate_text("   ", "ru-en")

import os
import sys
from pathlib import Path

import django

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")
django.setup()

from channels.db import database_sync_to_async  # noqa: E402
from channels.testing import WebsocketCommunicator  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.test import TransactionTestCase, override_settings  # noqa: E402

from auth.roles import ROLES_BY_CODE  # noqa: E402
from ingest.models import CCProductionChunk  # noqa: E402
from ingest.pipeline import deterministic_embedding  # noqa: E402
from sufler.asgi import application  # noqa: E402


@override_settings(
    CHANNEL_LAYERS={
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }
)
class SuflerWebsocketTests(TransactionTestCase):
    @database_sync_to_async
    def create_user(self, role_code: str):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"ws-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    @database_sync_to_async
    def add_chunk(self):
        return CCProductionChunk.objects.create(
            article_id=901,
            version_id=1,
            chunk_index=0,
            title="Оформление карты",
            content="как оформить банковскую карту",
            permalink="https://suz.local/articles/901",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum="sha256:ws",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding("как оформить банковскую карту"),
        )

    async def test_final_client_asr_returns_hints(self):
        user = await self.create_user("contact_center_telephony_operator")
        await self.add_chunk()
        communicator = WebsocketCommunicator(
            application,
            "/ws/sufler/call-1/",
        )
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        status = await communicator.receive_json_from()
        self.assertEqual(status["type"], "status")

        await communicator.send_json_to(
            {
                "type": "asr.final",
                "speaker": "client",
                "text": "как оформить банковскую карту",
                "turn_id": "turn-1",
            }
        )
        transcript = await communicator.receive_json_from()
        self.assertEqual(transcript["type"], "transcript")
        self.assertTrue(transcript["is_final"])

        hints = await communicator.receive_json_from()
        self.assertEqual(hints["type"], "hints")
        self.assertEqual(hints["turn_id"], "turn-1")
        self.assertGreaterEqual(len(hints["hints"]), 1)
        self.assertIn("latency_ms", hints)
        citation = hints["hints"][0]["citations"][0]
        self.assertEqual(citation["title"], "Оформление карты")
        self.assertTrue(citation["permalink"].startswith("https://"))

        await communicator.disconnect()

    async def test_ping_pong_via_asgi_application(self):
        """Daphne serves the same ASGI app; ping/pong verifies Channels WS path."""
        user = await self.create_user("contact_center_telephony_operator")
        communicator = WebsocketCommunicator(
            application,
            "/ws/sufler/health-check/",
        )
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        status = await communicator.receive_json_from()
        self.assertEqual(status["type"], "status")
        self.assertEqual(status["call_id"], "health-check")

        await communicator.send_json_to({"type": "ping"})
        pong = await communicator.receive_json_from()
        self.assertEqual(pong["type"], "pong")
        await communicator.disconnect()

    async def test_unauthorized_user_is_rejected(self):
        user = await self.create_user("document_recognition_module_administrator")
        communicator = WebsocketCommunicator(
            application,
            "/ws/sufler/call-2/",
        )
        communicator.scope["user"] = user
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4403)

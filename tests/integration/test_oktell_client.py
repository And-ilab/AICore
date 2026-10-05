import sys
import unittest
import unittest.mock
from pathlib import Path

import websockets


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from integrations.oktell.asr_pipeline import AsrPipeline  # noqa: E402
from integrations.oktell.client import OktellClient  # noqa: E402
from integrations.oktell_mock.server import (  # noqa: E402
    CHAIN_ID,
    COMMUTATION_ID,
    OktellMockServer,
)


class OktellClientIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_client_maps_mock_lifecycle_to_asr_pipeline(self):
        mock = OktellMockServer(event_delay_seconds=0)
        started: list[tuple[str, tuple[str, ...]]] = []
        stopped: list[str] = []

        def on_asr_start(session, legs):
            started.append(
                (
                    session.chain_id,
                    tuple(leg.speaker for leg in legs),
                )
            )

        def on_asr_stop(session):
            stopped.append(session.chain_id)

        pipeline = AsrPipeline(on_asr_start=on_asr_start, on_asr_stop=on_asr_stop)

        async with websockets.serve(mock.handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            async with OktellClient(
                url=f"ws://127.0.0.1:{port}",
                asr_pipeline=pipeline,
            ) as client:
                subscription = await client.subscribe_phoneevents(
                    qid="p1-14-subscription",
                )
                lifecycle = await client.drain_lifecycle()

        self.assertEqual(subscription["result"], 1)
        self.assertEqual(
            [name for name, _ in lifecycle],
            [
                "phoneevent_ringstarted",
                "phoneevent_commstarted",
                "phoneevent_commstopped",
            ],
        )

        ring_payload = lifecycle[0][1]
        started_payload = lifecycle[1][1]
        stopped_payload = lifecycle[2][1]
        self.assertEqual(ring_payload["chainid"], CHAIN_ID)
        self.assertEqual(started_payload["commutationid"], COMMUTATION_ID)
        self.assertEqual(
            stopped_payload["commutationid"],
            COMMUTATION_ID,
        )

        self.assertEqual(started, [(CHAIN_ID, ("operator", "client"))])
        self.assertEqual(stopped, [CHAIN_ID])

        session = pipeline.get_session(CHAIN_ID)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.state, "stopped")
        self.assertEqual(session.commutation_id, COMMUTATION_ID)
        self.assertEqual(
            {(leg.leg, leg.speaker) for leg in session.legs},
            {
                ("operator_leg", "operator"),
                ("client_leg", "client"),
            },
        )
        self.assertIn("operator_leg", session.record_links)
        self.assertIn("client_leg", session.record_links)

    async def test_settings_url_is_used_when_explicit_url_omitted(self):
        from integrations.oktell.config import OktellProfile

        mock = OktellMockServer(event_delay_seconds=0)
        async with websockets.serve(mock.handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            url = f"ws://127.0.0.1:{port}"
            profile = OktellProfile(
                mode="mock",
                ws_url=url,
                subscribe_event="phoneevent",
                profile_id="oktell_mock",
                enabled=True,
                line_label="local-oktell-mock",
                queue="mock",
                marking="DEV_MOCK",
                open_timeout=5.0,
            )
            with unittest.mock.patch(
                "integrations.oktell.client.resolve_oktell_profile",
                return_value=profile,
            ):
                client = OktellClient.from_settings()
                self.assertEqual(client.url, url)
                self.assertEqual(client.mode, "mock")
                await client.connect()
                result = await client.subscribe_phoneevents()
                await client.drain_lifecycle()
                await client.close()
        self.assertEqual(result["result"], 1)


if __name__ == "__main__":
    unittest.main()

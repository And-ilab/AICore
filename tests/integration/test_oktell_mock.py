import json
import sys
import unittest
from pathlib import Path

import websockets


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from integrations.oktell_mock.server import OktellMockServer  # noqa: E402


class OktellMockIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_subscribe_receives_phoneevent_with_dual_legs(self):
        mock = OktellMockServer(event_delay_seconds=0)

        async with websockets.serve(
            mock.handler,
            "127.0.0.1",
            0,
        ) as server:
            port = server.sockets[0].getsockname()[1]
            async with websockets.connect(
                f"ws://127.0.0.1:{port}"
            ) as client:
                await client.send(
                    json.dumps(
                        [
                            "subscribeevent",
                            {
                                "qid": "test-subscription",
                                "event": "phoneevent",
                            },
                        ]
                    )
                )

                subscription = json.loads(await client.recv())
                ring = json.loads(await client.recv())
                comm_started = json.loads(await client.recv())
                comm_stopped = json.loads(await client.recv())

        self.assertEqual(subscription[0], "subscribeeventresult")
        self.assertEqual(subscription[1]["result"], 1)
        self.assertEqual(ring[0], "phoneevent_ringstarted")
        self.assertEqual(comm_started[0], "phoneevent_commstarted")
        self.assertEqual(comm_stopped[0], "phoneevent_commstopped")

        legs = comm_started[1]["mock_audio_legs"]
        self.assertEqual(
            {(leg["leg"], leg["speaker"]) for leg in legs},
            {
                ("operator_leg", "operator"),
                ("client_leg", "client"),
            },
        )
        self.assertEqual(
            ring[1]["chainid"],
            comm_started[1]["chainid"],
        )
        self.assertEqual(
            comm_started[1]["commutationid"],
            comm_stopped[1]["commutationid"],
        )


if __name__ == "__main__":
    unittest.main()

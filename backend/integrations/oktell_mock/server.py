"""WebSocket mock for Oktell phoneevent lifecycle messages."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Mapping, Sequence

import websockets
from websockets.exceptions import ConnectionClosed


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766
CHAIN_ID = "D6C8232D-4E4A-48BB-954E-C719582A4718"
COMMUTATION_ID = "072F2EE0-4B3B-49A7-AB5B-E213AE752A53"
USER_ID = "3357F4D2-B37C-4809-9A1A-E4D64808DE1B"


def lifecycle_events() -> list[list[Any]]:
    """Return one deterministic incoming-call lifecycle."""
    common = {
        "userlogin": "ivanov",
        "userid": USER_ID,
        "chainid": CHAIN_ID,
        "callerid": "375291234567",
    }
    return [
        [
            "phoneevent_ringstarted",
            {
                **common,
                "qid": "00488421-97E4-443B-81B7-D645E403AEBB",
                "callername": "Клиент",
                "isextline": True,
            },
        ],
        [
            "phoneevent_commstarted",
            {
                **common,
                "qid": "B7ACFEC1-65BB-4773-A425-DC39F5D1A48C",
                "commutationid": COMMUTATION_ID,
                "isextline": True,
                "mock_audio_legs": [
                    {
                        "leg": "operator_leg",
                        "speaker": "operator",
                        "audio_path": (
                            "benchmarks/datasets/assets/asr/"
                            "OKTELL-MOCK-operator.wav"
                        ),
                        "codec": "PCM_S16LE",
                        "sample_rate_hz": 8000,
                        "status": "placeholder",
                    },
                    {
                        "leg": "client_leg",
                        "speaker": "client",
                        "audio_path": (
                            "benchmarks/datasets/assets/asr/"
                            "OKTELL-MOCK-client.wav"
                        ),
                        "codec": "PCM_S16LE",
                        "sample_rate_hz": 8000,
                        "status": "placeholder",
                    },
                ],
            },
        ],
        [
            "phoneevent_commstopped",
            {
                "qid": "D514511C-BD4F-406B-B9C7-695CDC6C40E7",
                "userlogin": "ivanov",
                "chainid": CHAIN_ID,
                "commutationid": COMMUTATION_ID,
                "mock_recordlinks": {
                    "operator_leg": (
                        "/mock-records/OKTELL-MOCK-operator.wav"
                    ),
                    "client_leg": "/mock-records/OKTELL-MOCK-client.wav",
                },
            },
        ],
    ]


class OktellMockServer:
    """Respond to Oktell commands and emit a deterministic phone lifecycle."""

    def __init__(self, *, event_delay_seconds: float = 0.05) -> None:
        if event_delay_seconds < 0:
            raise ValueError("event_delay_seconds cannot be negative")
        self.event_delay_seconds = event_delay_seconds

    async def _send(
        self,
        websocket: Any,
        message: Sequence[Any],
    ) -> None:
        await websocket.send(json.dumps(message, ensure_ascii=False))

    async def _emit_lifecycle(self, websocket: Any) -> None:
        for event in lifecycle_events():
            if self.event_delay_seconds:
                await asyncio.sleep(self.event_delay_seconds)
            await self._send(websocket, event)

    async def _handle_command(
        self,
        websocket: Any,
        command: str,
        payload: Mapping[str, Any],
    ) -> None:
        qid = payload.get("qid")
        if command == "subscribeevent":
            if payload.get("event") != "phoneevent":
                await self._send(
                    websocket,
                    [
                        "subscribeeventresult",
                        {
                            "qid": qid,
                            "result": 0,
                            "error": "only phoneevent is supported",
                        },
                    ],
                )
                return
            await self._send(
                websocket,
                ["subscribeeventresult", {"qid": qid, "result": 1}],
            )
            await self._emit_lifecycle(websocket)
            return

        if command == "getchaincontent":
            await self._send(
                websocket,
                [
                    "getchaincontentresult",
                    {
                        "qid": qid,
                        "result": 1,
                        "content": {
                            "chainid": CHAIN_ID,
                            "trace": [
                                {
                                    "commutationid": COMMUTATION_ID,
                                    "userlogin": "ivanov",
                                    "queue": "contact-center-dev",
                                }
                            ],
                        },
                    },
                ],
            )
            return

        await self._send(
            websocket,
            [
                "error",
                {
                    "qid": qid,
                    "code": "unsupported_command",
                    "command": command,
                },
            ],
        )

    async def handler(self, websocket: Any) -> None:
        try:
            async for raw_message in websocket:
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    await self._send(
                        websocket,
                        ["error", {"code": "invalid_json"}],
                    )
                    continue

                if (
                    not isinstance(message, list)
                    or len(message) != 2
                    or not isinstance(message[0], str)
                    or not isinstance(message[1], Mapping)
                ):
                    await self._send(
                        websocket,
                        ["error", {"code": "invalid_message_shape"}],
                    )
                    continue
                await self._handle_command(
                    websocket,
                    message[0],
                    message[1],
                )
        except ConnectionClosed:
            return


async def serve_forever(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    event_delay_seconds: float = 0.05,
) -> None:
    mock = OktellMockServer(event_delay_seconds=event_delay_seconds)
    async with websockets.serve(
        mock.handler,
        host,
        port,
        ping_interval=20,
        ping_timeout=20,
    ):
        print(f"Oktell mock is listening on ws://{host}:{port}")
        await asyncio.Future()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Oktell phoneevent WebSocket mock.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--event-delay-ms",
        type=float,
        default=50,
        help="Delay between lifecycle events (default: 50 ms).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 0 <= args.port <= 65535:
        raise SystemExit("--port must be between 0 and 65535")
    if args.event_delay_ms < 0:
        raise SystemExit("--event-delay-ms cannot be negative")
    try:
        asyncio.run(
            serve_forever(
                args.host,
                args.port,
                event_delay_seconds=args.event_delay_ms / 1000,
            )
        )
    except KeyboardInterrupt:
        print("Oktell mock stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

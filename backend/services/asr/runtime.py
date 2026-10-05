"""TEST/PROD ASR runtime: stub (default on TEST) or Vosk when models are mounted.

Stub mode needs only the ``websockets`` package — suitable for Docker without GPU.
Set ASR_MODE=vosk + VOSK_MODEL_PATH to use the approved_dev Vosk candidate.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

ASR_MODE = os.getenv("ASR_MODE", "stub").strip().lower() or "stub"
ASR_HOST = os.getenv("ASR_HOST", "0.0.0.0")
ASR_WS_PORT = int(os.getenv("ASR_WS_PORT", "8765"))
ASR_HEALTH_PORT = int(os.getenv("ASR_HEALTH_PORT", "8764"))
ASR_STUB_TEXT = os.getenv(
    "ASR_STUB_TEXT",
    "клиент спрашивает как оформить банковскую карту",
)
AI_INFERENCE_PROFILE = os.getenv("AI_INFERENCE_PROFILE", "test")


def _health_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "sufler-asr",
        "mode": ASR_MODE,
        "profile": AI_INFERENCE_PROFILE,
        "gpu_required": False,
        "ws": f"ws://{ASR_HOST}:{ASR_WS_PORT}/",
    }


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in {"/health", "/health/"}:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(_health_payload(), ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def start_health_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((ASR_HOST, ASR_HEALTH_PORT), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def _stub_handler(websocket: WebSocketServerProtocol) -> None:
    await websocket.send(
        json.dumps(
            {
                "type": "status",
                "status": "connected",
                "mode": "stub",
                "profile": AI_INFERENCE_PROFILE,
            },
            ensure_ascii=False,
        )
    )
    async for raw in websocket:
        try:
            payload = json.loads(raw) if isinstance(raw, str) else {}
        except json.JSONDecodeError:
            await websocket.send(
                json.dumps({"type": "error", "message": "invalid JSON"})
            )
            continue
        if not isinstance(payload, dict):
            continue
        msg_type = payload.get("type")
        if msg_type in {"ping", "health"}:
            await websocket.send(json.dumps({"type": "pong", "mode": "stub"}))
        elif msg_type in {
            "recognize",
            "asr.final",
            "start_transcription",
            "audio",
        }:
            text = payload.get("text") or ASR_STUB_TEXT
            await websocket.send(
                json.dumps(
                    {
                        "type": "final",
                        "text": text,
                        "mode": "stub",
                        "profile": AI_INFERENCE_PROFILE,
                    },
                    ensure_ascii=False,
                )
            )
        else:
            await websocket.send(
                json.dumps(
                    {
                        "type": "final",
                        "text": ASR_STUB_TEXT,
                        "mode": "stub",
                    },
                    ensure_ascii=False,
                )
            )


async def run_stub() -> None:
    start_health_server()
    print(
        f"ASR stub listening ws://{ASR_HOST}:{ASR_WS_PORT} "
        f"health http://{ASR_HOST}:{ASR_HEALTH_PORT}/health "
        f"profile={AI_INFERENCE_PROFILE}"
    )
    async with websockets.serve(_stub_handler, ASR_HOST, ASR_WS_PORT):
        await asyncio.Future()


def main() -> None:
    if ASR_MODE == "vosk":
        # Delegate to legacy microphone/Vosk server (local/dev with model files).
        from services.asr.main import main as vosk_main

        vosk_main()
        return
    if ASR_MODE != "stub":
        raise SystemExit(f"Unsupported ASR_MODE={ASR_MODE!r} (use stub|vosk)")
    asyncio.run(run_stub())


if __name__ == "__main__":
    main()

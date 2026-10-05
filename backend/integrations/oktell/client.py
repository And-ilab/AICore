"""Oktell WebSocket client for SuflerTelephony (VI.2 / P4-02).

Connects to mock or real Oktell WS endpoint based on OKTELL_MODE,
subscribes to phoneevents, and maps lifecycle events onto the ASR pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from integrations.oktell.asr_pipeline import AsrPipeline
from integrations.oktell.config import (
    DEFAULT_SUBSCRIBE_EVENT,
    OktellProfile,
    resolve_oktell_mode,
    resolve_oktell_profile,
)

logger = logging.getLogger(__name__)

EventHandler = Callable[[str, Mapping[str, Any]], Any]


class OktellClientError(RuntimeError):
    """Raised when the Oktell WS protocol exchange fails."""


class OktellClient:
    """Async client for Oktell phoneevent WebSocket (mock or production)."""

    def __init__(
        self,
        url: str | None = None,
        *,
        mode: str | None = None,
        profile: OktellProfile | None = None,
        subscribe_event: str | None = None,
        asr_pipeline: AsrPipeline | None = None,
        on_event: EventHandler | None = None,
        open_timeout: float | None = None,
    ) -> None:
        self.profile = profile or resolve_oktell_profile(mode=mode, ws_url=url)
        self.mode = self.profile.mode
        self.url = url or self.profile.ws_url
        self.subscribe_event = (
            subscribe_event or self.profile.subscribe_event or DEFAULT_SUBSCRIBE_EVENT
        )
        self.asr_pipeline = asr_pipeline or AsrPipeline()
        self.on_event = on_event
        self.open_timeout = (
            open_timeout if open_timeout is not None else self.profile.open_timeout
        )
        self._websocket: Any | None = None
        self._recv_task: asyncio.Task[None] | None = None
        self.received_events: list[tuple[str, dict[str, Any]]] = []

    @classmethod
    def from_settings(
        cls,
        *,
        mode: str | None = None,
        asr_pipeline: AsrPipeline | None = None,
        on_event: EventHandler | None = None,
    ) -> OktellClient:
        """P4-02 factory: build client from OKTELL_MODE + env profile."""
        profile = resolve_oktell_profile(mode=mode)
        return cls(
            profile=profile,
            asr_pipeline=asr_pipeline,
            on_event=on_event,
        )

    @property
    def connected(self) -> bool:
        return self._websocket is not None

    async def connect(self) -> None:
        if self._websocket is not None:
            return
        self._websocket = await websockets.connect(
            self.url,
            open_timeout=self.open_timeout,
            ping_interval=20,
            ping_timeout=20,
        )
        logger.info(
            "Connected to Oktell WS %s (mode=%s profile=%s)",
            self.url,
            self.mode,
            self.profile.profile_id,
        )

    async def close(self) -> None:
        if self._recv_task is not None:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
            self._recv_task = None
        if self._websocket is not None:
            await self._websocket.close()
            self._websocket = None

    async def __aenter__(self) -> OktellClient:
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def _send(self, command: str, payload: Mapping[str, Any]) -> None:
        if self._websocket is None:
            raise OktellClientError("client is not connected")
        message = [command, dict(payload)]
        await self._websocket.send(json.dumps(message, ensure_ascii=False))

    async def _recv(self) -> tuple[str, dict[str, Any]]:
        if self._websocket is None:
            raise OktellClientError("client is not connected")
        raw = await self._websocket.recv()
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OktellClientError("invalid JSON from Oktell") from exc
        if (
            not isinstance(message, list)
            or len(message) != 2
            or not isinstance(message[0], str)
            or not isinstance(message[1], Mapping)
        ):
            raise OktellClientError("invalid Oktell message shape")
        return message[0], dict(message[1])

    async def subscribe_phoneevents(
        self,
        *,
        qid: str | None = None,
    ) -> dict[str, Any]:
        """Subscribe to phoneevent stream (INT-T04)."""
        request_qid = qid or str(uuid.uuid4())
        await self._send(
            "subscribeevent",
            {"qid": request_qid, "event": self.subscribe_event},
        )
        name, payload = await self._recv()
        if name != "subscribeeventresult":
            raise OktellClientError(
                f"expected subscribeeventresult, got {name}"
            )
        if payload.get("result") != 1:
            raise OktellClientError(
                f"subscribeevent failed: {payload.get('error') or payload}"
            )
        return payload

    async def get_chain_content(
        self,
        *,
        userlogin: str,
        qid: str | None = None,
    ) -> dict[str, Any]:
        """Fetch commutation chain content (INT-T05)."""
        request_qid = qid or str(uuid.uuid4())
        await self._send(
            "getchaincontent",
            {"qid": request_qid, "userlogin": userlogin},
        )
        name, payload = await self._recv()
        if name != "getchaincontentresult":
            raise OktellClientError(
                f"expected getchaincontentresult, got {name}"
            )
        if payload.get("result") != 1:
            raise OktellClientError(
                f"getchaincontent failed: {payload}"
            )
        return payload

    def _dispatch(self, name: str, payload: Mapping[str, Any]) -> None:
        self.received_events.append((name, dict(payload)))
        if name.startswith("phoneevent_"):
            self.asr_pipeline.handle_event(name, payload)
        if self.on_event is not None:
            self.on_event(name, payload)

    async def receive_event(self) -> tuple[str, dict[str, Any]]:
        """Receive and dispatch one Oktell message."""
        name, payload = await self._recv()
        self._dispatch(name, payload)
        return name, payload

    async def drain_lifecycle(
        self,
        *,
        expected: Sequence[str] = (
            "phoneevent_ringstarted",
            "phoneevent_commstarted",
            "phoneevent_commstopped",
        ),
    ) -> list[tuple[str, dict[str, Any]]]:
        """Receive the standard ring → talk → hangup sequence."""
        collected: list[tuple[str, dict[str, Any]]] = []
        for expected_name in expected:
            name, payload = await self.receive_event()
            if name != expected_name:
                raise OktellClientError(
                    f"expected {expected_name}, got {name}"
                )
            collected.append((name, payload))
        return collected

    async def run_forever(self) -> None:
        """Receive loop until the socket closes."""
        try:
            while True:
                await self.receive_event()
        except ConnectionClosed:
            logger.info("Oktell WS closed")
            return

    async def connect_and_subscribe(
        self,
        *,
        qid: str | None = None,
        run_lifecycle: bool = False,
    ) -> dict[str, Any]:
        """Connect, subscribe, optionally drain one mock lifecycle."""
        await self.connect()
        result = await self.subscribe_phoneevents(qid=qid)
        if run_lifecycle:
            if self.mode != "mock":
                raise OktellClientError(
                    "run_lifecycle=True is only supported in OKTELL_MODE=mock"
                )
            await self.drain_lifecycle()
        return result

    def describe(self) -> dict[str, Any]:
        """Ops-facing snapshot of the active profile."""
        payload = self.profile.as_dict()
        payload["connected"] = self.connected
        payload["resolved_mode"] = resolve_oktell_mode(self.mode)
        return payload

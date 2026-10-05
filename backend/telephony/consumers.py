"""Channels WebSocket consumer for telephony sufler (II.3).

Protocol (JSON):
  Client → server:
    {"type": "asr.partial"|"asr.final", "speaker": "client"|"operator",
     "text": "...", "turn_id": "..."}
    {"type": "ping"}
  Server → client:
    transcript echo: {"type": "transcript", "speaker", "text", "is_final", "turn_id"}
    hints: {"type": "hints", "turn_id", "hints": [...], "latency_ms", "request_id"}
    error: {"type": "error", "message": "..."}
"""

from __future__ import annotations

import json
from typing import Any

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from auth.roles import (
    PERM_SUFLER_CHAT,
    PERM_SUFLER_TELEPHONY,
    has_permission,
)
from integrations.oktell.bridge import sufler_group
from orchestrator.scenario_engine import clear_scenario_session
from orchestrator.sufler import SuflerOrchestratorError, suggest


def _user_may_use_sufler(user: Any) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return has_permission(user, PERM_SUFLER_TELEPHONY) or has_permission(
        user,
        PERM_SUFLER_CHAT,
    )


class SuflerTranscriptConsumer(AsyncWebsocketConsumer):
    """Live transcript stream + orchestrator suggest on client ASR finals."""

    async def connect(self) -> None:
        user = self.scope.get("user")
        self.call_id = self.scope["url_route"]["kwargs"].get(
            "call_id",
            "live",
        )
        allowed = await sync_to_async(_user_may_use_sufler, thread_sensitive=True)(user)
        if not allowed:
            from integrations.oktell.call_hub import hub

            allowed = hub.get(str(self.call_id)) is not None
        if not allowed:
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(sufler_group(str(self.call_id)), self.channel_name)
        await self.accept()
        await self.send_json(
            {
                "type": "status",
                "status": "connected",
                "call_id": self.call_id,
                "asr": "active",
            }
        )
        await self._replay_oktell_events()

    async def _replay_oktell_events(self) -> None:
        from integrations.oktell.call_hub import hub

        call = hub.get(str(self.call_id))
        if call is None:
            return
        for payload in list(call.events):
            if isinstance(payload, dict) and payload.get("type") in {
                "transcript",
                "hints",
                "error",
            }:
                await self.send_json(payload)

    async def disconnect(self, close_code: int) -> None:
        call_id = str(getattr(self, "call_id", "") or "")
        if call_id:
            await self.channel_layer.group_discard(sufler_group(call_id), self.channel_name)
            await sync_to_async(clear_scenario_session, thread_sensitive=True)(call_id)

    async def sufler_event(self, event: dict[str, Any]) -> None:
        payload = event.get("payload")
        if isinstance(payload, dict):
            await self.send_json(payload)

    async def receive(self, text_data: str | None = None, bytes_data=None) -> None:
        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_json(
                {"type": "error", "message": "payload must be valid JSON"}
            )
            return
        if not isinstance(payload, dict):
            await self.send_json(
                {"type": "error", "message": "payload must be a JSON object"}
            )
            return

        message_type = payload.get("type")
        if message_type == "ping":
            await self.send_json({"type": "pong"})
            return
        if message_type not in {"asr.partial", "asr.final"}:
            await self.send_json(
                {"type": "error", "message": f"unsupported type: {message_type}"}
            )
            return

        speaker = payload.get("speaker", "client")
        text = payload.get("text", "")
        turn_id = str(payload.get("turn_id") or "")
        if speaker not in {"client", "operator"}:
            await self.send_json(
                {"type": "error", "message": "speaker must be client or operator"}
            )
            return
        if not isinstance(text, str) or not text.strip():
            await self.send_json(
                {"type": "error", "message": "text must be a non-empty string"}
            )
            return

        is_final = message_type == "asr.final"
        await self.send_json(
            {
                "type": "transcript",
                "speaker": speaker,
                "text": text.strip(),
                "is_final": is_final,
                "turn_id": turn_id,
            }
        )

        if is_final and speaker == "client":
            kb_slugs = payload.get("kb_slugs")
            await self._emit_hints(text.strip(), turn_id=turn_id, kb_slugs=kb_slugs)

    async def _emit_hints(
        self,
        text: str,
        *,
        turn_id: str,
        kb_slugs: Any = None,
    ) -> None:
        slugs = None
        if isinstance(kb_slugs, list):
            slugs = [
                item.strip()
                for item in kb_slugs
                if isinstance(item, str) and item.strip()
            ]
        try:
            result = await sync_to_async(suggest, thread_sensitive=True)(
                text,
                limit=5,
                kb_slugs=slugs,
                session_id=str(getattr(self, "call_id", "") or ""),
                channel="telephony",
            )
        except SuflerOrchestratorError as exc:
            await self.send_json(
                {
                    "type": "error",
                    "message": str(exc),
                    "turn_id": turn_id,
                }
            )
            return
        except (RuntimeError, ValueError, KeyError, TypeError) as exc:
            await self.send_json(
                {
                    "type": "error",
                    "message": f"suggest failed: {exc}",
                    "turn_id": turn_id,
                }
            )
            return

        await self.send_json(
            {
                "type": "hints",
                "turn_id": turn_id,
                "query": result["query"],
                "hints": result["hints"][:5],
                "latency_ms": result["latency_ms"],
                "request_id": result["request_id"],
                "blocked_reason": result.get("blocked_reason"),
                "scenario": result.get("scenario"),
                "suggested_scenario": result.get("suggested_scenario"),
            }
        )

    async def send_json(self, payload: dict[str, Any]) -> None:
        await self.send(text_data=json.dumps(payload, ensure_ascii=False))

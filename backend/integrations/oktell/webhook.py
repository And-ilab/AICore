"""Parse Oktell pickup webhook from the vendor 'Подслушивание' note."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


class OktellWebhookError(ValueError):
    """Invalid pickup payload."""


@dataclass(frozen=True)
class PickupEvent:
    """POST after the operator answers: CallerID / CalledID / Idchain."""

    caller_id: str
    called_id: str
    idchain: str
    op_name: str
    call_type: str

    def as_dict(self) -> dict[str, str]:
        return {
            "CallerID": self.caller_id,
            "CalledID": self.called_id,
            "Idchain": self.idchain,
            "op_name": self.op_name,
            "call_type": self.call_type,
        }


def _field(payload: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def parse_pickup_payload(payload: Mapping[str, Any] | None) -> PickupEvent:
    if not isinstance(payload, Mapping):
        raise OktellWebhookError("body must be a JSON object")
    caller_id = _field(payload, "CallerID", "callerid", "caller_id")
    called_id = _field(payload, "CalledID", "calledid", "called_id")
    idchain = _field(payload, "Idchain", "idchain", "chainid", "IdChain")
    op_name = _field(payload, "op_name", "opName", "userlogin")
    call_type = _field(payload, "call_type", "callType").lower() or "in"
    if call_type not in {"in", "out"}:
        raise OktellWebhookError("call_type must be in or out")
    missing = [
        name
        for name, value in (
            ("CallerID", caller_id),
            ("CalledID", called_id),
            ("Idchain", idchain),
        )
        if not value
    ]
    if missing:
        raise OktellWebhookError(f"missing fields: {', '.join(missing)}")
    if not called_id.isdigit():
        raise OktellWebhookError("CalledID must be the 1xxx line number")
    return PickupEvent(
        caller_id=caller_id,
        called_id=called_id,
        idchain=idchain,
        op_name=op_name,
        call_type=call_type,
    )


def listen_codes(called_id: str) -> dict[str, str]:
    """Oktell 02*/03* or plain line (listen PBX has no star codes)."""
    line = called_id.strip()
    style = (os.getenv("OKTELL_SIP_BARGE") or "star").strip().lower()
    if style in {"direct", "line", "plain"}:
        return {"client": line, "operator": line, "mixed": line}
    swap = (os.getenv("OKTELL_SIP_SWAP_SPEAKERS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if swap:
        return {
            "client": f"03*{line}",
            "operator": f"02*{line}",
            "mixed": f"01*{line}",
        }
    return {
        "client": f"02*{line}",
        "operator": f"03*{line}",
        "mixed": f"01*{line}",
    }

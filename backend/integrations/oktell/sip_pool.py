"""SIP listen accounts 2xxx (vendor sipuser_extended_LP). Passwords stay in env."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from django.conf import settings


@dataclass(frozen=True)
class SipAccount:
    user: str
    password: str
    server: str
    proxy: str

    @property
    def uri(self) -> str:
        return f"sip:{self.user}@{self.server}" if self.server else f"sip:{self.user}"


def _truthy(name: str, default: str = "") -> str:
    return str(getattr(settings, name, default) or default).strip()


def sip_server() -> str:
    return _truthy("OKTELL_SIP_SERVER", "127.0.0.1")


def sip_proxy() -> str:
    return _truthy("OKTELL_SIP_PROXY")


def sip_domain() -> str:
    return _truthy("OKTELL_SIP_DOMAIN") or sip_server()


def sip_packet_host() -> str:
    """UDP destination for REGISTER/INVITE. PBX IP, not this Debian host."""
    return sip_proxy() or sip_server()


def parse_password_map(raw: str) -> dict[str, str]:
    text = (raw or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("OKTELL_SIP_PASSWORDS_JSON must be an object")
        return {str(key): str(value) for key, value in data.items()}
    mapping: dict[str, str] = {}
    for chunk in text.split(","):
        if not chunk.strip():
            continue
        if ":" not in chunk:
            raise ValueError("OKTELL_SIP_ACCOUNTS items must be user:password")
        user, password = chunk.split(":", 1)
        mapping[user.strip()] = password
    return mapping


def account_pool() -> list[SipAccount]:
    start = int(getattr(settings, "OKTELL_SIP_USER_START", 2001) or 2001)
    count = int(getattr(settings, "OKTELL_SIP_USER_COUNT", 8) or 8)
    passwords = parse_password_map(_truthy("OKTELL_SIP_PASSWORDS_JSON") or _truthy("OKTELL_SIP_ACCOUNTS"))
    default_password = _truthy("OKTELL_SIP_PASSWORD")
    server = sip_domain()
    proxy = sip_packet_host()
    accounts: list[SipAccount] = []
    for offset in range(max(count, 1)):
        user = str(start + offset)
        accounts.append(
            SipAccount(
                user=user,
                password=passwords.get(user, default_password),
                server=server,
                proxy=proxy,
            )
        )
    return accounts


def listen_mode() -> str:
    mode = _truthy("OKTELL_LISTEN_MODE", "mock").lower()
    return "sip" if mode == "sip" else "mock"


def mock_client_text() -> str:
    return (
        _truthy("OKTELL_MOCK_CLIENT_TEXT")
        or "Подскажите, как оформить перевод в Россию через мобильный банк?"
    )


def mock_operator_text() -> str:
    return _truthy("OKTELL_MOCK_OPERATOR_TEXT")


def as_settings_snapshot() -> dict[str, Any]:
    return {
        "listen_mode": listen_mode(),
        "sip_server": sip_server(),
        "sip_domain": sip_domain(),
        "sip_proxy": sip_packet_host(),
        "pool_size": len(account_pool()),
        "user_start": int(getattr(settings, "OKTELL_SIP_USER_START", 2001) or 2001),
    }

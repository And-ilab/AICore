"""Oktell connection profiles (VI.2 / P4-02): OKTELL_MODE=mock|prod."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_MOCK_WS_URL = "ws://127.0.0.1:8766"
DEFAULT_SUBSCRIBE_EVENT = "phoneevent"
# Bank TEST line delivered at T+45 (FR-SUF-04 / OKT-7).
TEST_LINE_PROFILE = "test_line_t45"


@dataclass(frozen=True)
class OktellProfile:
    """Resolved runtime profile for SuflerTelephony ↔ Oktell."""

    mode: str
    ws_url: str
    subscribe_event: str
    profile_id: str
    enabled: bool
    line_label: str
    queue: str
    marking: str
    open_timeout: float
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "ws_url": self.ws_url,
            "subscribe_event": self.subscribe_event,
            "profile_id": self.profile_id,
            "enabled": self.enabled,
            "line_label": self.line_label,
            "queue": self.queue,
            "marking": self.marking,
            "open_timeout": self.open_timeout,
            "notes": self.notes,
        }


def normalize_oktell_mode(value: str | None) -> str:
    mode = (value or "mock").strip().lower()
    if mode in {"prod", "production", "test", "t45"}:
        return "prod"
    return "mock"


def _settings_value(name: str, default: Any = None) -> Any:
    try:
        from django.conf import settings

        if settings.configured:
            return getattr(settings, name, default)
    except ImportError:
        pass
    return default


def resolve_oktell_mode(explicit: str | None = None) -> str:
    if explicit:
        return normalize_oktell_mode(explicit)
    return normalize_oktell_mode(str(_settings_value("OKTELL_MODE", "mock") or "mock"))


def resolve_oktell_profile(
    *,
    mode: str | None = None,
    ws_url: str | None = None,
) -> OktellProfile:
    """Pick mock local mock or prod/TEST T+45 line profile."""
    resolved_mode = resolve_oktell_mode(mode)
    enabled = bool(_settings_value("OKTELL_ENABLED", False))
    subscribe = str(
        _settings_value("OKTELL_SUBSCRIBE_EVENT", DEFAULT_SUBSCRIBE_EVENT)
        or DEFAULT_SUBSCRIBE_EVENT
    )
    open_timeout = float(_settings_value("OKTELL_OPEN_TIMEOUT_SECONDS", 5.0) or 5.0)

    if resolved_mode == "mock":
        url = ws_url or str(
            _settings_value("OKTELL_WS_URL", DEFAULT_MOCK_WS_URL) or DEFAULT_MOCK_WS_URL
        )
        # In mock mode prefer dedicated mock URL if set.
        mock_url = _settings_value("OKTELL_MOCK_WS_URL", "")
        if mock_url and not ws_url:
            url = str(mock_url)
        return OktellProfile(
            mode="mock",
            ws_url=url,
            subscribe_event=subscribe,
            profile_id="oktell_mock",
            enabled=enabled,
            line_label="local-oktell-mock",
            queue="mock",
            marking="DEV_MOCK",
            open_timeout=open_timeout,
            notes="P1-14 / P4-02 local websocket mock (oktell_mock)",
        )

    # prod / TEST T+45 profile
    prod_url = ws_url or str(
        _settings_value("OKTELL_PROD_WS_URL", "")
        or _settings_value("OKTELL_WS_URL", "")
        or ""
    )
    if not prod_url:
        raise ValueError(
            "OKTELL_MODE=prod requires OKTELL_PROD_WS_URL or OKTELL_WS_URL "
            "(test Oktell line T+45)"
        )
    return OktellProfile(
        mode="prod",
        ws_url=prod_url,
        subscribe_event=subscribe,
        profile_id=str(
            _settings_value("OKTELL_PROFILE_ID", TEST_LINE_PROFILE)
            or TEST_LINE_PROFILE
        ),
        enabled=enabled,
        line_label=str(
            _settings_value("OKTELL_TEST_LINE_LABEL", "T+45 test line")
            or "T+45 test line"
        ),
        queue=str(_settings_value("OKTELL_TEST_QUEUE", "") or ""),
        marking=str(
            _settings_value("OKTELL_TEST_MARKING", "TEST_OKTELL_T45")
            or "TEST_OKTELL_T45"
        ),
        open_timeout=open_timeout,
        notes="Bank TEST Oktell line (T+45 / FR-SUF-04 / OKT-7)",
    )


def resolve_oktell_ws_url(
    explicit: str | None = None,
    *,
    mode: str | None = None,
) -> str:
    """Resolve WS URL honouring OKTELL_MODE (P4-02 entry point)."""
    if explicit:
        return explicit
    return resolve_oktell_profile(mode=mode).ws_url

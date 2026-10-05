"""Bitrix SUZ Model B client: webhook config + INT-09 /changes polling."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from django.conf import settings


class BitrixClientError(RuntimeError):
    """Bitrix REST / changes API failure."""


@dataclass
class ChangesPage:
    cursor: str
    events: list[dict[str, Any]]


class BitrixChangesClient(Protocol):
    def fetch_changes(self, since: str, *, limit: int = 100) -> ChangesPage: ...


@dataclass
class MockBitrixChangesClient:
    """In-process stand-in used when SUZ_INGEST_MODE=mock (local INT-T)."""

    pages: dict[str, ChangesPage] = field(default_factory=dict)
    default_page: ChangesPage | None = None

    def seed(self, since: str, events: list[Mapping[str, Any]], cursor: str) -> None:
        self.pages[since] = ChangesPage(
            cursor=cursor,
            events=[dict(item) for item in events],
        )

    def fetch_changes(self, since: str, *, limit: int = 100) -> ChangesPage:
        page = self.pages.get(since) or self.default_page
        if page is None:
            return ChangesPage(cursor=since or _utcnow_iso(), events=[])
        return ChangesPage(cursor=page.cursor, events=list(page.events)[:limit])


@dataclass
class HttpBitrixChangesClient:
    """Production Model B fallback: GET …/changes?since=&limit= (INT-09)."""

    base_url: str
    service_token: str
    changes_path: str
    timeout_seconds: float = 15.0

    def fetch_changes(self, since: str, *, limit: int = 100) -> ChangesPage:
        if not self.base_url:
            raise BitrixClientError("BITRIX_REST_BASE_URL is not configured")
        if not self.service_token:
            raise BitrixClientError("BITRIX_SERVICE_TOKEN is not configured")

        query = urlencode({"since": since, "limit": min(max(limit, 1), 100)})
        path = self.changes_path.lstrip("/")
        url = urljoin(self.base_url.rstrip("/") + "/", f"{path}?{query}")
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self.service_token}",
                "Accept": "application/json",
                "User-Agent": "sufler-ingest-reconcile/1.0",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise BitrixClientError(
                f"Bitrix changes HTTP {exc.code}: {body[:300]}"
            ) from exc
        except URLError as exc:
            raise BitrixClientError(f"Bitrix changes unreachable: {exc}") from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BitrixClientError("Bitrix changes returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise BitrixClientError("Bitrix changes root must be an object")

        cursor = str(payload.get("cursor") or since or _utcnow_iso())
        events_raw = payload.get("events") or []
        if not isinstance(events_raw, list):
            raise BitrixClientError("Bitrix changes.events must be a list")
        events = [dict(item) for item in events_raw if isinstance(item, Mapping)]
        return ChangesPage(cursor=cursor, events=events[:limit])


_MOCK_CLIENT = MockBitrixChangesClient()


def reset_mock_bitrix_client() -> MockBitrixChangesClient:
    global _MOCK_CLIENT
    _MOCK_CLIENT = MockBitrixChangesClient()
    return _MOCK_CLIENT


def get_mock_bitrix_client() -> MockBitrixChangesClient:
    return _MOCK_CLIENT


def ingest_mode() -> str:
    mode = str(getattr(settings, "SUZ_INGEST_MODE", "mock") or "mock").strip().lower()
    return mode if mode in {"mock", "prod"} else "mock"


def get_bitrix_changes_client() -> BitrixChangesClient:
    if ingest_mode() == "mock" or not getattr(settings, "BITRIX_REST_BASE_URL", ""):
        return _MOCK_CLIENT
    return HttpBitrixChangesClient(
        base_url=str(settings.BITRIX_REST_BASE_URL),
        service_token=str(getattr(settings, "BITRIX_SERVICE_TOKEN", "") or ""),
        changes_path=str(
            getattr(settings, "BITRIX_CHANGES_PATH", "/local/api/sufler/v1/changes")
        ),
        timeout_seconds=float(
            getattr(settings, "BITRIX_HTTP_TIMEOUT_SECONDS", 15.0)
        ),
    )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

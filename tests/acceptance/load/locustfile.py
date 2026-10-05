"""II.7.4 Locust load: 75 virtual operators → POST /api/v1/sufler/suggest.

Two user classes:

- ``SuflerSuggestHttpUser`` — HTTP against a running backend (manual / staging).
- ``SuflerSuggestPipelineUser`` — in-process ``orchestrator.sufler.suggest``
  (CI / no external server). Selected with ``--class-picker`` or
  ``LOAD_MODE=pipeline|http`` via ``run_load.py``.

Target: p95(suggest) ≤ 2000 ms at 75 concurrent operators (FR-SUF-06).
"""

from __future__ import annotations

import json
import os
import random
import time
from typing import Any

from locust import HttpUser, User, between, events, task


TARGET_P95_MS = 2000
DEFAULT_USERS = 75

QUERIES = (
    "как оформить дебетовую карту",
    "замена пин-кода карты",
    "лимит снятия наличных",
    "как открыть вклад",
    "комиссия за перевод",
    "блокировка карты при утере",
    "реквизиты для перевода",
    "справка о состоянии счета",
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@events.init.add_listener
def _on_locust_init(environment, **_kwargs):
    """Ensure Django is ready when running pipeline users."""
    mode = os.getenv("LOAD_MODE", "pipeline").strip().lower()
    if mode != "pipeline" and not _env_bool("LOAD_FORCE_DJANGO_SETUP"):
        return
    import django
    from pathlib import Path
    import sys

    root = Path(__file__).resolve().parents[3]
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")
    django.setup()


class SuflerSuggestHttpUser(HttpUser):
    """75 virtual operators hitting the suggest HTTP API."""

    wait_time = between(0.3, 1.0)
    host = os.getenv("SUFLER_BASE_URL", "http://127.0.0.1:8000")

    def on_start(self) -> None:
        self._ensure_session()

    def _ensure_session(self) -> None:
        session_id = os.getenv("SUFLER_LOAD_SESSIONID", "").strip()
        if session_id:
            self.client.cookies.set("sessionid", session_id)
            return
        username = os.getenv("SUFLER_LOAD_USERNAME", "dev-role-04")
        password = os.getenv(
            "SUFLER_LOAD_PASSWORD",
            os.getenv("AUTH_MOCK_LDAP_DEFAULT_PASSWORD", "dev-only-password"),
        )
        response = self.client.post(
            "/api/auth/login/",
            data=json.dumps({"username": username, "password": password}),
            headers={"Content-Type": "application/json"},
            name="auth_login",
        )
        if response.status_code >= 400:
            response.failure(
                f"login failed HTTP {response.status_code}: {response.text[:200]}"
            )

    @task
    def suggest(self) -> None:
        query = random.choice(QUERIES)
        with self.client.post(
            "/api/v1/sufler/suggest",
            data=json.dumps({"text": query, "limit": 3}),
            headers={
                "Content-Type": "application/json",
                "X-Request-ID": f"load-{random.randint(1, 10_000_000)}",
            },
            name="sufler_suggest",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return
            try:
                body = response.json()
            except Exception as exc:  # noqa: BLE001
                response.failure(f"invalid JSON: {exc}")
                return
            total_ms = float((body.get("latency_ms") or {}).get("total") or 0)
            if total_ms > TARGET_P95_MS:
                # Still a successful request; SLA judged on aggregate p95.
                response.success()
            else:
                response.success()


class SuflerSuggestPipelineUser(User):
    """In-process suggest pipeline (CI-friendly, no HTTP server)."""

    wait_time = between(0.05, 0.25)
    abstract = False

    def on_start(self) -> None:
        from orchestrator.sufler import suggest

        self._bind_db_to_greenlet()
        self._suggest = suggest

    @staticmethod
    def _bind_db_to_greenlet() -> None:
        """Drop DB wrappers created on another OS thread / greenlet."""
        from django.db import connections
        from django.db.utils import DatabaseError

        for alias in connections:
            try:
                conn = connections[alias]
                if conn.connection is not None:
                    conn.validate_thread_sharing()
            except DatabaseError:
                try:
                    delattr(connections._connections, alias)
                except AttributeError:
                    pass

    @task
    def suggest(self) -> None:
        self._bind_db_to_greenlet()
        query = random.choice(QUERIES)
        started = time.perf_counter()
        exception: Exception | None = None
        length = 0
        try:
            result: dict[str, Any] = self._suggest(query, limit=3)
            length = len(json.dumps(result, ensure_ascii=False))
            # Prefer pipeline-reported total; fall back to wall clock.
            reported = float((result.get("latency_ms") or {}).get("total") or 0)
            wall_ms = (time.perf_counter() - started) * 1000
            response_time = reported if reported > 0 else wall_ms
        except Exception as exc:  # noqa: BLE001
            exception = exc
            response_time = (time.perf_counter() - started) * 1000

        self.environment.events.request.fire(
            request_type="PIPELINE",
            name="sufler_suggest",
            response_time=response_time,
            response_length=length,
            exception=exception,
            context={},
        )

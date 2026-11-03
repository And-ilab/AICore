"""Windows Integrated Auth (Kerberos Negotiate) for I.10.

Disabled unless ``AUTH_SSO_NEGOTIATE`` is true. The browser presents the
ticket of the user who already signed in to Windows. This module checks
the ticket with the keytab (``KRB5_KTNAME``) and loads the AD profile
through the existing service bind — the user password is not required.

``gssapi`` is imported only when a ticket is presented, so local Windows
development without Kerberos libraries still starts.
"""

from __future__ import annotations

import base64
import logging
import secrets
import threading
import time
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

LDAP_BACKEND_PATH = "django_auth_ldap.backend.LDAPBackend"
SSO_STATE_COOKIE = "sso_nego"
REFRESH_SESSION_KEY = "ad_profile_refreshed_at"
_PENDING_TTL_SECONDS = 120
_pending: dict[str, tuple[float, object]] = {}
_pending_lock = threading.Lock()


class SsoError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail or code
        super().__init__(self.detail)


def log_sso(
    stage: str,
    *,
    http_status: int | str,
    message: str,
    user: str = "",
    remote: str = "",
    error: str = "",
    level: int = logging.INFO,
) -> None:
    """One line for an SSO step: stage, HTTP status, who, and why."""
    logger.log(
        level,
        "sso stage=%s http=%s user=%s remote=%s error=%s message=%s",
        stage,
        http_status,
        user or "-",
        remote or "-",
        error or "-",
        message,
    )


@dataclass(frozen=True)
class NegotiateResult:
    username: str = ""
    continuation: str | None = None
    state: str | None = None
    mutual_token: str | None = None


def sso_enabled() -> bool:
    return bool(getattr(settings, "AUTH_SSO_NEGOTIATE", False))


def sam_account_name(principal: str) -> str:
    """``user@REALM``, ``DOMAIN\\user``, or ``user/extra@REALM`` → sAMAccountName."""
    raw = (principal or "").strip()
    if len(raw) >= 6 and raw[:5].lower() == "name(" and raw.endswith(")"):
        raw = raw[5:-1].strip()
    if "\\" in raw:
        raw = raw.rsplit("\\", 1)[-1].strip()
    if "@" in raw:
        raw = raw.split("@", 1)[0].strip()
    if "/" in raw:
        raw = raw.split("/", 1)[0].strip()
    return raw


def profile_names(user: object, authenticated: bool) -> dict[str, str | None]:
    if not authenticated:
        return {
            "first_name": None,
            "last_name": None,
            "display_name": None,
        }
    first = str(getattr(user, "first_name", "") or "").strip()
    last = str(getattr(user, "last_name", "") or "").strip()
    username = ""
    get_username = getattr(user, "get_username", None)
    if callable(get_username):
        username = str(get_username() or "").strip()
    display = f"{first} {last}".strip() or username or None
    return {
        "first_name": first or None,
        "last_name": last or None,
        "display_name": display,
    }


def _attr_text(attrs: dict, *keys: str) -> str:
    for key in keys:
        values = attrs.get(key)
        if not values:
            continue
        raw = values[0]
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        text = str(raw).strip()
        if text:
            return text
    return ""


def ldap_display_name(user: object) -> str:
    ldap_user = getattr(user, "ldap_user", None)
    attrs = getattr(ldap_user, "attrs", None) or {}
    if not isinstance(attrs, dict):
        return ""
    return _attr_text(attrs, "displayName", "displayname", "DisplayName")


def apply_display_name_fallback(user: object) -> None:
    """If AD left givenName/sn empty, persist displayName as the visible name."""
    first = str(getattr(user, "first_name", "") or "").strip()
    last = str(getattr(user, "last_name", "") or "").strip()
    if first or last:
        return
    display = ldap_display_name(user)
    if not display or not hasattr(user, "save"):
        return
    user.first_name = display[:150]
    user.save(update_fields=["first_name"])


def provision_ad_user(username: str):
    """Service-bind lookup. Password of the Windows user is not used."""
    account = sam_account_name(username)
    if not account:
        return None
    if getattr(settings, "AUTH_BACKEND", "") != "ldaps":
        raise SsoError("ldaps_required", "AUTH_BACKEND is not ldaps")
    try:
        from django_auth_ldap.backend import LDAPBackend
    except ImportError as exc:
        raise SsoError("ldap_backend_unavailable", str(exc)) from exc
    try:
        user = LDAPBackend().populate_user(account)
    except Exception as exc:
        raise SsoError("ad_lookup_failed", str(exc)) from exc
    if user is None or not getattr(user, "is_active", True):
        return None
    apply_display_name_fallback(user)
    user.backend = LDAP_BACKEND_PATH
    return user


def _purge_pending(now: float) -> None:
    stale = [
        key
        for key, (created, _ctx) in _pending.items()
        if now - created > _PENDING_TTL_SECONDS
    ]
    for key in stale:
        _pending.pop(key, None)


def _store_context(ctx: object) -> str:
    state = secrets.token_urlsafe(24)
    now = time.time()
    with _pending_lock:
        _purge_pending(now)
        _pending[state] = (now, ctx)
    return state


def _take_context(state: str):
    if not state:
        return None
    with _pending_lock:
        item = _pending.pop(state, None)
    if item is None:
        log_sso(
            "negotiate_context",
            http_status=401,
            error="context_missing",
            message="sso_nego cookie does not match a pending negotiate context",
            level=logging.WARNING,
        )
        return None
    created, ctx = item
    if time.time() - created > _PENDING_TTL_SECONDS:
        log_sso(
            "negotiate_context",
            http_status=401,
            error="context_expired",
            message="pending negotiate context is older than 120 seconds",
            level=logging.WARNING,
        )
        return None
    return ctx


def accept_negotiate(token_b64: str, state: str = "") -> NegotiateResult:
    try:
        import gssapi
    except ImportError as exc:
        raise SsoError("gssapi_unavailable", str(exc)) from exc
    ctx = _take_context(state)
    if ctx is None:
        try:
            creds = gssapi.Credentials(usage="accept")
            ctx = gssapi.SecurityContext(creds=creds, usage="accept")
        except Exception as exc:
            raise SsoError("keytab_unavailable", str(exc)) from exc
    try:
        incoming = base64.b64decode(token_b64.strip(), validate=False)
    except Exception as exc:
        raise SsoError("invalid_negotiate_token", str(exc)) from exc
    try:
        out_token = ctx.step(incoming)
    except Exception as exc:
        raise SsoError("negotiate_rejected", str(exc)) from exc
    out_b64 = ""
    if out_token:
        out_b64 = base64.b64encode(bytes(out_token)).decode("ascii")
    if not getattr(ctx, "complete", False):
        new_state = _store_context(ctx)
        return NegotiateResult(
            continuation=out_b64 or None,
            state=new_state,
        )
    principal = str(getattr(ctx, "initiator_name", "") or "")
    username = sam_account_name(principal)
    if not username:
        raise SsoError("empty_principal", "initiator name is empty")
    return NegotiateResult(
        username=username,
        mutual_token=out_b64 or None,
    )


def mark_profile_refreshed(request) -> None:
    request.session[REFRESH_SESSION_KEY] = time.time()


def refresh_ad_profile(request) -> None:
    """Reload name and groups, at most once per AUTH_LDAP_CACHE_TIMEOUT."""
    if getattr(settings, "AUTH_BACKEND", "") != "ldaps":
        return
    if not getattr(request.user, "is_authenticated", False):
        return
    timeout = int(getattr(settings, "AUTH_LDAP_CACHE_TIMEOUT", 300) or 300)
    now = time.time()
    raw_last = request.session.get(REFRESH_SESSION_KEY)
    try:
        last = float(raw_last) if raw_last is not None else 0.0
    except (TypeError, ValueError):
        last = 0.0
    if last and now - last < timeout:
        return
    username = request.user.get_username()
    try:
        user = provision_ad_user(username)
    except SsoError as exc:
        log_sso(
            "refresh",
            http_status="-",
            user=username,
            error=exc.code,
            message=exc.detail,
            level=logging.WARNING,
        )
        return
    if user is None:
        log_sso(
            "refresh",
            http_status="-",
            user=username,
            error="ad_user_not_found",
            message="AD user is missing or inactive",
            level=logging.WARNING,
        )
        return
    request.session[REFRESH_SESSION_KEY] = now
    request.user = user

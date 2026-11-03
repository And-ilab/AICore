"""HTTP side of Windows Negotiate: ask for a ticket or open a session."""

from __future__ import annotations

import logging

from django.contrib.auth import login
from django.http import HttpRequest, JsonResponse

from auth.sso import (
    SSO_STATE_COOKIE,
    SsoError,
    accept_negotiate,
    log_sso,
    mark_profile_refreshed,
    provision_ad_user,
    refresh_ad_profile,
    sso_enabled,
)


def _anonymous_body(*, error: str | None = None) -> dict:
    body = {
        "authenticated": False,
        "username": None,
        "roles": [],
        "tabs": [],
        "first_name": None,
        "last_name": None,
        "display_name": None,
    }
    if error:
        body["error"] = error
    return body


def _negotiate_challenge(
    *,
    error: str | None = None,
    token: str | None = None,
) -> JsonResponse:
    response = JsonResponse(_anonymous_body(error=error), status=401)
    if token:
        response["WWW-Authenticate"] = f"Negotiate {token}"
    else:
        response["WWW-Authenticate"] = "Negotiate"
    return response


def _sso_remote(request: HttpRequest) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or "-"
    return request.META.get("REMOTE_ADDR", "") or "-"


def _establish_sso(request: HttpRequest) -> JsonResponse | None:
    """Create a session from a Kerberos ticket, or ask the browser for one.

    Returns a 401 challenge, or None when the request can be answered
    from the (possibly just created) session.
    """
    if not sso_enabled():
        return None
    remote = _sso_remote(request)
    if getattr(request.user, "is_authenticated", False):
        refresh_ad_profile(request)
        return None
    header = request.headers.get("Authorization", "")
    if header[:10].lower() != "negotiate ":
        log_sso(
            "challenge",
            http_status=401,
            remote=remote,
            message="browser did not send a Negotiate token",
        )
        return _negotiate_challenge()
    token = header.split(" ", 1)[1].strip()
    if not token:
        log_sso(
            "read_token",
            http_status=401,
            remote=remote,
            error="invalid_negotiate_token",
            message="Authorization Negotiate value is empty",
            level=logging.WARNING,
        )
        return _negotiate_challenge(error="invalid_negotiate_token")
    state = request.COOKIES.get(SSO_STATE_COOKIE, "")
    try:
        result = accept_negotiate(token, state)
    except SsoError as exc:
        log_sso(
            "accept_ticket",
            http_status=401,
            remote=remote,
            error=exc.code,
            message=exc.detail,
            level=logging.WARNING,
        )
        response = _negotiate_challenge(error=exc.code)
        response.delete_cookie(SSO_STATE_COOKIE, path="/")
        return response
    if result.state:
        log_sso(
            "continue",
            http_status=401,
            remote=remote,
            error="negotiate_continue",
            message="negotiate context is incomplete",
        )
        response = _negotiate_challenge(
            error="negotiate_continue",
            token=result.continuation,
        )
        response.set_cookie(
            SSO_STATE_COOKIE,
            result.state,
            max_age=120,
            httponly=True,
            samesite="Lax",
            path="/",
        )
        return response
    try:
        user = provision_ad_user(result.username)
    except SsoError as exc:
        log_sso(
            "ad_lookup",
            http_status=401,
            user=result.username,
            remote=remote,
            error=exc.code,
            message=exc.detail,
            level=logging.WARNING,
        )
        return _negotiate_challenge(error=exc.code)
    if user is None:
        log_sso(
            "ad_lookup",
            http_status=401,
            user=result.username,
            remote=remote,
            error="ad_user_not_found",
            message="AD user is missing or inactive",
            level=logging.WARNING,
        )
        return _negotiate_challenge(error="ad_user_not_found")
    login(request, user)
    mark_profile_refreshed(request)
    request.user = user
    request._sso_clear_nego = True  # type: ignore[attr-defined]
    if result.mutual_token:
        request._sso_mutual_token = result.mutual_token  # type: ignore[attr-defined]
    log_sso(
        "session",
        http_status=200,
        user=result.username,
        remote=remote,
        message="session created",
    )
    return None

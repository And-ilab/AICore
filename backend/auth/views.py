"""Session-auth context and login API for portal / I.10 AD smoke tests."""

from __future__ import annotations

import json

from django.contrib.auth import authenticate, login, logout
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from auth.negotiate import _establish_sso
from auth.roles import role_codes_for_user, tabs_for_user
from auth.sso import (
    SSO_STATE_COOKIE,
    apply_display_name_fallback,
    profile_names,
)


def _auth_payload(request: HttpRequest) -> dict:
    authenticated = bool(
        getattr(request.user, "is_authenticated", False)
    )
    body = {
        "authenticated": authenticated,
        "username": (
            request.user.get_username() if authenticated else None
        ),
        "roles": sorted(role_codes_for_user(request.user)),
        "tabs": list(tabs_for_user(request.user)),
    }
    body.update(profile_names(request.user, authenticated))
    return body


@require_GET
@ensure_csrf_cookie
def auth_context(request: HttpRequest) -> JsonResponse:
    """Also sets csrftoken cookie for SPA mutating calls (KB upload, create).

    When ``AUTH_SSO_NEGOTIATE`` is on and there is no session, the response
    is 401 ``WWW-Authenticate: Negotiate`` so the browser can send the
    Windows ticket without a second password.
    """
    challenge = _establish_sso(request)
    if challenge is not None:
        return challenge
    response = JsonResponse(_auth_payload(request))
    if getattr(request, "_sso_clear_nego", False):
        response.delete_cookie(SSO_STATE_COOKIE, path="/")
    mutual = getattr(request, "_sso_mutual_token", None)
    if mutual:
        response["WWW-Authenticate"] = f"Negotiate {mutual}"
    return response


@csrf_exempt
@require_http_methods(["POST"])
def auth_login(request: HttpRequest) -> JsonResponse:
    """I.10 test login: AD / mock credentials → Django session.

    Body JSON: ``{"username": "...", "password": "..."}``.
    On success mirrors groups → I.4 roles via AUTH_LDAP_ROLE_GROUP_MAP / C2.
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {"ok": False, "error": "invalid_json"},
            status=400,
        )
    username = str(payload.get("username") or "").strip()
    password = payload.get("password")
    if not username or not isinstance(password, str):
        return JsonResponse(
            {"ok": False, "error": "username_and_password_required"},
            status=400,
        )
    user = authenticate(
        request,
        username=username,
        password=password,
    )
    if user is None:
        return JsonResponse(
            {"ok": False, "error": "invalid_credentials"},
            status=401,
        )
    apply_display_name_fallback(user)
    if not hasattr(user, "backend"):
        backends = getattr(settings, "AUTHENTICATION_BACKENDS", ())
        user.backend = (
            backends[0]
            if backends
            else "django.contrib.auth.backends.ModelBackend"
        )
    login(request, user)
    body = _auth_payload(request)
    body["ok"] = True
    return JsonResponse(body)


@csrf_exempt
@require_http_methods(["POST"])
def auth_logout(request: HttpRequest) -> JsonResponse:
    logout(request)
    return JsonResponse({"ok": True, "authenticated": False})

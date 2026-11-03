"""HTTP side of Windows Negotiate: ask for a ticket or open a session."""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import login
from django.http import HttpRequest, JsonResponse

from auth.sso import (
    SSO_STATE_COOKIE,
    AdProfile,
    KerberosTicket,
    SsoError,
    ad_profile,
    kerberos_ticket,
)

logger = logging.getLogger(__name__)


class NegotiateHandshake:
    """Turn a browser Negotiate exchange into a Django session."""

    def __init__(self, ticket: KerberosTicket, profile: AdProfile) -> None:
        self.ticket = ticket
        self.profile = profile

    def establish(self, request: HttpRequest) -> JsonResponse | None:
        """Create a session from a Kerberos ticket, or ask the browser for one.

        Returns a 401 challenge, or None when the request can be answered
        from the (possibly just created) session.
        """
        if not self.enabled():
            return None
        remote = self.remote(request)
        if getattr(request.user, "is_authenticated", False):
            self.profile.refresh(request)
            return None
        header = request.headers.get("Authorization", "")
        if header[:10].lower() != "negotiate ":
            logger.info("sso_challenge remote=%s http=%s", remote, 401)
            return self.challenge()
        token = header.split(" ", 1)[1].strip()
        if not token:
            logger.warning(
                "sso_read_token remote=%s http=%s error=%s detail=%s",
                remote,
                401,
                "invalid_negotiate_token",
                "Authorization Negotiate value is empty",
            )
            return self.challenge(error="invalid_negotiate_token")
        state = request.COOKIES.get(SSO_STATE_COOKIE, "")
        try:
            result = self.ticket.accept(token, state)
        except SsoError as exc:
            logger.warning(
                "sso_accept_ticket remote=%s http=%s error=%s detail=%s",
                remote,
                401,
                exc.code,
                exc.detail,
            )
            response = self.challenge(error=exc.code)
            response.delete_cookie(SSO_STATE_COOKIE, path="/")
            return response
        if result.state:
            logger.info(
                "sso_continue remote=%s http=%s error=%s",
                remote,
                401,
                "negotiate_continue",
            )
            response = self.challenge(
                error="negotiate_continue",
                token=result.continuation,
            )
            response.set_cookie(
                SSO_STATE_COOKIE,
                result.state,
                max_age=self.ticket.pending.ttl_seconds,
                httponly=True,
                samesite="Lax",
                path="/",
            )
            return response
        try:
            user = self.profile.provision(result.username)
        except SsoError as exc:
            logger.warning(
                "sso_ad_lookup user=%s remote=%s http=%s error=%s detail=%s",
                result.username,
                remote,
                401,
                exc.code,
                exc.detail,
            )
            return self.challenge(error=exc.code)
        if user is None:
            logger.warning(
                "sso_ad_lookup user=%s remote=%s http=%s error=%s detail=%s",
                result.username,
                remote,
                401,
                "ad_user_not_found",
                "AD user is missing or inactive",
            )
            return self.challenge(error="ad_user_not_found")
        login(request, user)
        self.profile.mark_refreshed(request)
        request.user = user
        request._sso_clear_nego = True  # type: ignore[attr-defined]
        if result.mutual_token:
            request._sso_mutual_token = result.mutual_token  # type: ignore[attr-defined]
        logger.info(
            "sso_session user=%s remote=%s http=%s",
            result.username,
            remote,
            200,
        )
        return None

    def enabled(self) -> bool:
        return bool(getattr(settings, "AUTH_SSO_NEGOTIATE", False))

    def challenge(
        self,
        *,
        error: str | None = None,
        token: str | None = None,
    ) -> JsonResponse:
        response = JsonResponse(self.anonymous_body(error=error), status=401)
        if token:
            response["WWW-Authenticate"] = f"Negotiate {token}"
        else:
            response["WWW-Authenticate"] = "Negotiate"
        return response

    @staticmethod
    def anonymous_body(*, error: str | None = None) -> dict:
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

    @staticmethod
    def remote(request: HttpRequest) -> str:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip() or "-"
        return request.META.get("REMOTE_ADDR", "") or "-"


handshake = NegotiateHandshake(kerberos_ticket, ad_profile)

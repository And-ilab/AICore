"""Windows Negotiate SSO: ticket → AD profile, without a second password."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client, SimpleTestCase, TestCase, override_settings  # noqa: E402

from auth.sso import (  # noqa: E402
    NegotiateResult,
    SsoError,
    account_name,
    ad_profile,
)


class SamAccountNameTest(SimpleTestCase):
    def test_strips_realm_domain_and_extra_components(self):
        self.assertEqual(account_name.parse("ivan.petrov@BANK.LOCAL"), "ivan.petrov")
        self.assertEqual(account_name.parse(r"BANK\ivan.petrov"), "ivan.petrov")
        self.assertEqual(
            account_name.parse("ivan.petrov/admin@BANK.LOCAL"),
            "ivan.petrov",
        )
        self.assertEqual(account_name.parse("  ivan.petrov  "), "ivan.petrov")
        self.assertEqual(account_name.parse("Name(ivan.petrov@BANK.LOCAL)"), "ivan.petrov")
        self.assertEqual(account_name.parse(""), "")


@override_settings(AUTH_SSO_NEGOTIATE=False)
class AuthMeProfileTest(TestCase):
    def test_me_returns_given_name_and_surname(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="ivan.petrov",
            password="unused",
            first_name="Иван",
            last_name="Петров",
        )
        client = Client()
        client.force_login(user)
        payload = client.get("/api/auth/me/").json()
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["first_name"], "Иван")
        self.assertEqual(payload["last_name"], "Петров")
        self.assertEqual(payload["display_name"], "Иван Петров")

    def test_display_name_attribute_fills_empty_given_name(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="display.only",
            password="unused",
        )

        class _Ldap:
            attrs = {"displayName": ["Иванов Иван Иванович"]}

        user.ldap_user = _Ldap()
        ad_profile.apply_display_name(user)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Иванов Иван Иванович")

        named = user_model.objects.create_user(
            username="kept.name",
            password="unused",
            first_name="Иван",
            last_name="Петров",
        )
        named.ldap_user = _Ldap()
        ad_profile.apply_display_name(named)
        named.refresh_from_db()
        self.assertEqual(named.first_name, "Иван")
        self.assertEqual(named.last_name, "Петров")


@override_settings(
    AUTH_SSO_NEGOTIATE=True,
    AUTH_BACKEND="ldaps",
    AUTH_LDAP_CACHE_TIMEOUT=300,
)
class NegotiateLoginTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_model = get_user_model()

    def _ad_user(self, username: str, *, group: str | None):
        user = self.user_model.objects.create_user(
            username=username,
            password="unused",
            first_name="Иван",
            last_name="Петров",
        )
        if group:
            ad_group, _ = Group.objects.get_or_create(name=group)
            user.groups.add(ad_group)
        # ModelBackend is what the test client can reload from the session.
        # Production AdProfile.provision sets the LDAP backend instead.
        user.backend = "django.contrib.auth.backends.ModelBackend"
        return user

    def test_anonymous_me_asks_for_a_ticket(self):
        with self.assertLogs("auth.negotiate", level="INFO") as logs:
            response = self.client.get("/api/auth/me/")
        self.assertTrue(
            any("sso_challenge" in line and "http=401" in line for line in logs.output)
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Negotiate")
        body = response.json()
        self.assertFalse(body["authenticated"])
        self.assertIsNone(body["display_name"])
        self.assertEqual(body["roles"], [])

    @patch("auth.negotiate.handshake.profile.provision")
    @patch("auth.negotiate.handshake.ticket.accept")
    def test_ticket_opens_session_with_ad_roles(
        self,
        accept,
        provision,
    ):
        user = self._ad_user(
            "ivan.petrov",
            group="BB_CC_Telephony_Operator",
        )
        accept.return_value = NegotiateResult(
            username="ivan.petrov",
            mutual_token="mutual-token",
        )
        provision.return_value = user

        response = self.client.get(
            "/api/auth/me/",
            HTTP_AUTHORIZATION="Negotiate dG9rZW4=",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["WWW-Authenticate"], "Negotiate mutual-token")
        body = response.json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["username"], "ivan.petrov")
        self.assertEqual(body["display_name"], "Иван Петров")
        self.assertEqual(body["first_name"], "Иван")
        self.assertEqual(body["last_name"], "Петров")
        # Roles come from the AD group on the session, not from a demo picker.
        self.assertEqual(body["roles"], ["contact_center_telephony_operator"])
        provision.assert_called_once_with("ivan.petrov")

        again = self.client.get("/api/auth/me/")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(
            again.json()["roles"],
            ["contact_center_telephony_operator"],
        )
        provision.assert_called_once_with("ivan.petrov")

    @patch("auth.negotiate.handshake.profile.provision")
    @patch("auth.negotiate.handshake.ticket.accept")
    def test_user_without_mapped_group_still_signs_in(self, accept, provision):
        user = self._ad_user("ivan.petrov", group=None)
        accept.return_value = NegotiateResult(username="ivan.petrov")
        provision.return_value = user

        response = self.client.get(
            "/api/auth/me/",
            HTTP_AUTHORIZATION="Negotiate dG9rZW4=",
        )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["display_name"], "Иван Петров")
        self.assertEqual(body["roles"], [])

    @patch("auth.negotiate.handshake.profile.provision", return_value=None)
    @patch(
        "auth.negotiate.handshake.ticket.accept",
        return_value=NegotiateResult(username="missing"),
    )
    def test_unknown_ad_user_is_rejected(self, _accept, _provision):
        with self.assertLogs("auth.negotiate", level="WARNING") as logs:
            response = self.client.get(
                "/api/auth/me/",
                HTTP_AUTHORIZATION="Negotiate dG9rZW4=",
            )
        self.assertTrue(
            any(
                "sso_ad_lookup" in line and "error=ad_user_not_found" in line
                for line in logs.output
            )
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "ad_user_not_found")

    @patch("auth.negotiate.handshake.ticket.accept")
    def test_incomplete_negotiate_keeps_state(self, accept):
        accept.return_value = NegotiateResult(
            continuation="next-token",
            state="state-1",
        )
        response = self.client.get(
            "/api/auth/me/",
            HTTP_AUTHORIZATION="Negotiate dG9rZW4=",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Negotiate next-token")
        self.assertEqual(response.cookies["sso_nego"].value, "state-1")
        self.assertEqual(response.json()["error"], "negotiate_continue")

    @patch(
        "auth.negotiate.handshake.ticket.accept",
        side_effect=SsoError("negotiate_rejected"),
    )
    def test_rejected_ticket(self, _accept):
        with self.assertLogs("auth.negotiate", level="WARNING") as logs:
            response = self.client.get(
                "/api/auth/me/",
                HTTP_AUTHORIZATION="Negotiate dG9rZW4=",
            )
        self.assertTrue(
            any(
                "sso_accept_ticket" in line
                and "http=401" in line
                and "error=negotiate_rejected" in line
                for line in logs.output
            )
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "negotiate_rejected")
        self.assertEqual(response["WWW-Authenticate"], "Negotiate")


class ProvisionGuardTest(SimpleTestCase):
    @override_settings(AUTH_BACKEND="mock_ldap", AUTH_SSO_NEGOTIATE=True)
    def test_provision_requires_ldaps_backend(self):
        with self.assertRaises(SsoError) as caught:
            ad_profile.provision("ivan.petrov")
        self.assertEqual(caught.exception.code, "ldaps_required")


if __name__ == "__main__":
    unittest.main()

"""I.10 / VII.5 C2 LDAPS auth: backend switch + 13 AD group→role map."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.core.exceptions import ImproperlyConfigured  # noqa: E402
from django.test import Client, SimpleTestCase, TestCase  # noqa: E402

from auth.c2_groups import C2_ROLE_GROUP_MAP, c2_role_group_map  # noqa: E402
from auth.ldap_config import (  # noqa: E402
    merge_c2_role_group_map,
    resolve_auth_backend,
)
from auth.roles import (  # noqa: E402
    ROLE_DEFINITIONS,
    role_codes_from_group_names,
    role_codes_for_user,
)


class C2AdGroupMapTest(SimpleTestCase):
    def test_c2_covers_exactly_thirteen_i4_roles(self):
        mapping = c2_role_group_map()
        self.assertEqual(len(mapping), 13)
        self.assertEqual(set(mapping), {role.code for role in ROLE_DEFINITIONS})
        self.assertEqual(mapping, C2_ROLE_GROUP_MAP)
        for role in ROLE_DEFINITIONS:
            self.assertEqual(mapping[role.code], role.c2_ad_group)
            self.assertTrue(role.c2_ad_group.startswith("BB_"))

    def test_each_c2_group_maps_to_its_i4_role(self):
        for role in ROLE_DEFINITIONS:
            with self.subTest(role=role.code):
                roles = role_codes_from_group_names((role.c2_ad_group,))
                self.assertEqual(roles, {role.code})

    def test_json_override_replaces_single_c2_group(self):
        merged = merge_c2_role_group_map(
            {"ai_assistant_user": "BANK_APPROVED_ASSISTANT_USERS"}
        )
        self.assertEqual(
            merged["ai_assistant_user"],
            "BANK_APPROVED_ASSISTANT_USERS",
        )
        self.assertEqual(len(merged), 13)
        roles = role_codes_from_group_names(
            ("BANK_APPROVED_ASSISTANT_USERS",),
            merged,
        )
        self.assertEqual(roles, {"ai_assistant_user"})

    def test_duplicate_group_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            merge_c2_role_group_map(
                {
                    "ai_assistant_analyst": C2_ROLE_GROUP_MAP[
                        "ai_assistant_user"
                    ],
                }
            )

    def test_unknown_role_in_json_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            merge_c2_role_group_map({"not_a_role": "X"})


class AuthBackendResolveTest(SimpleTestCase):
    def test_auth_backend_wins_over_auth_mode(self):
        self.assertEqual(
            resolve_auth_backend(
                auth_backend="ldaps",
                auth_mode="mock_ldap",
            ),
            "ldaps",
        )

    def test_aliases(self):
        self.assertEqual(
            resolve_auth_backend(auth_mode="ldap"),
            "ldaps",
        )
        self.assertEqual(
            resolve_auth_backend(auth_mode="mock"),
            "mock_ldap",
        )
        self.assertEqual(
            resolve_auth_backend(auth_backend="prod"),
            "ldaps",
        )


class LdapsSettingsBuildTest(SimpleTestCase):
    def test_build_requires_ldaps_uri_and_packages(self):
        from auth import ldap_config

        env = {
            "AUTH_LDAP_SERVER_URI": "ldap://insecure.example",
            "AUTH_LDAP_BIND_DN": "CN=svc",
            "AUTH_LDAP_BIND_PASSWORD": "x",
            "AUTH_LDAP_USER_SEARCH_BASE": "OU=Users",
            "AUTH_LDAP_GROUP_SEARCH_BASE": "OU=Groups",
        }
        with patch.dict(os.environ, env, clear=False):
            # Without ALLOW_INSECURE, plain ldap:// must fail — but only after
            # packages import. Stub packages so Windows CI can run this.
            fake_ldap = MagicMock()
            fake_ldap.SCOPE_SUBTREE = 2
            fake_ldap.OPT_REFERRALS = 0
            fake_ldap.OPT_X_TLS_REQUIRE_CERT = 1
            fake_ldap.OPT_X_TLS_DEMAND = 2
            fake_ldap.OPT_X_TLS_CACERTFILE = 3
            fake_ldap.OPT_X_TLS_NEWCTX = 4
            fake_search = MagicMock()
            fake_group_type = MagicMock()
            with patch.dict(
                sys.modules,
                {
                    "ldap": fake_ldap,
                    "django_auth_ldap": MagicMock(),
                    "django_auth_ldap.config": MagicMock(
                        LDAPSearch=fake_search,
                        NestedActiveDirectoryGroupType=fake_group_type,
                    ),
                    "django_auth_ldap.backend": MagicMock(),
                },
            ):
                with self.assertRaises(ImproperlyConfigured) as ctx:
                    ldap_config.build_ldap_settings()
                self.assertIn("ldaps://", str(ctx.exception))

    def test_build_accepts_ldaps_and_loads_c2_map(self):
        from auth import ldap_config

        env = {
            "AUTH_LDAP_SERVER_URI": "ldaps://ad.bank.local:636",
            "AUTH_LDAP_BIND_DN": "CN=svc-sufler,OU=Service,DC=bank,DC=local",
            "AUTH_LDAP_BIND_PASSWORD": "vault-secret",
            "AUTH_LDAP_USER_SEARCH_BASE": "OU=Users,DC=bank,DC=local",
            "AUTH_LDAP_GROUP_SEARCH_BASE": "OU=Groups,DC=bank,DC=local",
            "AUTH_LDAP_ROLE_GROUP_MAP_JSON": "",
            "AUTH_LDAP_TLS_CACERTFILE": "/etc/ssl/certs/bank-ad-ca.pem",
        }
        fake_ldap = MagicMock()
        fake_ldap.SCOPE_SUBTREE = 2
        fake_ldap.OPT_REFERRALS = 0
        fake_ldap.OPT_X_TLS_REQUIRE_CERT = 1
        fake_ldap.OPT_X_TLS_DEMAND = 2
        fake_ldap.OPT_X_TLS_CACERTFILE = 3
        fake_ldap.OPT_X_TLS_NEWCTX = 4

        class _Search:
            def __init__(self, *args, **kwargs):
                self.args = args

        with patch.dict(os.environ, env, clear=False):
            with patch.dict(
                sys.modules,
                {
                    "ldap": fake_ldap,
                    "django_auth_ldap": MagicMock(),
                    "django_auth_ldap.config": MagicMock(
                        LDAPSearch=_Search,
                        NestedActiveDirectoryGroupType=MagicMock,
                    ),
                    "django_auth_ldap.backend": MagicMock(),
                },
            ):
                settings_dict = ldap_config.build_ldap_settings()

        self.assertEqual(
            settings_dict["AUTH_LDAP_SERVER_URI"],
            "ldaps://ad.bank.local:636",
        )
        self.assertEqual(len(settings_dict["AUTH_LDAP_ROLE_GROUP_MAP"]), 13)
        self.assertEqual(
            settings_dict["AUTH_LDAP_ROLE_GROUP_MAP"][
                "contact_center_telephony_operator"
            ],
            "BB_CC_Telephony_Operator",
        )
        self.assertEqual(settings_dict["AUTH_C2_GROUP_COUNT"], 13)


class AdGroupLoginTest(TestCase):
    """Simulate LDAPS-mirrored AD group membership → I.4 role + /api/auth/login."""

    def setUp(self):
        self.client = Client()
        self.user_model = get_user_model()

    def test_login_with_c2_ad_group_exposes_i4_role(self):
        user = self.user_model.objects.create_user(
            username="ad.operator",
            password="unused-local",
        )
        user.set_unusable_password()
        user.save()
        group, _ = Group.objects.get_or_create(
            name="BB_CC_Telephony_Operator",
        )
        user.groups.add(group)

        self.assertEqual(
            role_codes_for_user(user),
            {"contact_center_telephony_operator"},
        )

        def fake_authenticate(request, username=None, password=None, **kwargs):
            del request, kwargs
            if username == "ad.operator" and password == "ad-password":
                return user
            return None

        with patch(
            "auth.views.authenticate",
            side_effect=fake_authenticate,
        ):
            response = self.client.post(
                "/api/auth/login/",
                data=json.dumps(
                    {
                        "username": "ad.operator",
                        "password": "ad-password",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["username"], "ad.operator")
        self.assertEqual(
            payload["roles"],
            ["contact_center_telephony_operator"],
        )
        self.assertIn("sufler_telephony", payload["tabs"])

    def test_login_rejects_bad_credentials(self):
        with patch("auth.views.authenticate", return_value=None):
            response = self.client.post(
                "/api/auth/login/",
                data=json.dumps(
                    {"username": "nobody", "password": "nope"}
                ),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["ok"])


if __name__ == "__main__":
    unittest.main()

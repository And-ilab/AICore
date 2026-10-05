import os
import sys
import unittest
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.http import HttpResponse  # noqa: E402
from django.test import RequestFactory, override_settings  # noqa: E402

from auth.decorators import (  # noqa: E402
    admin_permission_required,
    api_permission_required,
    panel_tab_required,
)
from auth.middleware import RBACMiddleware  # noqa: E402
from auth.mock_ldap import (  # noqa: E402
    MockLDAPDirectory,
    MockLDAPRecord,
)
from auth.roles import (  # noqa: E402
    ALL_PERMISSIONS,
    PERM_CC_REPORTS,
    ROLE_DEFINITIONS,
    has_permission,
    permissions_for_user,
    role_codes_from_group_names,
    role_codes_for_user,
    tabs_for_user,
)
from auth.views import auth_context  # noqa: E402


class FakeGroups:
    def __init__(self, names):
        self.names = names

    def values_list(self, name, flat=False):
        if name != "name" or not flat:
            raise AssertionError("Unexpected group query")
        return self.names


class FakeUser:
    def __init__(
        self,
        groups=(),
        *,
        authenticated=True,
        superuser=False,
    ):
        self.is_authenticated = authenticated
        self.is_superuser = superuser
        self.groups = FakeGroups(groups)

    def get_username(self):
        return "test-user"


class RBACFoundationTest(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.roles_by_number = {
            role.number: role for role in ROLE_DEFINITIONS
        }

    def user_for_role(self, number):
        return FakeUser(
            (self.roles_by_number[number].mock_ad_group,)
        )

    def test_i4_maps_exactly_thirteen_contractual_roles(self):
        expected_names = (
            "Администратор ПО",
            "Администратор базы знаний LLM",
            "Администратор модуля Контакт-центра",
            "Оператор канала телефония Контакт-центра",
            "Оператор онлайн-чата Контакт-центра",
            "Внутренний пользователь Контакт-центра",
            "Аналитик Контакт-центра",
            "Администратор модуля ИИ-ассистент",
            "Пользователь ИИ-ассистента",
            "Аналитик ИИ-ассистента",
            "Администратор модуля распознавания документов",
            "Пользователь модуля распознавания документов",
            "Аналитик модуля распознавания документов",
        )

        self.assertEqual(len(ROLE_DEFINITIONS), 13)
        self.assertEqual(
            tuple(role.contractual_name for role in ROLE_DEFINITIONS),
            expected_names,
        )
        self.assertEqual(
            {role.number for role in ROLE_DEFINITIONS},
            set(range(1, 14)),
        )

    def test_each_i4_role_allows_own_scope_and_denies_other_scope(self):
        for role in ROLE_DEFINITIONS:
            with self.subTest(role=role.code):
                user = self.user_for_role(role.number)
                self.assertEqual(
                    role_codes_for_user(user),
                    {role.code},
                )
                permissions = permissions_for_user(user)
                for permission in role.permissions:
                    if permission != "*":
                        self.assertTrue(
                            has_permission(user, permission)
                        )
                if "*" in role.permissions:
                    self.assertEqual(
                        permissions - {"*"},
                        ALL_PERMISSIONS,
                    )
                else:
                    denied_candidates = ALL_PERMISSIONS - permissions
                    self.assertTrue(denied_candidates)
                    self.assertFalse(
                        has_permission(
                            user,
                            next(iter(denied_candidates)),
                        )
                    )
                self.assertEqual(
                    set(tabs_for_user(user)),
                    set(role.tabs),
                )

    def test_mock_ldap_authenticates_and_rejects_bad_password(self):
        record = MockLDAPRecord(
            username="operator",
            password="secret",
            first_name="Dev",
            last_name="Operator",
            email="operator@example.invalid",
            department="Contact center",
            groups=(self.roles_by_number[4].mock_ad_group,),
        )
        directory = MockLDAPDirectory((record,))

        self.assertEqual(
            directory.authenticate("OPERATOR", "secret"),
            record,
        )
        self.assertIsNone(
            directory.authenticate("operator", "wrong"),
        )
        self.assertIsNone(
            directory.authenticate("missing", "secret"),
        )

    @override_settings(
        AUTH_MOCK_LDAP_USERS_JSON="",
        AUTH_MOCK_LDAP_DEFAULT_PASSWORD="dev-test-password",
    )
    def test_default_mock_directory_has_one_user_per_i4_role(self):
        directory = MockLDAPDirectory.from_settings()

        for role in ROLE_DEFINITIONS:
            with self.subTest(role=role.code):
                record = directory.authenticate(
                    f"dev-role-{role.number:02d}",
                    "dev-test-password",
                )
                self.assertIsNotNone(record)
                self.assertEqual(record.groups, (role.mock_ad_group,))

    def test_real_ad_group_mapping_can_replace_mock_group_name(self):
        roles = role_codes_from_group_names(
            ("BANK_AI_ASSISTANT_USERS",),
            {
                "ai_assistant_user": "BANK_AI_ASSISTANT_USERS",
            },
        )

        self.assertEqual(roles, {"ai_assistant_user"})

    def test_api_permission_denies_operator_and_allows_analyst(self):
        @api_permission_required(PERM_CC_REPORTS)
        def report_api(request):
            return HttpResponse("ok")

        denied_request = self.factory.get("/api/reports/")
        denied_request.user = self.user_for_role(4)
        denied = report_api(denied_request)

        allowed_request = self.factory.get("/api/reports/")
        allowed_request.user = self.user_for_role(7)
        allowed = report_api(allowed_request)

        anonymous_request = self.factory.get("/api/reports/")
        anonymous_request.user = FakeUser(authenticated=False)
        anonymous = report_api(anonymous_request)

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(anonymous.status_code, 401)

    def test_admin_and_panel_tab_decorators(self):
        @admin_permission_required
        def admin_panel(request):
            return HttpResponse("admin")

        @panel_tab_required("assistant")
        def assistant_panel(request):
            return HttpResponse("assistant")

        admin_request = self.factory.get("/ai-hub/admin/")
        admin_request.user = self.user_for_role(1)
        operator_request = self.factory.get("/ai-hub/admin/")
        operator_request.user = self.user_for_role(4)

        self.assertEqual(admin_panel(admin_request).status_code, 200)
        self.assertEqual(admin_panel(operator_request).status_code, 403)
        self.assertEqual(assistant_panel(operator_request).status_code, 200)
        self.assertIn("assistant", tabs_for_user(operator_request.user))
        self.assertNotIn("settings", tabs_for_user(operator_request.user))

    @override_settings(
        RBAC_PATH_PERMISSIONS={
            "/api/admin/": "system.admin",
        }
    )
    def test_middleware_enforces_path_policy_and_attaches_context(self):
        middleware = RBACMiddleware(lambda request: HttpResponse("ok"))

        denied_request = self.factory.get("/api/admin/config/")
        denied_request.user = self.user_for_role(4)
        denied = middleware(denied_request)

        allowed_request = self.factory.get("/api/admin/config/")
        allowed_request.user = self.user_for_role(1)
        allowed = middleware(allowed_request)

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
        self.assertIn(
            "software_administrator",
            allowed_request.rbac_roles,
        )
        self.assertIn("settings", allowed_request.rbac_tabs)

    def test_auth_context_exposes_roles_for_launcher(self):
        request = self.factory.get("/api/auth/me/")
        request.user = self.user_for_role(4)

        response = auth_context(request)
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["username"], "test-user")
        self.assertEqual(
            payload["roles"],
            ["contact_center_telephony_operator"],
        )
        self.assertIn("assistant", payload["tabs"])

    def test_auth_context_is_empty_for_anonymous_user(self):
        request = self.factory.get("/api/auth/me/")
        request.user = FakeUser(authenticated=False)

        payload = json.loads(auth_context(request).content)

        self.assertFalse(payload["authenticated"])
        self.assertIsNone(payload["username"])
        self.assertEqual(payload["roles"], [])


if __name__ == "__main__":
    unittest.main()

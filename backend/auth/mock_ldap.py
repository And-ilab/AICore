"""Development-only LDAP-like directory and Django auth backend."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured
from django.utils.crypto import constant_time_compare

from auth.roles import ROLE_DEFINITIONS, role_codes_from_group_names


@dataclass(frozen=True)
class MockLDAPRecord:
    username: str
    password: str
    first_name: str
    last_name: str
    email: str
    department: str
    groups: tuple[str, ...]


def _default_records(password: str) -> tuple[MockLDAPRecord, ...]:
    return tuple(
        MockLDAPRecord(
            username=f"dev-role-{role.number:02d}",
            password=password,
            first_name="Dev",
            last_name=f"Role {role.number:02d}",
            email=f"dev-role-{role.number:02d}@example.invalid",
            department="Sufler development",
            groups=(role.mock_ad_group,),
        )
        for role in ROLE_DEFINITIONS
    )


def _record_from_mapping(
    username: str,
    payload: Mapping[str, Any],
) -> MockLDAPRecord:
    password = payload.get("password")
    groups = payload.get("groups")
    if not isinstance(password, str) or not password:
        raise ImproperlyConfigured(
            f"Mock LDAP user {username!r} requires password"
        )
    if (
        not isinstance(groups, list)
        or not groups
        or not all(isinstance(group, str) and group for group in groups)
    ):
        raise ImproperlyConfigured(
            f"Mock LDAP user {username!r} requires groups"
        )
    return MockLDAPRecord(
        username=username,
        password=password,
        first_name=str(payload.get("first_name", "")),
        last_name=str(payload.get("last_name", "")),
        email=str(payload.get("email", "")),
        department=str(payload.get("department", "")),
        groups=tuple(groups),
    )


class MockLDAPDirectory:
    """Small deterministic directory used instead of a network LDAP server."""

    def __init__(self, records: tuple[MockLDAPRecord, ...]) -> None:
        self._records = {
            record.username.casefold(): record for record in records
        }
        if len(self._records) != len(records):
            raise ImproperlyConfigured(
                "Mock LDAP usernames must be case-insensitively unique"
            )

    @classmethod
    def from_settings(cls) -> MockLDAPDirectory:
        configured = getattr(settings, "AUTH_MOCK_LDAP_USERS_JSON", "")
        if configured:
            try:
                payload = json.loads(configured)
            except json.JSONDecodeError as exc:
                raise ImproperlyConfigured(
                    "AUTH_MOCK_LDAP_USERS_JSON is invalid JSON"
                ) from exc
            if not isinstance(payload, Mapping) or not payload:
                raise ImproperlyConfigured(
                    "AUTH_MOCK_LDAP_USERS_JSON must be a non-empty object"
                )
            records = tuple(
                _record_from_mapping(str(username), user_payload)
                for username, user_payload in payload.items()
                if isinstance(user_payload, Mapping)
            )
            if len(records) != len(payload):
                raise ImproperlyConfigured(
                    "Every mock LDAP user must be an object"
                )
            return cls(records)
        password = getattr(
            settings,
            "AUTH_MOCK_LDAP_DEFAULT_PASSWORD",
            "dev-only-password",
        )
        return cls(_default_records(password))

    def authenticate(
        self,
        username: str,
        password: str,
    ) -> MockLDAPRecord | None:
        record = self._records.get(username.casefold())
        if record is None:
            return None
        if not constant_time_compare(record.password, password):
            return None
        return record


class MockLDAPBackend:
    """Provision Django users/groups from the development mock directory."""

    def authenticate(
        self,
        request: Any,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> Any:
        del request, kwargs
        if not (
            settings.DEBUG
            or getattr(
                settings,
                "AUTH_MOCK_LDAP_ALLOW_INSECURE",
                False,
            )
        ):
            return None
        if not username or password is None:
            return None
        record = MockLDAPDirectory.from_settings().authenticate(
            username,
            password,
        )
        if record is None:
            return None
        role_codes = role_codes_from_group_names(record.groups)
        if not role_codes:
            return None

        user_model = get_user_model()
        user, _ = user_model.objects.get_or_create(
            username=record.username,
        )
        user.first_name = record.first_name
        user.last_name = record.last_name
        user.email = record.email
        user.is_active = True
        user.is_staff = "software_administrator" in role_codes
        user.set_unusable_password()
        user.save()

        managed_prefix = "Sufler_Role_"
        managed_groups = list(
            user.groups.filter(name__startswith=managed_prefix)
        )
        if managed_groups:
            user.groups.remove(*managed_groups)
        for group_name in record.groups:
            group, _ = Group.objects.get_or_create(name=group_name)
            user.groups.add(group)
        user._sufler_rbac_roles = role_codes
        user.ldap_department = record.department
        return user

    def get_user(self, user_id: Any) -> Any:
        user_model = get_user_model()
        try:
            return user_model.objects.get(pk=user_id)
        except user_model.DoesNotExist:
            return None

"""Production LDAPS settings (I.10 / AUTH_BACKEND=ldaps).

Imported when ``AUTH_BACKEND`` / ``AUTH_MODE`` resolves to ``ldaps`` or ``ldap``.
Requires optional packages ``django-auth-ldap`` and ``python-ldap`` (see
``requirements-ldap.txt``). Windows local/dev keeps ``mock_ldap``.
"""

from __future__ import annotations

import json
import os
from typing import Any

from django.core.exceptions import ImproperlyConfigured

from auth.c2_groups import C2_ROLE_GROUP_MAP, c2_role_group_map
from auth.roles import ROLES_BY_CODE


def resolve_auth_backend(
    *,
    auth_backend: str | None = None,
    auth_mode: str | None = None,
    debug: bool = False,
) -> str:
    """Normalize AUTH_BACKEND / AUTH_MODE to mock_ldap | ldaps | model.

    ``AUTH_BACKEND`` wins when set. Aliases:
    - ldaps / ldap / prod → ldaps (real AD)
    - mock_ldap / mock → mock_ldap (P2-01, not for prod)
    - model → Django ModelBackend only
    """
    raw = (auth_backend or auth_mode or "").strip().lower()
    if not raw:
        return "mock_ldap" if debug else "model"
    if raw in {"ldaps", "ldap", "prod", "production", "ad"}:
        return "ldaps"
    if raw in {"mock_ldap", "mock", "dev"}:
        return "mock_ldap"
    if raw == "model":
        return "model"
    raise ImproperlyConfigured(
        "AUTH_BACKEND / AUTH_MODE must be one of: "
        "ldaps (ldap), mock_ldap (mock), model"
    )


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"{name} is required when AUTH_BACKEND=ldaps"
        )
    return value


def merge_c2_role_group_map(
    overrides: dict[str, Any] | None = None,
) -> dict[str, str]:
    """C2 defaults + JSON overrides; must cover all 13 I.4 roles."""
    merged = c2_role_group_map()
    for role_code, group_name in (overrides or {}).items():
        if role_code not in ROLES_BY_CODE:
            raise ImproperlyConfigured(
                f"AUTH_LDAP_ROLE_GROUP_MAP_JSON unknown role: {role_code!r}"
            )
        if not isinstance(group_name, str) or not group_name.strip():
            raise ImproperlyConfigured(
                f"AUTH_LDAP_ROLE_GROUP_MAP_JSON[{role_code!r}] "
                "must be a non-empty AD group name"
            )
        merged[role_code] = group_name.strip()
    missing = sorted(set(ROLES_BY_CODE) - set(merged))
    if missing:
        raise ImproperlyConfigured(
            "C2 AD map incomplete; missing roles: " + ", ".join(missing)
        )
    if len(merged) != 13:
        raise ImproperlyConfigured(
            "C2 AD map must contain exactly 13 role→group entries"
        )
    seen: dict[str, str] = {}
    for role_code, group_name in merged.items():
        key = group_name.casefold()
        if key in seen:
            raise ImproperlyConfigured(
                f"Duplicate AD group {group_name!r} for "
                f"{seen[key]!r} and {role_code!r}"
            )
        seen[key] = role_code
    return merged


def load_role_group_map_from_env() -> dict[str, str]:
    raw = os.getenv("AUTH_LDAP_ROLE_GROUP_MAP_JSON", "").strip()
    if not raw:
        return merge_c2_role_group_map()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(
            "AUTH_LDAP_ROLE_GROUP_MAP_JSON is invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise ImproperlyConfigured(
            "AUTH_LDAP_ROLE_GROUP_MAP_JSON must be an object"
        )
    return merge_c2_role_group_map(payload)


def build_ldap_settings() -> dict[str, Any]:
    try:
        import ldap
        from django_auth_ldap.config import (
            LDAPSearch,
            NestedActiveDirectoryGroupType,
        )
    except ImportError as exc:
        raise ImproperlyConfigured(
            "AUTH_BACKEND=ldaps requires django-auth-ldap and python-ldap "
            "(install backend/requirements-ldap.txt)"
        ) from exc

    server_uri = _required("AUTH_LDAP_SERVER_URI")
    if not server_uri.lower().startswith("ldaps://"):
        allow_plain = os.getenv(
            "AUTH_LDAP_ALLOW_INSECURE_URI",
            "false",
        ).lower() in {"1", "true", "yes"}
        if not allow_plain:
            raise ImproperlyConfigured(
                "AUTH_LDAP_SERVER_URI must use ldaps:// (I.10); "
                "set AUTH_LDAP_ALLOW_INSECURE_URI=true only for lab"
            )

    user_base = _required("AUTH_LDAP_USER_SEARCH_BASE")
    group_base = _required("AUTH_LDAP_GROUP_SEARCH_BASE")
    bind_dn = _required("AUTH_LDAP_BIND_DN")
    bind_password = _required("AUTH_LDAP_BIND_PASSWORD")
    user_filter = os.getenv(
        "AUTH_LDAP_USER_FILTER",
        "(sAMAccountName=%(user)s)",
    )
    role_group_map = load_role_group_map_from_env()

    connection_options: dict[Any, Any] = {
        ldap.OPT_REFERRALS: 0,
        ldap.OPT_X_TLS_REQUIRE_CERT: ldap.OPT_X_TLS_DEMAND,
    }
    ca_file = os.getenv("AUTH_LDAP_TLS_CACERTFILE", "").strip()
    if ca_file:
        connection_options[ldap.OPT_X_TLS_CACERTFILE] = ca_file
        connection_options[ldap.OPT_X_TLS_NEWCTX] = 0

    return {
        "AUTH_LDAP_SERVER_URI": server_uri,
        "AUTH_LDAP_BIND_DN": bind_dn,
        "AUTH_LDAP_BIND_PASSWORD": bind_password,
        "AUTH_LDAP_USER_SEARCH": LDAPSearch(
            user_base,
            ldap.SCOPE_SUBTREE,
            user_filter,
        ),
        "AUTH_LDAP_GROUP_SEARCH": LDAPSearch(
            group_base,
            ldap.SCOPE_SUBTREE,
            "(objectClass=group)",
        ),
        "AUTH_LDAP_GROUP_TYPE": NestedActiveDirectoryGroupType(),
        "AUTH_LDAP_USER_ATTR_MAP": {
            "first_name": "givenName",
            "last_name": "sn",
            "email": "mail",
        },
        "AUTH_LDAP_ALWAYS_UPDATE_USER": True,
        "AUTH_LDAP_MIRROR_GROUPS": True,
        "AUTH_LDAP_CACHE_TIMEOUT": int(
            os.getenv("AUTH_LDAP_CACHE_TIMEOUT", "300")
        ),
        "AUTH_LDAP_CONNECTION_OPTIONS": connection_options,
        "AUTH_LDAP_ROLE_GROUP_MAP": role_group_map,
        "AUTH_C2_GROUP_COUNT": len(role_group_map),
        "AUTH_C2_DEFAULT_GROUPS": dict(C2_ROLE_GROUP_MAP),
    }

"""Expose RBAC roles and visible Hub tabs to Django templates."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from auth.roles import (
    permissions_for_user,
    role_codes_for_user,
    tabs_for_user,
)


def rbac(request: HttpRequest) -> dict[str, Any]:
    roles = getattr(
        request,
        "rbac_roles",
        role_codes_for_user(request.user),
    )
    permissions = getattr(
        request,
        "rbac_permissions",
        permissions_for_user(request.user),
    )
    tabs = getattr(
        request,
        "rbac_tabs",
        tabs_for_user(request.user),
    )
    return {
        "rbac_roles": roles,
        "rbac_permissions": permissions,
        "rbac_tabs": tabs,
    }

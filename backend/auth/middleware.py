"""Attach I.4 RBAC context and enforce configured path/view policies."""

from __future__ import annotations

from typing import Any, Callable, Iterable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from auth.decorators import permission_denied_response
from auth.roles import (
    has_permission,
    permissions_for_user,
    role_codes_for_user,
    tabs_for_user,
)


class RBACMiddleware:
    """Resolve roles after Django AuthenticationMiddleware."""

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self._attach_context(request)
        required = self._path_permissions(request.path)
        if required and not all(
            has_permission(request.user, permission)
            for permission in required
        ):
            return permission_denied_response(
                request,
                required=required,
                force_json=request.path.startswith("/api/"),
            )
        return self.get_response(request)

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., Any],
        view_args: list[Any],
        view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        del view_args, view_kwargs
        permissions = getattr(
            view_func,
            "rbac_required_permissions",
            (),
        )
        require_all = getattr(view_func, "rbac_require_all", True)
        if permissions:
            checks = [
                has_permission(request.user, permission)
                for permission in permissions
            ]
            allowed = all(checks) if require_all else any(checks)
            if not allowed:
                return permission_denied_response(
                    request,
                    required=permissions,
                    force_json=getattr(
                        view_func,
                        "rbac_force_json",
                        False,
                    ),
                )
        roles = getattr(view_func, "rbac_required_roles", ())
        if roles and not request.rbac_roles.intersection(roles):
            return permission_denied_response(
                request,
                required=(f"role:{role}" for role in roles),
                force_json=getattr(
                    view_func,
                    "rbac_force_json",
                    False,
                ),
            )
        tab = getattr(view_func, "rbac_required_tab", None)
        if tab and tab not in request.rbac_tabs:
            return permission_denied_response(
                request,
                required=(f"tab:{tab}",),
            )
        return None

    @staticmethod
    def _attach_context(request: HttpRequest) -> None:
        request.rbac_roles = role_codes_for_user(request.user)
        request.rbac_permissions = permissions_for_user(request.user)
        request.rbac_tabs = tabs_for_user(request.user)

    @staticmethod
    def _path_permissions(path: str) -> tuple[str, ...]:
        public_prefixes = getattr(
            settings,
            "RBAC_PUBLIC_PATH_PREFIXES",
            (),
        )
        if any(path.startswith(prefix) for prefix in public_prefixes):
            return ()
        policies = getattr(settings, "RBAC_PATH_PERMISSIONS", {})
        matches = [
            (prefix, required)
            for prefix, required in policies.items()
            if path.startswith(prefix)
        ]
        if not matches:
            return ()
        _, required = max(matches, key=lambda item: len(item[0]))
        if isinstance(required, str):
            return (required,)
        if isinstance(required, Iterable):
            return tuple(
                permission
                for permission in required
                if isinstance(permission, str) and permission
            )
        return ()

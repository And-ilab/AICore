"""RBAC decorators for HTML panels and JSON API endpoints."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Iterable

from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseForbidden,
    JsonResponse,
)

from auth.roles import (
    PERM_SYSTEM_ADMIN,
    has_permission,
    role_codes_for_user,
    tabs_for_user,
)


View = Callable[..., HttpResponse]


def _is_api_request(request: HttpRequest, force_json: bool) -> bool:
    return (
        force_json
        or request.path.startswith("/api/")
        or "application/json" in request.headers.get("Accept", "")
    )


def permission_denied_response(
    request: HttpRequest,
    *,
    required: Iterable[str],
    force_json: bool = False,
) -> HttpResponse:
    authenticated = getattr(request.user, "is_authenticated", False)
    status = 403 if authenticated else 401
    code = "permission_denied" if authenticated else "authentication_required"
    if _is_api_request(request, force_json):
        return JsonResponse(
            {
                "error": code,
                "required_permissions": sorted(set(required)),
            },
            status=status,
        )
    if authenticated:
        return HttpResponseForbidden("Permission denied")
    return HttpResponse("Authentication required", status=401)


def _has_required_permissions(
    user: Any,
    permissions: tuple[str, ...],
    *,
    require_all: bool,
) -> bool:
    checks = [has_permission(user, permission) for permission in permissions]
    return all(checks) if require_all else any(checks)


def require_permissions(
    *permissions: str,
    require_all: bool = True,
    api: bool = False,
) -> Callable[[View], View]:
    if not permissions or not all(
        isinstance(permission, str) and permission
        for permission in permissions
    ):
        raise ValueError("At least one non-empty permission is required")

    def decorator(view: View) -> View:
        @wraps(view)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            if not _has_required_permissions(
                request.user,
                permissions,
                require_all=require_all,
            ):
                return permission_denied_response(
                    request,
                    required=permissions,
                    force_json=api,
                )
            return view(request, *args, **kwargs)

        wrapped.rbac_required_permissions = permissions
        wrapped.rbac_require_all = require_all
        wrapped.rbac_force_json = api
        return wrapped

    return decorator


def require_permission(permission: str) -> Callable[[View], View]:
    return require_permissions(permission)


def api_permission_required(permission: str) -> Callable[[View], View]:
    return require_permissions(permission, api=True)


def admin_permission_required(view: View) -> View:
    return require_permissions(PERM_SYSTEM_ADMIN)(view)


def roles_required(*role_codes: str, api: bool = False) -> Callable[[View], View]:
    if not role_codes:
        raise ValueError("At least one role code is required")

    def decorator(view: View) -> View:
        @wraps(view)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            user_roles = role_codes_for_user(request.user)
            if not user_roles.intersection(role_codes):
                return permission_denied_response(
                    request,
                    required=(f"role:{role}" for role in role_codes),
                    force_json=api,
                )
            return view(request, *args, **kwargs)

        wrapped.rbac_required_roles = role_codes
        wrapped.rbac_force_json = api
        return wrapped

    return decorator


def panel_tab_required(tab: str) -> Callable[[View], View]:
    if not isinstance(tab, str) or not tab:
        raise ValueError("tab must be a non-empty string")

    def decorator(view: View) -> View:
        @wraps(view)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            if tab not in tabs_for_user(request.user):
                return permission_denied_response(
                    request,
                    required=(f"tab:{tab}",),
                )
            return view(request, *args, **kwargs)

        wrapped.rbac_required_tab = tab
        return wrapped

    return decorator

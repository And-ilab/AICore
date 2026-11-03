from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from audit.events import (
    CATEGORY_AUTHENTICATION,
    LOGIN_FAILURE,
    LOGIN_SUCCESS,
    LOGOUT,
    RESULT_FAILURE,
    RESULT_SUCCESS,
)
from audit.schema import AuditSubject
from audit.service import emit, request_context, subject_from_request
from auth.roles import role_codes_for_user

logger = logging.getLogger(__name__)

_SECRET_ATTRIBUTES = frozenset(
    {"unicodepwd", "userpassword", "password", "pwdlastset"}
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _directory_body(user: Any) -> dict[str, Any]:
    groups: list[str] = []
    group_set = getattr(user, "groups", None)
    if group_set is not None:
        groups = sorted(group_set.values_list("name", flat=True))
    attributes = None
    ldap_user = getattr(user, "ldap_user", None)
    attrs = getattr(ldap_user, "attrs", None) if ldap_user is not None else None
    if isinstance(attrs, Mapping):
        attributes = {
            str(key): _jsonable(value)
            for key, value in attrs.items()
            if str(key).casefold() not in _SECRET_ATTRIBUTES
        }
    return {
        "username": user.get_username() if user is not None else None,
        "first_name": getattr(user, "first_name", ""),
        "last_name": getattr(user, "last_name", ""),
        "email": getattr(user, "email", ""),
        "department": getattr(user, "ldap_department", ""),
        "roles": sorted(role_codes_for_user(user)),
        "groups": groups,
        "attributes": attributes,
    }


def _subject(request: Any, user: Any = None) -> AuditSubject:
    if request is not None:
        return subject_from_request(request)
    username = user.get_username() if user is not None else "anonymous"
    return AuditSubject(
        user_login=username or "anonymous",
        roles=tuple(sorted(role_codes_for_user(user))),
    )


@receiver(user_logged_in, dispatch_uid="sufler.audit.login")
def audit_login(
    sender: Any,
    request: Any,
    user: Any,
    **kwargs: Any,
) -> None:
    del sender, kwargs
    emit(
        category=CATEGORY_AUTHENTICATION,
        event_type=LOGIN_SUCCESS,
        result=RESULT_SUCCESS,
        subject=_subject(request, user),
        module="auth",
        description="User authentication succeeded",
        request=request_context(request) if request is not None else None,
    )
    logger.info(
        "ad_response username=%s body=%s",
        user.get_username() if user is not None else "anonymous",
        json.dumps(_directory_body(user), ensure_ascii=False),
    )


@receiver(user_login_failed, dispatch_uid="sufler.audit.login_failed")
def audit_login_failed(
    sender: Any,
    credentials: dict[str, Any],
    request: Any = None,
    **kwargs: Any,
) -> None:
    del sender, kwargs
    attempted_username = str(
        credentials.get("username") or credentials.get("email") or "unknown"
    )
    logger.info("ad_response_failed username=%s", attempted_username)
    emit(
        category=CATEGORY_AUTHENTICATION,
        event_type=LOGIN_FAILURE,
        result=RESULT_FAILURE,
        subject=AuditSubject(user_login=attempted_username),
        module="auth",
        description="User authentication failed",
        severity="medium",
        request=request_context(request) if request is not None else None,
    )


@receiver(user_logged_out, dispatch_uid="sufler.audit.logout")
def audit_logout(
    sender: Any,
    request: Any,
    user: Any,
    **kwargs: Any,
) -> None:
    del sender, kwargs
    emit(
        category=CATEGORY_AUTHENTICATION,
        event_type=LOGOUT,
        result=RESULT_SUCCESS,
        subject=_subject(request, user),
        module="auth",
        description="User session ended",
        request=request_context(request) if request is not None else None,
    )

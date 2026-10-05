from __future__ import annotations

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

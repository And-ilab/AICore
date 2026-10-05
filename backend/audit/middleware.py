from __future__ import annotations

import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from audit.events import (
    ACCESS_DENIED,
    CATEGORY_AUTHORIZATION,
    RESULT_FAILURE,
)
from audit.service import emit, request_context, subject_from_request


class AuditMiddleware:
    """Attach correlation IDs and emit authorization failures."""

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.audit_request_id = (
            request.headers.get("X-Request-ID") or str(uuid.uuid4())
        )
        response = self.get_response(request)
        response["X-Request-ID"] = request.audit_request_id
        if response.status_code in {401, 403}:
            emit(
                category=CATEGORY_AUTHORIZATION,
                event_type=ACCESS_DENIED,
                result=RESULT_FAILURE,
                subject=subject_from_request(request),
                module="auth",
                description="Request authorization denied",
                severity="medium",
                request=request_context(request),
                outcome={"http_status": response.status_code},
            )
        return response

"""Monitoring failures and the single place that turns them into HTTP."""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest, JsonResponse


logger = logging.getLogger("assistant.monitoring")


class MonitoringError(Exception):
    """Base monitoring failure. The message is safe to show to the analyst."""

    status_code = 500
    code = "monitoring_error"
    default_message = "Не удалось построить отчёт."

    def __init__(
        self,
        message: str | None = None,
        fields: dict[str, list[str]] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.fields = fields or {}
        super().__init__(self.message)


class InvalidQueryError(MonitoringError):
    status_code = 400
    code = "invalid_query"
    default_message = "Некорректные параметры запроса."


class InvalidPeriodError(MonitoringError):
    status_code = 400
    code = "invalid_period"
    default_message = "Некорректный период."


class PeriodTooLargeError(MonitoringError):
    status_code = 422
    code = "period_too_large"
    default_message = "Период слишком большой. Укажите не больше 366 дней."


class EventNotFoundError(MonitoringError):
    status_code = 404
    code = "not_found"
    default_message = "Запись не найдена."


class AuthenticationRequiredError(MonitoringError):
    status_code = 401
    code = "authentication_required"
    default_message = "Нужно войти в систему."


class MonitoringPermissionError(MonitoringError):
    status_code = 403
    code = "permission_denied"
    default_message = "Недостаточно прав для просмотра мониторинга."


class AggregationError(MonitoringError):
    status_code = 500
    code = "aggregation_error"
    default_message = "Не удалось посчитать показатель."


class ExportError(MonitoringError):
    status_code = 500
    code = "export_error"
    default_message = "Не удалось сформировать файл."


class ExportTooLargeError(MonitoringError):
    status_code = 422
    code = "export_too_large"
    default_message = (
        "Слишком много строк для этого формата. "
        "Сузьте период или выгрузите CSV."
    )


class MetricsStoreUnavailable(MonitoringError):
    status_code = 503
    code = "store_unavailable"
    default_message = "Хранилище метрик временно недоступно."


class QueryTimeoutError(MonitoringError):
    status_code = 504
    code = "query_timeout"
    default_message = "Запрос к отчёту выполнялся слишком долго."


class MetricWriteError(MonitoringError):
    status_code = 500
    code = "metric_write_error"
    default_message = "Не удалось записать событие мониторинга."


class ScheduleUnavailableError(MonitoringError):
    status_code = 503
    code = "schedule_unavailable"
    default_message = (
        "Регулярный отчёт сейчас не запущен: очередь задач недоступна. "
        "Отчёт по запросу по-прежнему можно открыть."
    )


def request_id_of(request: HttpRequest) -> str:
    request_id = getattr(request, "audit_request_id", None)
    if isinstance(request_id, str) and request_id.strip():
        return request_id.strip()[:64]
    return "-"


def user_id_of(request: HttpRequest) -> str:
    user = getattr(request, "user", None)
    pk = getattr(user, "pk", None)
    if pk is None:
        return "-"
    return str(pk)


def monitoring_error_response(
    exc: MonitoringError,
    request: HttpRequest,
) -> JsonResponse:
    """Map a monitoring exception to JSON. Library text stays in the log."""
    request_id = request_id_of(request)
    user_id = user_id_of(request)
    if exc.status_code >= 500:
        logger.error(
            "monitoring_error code=%s status=%s request_id=%s user_id=%s",
            exc.code,
            exc.status_code,
            request_id,
            user_id,
        )
    else:
        logger.warning(
            "monitoring_rejected code=%s status=%s request_id=%s user_id=%s",
            exc.code,
            exc.status_code,
            request_id,
            user_id,
        )
    payload: dict[str, Any] = {
        "error": exc.code,
        "message": exc.message,
        "request_id": request_id,
    }
    if exc.fields:
        payload["fields"] = exc.fields
    return JsonResponse(payload, status=exc.status_code)

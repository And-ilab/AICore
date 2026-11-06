"""HTTP endpoints for the assistant monitoring tab and FR-RPT-ASS reports."""

from __future__ import annotations

import json
import logging
from functools import wraps
from typing import Any, Callable

from django.db.utils import OperationalError
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods

from assistant.ass_reports import (
    build_xlsx_export,
    catalog,
    export_filename,
    iter_csv_chunks,
)
from assistant.models import (
    AssistantReportSchedule,
    AssistantReportTemplate,
    AssistantRequestEvent,
)
from assistant.monitoring_errors import (
    AuthenticationRequiredError,
    EventNotFoundError,
    ExportTooLargeError,
    InvalidQueryError,
    MonitoringError,
    MonitoringPermissionError,
    ScheduleUnavailableError,
    monitoring_error_response,
    request_id_of,
    user_id_of,
)
from assistant.monitoring_query import (
    LIST_KEYS,
    PERIOD_KEYS,
    SERIES_KEYS,
    XLSX_MAX_ROWS,
    build_analytics_payload,
    build_series,
    build_summary,
    event_detail,
    list_events,
    parse_page,
    parse_period,
    parse_report_filters,
    run_read,
    schedule_public,
    template_public,
    validate_schedule_payload,
    validate_template_payload,
)
from assistant.monitoring_record import mark_hallucination
from assistant.tasks import run_due_report_schedules
from auth.roles import PERM_ASSISTANT_REPORTS, has_permission


logger = logging.getLogger("assistant.monitoring")

View = Callable[..., HttpResponse]


def monitoring_endpoint(view: View) -> View:
    """Auth via the shared permission check, then one error-to-HTTP mapping."""

    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not getattr(request.user, "is_authenticated", False):
            return monitoring_error_response(AuthenticationRequiredError(), request)
        if not has_permission(request.user, PERM_ASSISTANT_REPORTS):
            return monitoring_error_response(MonitoringPermissionError(), request)
        try:
            return view(request, *args, **kwargs)
        except MonitoringError as exc:
            return monitoring_error_response(exc, request)
        except OperationalError as exc:
            logger.error(
                "monitoring_store_failure request_id=%s user_id=%s error_type=%s",
                request_id_of(request),
                user_id_of(request),
                type(exc).__name__,
            )
            from assistant.monitoring_query import _guard_store

            return monitoring_error_response(_guard_store(exc), request)
        except Exception:
            logger.exception(
                "monitoring_unhandled request_id=%s user_id=%s",
                request_id_of(request),
                user_id_of(request),
            )
            return monitoring_error_response(MonitoringError(), request)

    return wrapped


def _json_object(request: HttpRequest) -> dict[str, Any]:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise InvalidQueryError(
            "Тело запроса должно быть JSON.",
            fields={"body": ["Ожидается объект JSON."]},
        ) from exc
    if not isinstance(body, dict):
        raise InvalidQueryError(
            "Тело запроса должно быть объектом JSON.",
            fields={"body": ["Ожидается объект JSON."]},
        )
    return body


def _log_access(request: HttpRequest, action: str, target: str) -> None:
    logger.info(
        "monitoring_access action=%s request_id=%s user_id=%s target=%s",
        action,
        request_id_of(request),
        user_id_of(request),
        target,
    )


def _event_or_404(event_id: int) -> AssistantRequestEvent:
    try:
        return AssistantRequestEvent.objects.get(pk=event_id)
    except AssistantRequestEvent.DoesNotExist as exc:
        raise EventNotFoundError() from exc


def _user_pk(request: HttpRequest) -> int | None:
    pk = getattr(request.user, "pk", None)
    return int(pk) if isinstance(pk, int) else None


@require_http_methods(["GET"])
@monitoring_endpoint
def monitoring_summary(request: HttpRequest) -> JsonResponse:
    filters = parse_period(request.GET, allowed=PERIOD_KEYS)
    _log_access(request, "summary", "summary")
    return JsonResponse(build_summary(filters))


@require_http_methods(["GET"])
@monitoring_endpoint
def monitoring_events(request: HttpRequest) -> JsonResponse:
    filters = parse_period(request.GET, allowed=LIST_KEYS)
    page, page_size, order = parse_page(request.GET)
    kind = request.GET.get("kind") or "all"
    if kind not in {"all", "errors", "hallucinations"}:
        raise InvalidQueryError(
            "Некорректный вид списка.",
            fields={"kind": ["Допустимо all, errors или hallucinations."]},
        )
    feedback = request.GET.get("feedback") or ""
    if feedback and feedback not in {"useful", "incomplete", "incorrect", "unrated"}:
        raise InvalidQueryError(
            "Некорректная оценка.",
            fields={"feedback": ["Допустимо useful, incomplete, incorrect или unrated."]},
        )
    if kind in {"errors", "hallucinations"}:
        _log_access(request, "sensitive_list", kind)
    payload = run_read(
        lambda: list_events(
            filters,
            page=page,
            page_size=page_size,
            order=order,
            kind=kind,
            feedback=feedback,
        )
    )
    return JsonResponse(payload)


@require_http_methods(["GET"])
@monitoring_endpoint
def monitoring_event_detail(request: HttpRequest, event_id: int) -> JsonResponse:
    event = _event_or_404(event_id)
    _log_access(request, "event_detail", str(event_id))
    return JsonResponse(run_read(lambda: event_detail(event)))


@require_http_methods(["POST"])
@monitoring_endpoint
def monitoring_event_hallucination(
    request: HttpRequest,
    event_id: int,
) -> JsonResponse:
    event = _event_or_404(event_id)
    body = _json_object(request)
    marked = body.get("marked")
    if not isinstance(marked, bool):
        raise InvalidQueryError(
            "Укажите отметку галлюцинации.",
            fields={"marked": ["Ожидается true или false."]},
        )
    mark_hallucination(event, marked=marked, user_id=_user_pk(request))
    _log_access(request, "hallucination_mark", str(event_id))
    return JsonResponse(event_detail(event))


@require_http_methods(["GET"])
@monitoring_endpoint
def monitoring_series(request: HttpRequest) -> JsonResponse:
    filters = parse_period(request.GET, allowed=SERIES_KEYS)
    grain = request.GET.get("grain") or "day"
    metric = request.GET.get("metric") or "usefulness"
    _log_access(request, "series", metric)
    return JsonResponse(run_read(lambda: build_series(filters, grain=grain, metric=metric)))


@require_http_methods(["GET"])
@monitoring_endpoint
def monitoring_reports_catalog(request: HttpRequest) -> JsonResponse:
    return JsonResponse(catalog())


@require_http_methods(["GET"])
@monitoring_endpoint
def monitoring_reports_analytics(request: HttpRequest) -> JsonResponse:
    filters = parse_report_filters(request.GET)
    _log_access(request, "analytics", filters.get("report_id") or "all")
    return JsonResponse(run_read(lambda: build_analytics_payload(filters)))


@require_http_methods(["GET"])
@monitoring_endpoint
def monitoring_report_detail(request: HttpRequest, report_id: str) -> JsonResponse:
    filters = parse_report_filters(request.GET)
    filters["report_id"] = report_id
    from assistant.ass_reports import FR_IDS

    if report_id not in FR_IDS:
        raise InvalidQueryError(
            "Неизвестный отчёт.",
            fields={"report_id": ["Укажите идентификатор FR-RPT-ASS."]},
        )
    payload = run_read(lambda: build_analytics_payload(filters))
    payload["report_id"] = report_id
    return JsonResponse(payload)


@require_http_methods(["GET"])
@monitoring_endpoint
def monitoring_reports_export(request: HttpRequest) -> HttpResponse:
    filters = parse_report_filters(request.GET)
    _log_access(request, "export", filters.get("format") or "csv")
    analytics = run_read(lambda: build_analytics_payload(filters))
    export_format = filters["format"]
    filename = export_filename(filters, export_format)
    if export_format == "xlsx":
        if len(analytics["rows"]) > XLSX_MAX_ROWS:
            raise ExportTooLargeError()
        payload = build_xlsx_export(analytics)
        response = HttpResponse(
            payload,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
    else:
        response = StreamingHttpResponse(
            iter_csv_chunks(analytics),
            content_type="text/csv; charset=utf-8",
        )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-FR-Catalog"] = "FR-RPT-ASS"
    return response


@require_http_methods(["GET", "POST"])
@monitoring_endpoint
def monitoring_templates(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        items = [template_public(item) for item in AssistantReportTemplate.objects.all()]
        return JsonResponse({"items": items})
    payload = validate_template_payload(_json_object(request))
    item = AssistantReportTemplate.objects.create(
        created_by_id=_user_pk(request),
        **payload,
    )
    return JsonResponse(template_public(item), status=201)


@require_http_methods(["GET", "PUT", "DELETE"])
@monitoring_endpoint
def monitoring_template_detail(
    request: HttpRequest,
    template_id: int,
) -> HttpResponse:
    try:
        item = AssistantReportTemplate.objects.get(pk=template_id)
    except AssistantReportTemplate.DoesNotExist as exc:
        raise EventNotFoundError("Шаблон не найден.") from exc
    if request.method == "DELETE":
        item.delete()
        return HttpResponse(status=204)
    if request.method == "PUT":
        payload = validate_template_payload(_json_object(request))
        for field, value in payload.items():
            setattr(item, field, value)
        item.save(update_fields=[*payload.keys(), "updated_at"])
    return JsonResponse(template_public(item))


@require_http_methods(["GET", "POST"])
@monitoring_endpoint
def monitoring_schedules(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        items = [
            schedule_public(item)
            for item in AssistantReportSchedule.objects.select_related("template")
        ]
        return JsonResponse({"items": items})
    payload = validate_schedule_payload(_json_object(request))
    template = _template_or_404(payload.pop("template_id"))
    item = AssistantReportSchedule.objects.create(
        template=template,
        created_by_id=_user_pk(request),
        **payload,
    )
    return JsonResponse(schedule_public(item), status=201)


@require_http_methods(["GET", "PUT", "DELETE"])
@monitoring_endpoint
def monitoring_schedule_detail(
    request: HttpRequest,
    schedule_id: int,
) -> HttpResponse:
    item = _schedule_or_404(schedule_id)
    if request.method == "DELETE":
        item.delete()
        return HttpResponse(status=204)
    if request.method == "PUT":
        payload = validate_schedule_payload(_json_object(request))
        template = _template_or_404(payload.pop("template_id"))
        item.template = template
        for field, value in payload.items():
            setattr(item, field, value)
        item.save(update_fields=[*payload.keys(), "template", "updated_at"])
    return JsonResponse(schedule_public(item))


@require_http_methods(["POST"])
@monitoring_endpoint
def monitoring_schedule_run(request: HttpRequest, schedule_id: int) -> JsonResponse:
    item = _schedule_or_404(schedule_id)
    _log_access(request, "schedule_run", str(schedule_id))
    try:
        async_result = run_due_report_schedules.delay(item.pk)
    except Exception:
        logger.warning(
            "schedule_broker_unavailable request_id=%s user_id=%s schedule_id=%s",
            request_id_of(request),
            user_id_of(request),
            item.pk,
        )
        item.last_status = AssistantReportSchedule.STATUS_ERROR
        item.last_error = "broker_unavailable"
        item.save(update_fields=["last_status", "last_error", "updated_at"])
        raise ScheduleUnavailableError()
    return JsonResponse(
        {
            "id": item.pk,
            "queued": True,
            "task_id": getattr(async_result, "id", ""),
            "last_status": item.last_status,
        }
    )


def _template_or_404(template_id: int | None) -> AssistantReportTemplate | None:
    if template_id is None:
        return None
    try:
        return AssistantReportTemplate.objects.get(pk=template_id)
    except AssistantReportTemplate.DoesNotExist as exc:
        raise EventNotFoundError("Шаблон не найден.") from exc


def _schedule_or_404(schedule_id: int) -> AssistantReportSchedule:
    try:
        return AssistantReportSchedule.objects.select_related("template").get(pk=schedule_id)
    except AssistantReportSchedule.DoesNotExist as exc:
        raise EventNotFoundError("Расписание не найдено.") from exc

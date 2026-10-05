"""HTTP API for ASR QA catalogue (FR-ASR-10) and CC reports (FR-RPT-CC / II.6)."""

from __future__ import annotations

import json
from functools import wraps
from typing import Any, Callable, Mapping

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from auth.decorators import permission_denied_response
from auth.roles import PERM_CC_REPORTS, has_permission
from reports.asr_qa import (
    AsrQaError,
    build_silence_wav,
    catalogue_stats,
    get_session,
    list_sessions,
    parse_filters,
    seed_demo_sessions,
    set_training_candidate,
)
from reports.cc_analytics import (
    CcAnalyticsError,
    build_analytics,
    parse_analytics_filters,
)
from reports.cc_report_export import (
    export_report_csv,
    export_report_pdf,
    export_report_xlsx,
    report_export_filename,
)
from reports.cc_catalog import (
    build_report_payload,
    list_builder_templates,
    preview_builder,
)
from reports.cc_live import build_live_dashboard
from reports.models import AsrDialogueSession, CcReportTemplate

View = Callable[..., HttpResponse]


def require_cc_reports(view: View) -> View:
    """PERM_CC_REPORTS; in DEBUG open the module for local SPA without RBAC friction."""

    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        if has_permission(request.user, PERM_CC_REPORTS):
            return view(request, *args, **kwargs)
        if settings.DEBUG:
            return view(request, *args, **kwargs)
        return permission_denied_response(
            request,
            required=(PERM_CC_REPORTS,),
            force_json=True,
        )

    return wrapped


def _cc_validation_error(exc: CcAnalyticsError) -> JsonResponse:
    return JsonResponse(
        {
            "error": "validation_error",
            "details": {"request": [str(exc)]},
        },
        status=400,
    )


def _validation_error(exc: AsrQaError) -> JsonResponse:
    return JsonResponse(
        {
            "error": "validation_error",
            "details": {"request": [str(exc)]},
        },
        status=400,
    )


@require_http_methods(["GET"])
@require_cc_reports
def asr_sessions(request: HttpRequest) -> JsonResponse:
    try:
        filters = parse_filters(request.GET)
        items = list_sessions(**filters)
    except AsrQaError as exc:
        return _validation_error(exc)
    return JsonResponse(
        {
            "items": items,
            "stats": catalogue_stats(),
            "filters": filters,
        }
    )


@require_http_methods(["GET"])
@require_cc_reports
def asr_session_detail(request: HttpRequest, session_id: int) -> JsonResponse:
    try:
        return JsonResponse(get_session(session_id))
    except AsrDialogueSession.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)


@require_http_methods(["GET"])
@require_cc_reports
def asr_session_audio(request: HttpRequest, session_id: int) -> HttpResponse:
    try:
        session = AsrDialogueSession.objects.get(pk=session_id)
    except AsrDialogueSession.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)
    if session.channel != AsrDialogueSession.CHANNEL_TELEPHONY:
        return JsonResponse(
            {
                "error": "audio_unavailable",
                "detail": "chat sessions have no audio",
            },
            status=404,
        )
    payload = build_silence_wav(
        duration_sec=max(1.0, float(session.duration_sec or 1))
    )
    response = HttpResponse(payload, content_type="audio/wav")
    response["Content-Disposition"] = (
        f'inline; filename="{session.session_id}.wav"'
    )
    return response


@require_http_methods(["POST"])
@require_cc_reports
def asr_utterance_annotation(
    request: HttpRequest,
    session_id: int,
    utterance_id: int,
) -> JsonResponse:
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, Mapping):
            raise AsrQaError("Request body must be a JSON object")
        if "training_candidate" not in body:
            raise AsrQaError("training_candidate is required")
        result = set_training_candidate(
            session_id,
            utterance_id,
            training_candidate=bool(body.get("training_candidate")),
            username=request.user.get_username()
            if getattr(request.user, "is_authenticated", False)
            else "demo",
        )
    except json.JSONDecodeError:
        return _validation_error(AsrQaError("Request body must be valid JSON"))
    except AsrQaError as exc:
        return _validation_error(exc)
    except AsrDialogueSession.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)
    return JsonResponse(result)


@require_http_methods(["POST"])
@require_cc_reports
def asr_seed_demo(request: HttpRequest) -> JsonResponse:
    """Seed deterministic demo catalogue (local/acceptance)."""
    force = False
    try:
        body = json.loads(request.body or b"{}")
        if isinstance(body, Mapping):
            force = bool(body.get("force"))
    except json.JSONDecodeError:
        pass
    items = seed_demo_sessions(force=force)
    return JsonResponse({"items": items, "stats": catalogue_stats()})


@require_http_methods(["GET"])
@require_cc_reports
def cc_analytics(request: HttpRequest) -> JsonResponse:
    """FR-RPT-CC dashboard: tables + ASR quality series."""
    try:
        filters = parse_analytics_filters(request.GET)
        payload = build_analytics(filters)
    except CcAnalyticsError as exc:
        return _cc_validation_error(exc)
    return JsonResponse(payload)


@require_http_methods(["GET"])
@require_cc_reports
def cc_export(request: HttpRequest) -> HttpResponse:
    """CSV / XLSX / PDF export for the selected online-chat report template."""
    try:
        report_payload = build_report_payload(request.GET)
        export_format = (request.GET.get("format") or "csv").strip().lower()
        if export_format == "xlsx":
            payload = export_report_xlsx(report_payload)
            content_type = (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        elif export_format == "pdf":
            from reports.cc_pdf_categories import resolve_author_name

            report_payload["generated_at"] = timezone.now()
            report_payload["generated_by"] = resolve_author_name(request.user)
            payload = export_report_pdf(report_payload)
            content_type = "application/pdf"
        else:
            payload = export_report_csv(report_payload)
            content_type = "text/csv; charset=utf-8"
        filename = report_export_filename(report_payload, export_format)
    except CcAnalyticsError as exc:
        return _cc_validation_error(exc)

    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_http_methods(["GET"])
@require_cc_reports
def cc_live(request: HttpRequest) -> JsonResponse:
    return JsonResponse(build_live_dashboard())


@require_http_methods(["GET"])
@require_cc_reports
def cc_report_catalog(request: HttpRequest) -> JsonResponse:
    try:
        return JsonResponse(build_report_payload(request.GET))
    except CcAnalyticsError as exc:
        return _cc_validation_error(exc)
    except Exception as exc:  # noqa: BLE001 — surface readable Russian error to UI
        report = (request.GET.get("report") or "").strip()
        label = report
        for item in (
            {"id": "chat-period", "label": "Обращения за период"},
            {"id": "chat-sla", "label": "SLA и время ожидания"},
            {"id": "chat-operators", "label": "Нагрузка и эффективность операторов"},
            {"id": "usefulness", "label": "Полезность подсказок суфлёра"},
            {"id": "relevance", "label": "Релевантность ответов"},
            {"id": "chat_history", "label": "Диалоги онлайн-чата (реестр)"},
            {"id": "chat-offline", "label": "Необработанные и отказные обращения"},
            {"id": "performance", "label": "Производительность (время ответа, AHT)"},
        ):
            if item["id"] == report:
                label = item["label"]
                break
        return JsonResponse(
            {
                "error": f"Не удалось сформировать отчёт «{label or 'выбранный'}». Попробуйте другой период или тип отчёта.",
                "details": {"reason": str(exc), "report": report},
            },
            status=500,
        )


@require_http_methods(["GET", "POST"])
@require_cc_reports
def cc_builder_templates(request: HttpRequest) -> JsonResponse:
    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
            if not isinstance(body, Mapping):
                raise CcAnalyticsError("Request body must be a JSON object")
            name = str(body.get("name") or "").strip()
            if not name:
                raise CcAnalyticsError("name is required")
            metrics = body.get("metrics") or []
            if not isinstance(metrics, list):
                raise CcAnalyticsError("metrics must be a list")
            view_mode = str(body.get("view_mode") or "table").strip()
            filters = body.get("filters") or {}
            if not isinstance(filters, dict):
                raise CcAnalyticsError("filters must be an object")
            date_from = body.get("date_from")
            date_to = body.get("date_to")
            owner = (
                request.user.get_username()
                if getattr(request.user, "is_authenticated", False)
                else str(body.get("owner_username") or "")
            )
            template = CcReportTemplate.objects.create(
                name=name,
                metrics=metrics,
                view_mode=view_mode,
                filters=filters,
                owner_username=owner,
                date_from=_parse_template_date(date_from),
                date_to=_parse_template_date(date_to),
            )
            return JsonResponse({"saved": template.to_dict()}, status=201)
        except json.JSONDecodeError:
            return JsonResponse(
                {"error": "validation_error", "details": {"request": ["Invalid JSON"]}},
                status=400,
            )
        except CcAnalyticsError as exc:
            return _cc_validation_error(exc)

    saved = [item.to_dict() for item in CcReportTemplate.objects.all()[:50]]
    payload = list_builder_templates(saved=saved)
    return JsonResponse(payload)


def _parse_template_date(value: Any) -> Any:
    if value in (None, ""):
        return None
    from datetime import date as date_cls

    try:
        return date_cls.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise CcAnalyticsError("date_from/date_to must be YYYY-MM-DD") from exc


@require_http_methods(["POST"])
@require_cc_reports
def cc_builder_preview(request: HttpRequest) -> JsonResponse:
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, Mapping):
            raise CcAnalyticsError("Request body must be a JSON object")
    except (json.JSONDecodeError, CcAnalyticsError) as exc:
        return JsonResponse(
            {"error": "validation_error", "details": {"request": [str(exc)]}},
            status=400,
        )
    return JsonResponse(preview_builder(dict(body)))



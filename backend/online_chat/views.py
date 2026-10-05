from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import uuid
from collections.abc import Mapping
from datetime import timedelta
from functools import wraps
from io import BytesIO
from typing import Any
from urllib.parse import quote, urlparse

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db.models import Avg, Count, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from auth.roles import (
    PERM_CC_ADMIN,
    PERM_CC_REPORTS,
    PERM_SUFLER_CHAT,
    has_permission,
)
from online_chat.models import (
    AssignmentSettings,
    BaseMessage,
    BotConfiguration,
    ChannelConnection,
    ClientBlock,
    Department,
    DialogCloseTopicNode,
    Dialog,
    DialogFeedback,
    DialogMessage,
    InternalMessage,
    OperatorProfile,
    RoutingRule,
    ServiceLevelSettings,
    SuflerHintFeedback,
    WidgetPlacement,
    WorkScheduleSettings,
    normalize_form_fields,
)
from online_chat.storage import get_chat_object_store
from online_chat.routing_services import (
    accept_waiting_dialog,
    close_working_day,
    line_is_open,
    open_working_day,
    record_event,
    run_assignments,
    sync_schedule_state,
    transfer_to_operator,
    update_operator_presence,
)
from online_chat.services import (
    ARM_GROUP,
    accept_dialog,
    append_message,
    block_dialog,
    broadcast,
    close_dialog,
    create_dialog_with_message,
    delete_message,
    edit_message,
    mark_dialog_messages_read,
    request_transcript_email,
    save_feedback,
    serialize_client_block,
    serialize_dialog,
    serialize_feedback,
    serialize_message,
    history_identity_query,
    channel_label,
    serialize_transcript_email,
    set_client_presence,
    transfer_dialog,
    unblock_client,
)
from online_chat.dialog_topics_service import (
    classify_by_titles,
    rebuild_full_paths,
    topic_tree,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


class OnlineChatApiError(ValueError):
    """Invalid online-chat API payload."""


def _request_client_ip(request: HttpRequest) -> str:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return str(request.META.get("REMOTE_ADDR") or "").strip()[:64]


def _chat_permissions(*permissions: str):
    """Require one permission in non-DEBUG environments."""

    def decorator(view):
        @wraps(view)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any):
            if settings.DEBUG or any(
                has_permission(request.user, permission)
                for permission in permissions
            ):
                return view(request, *args, **kwargs)
            return JsonResponse(
                {
                    "ok": False,
                    "error": "forbidden",
                    "required_permissions": list(permissions),
                },
                status=403,
            )

        return wrapped

    return decorator


def _operator_write_denied(
    request: HttpRequest,
    dialog: Dialog,
    *,
    claimed_name: str = "",
) -> JsonResponse | None:
    is_admin = has_permission(request.user, PERM_CC_ADMIN)
    can_chat = has_permission(request.user, PERM_SUFLER_CHAT)
    if not settings.DEBUG and not (is_admin or can_chat):
        return JsonResponse(
            {"ok": False, "error": "forbidden"},
            status=403,
        )
    profile = None
    if getattr(request.user, "is_authenticated", False):
        profile = OperatorProfile.objects.filter(
            external_id=request.user.get_username(),
            is_active=True,
        ).first()
    actor_name = profile.display_name if profile else claimed_name.strip()
    # Never write to another operator's dialog (including module admin / spoofed name).
    if (
        dialog.operator_name
        and actor_name
        and actor_name != dialog.operator_name
    ):
        return JsonResponse(
            {
                "ok": False,
                "error": "colleague_dialog_read_only",
                "detail": "Диалог коллеги доступен только для чтения",
            },
            status=403,
        )
    return None


def _strip_suz_links(text: str) -> str:
    without_markdown_urls = re.sub(
        r"\[([^\]]+)\]\(https?://[^)\s]+\)",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    without_urls = re.sub(
        r"(?:https?://|www\.)\S+",
        "",
        without_markdown_urls,
        flags=re.IGNORECASE,
    )
    return re.sub(r"[ \t]{2,}", " ", without_urls).strip()


def _json_body(request: HttpRequest) -> Mapping[str, Any]:
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise OnlineChatApiError("Request body must be valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise OnlineChatApiError("Request body must be a JSON object")
    return payload


def _error(exc: OnlineChatApiError, status: int = 400) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "error": "validation_error", "detail": str(exc)},
        status=status,
    )


def _str_field(payload: Mapping[str, Any], key: str, default: str = "") -> str:
    value = payload.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise OnlineChatApiError(f"{key} must be a string")
    return value.strip()


def _int_field(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise OnlineChatApiError(f"{key} must be an integer")
    return value


def _dialog_topic_dict(item: DialogCloseTopicNode) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "parent_id": str(item.parent_id) if item.parent_id else None,
        "label": item.label,
        "full_path": item.full_path,
        "sort_order": item.sort_order,
        "is_active": item.is_active,
        "is_selectable": item.is_selectable,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _would_create_topic_cycle(
    node: DialogCloseTopicNode,
    parent: DialogCloseTopicNode | None,
) -> bool:
    current = parent
    while current is not None:
        if current.id == node.id:
            return True
        current = current.parent
    return False


@csrf_exempt
@require_http_methods(["GET", "POST"])
def dialogs_collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        from django.db.models.functions import Coalesce

        status = (request.GET.get("status") or "").strip()
        qs = Dialog.objects.all()
        if status:
            qs = qs.filter(status=status)
        online = (request.GET.get("client_online") or "").strip().lower()
        if online in {"1", "true", "yes"}:
            qs = qs.filter(client_online=True)
        elif online in {"0", "false", "no"}:
            qs = qs.filter(client_online=False)
        initiated_by = (request.GET.get("initiated_by") or "").strip()
        if initiated_by:
            qs = qs.filter(initiated_by=initiated_by)
        external_id = (request.GET.get("client_external_id") or "").strip()
        if external_id:
            qs = qs.filter(client_external_id=external_id)
        if request.GET.get("operator_id"):
            qs = qs.filter(operator_id=request.GET["operator_id"])
        if request.GET.get("operator_name"):
            qs = qs.filter(operator_name=request.GET["operator_name"])
        client_ip = (request.GET.get("client_ip") or "").strip()
        if client_ip:
            qs = qs.filter(client_ip__icontains=client_ip)
        if request.GET.get("department_id"):
            qs = qs.filter(department_id=request.GET["department_id"])
        if request.GET.get("channel"):
            qs = qs.filter(channel=request.GET["channel"])
        if request.GET.get("outcome"):
            qs = qs.filter(outcome=request.GET["outcome"])
        if request.GET.get("close_topic"):
            qs = qs.filter(close_topic__icontains=request.GET["close_topic"].strip())
        has_feedback = (request.GET.get("has_feedback") or "").strip().lower()
        if has_feedback in {"1", "true", "yes"}:
            qs = qs.filter(feedback__isnull=False).distinct()
        elif has_feedback in {"0", "false", "no"}:
            qs = qs.filter(feedback__isnull=True)
        ratings_raw = (request.GET.get("ratings") or "").strip()
        if ratings_raw:
            ratings: list[int] = []
            for chunk in re.split(r"[,\s]+", ratings_raw):
                if not chunk:
                    continue
                if not chunk.isdigit():
                    continue
                value = int(chunk)
                if 1 <= value <= 5 and value not in ratings:
                    ratings.append(value)
            if ratings:
                qs = qs.filter(feedback__rating__in=ratings).distinct()
        date_from = (request.GET.get("date_from") or "").strip()
        date_to = (request.GET.get("date_to") or "").strip()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        q_raw = (request.GET.get("q") or "").strip()
        if q_raw:
            from django.db.models import Q
            tokens = [token for token in re.split(r"\s+", q_raw) if token]
            for token in tokens:
                token_q = (
                    Q(client_first_name__icontains=token)
                    | Q(client_last_name__icontains=token)
                    | Q(client_phone__icontains=token)
                    | Q(operator_name__icontains=token)
                    | Q(close_topic__icontains=token)
                    | Q(preview__icontains=token)
                    | Q(channel__icontains=token)
                    | Q(client_ip__icontains=token)
                    | Q(id__icontains=token)
                    | Q(messages__text__icontains=token)
                )
                qs = qs.filter(token_q)
            qs = qs.distinct()
        # Waiting queue: oldest first so the newest writer is at the bottom in UI.
        if status == Dialog.Status.WAITING:
            qs = qs.annotate(
                queue_key=Coalesce("last_client_message_at", "created_at"),
            ).order_by("queue_key", "created_at")
        else:
            qs = qs.order_by("-updated_at")
        items = [serialize_dialog(dialog) for dialog in qs[:200]]
        return JsonResponse({"ok": True, "items": items, "count": len(items)})

    try:
        payload = _json_body(request)
        text = _str_field(payload, "text")
        attachment_name = _str_field(payload, "attachment_name")
        if not text and not attachment_name:
            raise OnlineChatApiError("text must be a non-empty string")
        initiated_by = (
            _str_field(payload, "initiated_by", Dialog.InitiatedBy.CLIENT)
            or Dialog.InitiatedBy.CLIENT
        )
        if initiated_by not in {
            Dialog.InitiatedBy.CLIENT,
            Dialog.InitiatedBy.OPERATOR,
        }:
            raise OnlineChatApiError("initiated_by must be client or operator")
        try:
            dialog, message = create_dialog_with_message(
                text=text or f"Файл: {attachment_name}",
                widget_id=_str_field(payload, "widget_id", "site-belarusbank")
                or "site-belarusbank",
                placement=_str_field(payload, "placement", "website") or "website",
                client_first_name=_str_field(payload, "first_name")
                or _str_field(payload, "name"),
                client_last_name=_str_field(payload, "last_name"),
                client_phone=_str_field(payload, "phone"),
                client_external_id=_str_field(payload, "client_external_id"),
                entry_url=_str_field(payload, "entry_url")
                or _str_field(payload, "page_url"),
                locale=_str_field(payload, "locale", "ru") or "ru",
                channel=_str_field(payload, "channel", "widget") or "widget",
                initiated_by=initiated_by,
                operator_name=_str_field(payload, "operator_name"),
                client_ip=_request_client_ip(request),
                client_fields=payload.get("fields")
                if isinstance(payload.get("fields"), list)
                else None,
            )
        except PermissionError as exc:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "client_blocked",
                    "detail": str(exc),
                },
                status=403,
            )
        return JsonResponse(
            {
                "ok": True,
                "dialog": serialize_dialog(dialog, include_messages=True),
                "message": serialize_message(message),
            },
            status=201,
        )
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["GET"])
def dialog_detail(request: HttpRequest, dialog_id: str) -> HttpResponse:
    dialog = get_object_or_404(Dialog, pk=dialog_id)
    include_history = (request.GET.get("include_history") or "").strip().casefold() in {
        "1",
        "true",
        "yes",
    }
    return JsonResponse(
        {
            "ok": True,
            "dialog": serialize_dialog(
                dialog,
                include_messages=True,
                include_history=include_history,
            ),
        },
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def dialog_messages(request: HttpRequest, dialog_id: str) -> HttpResponse:
    dialog = get_object_or_404(Dialog, pk=dialog_id)
    if request.method == "GET":
        items = [serialize_message(item) for item in dialog.messages.all()]
        return JsonResponse({"ok": True, "items": items, "count": len(items)})

    try:
        payload = _json_body(request)
        text = _str_field(payload, "text")
        attachment_name = _str_field(payload, "attachment_name")
        if not text and not attachment_name:
            raise OnlineChatApiError("text or attachment_name is required")
        speaker = _str_field(payload, "speaker", DialogMessage.Speaker.CLIENT)
        if speaker not in {
            DialogMessage.Speaker.CLIENT,
            DialogMessage.Speaker.OPERATOR,
            DialogMessage.Speaker.SYSTEM,
        }:
            raise OnlineChatApiError("speaker must be client, operator, or system")
        if speaker == DialogMessage.Speaker.OPERATOR:
            denied = _operator_write_denied(
                request,
                dialog,
                claimed_name=_str_field(payload, "operator_name"),
            )
            if denied:
                return denied
        response_origin = _str_field(payload, "response_origin")
        suggestion_text = _str_field(payload, "sufler_suggestion_text")
        if response_origin == "sufler":
            text = _strip_suz_links(text)
            if not text and not attachment_name:
                raise OnlineChatApiError("answer is empty after link removal")
        if dialog.status in {Dialog.Status.CLOSED, Dialog.Status.BLOCKED}:
            raise OnlineChatApiError("dialog is closed")
        reply_to = None
        reply_to_id = _str_field(payload, "reply_to_id")
        if reply_to_id:
            reply_to = dialog.messages.filter(pk=reply_to_id).first()
            if reply_to is None:
                raise OnlineChatApiError("reply_to_id not found in dialog")
        message = append_message(
            dialog,
            speaker=speaker,
            text=text,
            reply_to=reply_to,
            attachment_name=attachment_name,
            response_origin=response_origin,
            sufler_suggestion_text=suggestion_text,
        )
        return JsonResponse(
            {"ok": True, "message": serialize_message(message)},
            status=201,
        )
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def dialog_attachment_upload(request: HttpRequest, dialog_id: str) -> HttpResponse:
    dialog = get_object_or_404(Dialog, pk=dialog_id)
    if dialog.status in {Dialog.Status.CLOSED, Dialog.Status.BLOCKED}:
        return _error(OnlineChatApiError("dialog is closed"))
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return _error(OnlineChatApiError("file is required"))
    if uploaded.size > settings.ONLINE_CHAT_MAX_UPLOAD_BYTES:
        return _error(OnlineChatApiError("file is too large"), status=413)
    content_type = uploaded.content_type or "application/octet-stream"
    if content_type not in settings.ONLINE_CHAT_ALLOWED_UPLOAD_TYPES:
        return _error(OnlineChatApiError("file type is not allowed"), status=415)
    speaker = (request.POST.get("speaker") or DialogMessage.Speaker.CLIENT).strip()
    if speaker not in {
        DialogMessage.Speaker.CLIENT,
        DialogMessage.Speaker.OPERATOR,
    }:
        return _error(OnlineChatApiError("speaker must be client or operator"))
    if speaker == DialogMessage.Speaker.OPERATOR:
        denied = _operator_write_denied(
            request,
            dialog,
            claimed_name=(request.POST.get("operator_name") or ""),
        )
        if denied:
            return denied
    safe_name = re.sub(r"[^A-Za-zА-Яа-я0-9._-]+", "_", uploaded.name)[:180]
    key = f"dialogs/{dialog.id}/{uuid.uuid4().hex}/{safe_name}"
    get_chat_object_store().put_bytes(
        key,
        uploaded.read(),
        content_type=content_type,
    )
    # Mark clean after type/size validation unless an external AV scanner is enabled.
    av_enabled = bool(getattr(settings, "ONLINE_CHAT_AV_ENABLED", False))
    message = append_message(
        dialog,
        speaker=speaker,
        text=(request.POST.get("text") or "").strip(),
        attachment_name=uploaded.name,
        attachment_key=key,
        attachment_content_type=content_type,
        attachment_size=uploaded.size,
        attachment_scan_status="pending" if av_enabled else "clean",
    )
    return JsonResponse(
        {"ok": True, "message": serialize_message(message)},
        status=201,
    )


@require_http_methods(["GET"])
def dialog_attachment_download(
    request: HttpRequest,
    dialog_id: str,
    message_id: str,
) -> HttpResponse:
    message = get_object_or_404(
        DialogMessage,
        pk=message_id,
        dialog_id=dialog_id,
    )
    if message.is_deleted or not message.attachment_key:
        return JsonResponse({"detail": "Not found"}, status=404)
    if message.attachment_scan_status not in {"clean", "not_required"}:
        return JsonResponse(
            {"detail": "Attachment is not cleared by security scan"},
            status=423,
        )
    payload = get_chat_object_store().get_bytes(message.attachment_key)
    response = HttpResponse(
        payload,
        content_type=message.attachment_content_type or "application/octet-stream",
    )
    response["Content-Disposition"] = (
        f"attachment; filename*=UTF-8''{quote(message.attachment_name)}"
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@csrf_exempt
@require_http_methods(["PATCH", "DELETE"])
def dialog_message_detail(
    request: HttpRequest,
    dialog_id: str,
    message_id: str,
) -> HttpResponse:
    dialog = get_object_or_404(Dialog, pk=dialog_id)
    message = get_object_or_404(DialogMessage, pk=message_id, dialog=dialog)
    try:
        if request.method == "DELETE":
            delete_message(message)
            return JsonResponse({"ok": True, "message": serialize_message(message)})
        payload = _json_body(request)
        if "text" not in payload:
            raise OnlineChatApiError("text is required")
        text = str(payload.get("text") or "")
        if not text.strip() and not message.attachment_key:
            raise OnlineChatApiError("text is required")
        edit_message(message, text=text)
        return JsonResponse({"ok": True, "message": serialize_message(message)})
    except (OnlineChatApiError, ValueError) as exc:
        return _error(OnlineChatApiError(str(exc)))


@csrf_exempt
@require_http_methods(["POST"])
def dialog_accept(request: HttpRequest, dialog_id: str) -> HttpResponse:
    dialog = get_object_or_404(Dialog, pk=dialog_id)
    try:
        payload = _json_body(request)
        operator_name = _str_field(payload, "operator_name", "Иванов И.И.") or "Иванов И.И."
        if dialog.status == Dialog.Status.CLOSED:
            raise OnlineChatApiError("dialog is closed")
        if not line_is_open():
            raise OnlineChatApiError(
                "Сейчас нерабочее время. Диалоги можно брать после начала рабочего дня."
            )
        if dialog.outcome == Dialog.Outcome.OFFLINE:
            raise OnlineChatApiError(
                "Диалог из офлайн-очереди станет доступен после начала рабочего дня."
            )
        operator_id = _str_field(payload, "operator_id")
        if operator_id:
            operator = get_object_or_404(OperatorProfile, pk=operator_id)
            dialog = accept_waiting_dialog(dialog.pk, operator=operator)
        else:
            dialog = accept_dialog(dialog, operator_name)
        return JsonResponse(
            {
                "ok": True,
                "dialog": serialize_dialog(
                    dialog,
                    include_messages=True,
                    include_history=True,
                ),
            },
        )
    except (OnlineChatApiError, ValueError) as exc:
        return _error(OnlineChatApiError(str(exc)), status=409 if isinstance(exc, ValueError) else 400)


@csrf_exempt
@require_http_methods(["POST"])
def dialog_transfer(request: HttpRequest, dialog_id: str) -> HttpResponse:
    from online_chat.routing_services import run_assignments

    dialog = get_object_or_404(Dialog, pk=dialog_id)
    try:
        payload = _json_body(request)
        to_operator = _str_field(payload, "to_operator_name") or _str_field(
            payload,
            "operator_name",
        )
        operator_id = _str_field(payload, "operator_id")
        if not to_operator and not operator_id:
            raise OnlineChatApiError("to_operator_name or operator_id is required")
        if dialog.status in {Dialog.Status.CLOSED, Dialog.Status.BLOCKED}:
            raise OnlineChatApiError("dialog is closed")
        previous_operator = dialog.operator
        previous_departments = list(
            previous_operator.departments.filter(is_active=True)
        ) if previous_operator else []
        if operator_id:
            dialog = transfer_to_operator(dialog, operator_id=operator_id)
        else:
            dialog = transfer_dialog(
                dialog,
                to_operator_name=to_operator,
                from_operator_name=_str_field(payload, "from_operator_name"),
            )
        # Free slot of the previous operator → pull next waiting dialogs.
        if previous_departments:
            for department in previous_departments:
                run_assignments(department=department)
        else:
            run_assignments()
        return JsonResponse({"ok": True, "dialog": serialize_dialog(dialog)})
    except (OnlineChatApiError, ValueError) as exc:
        return _error(OnlineChatApiError(str(exc)))


@csrf_exempt
@require_http_methods(["POST"])
def dialog_close(request: HttpRequest, dialog_id: str) -> HttpResponse:
    from online_chat.routing_services import run_assignments

    dialog = get_object_or_404(Dialog, pk=dialog_id)
    try:
        payload = _json_body(request)
        topic_id = _str_field(payload, "topic_id")
        topic_node = None
        topic = ""
        if topic_id:
            topic_node = get_object_or_404(
                DialogCloseTopicNode,
                pk=topic_id,
                is_active=True,
                is_selectable=True,
            )
            topic = topic_node.full_path or topic_node.label
        else:
            topic = _str_field(payload, "topic") or _str_field(payload, "close_topic")
        if not topic:
            raise OnlineChatApiError("topic is required")
        if dialog.status == Dialog.Status.CLOSED:
            if topic != dialog.close_topic:
                dialog.close_topic = topic
                dialog.close_topic_node = topic_node
                dialog.save(update_fields=["close_topic", "close_topic_node", "updated_at"])
            return JsonResponse({"ok": True, "dialog": serialize_dialog(dialog)})
        previous_operator = dialog.operator
        previous_departments = list(
            previous_operator.departments.filter(is_active=True)
        ) if previous_operator else []
        closed = close_dialog(dialog, topic=topic, topic_node=topic_node)
        # Held operator is skipped inside run_assignments; others can still receive work.
        if previous_departments:
            for department in previous_departments:
                run_assignments(department=department)
        else:
            run_assignments()
        response: dict[str, Any] = {"ok": True, "dialog": serialize_dialog(closed)}
        from django.utils import timezone as dj_tz

        from online_chat.models import OperatorAssignmentHold

        if previous_operator:
            hold = (
                OperatorAssignmentHold.objects.filter(operator=previous_operator)
                .order_by("-until")
                .first()
            )
            if hold is not None and hold.until > dj_tz.now():
                response["assignment_grace_until"] = hold.until.isoformat()
                response["assignment_grace_seconds"] = AssignmentSettings.GRACE_SECONDS
        return JsonResponse(response)
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@_chat_permissions(PERM_SUFLER_CHAT, PERM_CC_ADMIN)
def dialog_topics_collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        active_only = (request.GET.get("active") or "").strip().lower() not in {"0", "false", "no"}
        return JsonResponse({"ok": True, "items": topic_tree(active_only=active_only)})
    if not has_permission(request.user, PERM_CC_ADMIN) and not settings.DEBUG:
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    try:
        data = _json_body(request)
        label = _str_field(data, "label")
        if not label:
            raise OnlineChatApiError("label is required")
        parent = None
        parent_id = _str_field(data, "parent_id")
        if parent_id:
            parent = get_object_or_404(DialogCloseTopicNode, pk=parent_id)
        item = DialogCloseTopicNode.objects.create(
            parent=parent,
            label=label,
            full_path="",
            sort_order=_int_field(data, "sort_order") if "sort_order" in data else 100,
            # Topics are always active once an admin adds them; there is no
            # UI to deactivate one — removal is done via delete instead.
            is_active=True,
            is_selectable=_bool_field(data, "is_selectable", False),
        )
        # A node that just gained a child can no longer be a valid closing
        # topic on its own — only leaves are selectable. This keeps the tree
        # consistent even if a child gets nested under a former leaf "тема".
        if parent is not None and parent.is_selectable:
            parent.is_selectable = False
            parent.save(update_fields=["is_selectable", "updated_at"])
        rebuild_full_paths()
        item.refresh_from_db()
        return JsonResponse({"ok": True, "dialog_topic": _dialog_topic_dict(item)}, status=201)
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["PATCH", "DELETE"])
@_chat_permissions(PERM_CC_ADMIN)
def dialog_topic_detail(request: HttpRequest, item_id: str) -> HttpResponse:
    item = get_object_or_404(DialogCloseTopicNode, pk=item_id)
    if request.method == "DELETE":
        item.delete()
        rebuild_full_paths()
        return JsonResponse({"ok": True})
    try:
        data = _json_body(request)
        if "label" in data:
            item.label = _str_field(data, "label")
        if "sort_order" in data:
            item.sort_order = _int_field(data, "sort_order")
        if "is_active" in data:
            item.is_active = _bool_field(data, "is_active")
        if "is_selectable" in data:
            item.is_selectable = _bool_field(data, "is_selectable")
        if "parent_id" in data:
            parent_id = _str_field(data, "parent_id")
            parent = get_object_or_404(DialogCloseTopicNode, pk=parent_id) if parent_id else None
            if parent and _would_create_topic_cycle(item, parent):
                raise OnlineChatApiError("invalid parent_id")
            item.parent = parent
        item.save()
        rebuild_full_paths()
        item.refresh_from_db()
        return JsonResponse({"ok": True, "dialog_topic": _dialog_topic_dict(item)})
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
@_chat_permissions(PERM_CC_ADMIN)
def dialog_topics_reorder(request: HttpRequest) -> HttpResponse:
    try:
        data = _json_body(request)
        moved_id = _str_field(data, "id")
        if not moved_id:
            raise OnlineChatApiError("id is required")
        item = get_object_or_404(DialogCloseTopicNode, pk=moved_id)
        if "parent_id" in data:
            parent_id = _str_field(data, "parent_id")
            parent = get_object_or_404(DialogCloseTopicNode, pk=parent_id) if parent_id else None
            if parent and _would_create_topic_cycle(item, parent):
                raise OnlineChatApiError("invalid parent_id")
            item.parent = parent
        if "sort_order" in data:
            item.sort_order = _int_field(data, "sort_order")
        item.save(update_fields=["parent", "sort_order", "updated_at"])
        rebuild_full_paths()
        return JsonResponse({"ok": True})
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
@_chat_permissions(PERM_SUFLER_CHAT, PERM_CC_ADMIN)
def dialog_topics_suggest(request: HttpRequest) -> HttpResponse:
    try:
        data = _json_body(request)
        titles = _json_field(data, "article_titles", list, [])
        if any(not isinstance(item, str) for item in titles):
            raise OnlineChatApiError("article_titles must be a list of strings")
        result = classify_by_titles([str(item) for item in titles])
        return JsonResponse({"ok": True, **result})
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@_chat_permissions(PERM_CC_ADMIN)
def sla_settings(request: HttpRequest) -> HttpResponse:
    settings_obj = ServiceLevelSettings.get_solo()
    if request.method == "GET":
        return JsonResponse(
            {
                "ok": True,
                "settings": {
                    "first_response_seconds": settings_obj.first_response_seconds,
                    "updated_at": settings_obj.updated_at.isoformat(),
                },
            }
        )
    try:
        payload = _json_body(request)
        seconds = _int_field(payload, "first_response_seconds")
        if seconds < 15 or seconds > 3600:
            raise OnlineChatApiError("first_response_seconds must be between 15 and 3600")
        settings_obj.first_response_seconds = seconds
        settings_obj.save(update_fields=["first_response_seconds", "updated_at"])
        return JsonResponse(
            {
                "ok": True,
                "settings": {
                    "first_response_seconds": settings_obj.first_response_seconds,
                    "updated_at": settings_obj.updated_at.isoformat(),
                },
            }
        )
    except OnlineChatApiError as exc:
        return _error(exc)


def _work_schedule_dict(obj: WorkScheduleSettings) -> dict[str, Any]:
    return {
        "enabled": obj.enabled,
        "start_time": obj.start_time.strftime("%H:%M"),
        "end_time": obj.end_time.strftime("%H:%M"),
        "workdays": list(obj.workdays or []),
        "holidays": list(obj.holidays or []),
        "day_overrides": dict(obj.day_overrides or {}),
        "manual_override": obj.manual_override,
        "is_open": obj.is_open(),
        "updated_at": obj.updated_at.isoformat(),
    }


def _parse_hhmm(value: str, field: str):
    from datetime import datetime as _dt

    try:
        return _dt.strptime(str(value).strip(), "%H:%M").time()
    except (ValueError, TypeError) as exc:
        raise OnlineChatApiError(f"{field} must be HH:MM") from exc


def _normalize_day_overrides(raw) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise OnlineChatApiError("day_overrides must be an object")
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        date_key = str(key).strip()
        if len(date_key) != 10 or date_key[4] != "-" or date_key[7] != "-":
            raise OnlineChatApiError(f"invalid day_overrides date: {date_key}")
        if not isinstance(value, dict):
            raise OnlineChatApiError(f"day_overrides[{date_key}] must be an object")
        entry: dict[str, Any] = {
            "is_workday": bool(value.get("is_workday")),
        }
        if "start_time" in value and value.get("start_time"):
            start = _parse_hhmm(str(value.get("start_time")), "start_time")
            entry["start_time"] = start.strftime("%H:%M")
        if "end_time" in value and value.get("end_time"):
            end = _parse_hhmm(str(value.get("end_time")), "end_time")
            entry["end_time"] = end.strftime("%H:%M")
        cleaned[date_key] = entry
    return cleaned


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@_chat_permissions(PERM_CC_ADMIN)
def work_schedule_settings(request: HttpRequest) -> HttpResponse:
    obj = WorkScheduleSettings.get_solo()
    if request.method == "GET":
        return JsonResponse({"ok": True, "settings": _work_schedule_dict(obj)})
    try:
        payload = _json_body(request)
        if "enabled" in payload:
            obj.enabled = _bool_field(payload, "enabled", obj.enabled)
        if "start_time" in payload:
            obj.start_time = _parse_hhmm(payload.get("start_time"), "start_time")
        if "end_time" in payload:
            obj.end_time = _parse_hhmm(payload.get("end_time"), "end_time")
        if "workdays" in payload:
            raw = payload.get("workdays")
            if not isinstance(raw, list):
                raise OnlineChatApiError("workdays must be a list of 0..6")
            days = sorted({int(x) for x in raw if isinstance(x, (int, float)) and 0 <= int(x) <= 6})
            obj.workdays = days
        if "holidays" in payload:
            raw = payload.get("holidays")
            if not isinstance(raw, list):
                raise OnlineChatApiError("holidays must be a list of YYYY-MM-DD")
            obj.holidays = [str(x).strip() for x in raw if str(x).strip()]
        if "day_overrides" in payload:
            obj.day_overrides = _normalize_day_overrides(payload.get("day_overrides"))
        if "manual_override" in payload:
            override = str(payload.get("manual_override") or "").strip()
            if override not in WorkScheduleSettings.Override.values:
                raise OnlineChatApiError("invalid manual_override")
            obj.manual_override = override
        obj.save()
        # Applying settings may flip open⇄closed — run the matching transition
        # (queue restore + operators offline, or backlog flush) automatically.
        sync_result = sync_schedule_state(obj)
        if sync_result.get("changed"):
            _broadcast_schedule_change(obj)
        return JsonResponse({"ok": True, "settings": _work_schedule_dict(obj)})
    except OnlineChatApiError as exc:
        return _error(exc)


def _broadcast_schedule_change(obj: WorkScheduleSettings) -> None:
    broadcast(ARM_GROUP, "work_schedule.updated", {
        "is_open": obj.is_open(),
        "manual_override": obj.manual_override,
    })


@require_http_methods(["GET"])
def work_schedule_status(request: HttpRequest) -> HttpResponse:
    """Public status the ARM/widget poll to show the line state.

    Also doubles as a low-latency trigger for the automatic open⇄closed
    transition in between periodic Celery beat runs (both share
    ``sync_schedule_state``, which is a no-op unless the state actually
    changed since the last observation).
    """
    obj = WorkScheduleSettings.get_solo()
    sync_result = sync_schedule_state(obj)
    if sync_result.get("changed"):
        _broadcast_schedule_change(obj)
    return JsonResponse(
        {
            "ok": True,
            "is_open": sync_result["is_open"],
            "enabled": obj.enabled,
            "manual_override": obj.manual_override,
            "start_time": obj.start_time.strftime("%H:%M"),
            "end_time": obj.end_time.strftime("%H:%M"),
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def work_day_control(request: HttpRequest) -> HttpResponse:
    """Manual online/offline toggle — demo/test simulator only.

    Production relies on the schedule (``WorkScheduleSettings`` + the
    periodic sync task) to switch automatically; this endpoint exists so the
    test simulator can flip the line without waiting for the clock. Unlike
    ``sync_schedule_state`` (which only acts on genuine transitions so the
    passive pollers stay idempotent), this is an explicit human command, so
    it always (re)applies the matching transition — harmless no-op if the
    line was already in that state.
    """
    try:
        payload = _json_body(request)
        action = str(payload.get("action") or "").strip()
        obj = WorkScheduleSettings.get_solo()
        if action == "start":
            obj.manual_override = WorkScheduleSettings.Override.OPEN
        elif action == "stop":
            obj.manual_override = WorkScheduleSettings.Override.CLOSED
        elif action == "auto":
            obj.manual_override = WorkScheduleSettings.Override.AUTO
        else:
            raise OnlineChatApiError("action must be start, stop or auto")
        obj.save(update_fields=["manual_override", "updated_at"])
        now_open = obj.is_open()
        result = open_working_day() if now_open else close_working_day()
        obj.last_open_state = now_open
        obj.save(update_fields=["last_open_state"])
        _broadcast_schedule_change(obj)
        return JsonResponse(
            {
                "ok": True,
                "is_open": now_open,
                "assigned": result.get("assigned", 0),
                "returned_to_queue": result.get("returned_to_queue", 0),
            }
        )
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
def assignment_settings(request: HttpRequest) -> HttpResponse:
    settings_obj = AssignmentSettings.get_solo()
    if request.method == "GET":
        return JsonResponse(
            {
                "ok": True,
                "settings": {
                    "mode": settings_obj.mode,
                    "grace_seconds": AssignmentSettings.GRACE_SECONDS,
                    "modes": [
                        {
                            "id": AssignmentSettings.Mode.STRICT_AUTO,
                            "label": "Только автоназначение",
                        },
                        {
                            "id": AssignmentSettings.Mode.MANUAL_PLUS_AUTO,
                            "label": "Ручной выбор + авто (10 сек после закрытия)",
                        },
                    ],
                },
            }
        )
    try:
        payload = _json_body(request)
        mode = _str_field(payload, "mode")
        if mode not in AssignmentSettings.Mode.values:
            raise OnlineChatApiError("invalid assignment mode")
        settings_obj.mode = mode
        settings_obj.save(update_fields=["mode", "updated_at"])
        return JsonResponse(
            {
                "ok": True,
                "settings": {
                    "mode": settings_obj.mode,
                    "grace_seconds": AssignmentSettings.GRACE_SECONDS,
                },
            }
        )
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def sufler_hint_feedback(request: HttpRequest) -> HttpResponse:
    try:
        payload = _json_body(request)
        choice = _str_field(payload, "choice")
        if choice not in SuflerHintFeedback.Choice.values:
            raise OnlineChatApiError("choice must be used|not_used|partial")
        dialog_id = _str_field(payload, "dialog_id")
        dialog = None
        if dialog_id:
            dialog = Dialog.objects.filter(pk=dialog_id).first()
        relevance = payload.get("relevance_percent")
        relevance_int = None
        if isinstance(relevance, int) and not isinstance(relevance, bool):
            relevance_int = max(0, min(100, relevance))
        rank_raw = payload.get("hint_rank", 1)
        try:
            hint_rank = max(1, int(rank_raw))
        except (TypeError, ValueError):
            hint_rank = 1
        row = SuflerHintFeedback.objects.create(
            dialog=dialog,
            operator_name=_str_field(payload, "operator_name"),
            query=_str_field(payload, "query"),
            hint_rank=hint_rank,
            hint_text=_str_field(payload, "hint_text"),
            choice=choice,
            relevance_percent=relevance_int,
            citation_title=_str_field(payload, "citation_title"),
            request_id=_str_field(payload, "request_id"),
            source=(_str_field(payload, "source") or "chat")[:32],
            call_id=_str_field(payload, "call_id")[:64],
        )
        try:
            from qu.admin_service import enqueue_from_feedback

            enqueue_from_feedback(row)
        except Exception:
            logger.exception("QU enqueue from sufler feedback failed")
        return JsonResponse(
            {
                "ok": True,
                "feedback": {
                    "id": str(row.id),
                    "choice": row.choice,
                    "hint_rank": row.hint_rank,
                    "created_at": row.created_at.isoformat(),
                },
            }
        )
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def sufler_outage_report(request: HttpRequest) -> HttpResponse:
    """Operator reports a sufler outage — notify supervisors/admins (FR-CC error path)."""
    try:
        payload = _json_body(request)
        operator_name = _str_field(payload, "operator_name")
        query = _str_field(payload, "query")
        detail = _str_field(payload, "detail")
        dialog_id = _str_field(payload, "dialog_id")
        dialog = Dialog.objects.filter(pk=dialog_id).first() if dialog_id else None
        reported_at = timezone.now().isoformat()
        logger.error(
            "sufler_outage_reported operator=%s dialog=%s detail=%s query=%s",
            operator_name,
            dialog_id or "-",
            detail or "-",
            (query or "")[:200],
        )
        if dialog is not None:
            record_event(
                dialog,
                "sufler_outage_reported",
                actor_name=operator_name,
                payload={"query": query, "detail": detail},
            )
        notice = {
            "kind": "sufler_outage",
            "dialog_id": str(dialog.id) if dialog is not None else dialog_id,
            "operator_name": operator_name,
            "query": query,
            "detail": detail or "Суфлёр недоступен",
            "reported_at": reported_at,
        }
        # Supervisors and admins share the ARM socket group.
        broadcast(ARM_GROUP, "sufler.outage", notice)
        return JsonResponse({"ok": True, "notice": notice})
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def dialog_mark_read(request: HttpRequest, dialog_id: str) -> HttpResponse:
    dialog = get_object_or_404(Dialog, pk=dialog_id)
    try:
        payload = _json_body(request)
        reader = _str_field(payload, "reader")
        if reader not in {
            DialogMessage.Speaker.CLIENT,
            DialogMessage.Speaker.OPERATOR,
        }:
            raise OnlineChatApiError("reader must be client or operator")
        updated = mark_dialog_messages_read(dialog, reader=reader)
        return JsonResponse(
            {
                "ok": True,
                "dialog_id": str(dialog.id),
                "reader": reader,
                "message_ids": [str(item.id) for item in updated],
                "messages": [serialize_message(item) for item in updated],
            },
        )
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def dialog_presence(request: HttpRequest, dialog_id: str) -> HttpResponse:
    dialog = get_object_or_404(Dialog, pk=dialog_id)
    try:
        payload = _json_body(request)
        online_raw = payload.get("online", True)
        online = bool(online_raw) if not isinstance(online_raw, str) else online_raw.lower() in {
            "1",
            "true",
            "yes",
        }
        set_client_presence(dialog, online=online)
        return JsonResponse({"ok": True, "dialog": serialize_dialog(dialog)})
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def dialog_block(request: HttpRequest, dialog_id: str) -> HttpResponse:
    dialog = get_object_or_404(Dialog, pk=dialog_id)
    try:
        payload = _json_body(request)
        dialog, block = block_dialog(
            dialog,
            blocked_by=_str_field(payload, "blocked_by"),
            reason=_str_field(payload, "reason"),
        )
        body: dict[str, Any] = {"ok": True, "dialog": serialize_dialog(dialog)}
        if block is not None:
            body["block"] = serialize_client_block(block)
        return JsonResponse(body)
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def client_blocks_collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        active_only = (request.GET.get("active") or "1").strip().lower() not in {
            "0",
            "false",
            "no",
        }
        qs = ClientBlock.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
        items = [serialize_client_block(item) for item in qs[:200]]
        return JsonResponse({"ok": True, "items": items, "count": len(items)})
    return JsonResponse(
        {"ok": False, "error": "method_not_allowed", "detail": "POST via dialog block"},
        status=405,
    )


@csrf_exempt
@require_http_methods(["POST"])
def client_block_lift(request: HttpRequest, block_id: str) -> HttpResponse:
    block = get_object_or_404(ClientBlock, pk=block_id)
    try:
        payload = _json_body(request)
        unblock_client(block, lifted_by=_str_field(payload, "lifted_by", "admin"))
        return JsonResponse({"ok": True, "block": serialize_client_block(block)})
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def dialog_feedback(request: HttpRequest, dialog_id: str) -> HttpResponse:
    dialog = get_object_or_404(Dialog, pk=dialog_id)
    try:
        if dialog.status != Dialog.Status.CLOSED:
            raise OnlineChatApiError("dialog must be closed before feedback")
        payload = _json_body(request)
        rating = _int_field(payload, "rating")
        if rating < 1 or rating > 5:
            raise OnlineChatApiError("rating must be between 1 and 5")
        comment = _str_field(payload, "comment")
        feedback = save_feedback(dialog, rating=rating, comment=comment)
        return JsonResponse(
            {"ok": True, "feedback": serialize_feedback(feedback)},
            status=201,
        )
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def dialog_send_transcript(request: HttpRequest, dialog_id: str) -> HttpResponse:
    dialog = get_object_or_404(Dialog, pk=dialog_id)
    try:
        if dialog.status != Dialog.Status.CLOSED:
            raise OnlineChatApiError("dialog must be closed before sending transcript")
        payload = _json_body(request)
        email = _str_field(payload, "email")
        if not email:
            raise OnlineChatApiError("email is required")
        try:
            validate_email(email)
        except DjangoValidationError as exc:
            raise OnlineChatApiError("email is invalid") from exc
        if not EMAIL_RE.match(email):
            raise OnlineChatApiError("email is invalid")
        record = request_transcript_email(dialog, email=email)
        return JsonResponse(
            {
                "ok": record.status == "sent",
                "transcript_email": serialize_transcript_email(record),
            },
            status=201 if record.status == "sent" else 502,
        )
    except OnlineChatApiError as exc:
        return _error(exc)


def _bool_field(payload: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false", "1", "0"}:
        return value.lower() in {"true", "1"}
    raise OnlineChatApiError(f"{key} must be a boolean")


def _json_field(
    payload: Mapping[str, Any], key: str, expected: type, default: Any
) -> Any:
    value = payload.get(key, default)
    if not isinstance(value, expected):
        raise OnlineChatApiError(f"{key} must be a JSON {expected.__name__}")
    return value


def _department_dict(item: Department) -> dict[str, Any]:
    return {
        "id": str(item.id), "code": item.code, "name": item.name,
        "description": item.description, "is_active": item.is_active,
        "priority": item.priority, "max_queue_size": item.max_queue_size,
        "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
    }


def _operator_dict(item: OperatorProfile) -> dict[str, Any]:
    department_ids = [
        str(value) for value in item.departments.values_list("id", flat=True)
    ]
    first_department = item.departments.order_by("priority", "name").first()
    is_operator = item.role == OperatorProfile.Role.OPERATOR
    return {
        "id": str(item.id), "external_id": item.external_id,
        "display_name": item.display_name, "email": item.email, "role": item.role,
        "presence": item.presence,
        "department_ids": department_ids,
        "max_active_dialogs": item.max_active_dialogs, "auto_assign": item.auto_assign,
        "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
        "is_active": item.is_active,
        # Stable aliases consumed by the management SPA.
        "name": item.display_name,
        "username": item.external_id,
        "capacity": item.max_active_dialogs,
        "department_id": (
            str(first_department.id) if first_department and is_operator else None
        ),
        "department_name": (
            first_department.name if first_department and is_operator else ""
        ),
        "photo_url": getattr(item, "photo_url", "") or "",
        "skill_tags": list(getattr(item, "skill_tags", None) or []),
        "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
    }


def _placement_dict(item: WidgetPlacement, *, public: bool = False) -> dict[str, Any]:
    data = {
        "widget_id": item.widget_id, "name": item.name, "site_url": item.site_url,
        "code": item.widget_id,
        "allowed_domains": item.allowed_domains,
        "department_id": str(item.department_id) if item.department_id else None,
        "is_active": item.is_active, "theme": item.theme, "config": item.config,
        "welcome_message": item.welcome_message, "queue_message": item.queue_message,
        "offline_message": item.offline_message, "require_phone": item.require_phone,
        "form_fields": normalize_form_fields(item.form_fields, require_phone=False),
        "theme_accent": item.theme.get("accent", "#007A43"),
    }
    if not public:
        data.update({
            "id": str(item.id), "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
            "counters": _channel_counters("widget", widget_id=item.widget_id),
        })
    return data


SECRET_MARKERS = ("token", "secret", "password", "api_key", "private_key", "credential")


def _safe_config(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: (
                "***"
                if any(marker in key.lower() for marker in SECRET_MARKERS)
                else _safe_config(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe_config(item) for item in value]
    return value


def _channel_counters(channel: str, *, widget_id: str = "") -> dict[str, int]:

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    qs = Dialog.objects.filter(channel=channel)
    if channel == "widget" and widget_id:
        qs = qs.filter(widget_id=widget_id)
    return {
        "waiting": qs.filter(status=Dialog.Status.WAITING).count(),
        "active": qs.filter(status=Dialog.Status.ACTIVE).count(),
        "today": qs.filter(created_at__gte=today_start).count(),
        "closed_today": qs.filter(
            status=Dialog.Status.CLOSED, closed_at__gte=today_start
        ).count(),
    }


def _channel_dict(item: ChannelConnection) -> dict[str, Any]:
    safe_config = _safe_config(item.config)
    form_fields = []
    if isinstance(safe_config, dict) and isinstance(safe_config.get("form_fields"), list):
        form_fields = normalize_form_fields(
            safe_config.get("form_fields") or [],
            require_phone=False,
        )
    return {
        "id": str(item.id), "channel": item.channel, "name": item.name,
        "kind": item.channel,
        "external_id": item.external_id,
        "account": item.external_id,
        "department_id": str(item.department_id) if item.department_id else None,
        "is_active": item.is_active, "config": safe_config,
        "form_fields": form_fields,
        "endpoint": safe_config.get("endpoint", "") if isinstance(safe_config, dict) else "",
        "configured": bool(item.external_id or item.config),
        "health_status": item.health_status,
        "last_health_check_at": (
            item.last_health_check_at.isoformat() if item.last_health_check_at else None
        ),
        "counters": _channel_counters(item.channel),
        "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
    }


def _rule_dict(item: RoutingRule) -> dict[str, Any]:
    connection = ChannelConnection.objects.filter(channel=item.channel).first()
    return {
        "id": str(item.id), "name": item.name, "priority": item.priority,
        "channel": item.channel,
        "channel_id": str(connection.id) if connection else None,
        "placement_id": str(item.placement_id) if item.placement_id else None,
        "department_id": str(item.department_id), "conditions": item.conditions,
        "max_load": item.conditions.get("max_load") if isinstance(item.conditions, dict) else None,
        "is_active": item.is_active, "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _bot_dict(item: BotConfiguration) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "name": item.name,
        "department_id": str(item.department_id) if item.department_id else None,
        "is_active": item.is_active,
        "welcome_message": item.welcome_message,
        "offline_message": item.offline_message,
        "fallback_message": item.fallback_message,
        "trigger_responses": item.trigger_responses,
        "max_bot_turns": item.max_bot_turns,
        "handoff_message": item.handoff_message,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _bot_values(
    data: Mapping[str, Any],
    item: BotConfiguration | None = None,
) -> BotConfiguration:
    item = item or BotConfiguration()
    for field in (
        "name",
        "welcome_message",
        "offline_message",
        "fallback_message",
        "handoff_message",
    ):
        if field in data:
            setattr(item, field, _str_field(data, field))
    if "department_id" in data:
        department_id = data.get("department_id")
        item.department = (
            get_object_or_404(Department, pk=department_id) if department_id else None
        )
    if "trigger_responses" in data:
        item.trigger_responses = _json_field(
            data,
            "trigger_responses",
            dict,
            {},
        )
    if "max_bot_turns" in data:
        item.max_bot_turns = _int_field(data, "max_bot_turns")
    if "is_active" in data:
        item.is_active = _bool_field(data, "is_active")
    if not item.name:
        raise OnlineChatApiError("name is required")
    item.save()
    return item


def _base_message_dict(item: BaseMessage) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "message_type": item.message_type,
        "title": item.title,
        "text": item.text,
        "channel": item.channel,
        "channels": item.channels,
        "send_phase": item.send_phase,
        "sort_order": item.sort_order,
        "delay_seconds": item.delay_seconds,
        "placement_id": str(item.placement_id) if item.placement_id else None,
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _sync_base_message_targets(item: BaseMessage) -> None:
    """Keep widget/channel runtime fields in sync with base messages."""
    targets = [str(value) for value in (item.channels or []) if str(value)]
    if not targets:
        if item.placement_id:
            targets = [f"widget:{item.placement_id}"]
        elif item.channel:
            targets = [item.channel]

    placement_ids = [
        value.removeprefix("widget:")
        for value in targets
        if value.startswith("widget:")
    ]
    includes_all_widgets = not targets or "widget" in targets
    placement_qs = WidgetPlacement.objects.filter(is_active=True)
    if placement_ids and not includes_all_widgets:
        placement_qs = placement_qs.filter(pk__in=placement_ids)

    field = ""
    if item.send_phase == BaseMessage.SendPhase.BEFORE_BOT:
        field = "welcome_message"
    elif item.send_phase == BaseMessage.SendPhase.OFFLINE:
        field = "offline_message"
    if field and (includes_all_widgets or placement_ids):
        placement_qs.update(**{field: item.text})

    if item.send_phase == BaseMessage.SendPhase.OFFLINE:
        connection_qs = ChannelConnection.objects.all()
        selected_channels = [value for value in targets if not value.startswith("widget:")]
        if targets and selected_channels:
            connection_qs = connection_qs.filter(channel__in=selected_channels)
        elif targets and not includes_all_widgets:
            connection_qs = connection_qs.none()
        for connection in connection_qs:
            config = dict(connection.config or {})
            config["offline_message"] = item.text
            connection.config = config
            connection.save(update_fields=["config", "updated_at"])


def _base_message_values(
    data: Mapping[str, Any],
    item: BaseMessage | None = None,
) -> BaseMessage:
    is_new = item is None
    item = item or BaseMessage()
    if "message_type" in data or item.message_type == "":
        message_type = _str_field(data, "message_type", item.message_type or "welcome")
        if message_type not in BaseMessage.MessageType.values:
            raise OnlineChatApiError("invalid message_type")
        item.message_type = message_type
        if "send_phase" not in data:
            item.send_phase = {
                BaseMessage.MessageType.WELCOME: BaseMessage.SendPhase.BEFORE_BOT,
                BaseMessage.MessageType.OFFLINE: BaseMessage.SendPhase.OFFLINE,
                BaseMessage.MessageType.BROADCAST: BaseMessage.SendPhase.AFTER_BOT,
            }[message_type]
    if "title" in data:
        item.title = _str_field(data, "title")
    if "text" in data:
        item.text = _str_field(data, "text")
    if "channel" in data:
        item.channel = _str_field(data, "channel")
    if "channels" in data:
        channels = _json_field(data, "channels", list, [])
        if any(not isinstance(value, str) or not value.strip() for value in channels):
            raise OnlineChatApiError("channels must contain non-empty strings")
        item.channels = list(dict.fromkeys(value.strip() for value in channels))
    if "send_phase" in data:
        send_phase = _str_field(data, "send_phase")
        if send_phase not in BaseMessage.SendPhase.values:
            raise OnlineChatApiError("invalid send_phase")
        item.send_phase = send_phase
        item.message_type = {
            BaseMessage.SendPhase.BEFORE_BOT: BaseMessage.MessageType.WELCOME,
            BaseMessage.SendPhase.OFFLINE: BaseMessage.MessageType.OFFLINE,
            BaseMessage.SendPhase.AFTER_BOT: BaseMessage.MessageType.BROADCAST,
            BaseMessage.SendPhase.MID_DIALOG: BaseMessage.MessageType.BROADCAST,
            BaseMessage.SendPhase.HOLD: BaseMessage.MessageType.BROADCAST,
        }[send_phase]
    if "sort_order" in data:
        item.sort_order = _int_field(data, "sort_order")
    if "delay_seconds" in data:
        item.delay_seconds = max(0, _int_field(data, "delay_seconds"))
    if "placement_id" in data:
        placement_id = data.get("placement_id")
        item.placement = (
            get_object_or_404(WidgetPlacement, pk=placement_id) if placement_id else None
        )
    if "is_active" in data:
        item.is_active = _bool_field(data, "is_active")
    if not item.text:
        raise OnlineChatApiError("text is required")
    if not item.message_type:
        raise OnlineChatApiError("message_type is required")
    item.save()
    sync_fields = {
        "message_type",
        "send_phase",
        "text",
        "channel",
        "channels",
        "placement_id",
        "is_active",
    }
    if item.is_active and (is_new or sync_fields.intersection(data)):
        _sync_base_message_targets(item)
    return item


@csrf_exempt
@require_http_methods(["GET", "POST"])
@_chat_permissions(PERM_CC_ADMIN)
def base_messages_collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        items = [_base_message_dict(item) for item in BaseMessage.objects.all()]
        return JsonResponse({"ok": True, "items": items, "count": len(items)})
    try:
        item = _base_message_values(_json_body(request))
        return JsonResponse({"ok": True, "base_message": _base_message_dict(item)}, status=201)
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["PATCH", "DELETE"])
@_chat_permissions(PERM_CC_ADMIN)
def base_message_detail(request: HttpRequest, item_id: str) -> HttpResponse:
    item = get_object_or_404(BaseMessage, pk=item_id)
    if request.method == "DELETE":
        item.delete()
        return JsonResponse({"ok": True})
    try:
        item = _base_message_values(_json_body(request), item)
        return JsonResponse({"ok": True, "base_message": _base_message_dict(item)})
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@_chat_permissions(PERM_CC_ADMIN)
def bots_collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        items = [_bot_dict(item) for item in BotConfiguration.objects.all()]
        return JsonResponse({"ok": True, "items": items, "count": len(items)})
    try:
        item = _bot_values(_json_body(request))
        return JsonResponse(
            {"ok": True, "bot": _bot_dict(item)},
            status=201,
        )
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["PATCH", "DELETE"])
@_chat_permissions(PERM_CC_ADMIN)
def bot_detail(request: HttpRequest, item_id: str) -> HttpResponse:
    item = get_object_or_404(BotConfiguration, pk=item_id)
    if request.method == "DELETE":
        item.delete()
        return JsonResponse({"ok": True})
    try:
        item = _bot_values(_json_body(request), item)
        return JsonResponse({"ok": True, "bot": _bot_dict(item)})
    except OnlineChatApiError as exc:
        return _error(exc)


def _set_departments(operator: OperatorProfile, payload: Mapping[str, Any]) -> None:
    if "department_ids" not in payload:
        return
    ids = _json_field(payload, "department_ids", list, [])
    departments = list(Department.objects.filter(id__in=ids))
    if len(departments) != len(set(ids)):
        raise OnlineChatApiError("one or more department_ids are invalid")
    operator.departments.set(departments)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@_chat_permissions(PERM_CC_ADMIN)
def departments_collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        items = [_department_dict(item) for item in Department.objects.all()]
        return JsonResponse({"ok": True, "items": items, "count": len(items)})
    try:
        data = _json_body(request)
        code = _str_field(data, "code")
        name = _str_field(data, "name")
        if not name:
            raise OnlineChatApiError("name is required")
        if not code:
            code = f"dept-{uuid.uuid4().hex[:8]}"
        item = Department.objects.create(
            code=code, name=name,
            description=_str_field(data, "description"),
            is_active=_bool_field(data, "is_active", True),
            priority=data.get("priority", 100), max_queue_size=data.get("max_queue_size", 100),
        )
        return JsonResponse({"ok": True, "department": _department_dict(item)}, status=201)
    except (OnlineChatApiError, ValueError) as exc:
        return _error(OnlineChatApiError(str(exc)))


@csrf_exempt
@require_http_methods(["PATCH", "DELETE"])
@_chat_permissions(PERM_CC_ADMIN)
def department_detail(request: HttpRequest, item_id: str) -> HttpResponse:
    item = get_object_or_404(Department, pk=item_id)
    if request.method == "DELETE":
        item.delete()
        return JsonResponse({"ok": True})
    try:
        data = _json_body(request)
        for field in ("code", "name", "description"):
            if field in data:
                setattr(item, field, _str_field(data, field))
        for field in ("priority", "max_queue_size"):
            if field in data:
                setattr(item, field, _int_field(data, field))
        if "is_active" in data:
            item.is_active = _bool_field(data, "is_active")
        item.save()
        return JsonResponse({"ok": True, "department": _department_dict(item)})
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@_chat_permissions(PERM_CC_ADMIN, PERM_CC_REPORTS)
def operators_collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        items = [_operator_dict(item) for item in OperatorProfile.objects.prefetch_related("departments")]
        return JsonResponse({"ok": True, "items": items, "count": len(items)})
    try:
        data = _json_body(request)
        role = _str_field(data, "role", OperatorProfile.Role.OPERATOR)
        presence = _str_field(data, "presence", OperatorProfile.Presence.OFFLINE)
        external_id = _str_field(data, "external_id") or _str_field(data, "username")
        display_name = _str_field(data, "display_name") or _str_field(data, "name")
        if not external_id or not display_name:
            raise OnlineChatApiError("external_id and display_name are required")
        if role not in OperatorProfile.Role.values or presence not in OperatorProfile.Presence.values:
            raise OnlineChatApiError("invalid role or presence")
        item = OperatorProfile.objects.create(
            external_id=external_id,
            display_name=display_name, email=_str_field(data, "email"),
            role=role, presence=presence,
            max_active_dialogs=data.get("max_active_dialogs", data.get("capacity", 3)),
            auto_assign=_bool_field(data, "auto_assign", True),
            is_active=_bool_field(data, "is_active", True),
            photo_url=_normalize_photo_url(_str_field(data, "photo_url"))
            if _str_field(data, "photo_url")
            else "",
            skill_tags=_json_field(data, "skill_tags", list, []) if "skill_tags" in data else [],
        )
        if "department_id" in data and "department_ids" not in data:
            data = {**data, "department_ids": [data["department_id"]] if data["department_id"] else []}
        _set_departments(item, data)
        return JsonResponse({"ok": True, "operator": _operator_dict(item)}, status=201)
    except (OnlineChatApiError, ValueError) as exc:
        return _error(OnlineChatApiError(str(exc)))


_PHOTO_DATA_RE = re.compile(
    r"^data:(image/(?:png|jpe?g|webp))?(?:;charset=[^;,]*)?(;base64)?,(.+)$",
    re.DOTALL | re.IGNORECASE,
)
_PHOTO_MAX_BYTES = 500 * 1024
_PHOTO_MAX_SIDE = 256


def _decode_photo_data_url(raw: str) -> tuple[bytes, str] | None:
    match = _PHOTO_DATA_RE.match((raw or "").strip())
    if not match:
        return None
    content_type = (match.group(1) or "image/jpeg").lower()
    if content_type == "image/jpg":
        content_type = "image/jpeg"
    payload = match.group(3) or ""
    try:
        body = base64.b64decode(payload, validate=False)
    except (ValueError, binascii.Error):
        return None
    if not body:
        return None
    return body, content_type


def _photo_response_headers(response: HttpResponse) -> HttpResponse:
    response["Access-Control-Allow-Origin"] = "*"
    response["Cross-Origin-Resource-Policy"] = "cross-origin"
    response["Cache-Control"] = "private, max-age=300"
    return response


def _operator_for_request(request: HttpRequest, *, display_name: str = "") -> OperatorProfile | None:
    username = ""
    if getattr(request.user, "is_authenticated", False):
        username = (request.user.get_username() or "").strip()
    if username:
        match = OperatorProfile.objects.filter(
            external_id=username, is_active=True
        ).first()
        if match:
            return match
        match = OperatorProfile.objects.filter(
            display_name=username, is_active=True
        ).first()
        if match:
            return match
    name = (display_name or "").strip()
    if name:
        return OperatorProfile.objects.filter(display_name=name, is_active=True).first()
    return None


def _normalize_photo_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value[:2000]
    decoded = _decode_photo_data_url(value)
    if not decoded:
        raise OnlineChatApiError("photo_url must be a data:image or http(s) URL")
    body, content_type = decoded
    if len(body) > _PHOTO_MAX_BYTES:
        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover
            raise OnlineChatApiError("photo is too large") from exc
        image = Image.open(BytesIO(body))
        image = image.convert("RGB")
        image.thumbnail((_PHOTO_MAX_SIDE, _PHOTO_MAX_SIDE))
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        body = buffer.getvalue()
        content_type = "image/jpeg"
    encoded = base64.b64encode(body).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


@csrf_exempt
@require_http_methods(["GET"])
@_chat_permissions(PERM_SUFLER_CHAT, PERM_CC_ADMIN)
def operator_me(request: HttpRequest) -> HttpResponse:
    display_name = (request.GET.get("display_name") or "").strip()
    operator = _operator_for_request(request, display_name=display_name)
    if operator is None:
        return JsonResponse(
            {"ok": False, "error": "not_found", "detail": "Профиль оператора не найден"},
            status=404,
        )
    return JsonResponse({"ok": True, "operator": _operator_dict(operator)})


@csrf_exempt
@require_http_methods(["PATCH"])
@_chat_permissions(PERM_SUFLER_CHAT, PERM_CC_ADMIN)
def operator_me_photo(request: HttpRequest) -> HttpResponse:
    try:
        data = _json_body(request)
        display_name = _str_field(data, "display_name")
        operator = _operator_for_request(request, display_name=display_name)
        if operator is None:
            return JsonResponse(
                {"ok": False, "error": "not_found", "detail": "Профиль оператора не найден"},
                status=404,
            )
        operator.photo_url = _normalize_photo_url(_str_field(data, "photo_url"))
        operator.save(update_fields=["photo_url", "updated_at"])
        return JsonResponse({"ok": True, "operator": _operator_dict(operator)})
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["GET"])
def operator_photo(request: HttpRequest, item_id: str) -> HttpResponse:
    """Public operator photo for the client widget (avoids huge data URLs in WS payloads)."""
    operator = get_object_or_404(OperatorProfile, pk=item_id)
    raw = (operator.photo_url or "").strip()
    if not raw:
        return HttpResponse(status=404)
    if raw.startswith("data:"):
        decoded = _decode_photo_data_url(raw)
        if not decoded:
            return HttpResponse(status=404)
        body, content_type = decoded
        return _photo_response_headers(HttpResponse(body, content_type=content_type))
    if raw.startswith("http://") or raw.startswith("https://"):
        return _photo_response_headers(redirect(raw))
    return HttpResponse(status=404)


@csrf_exempt
@require_http_methods(["PATCH"])
@_chat_permissions(PERM_CC_ADMIN)
def operator_detail(request: HttpRequest, item_id: str) -> HttpResponse:
    from online_chat.routing_services import run_assignments, update_operator_presence

    item = get_object_or_404(OperatorProfile, pk=item_id)
    try:
        data = _json_body(request)
        if "name" in data and "display_name" not in data:
            data = {**data, "display_name": data["name"]}
        if "username" in data and "external_id" not in data:
            data = {**data, "external_id": data["username"]}
        presence_value = _str_field(data, "presence") if "presence" in data else ""
        for field in ("external_id", "display_name", "email", "role"):
            if field in data:
                setattr(item, field, _str_field(data, field))
        if item.role not in OperatorProfile.Role.values:
            raise OnlineChatApiError("invalid role or presence")
        capacity_changed = "max_active_dialogs" in data or "capacity" in data
        if "max_active_dialogs" in data:
            item.max_active_dialogs = _int_field(data, "max_active_dialogs")
        elif "capacity" in data:
            item.max_active_dialogs = _int_field(data, "capacity")
        auto_assign_changed = "auto_assign" in data
        for field in ("auto_assign", "is_active"):
            if field in data:
                setattr(item, field, _bool_field(data, field))
        if "photo_url" in data:
            raw_photo = _str_field(data, "photo_url")
            item.photo_url = _normalize_photo_url(raw_photo) if raw_photo else ""
        if "skill_tags" in data:
            tags = _json_field(data, "skill_tags", list, [])
            if any(not isinstance(value, str) for value in tags):
                raise OnlineChatApiError("skill_tags must be a list of strings")
            item.skill_tags = [value.strip() for value in tags if value.strip()]
        item.save()
        if "department_id" in data and "department_ids" not in data:
            data = {**data, "department_ids": [data["department_id"]] if data["department_id"] else []}
        _set_departments(item, data)
        if presence_value:
            item = update_operator_presence(item, presence_value)
        elif (
            (capacity_changed or auto_assign_changed)
            and item.auto_assign
            and item.presence == OperatorProfile.Presence.ONLINE
            and item.is_active
        ):
            for department in item.departments.filter(is_active=True):
                run_assignments(department=department)
        return JsonResponse({"ok": True, "operator": _operator_dict(item)})
    except (OnlineChatApiError, ValueError) as exc:
        return _error(OnlineChatApiError(str(exc)))


@csrf_exempt
@require_http_methods(["POST"])
@_chat_permissions(PERM_SUFLER_CHAT, PERM_CC_ADMIN)
def operator_presence(request: HttpRequest, item_id: str) -> HttpResponse:
    item = get_object_or_404(OperatorProfile, pk=item_id)
    try:
        item = update_operator_presence(item, _str_field(_json_body(request), "presence"))
        return JsonResponse({"ok": True, "operator": _operator_dict(item)})
    except (OnlineChatApiError, ValueError) as exc:
        return _error(OnlineChatApiError(str(exc)))


def _placement_values(data: Mapping[str, Any], item: WidgetPlacement | None = None) -> WidgetPlacement:
    item = item or WidgetPlacement()
    if "code" in data and "widget_id" not in data:
        data = {**data, "widget_id": data["code"]}
    for field in (
        "widget_id", "name", "site_url", "welcome_message", "queue_message", "offline_message"
    ):
        if field in data:
            setattr(item, field, _str_field(data, field))
    for field, expected, default in (
        ("allowed_domains", list, []), ("theme", dict, {}),
        ("config", dict, {}), ("form_fields", list, []),
    ):
        if field in data:
            setattr(item, field, _json_field(data, field, expected, default))
    if "form_fields" in data:
        item.form_fields = normalize_form_fields(
            item.form_fields,
            require_phone=False,
        )
    if "theme_accent" in data:
        theme = dict(item.theme or {})
        theme["accent"] = _str_field(data, "theme_accent")
        item.theme = theme
    for field in ("is_active", "require_phone"):
        if field in data:
            setattr(item, field, _bool_field(data, field))
    if "department_id" in data:
        item.department = (
            get_object_or_404(Department, pk=data["department_id"])
            if data["department_id"] else None
        )
    if not item.name:
        raise OnlineChatApiError("name is required")
    if not item.widget_id:
        item.widget_id = f"widget-{uuid.uuid4().hex[:8]}"
    item.save()
    return item


@csrf_exempt
@require_http_methods(["GET", "POST"])
@_chat_permissions(PERM_CC_ADMIN)
def placements_collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        items = [_placement_dict(item) for item in WidgetPlacement.objects.all()]
        return JsonResponse({"ok": True, "items": items, "count": len(items)})
    try:
        item = _placement_values(_json_body(request))
        return JsonResponse({"ok": True, "placement": _placement_dict(item)}, status=201)
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["PATCH", "DELETE"])
@_chat_permissions(PERM_CC_ADMIN)
def placement_detail(request: HttpRequest, item_id: str) -> HttpResponse:
    item = get_object_or_404(WidgetPlacement, pk=item_id)
    if request.method == "DELETE":
        item.delete()
        return JsonResponse({"ok": True})
    try:
        item = _placement_values(_json_body(request), item)
        return JsonResponse({"ok": True, "placement": _placement_dict(item)})
    except OnlineChatApiError as exc:
        return _error(exc)


def _channel_values(data: Mapping[str, Any], item: ChannelConnection | None = None) -> ChannelConnection:
    item = item or ChannelConnection()
    if "kind" in data and "channel" not in data:
        channel = "api" if data["kind"] == "external" else data["kind"]
        data = {**data, "channel": channel}
    if "account" in data and "external_id" not in data:
        data = {**data, "external_id": data["account"]}
    for field in ("channel", "name", "external_id", "health_status"):
        if field in data:
            setattr(item, field, _str_field(data, field))
    if item.channel not in ChannelConnection.Channel.values:
        raise OnlineChatApiError("invalid channel")
    if "config" in data:
        item.config = _json_field(data, "config", dict, {})
    if "form_fields" in data:
        config = dict(item.config or {})
        config["form_fields"] = normalize_form_fields(
            data.get("form_fields"),
            require_phone=False,
        )
        item.config = config
    if "endpoint" in data:
        config = dict(item.config or {})
        config["endpoint"] = _str_field(data, "endpoint")
        item.config = config
    if "is_active" in data:
        item.is_active = _bool_field(data, "is_active")
    if "department_id" in data:
        item.department = (
            get_object_or_404(Department, pk=data["department_id"])
            if data["department_id"] else None
        )
    if not item.name:
        raise OnlineChatApiError("name is required")
    item.save()
    return item


@csrf_exempt
@require_http_methods(["GET", "POST"])
@_chat_permissions(PERM_CC_ADMIN)
def channels_collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        items = [_channel_dict(item) for item in ChannelConnection.objects.all()]
        return JsonResponse({"ok": True, "items": items, "count": len(items)})
    try:
        item = _channel_values(_json_body(request))
        return JsonResponse({"ok": True, "channel": _channel_dict(item)}, status=201)
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["PATCH"])
@_chat_permissions(PERM_CC_ADMIN)
def channel_detail(request: HttpRequest, item_id: str) -> HttpResponse:
    try:
        item = _channel_values(_json_body(request), get_object_or_404(ChannelConnection, pk=item_id))
        return JsonResponse({"ok": True, "channel": _channel_dict(item)})
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
@_chat_permissions(PERM_CC_ADMIN)
def channel_health_check(request: HttpRequest, item_id: str) -> HttpResponse:

    from online_chat.channel_delivery import probe_channel

    item = get_object_or_404(ChannelConnection, pk=item_id)
    status, detail = probe_channel(item)
    item.health_status = status
    item.last_health_check_at = timezone.now()
    item.save(update_fields=["health_status", "last_health_check_at", "updated_at"])
    return JsonResponse(
        {
            "ok": True,
            "channel": _channel_dict(item),
            "health_status": status,
            "detail": detail,
        }
    )


def _rule_values(data: Mapping[str, Any], item: RoutingRule | None = None) -> RoutingRule:
    item = item or RoutingRule()
    if "channel_id" in data and "channel" not in data:
        channel_id = data.get("channel_id")
        connection = (
            get_object_or_404(ChannelConnection, pk=channel_id) if channel_id else None
        )
        data = {**data, "channel": connection.channel if connection else ""}
    for field in ("name", "channel"):
        if field in data:
            setattr(item, field, _str_field(data, field))
    if "priority" in data:
        item.priority = _int_field(data, "priority")
    if "conditions" in data:
        item.conditions = _json_field(data, "conditions", dict, {})
    if "max_load" in data:
        conditions = dict(item.conditions or {})
        conditions["max_load"] = _int_field(data, "max_load")
        item.conditions = conditions
    if "is_active" in data:
        item.is_active = _bool_field(data, "is_active")
    if "department_id" in data:
        item.department = get_object_or_404(Department, pk=data["department_id"])
    if "placement_id" in data:
        item.placement = (
            get_object_or_404(WidgetPlacement, pk=data["placement_id"])
            if data["placement_id"] else None
        )
    if not item.name or not item.department_id:
        raise OnlineChatApiError("name and department_id are required")
    item.save()
    return item


@csrf_exempt
@require_http_methods(["GET", "POST"])
@_chat_permissions(PERM_CC_ADMIN)
def routing_rules_collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        items = [_rule_dict(item) for item in RoutingRule.objects.all()]
        return JsonResponse({"ok": True, "items": items, "count": len(items)})
    try:
        item = _rule_values(_json_body(request))
        return JsonResponse({"ok": True, "routing_rule": _rule_dict(item)}, status=201)
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["PATCH", "DELETE"])
@_chat_permissions(PERM_CC_ADMIN)
def routing_rule_detail(request: HttpRequest, item_id: str) -> HttpResponse:
    item = get_object_or_404(RoutingRule, pk=item_id)
    if request.method == "DELETE":
        item.delete()
        return JsonResponse({"ok": True})
    try:
        item = _rule_values(_json_body(request), item)
        return JsonResponse({"ok": True, "routing_rule": _rule_dict(item)})
    except OnlineChatApiError as exc:
        return _error(exc)


@require_http_methods(["GET"])
@_chat_permissions(PERM_CC_REPORTS, PERM_CC_ADMIN)
def supervisor_overview(request: HttpRequest) -> HttpResponse:
    from datetime import timedelta


    statuses = {
        row["status"]: row["c"]
        for row in Dialog.objects.values("status").annotate(c=Count("id"))
    }
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    waiting_all = list(
        Dialog.objects.filter(status=Dialog.Status.WAITING).only(
            "id", "created_at", "outcome", "client_online"
        )
    )
    waiting_offline = [
        item
        for item in waiting_all
        if item.outcome == Dialog.Outcome.OFFLINE or item.client_online is False
    ]
    waiting_online = [item for item in waiting_all if item not in waiting_offline]

    def _avg_wait(rows: list) -> int:
        if not rows:
            return 0
        secs = [max(0, int((now - item.created_at).total_seconds())) for item in rows]
        return round(sum(secs) / len(secs))

    average_wait_online = _avg_wait(waiting_online)
    average_wait_offline = _avg_wait(waiting_offline)
    average_wait = _avg_wait(waiting_all)
    sla_window = timedelta(seconds=ServiceLevelSettings.get_solo().first_response_seconds)
    answered = list(
        Dialog.objects.filter(
            first_response_at__isnull=False,
            created_at__gte=today_start,
        ).only("created_at", "first_response_at")[:2000]
    )
    answered_count = len(answered)
    within_sla = sum(
        1
        for item in answered
        if item.first_response_at and item.first_response_at - item.created_at <= sla_window
    )
    sla_percent = round(within_sla / answered_count * 100, 1) if answered_count else None

    operators = []
    for item in OperatorProfile.objects.prefetch_related("departments"):
        data = _operator_dict(item)
        active_qs = Dialog.objects.filter(operator=item, status=Dialog.Status.ACTIVE)
        active_dialogs = active_qs.count()
        closed_today_qs = Dialog.objects.filter(
            operator=item,
            status=Dialog.Status.CLOSED,
            closed_at__gte=today_start,
        )
        closed_today = closed_today_qs.count()
        answered_today = list(
            Dialog.objects.filter(
                operator=item,
                first_response_at__isnull=False,
                first_response_at__gte=today_start,
            ).only("created_at", "first_response_at", "accepted_at", "closed_at")[:500]
        )
        response_secs = [
            (row.first_response_at - row.created_at).total_seconds()
            for row in answered_today
            if row.first_response_at and row.created_at
        ]
        avg_first_response = (
            round(sum(response_secs) / len(response_secs)) if response_secs else None
        )
        # Time in dialogs today: sum of (closed_at|now - accepted_at) for today's handled.
        time_in_dialogs = 0
        for row in Dialog.objects.filter(operator=item).filter(
            Q(status=Dialog.Status.ACTIVE)
            | Q(status=Dialog.Status.CLOSED, closed_at__gte=today_start)
        ).only("accepted_at", "closed_at", "created_at", "status")[:500]:
            start = row.accepted_at or row.created_at
            end = row.closed_at if row.status == Dialog.Status.CLOSED and row.closed_at else now
            if start and end and end >= start:
                # Clip to today.
                clipped_start = start if start >= today_start else today_start
                time_in_dialogs += max(0, int((end - clipped_start).total_seconds()))
        avg_dialog_seconds = (
            round(time_in_dialogs / closed_today) if closed_today else None
        )
        channel_rows = (
            Dialog.objects.filter(operator=item, status=Dialog.Status.ACTIVE)
            .values("channel")
            .annotate(count=Count("id"))
        )
        channels_breakdown = {
            (row["channel"] or "widget"): row["count"] for row in channel_rows
        }
        data["active_dialogs"] = active_dialogs
        data["load"] = active_dialogs
        data["closed_today"] = closed_today
        data["avg_first_response_seconds"] = avg_first_response
        data["time_in_dialogs_seconds"] = time_in_dialogs
        data["avg_dialog_seconds"] = avg_dialog_seconds
        data["channels_breakdown"] = channels_breakdown
        data["photo_url"] = getattr(item, "photo_url", "") or ""
        data["skill_tags"] = list(getattr(item, "skill_tags", None) or [])
        operators.append(data)

    queues = []
    for item in Department.objects.filter(is_active=True):
        dept_waiting_online = item.dialogs.filter(
            status=Dialog.Status.WAITING, client_online=True
        ).exclude(outcome=Dialog.Outcome.OFFLINE)
        dept_waiting_offline = item.dialogs.filter(status=Dialog.Status.WAITING).filter(
            Q(outcome=Dialog.Outcome.OFFLINE) | Q(client_online=False)
        )
        dept_waiting = list(item.dialogs.filter(status=Dialog.Status.WAITING).only("created_at"))
        longest = (
            max(int((now - d.created_at).total_seconds()) for d in dept_waiting)
            if dept_waiting
            else 0
        )
        queues.append(
            {
                "id": str(item.id),
                "department_id": str(item.id),
                "department_name": item.name,
                "name": item.name,
                "department": item.name,
                "waiting": len(dept_waiting),
                "waiting_online": dept_waiting_online.count(),
                "waiting_offline": dept_waiting_offline.count(),
                "active": item.dialogs.filter(status=Dialog.Status.ACTIVE).count(),
                "longest_wait_seconds": longest,
            }
        )

    return JsonResponse(
        {
            "ok": True,
            "kpis": {
                "waiting": statuses.get(Dialog.Status.WAITING, 0),
                "waiting_online": len(waiting_online),
                "waiting_offline": len(waiting_offline),
                "active": statuses.get(Dialog.Status.ACTIVE, 0),
                "closed": statuses.get(Dialog.Status.CLOSED, 0),
                "closed_today": Dialog.objects.filter(
                    status=Dialog.Status.CLOSED, closed_at__gte=today_start
                ).count(),
                "online_operators": OperatorProfile.objects.filter(
                    is_active=True, presence=OperatorProfile.Presence.ONLINE
                ).count(),
                "average_wait_seconds": average_wait,
                "average_wait_online_seconds": average_wait_online,
                "average_wait_offline_seconds": average_wait_offline,
                "sla_percent": sla_percent,
            },
            "operators": operators,
            "queues": queues,
        }
    )


@require_http_methods(["GET"])
@_chat_permissions(PERM_CC_REPORTS, PERM_CC_ADMIN)
def analytics(request: HttpRequest) -> HttpResponse:
    from datetime import datetime, timedelta

    period = (request.GET.get("period") or "7d").lower()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    if date_from or date_to:
        try:
            start = (
                datetime.fromisoformat(date_from).replace(tzinfo=timezone.get_current_timezone())
                if date_from
                else timezone.now() - timedelta(days=30)
            )
            end = (
                datetime.fromisoformat(date_to).replace(
                    hour=23, minute=59, second=59, tzinfo=timezone.get_current_timezone()
                )
                if date_to
                else timezone.now()
            )
        except ValueError:
            return JsonResponse(
                {"ok": False, "error": "date_from/date_to must be ISO dates (YYYY-MM-DD)"},
                status=400,
            )
        dialogs = Dialog.objects.filter(created_at__gte=start, created_at__lte=end)
        period_label = f"{date_from or '…'}…{date_to or '…'}"
    else:
        days = {
            "today": 1, "day": 1, "7d": 7, "week": 7,
            "30d": 30, "month": 30, "90d": 90,
        }.get(period, 7)
        start = timezone.now() - timedelta(days=days)
        dialogs = Dialog.objects.filter(created_at__gte=start)
        period_label = period
    closed = dialogs.filter(status=Dialog.Status.CLOSED)
    feedback = DialogFeedback.objects.filter(dialog__in=dialogs).aggregate(avg=Avg("rating"))
    response_seconds = [
        (item.first_response_at - item.created_at).total_seconds()
        for item in dialogs.exclude(first_response_at=None)
    ]
    return JsonResponse({
        "ok": True, "period": period_label, "from": start.isoformat(),
        "kpis": {
            "dialogs": dialogs.count(), "closed": closed.count(),
            "waiting": dialogs.filter(status=Dialog.Status.WAITING).count(),
            "resolution_rate": round(closed.count() / dialogs.count() * 100, 2) if dialogs.count() else 0,
            "average_first_response_seconds": (
                round(sum(response_seconds) / len(response_seconds), 2) if response_seconds else None
            ),
            "average_rating": feedback["avg"],
        },
    })


@require_http_methods(["GET"])
@_chat_permissions(PERM_CC_ADMIN)
def ad_pending_operators(request: HttpRequest) -> HttpResponse:
    """Local stub: operators that appeared in AD and need chat settings."""
    existing = set(OperatorProfile.objects.values_list("external_id", flat=True))
    stub = [
        {
            "external_id": "ad.ivanova.kk",
            "display_name": "Иванова К.К.",
            "email": "ivanova.kk@belarusbank.by",
            "ad_role": "operator_cc",
            "detected_at": timezone.now().isoformat(),
            "needs": ["limits", "photo", "chat_login"],
        },
        {
            "external_id": "ad.petrov.ss",
            "display_name": "Петров С.С.",
            "email": "petrov.ss@belarusbank.by",
            "ad_role": "operator_cc",
            "detected_at": timezone.now().isoformat(),
            "needs": ["limits", "photo", "skill_tags"],
        },
    ]
    pending = [item for item in stub if item["external_id"] not in existing]
    return JsonResponse({"ok": True, "items": pending, "count": len(pending)})


@require_http_methods(["GET"])
def client_history(request: HttpRequest) -> HttpResponse:
    dialog_id = (request.GET.get("dialog_id") or "").strip()
    phone = (request.GET.get("phone") or "").strip()
    external_id = (request.GET.get("external_id") or "").strip()
    current = None
    first_name = ""
    last_name = ""
    if dialog_id:
        current = get_object_or_404(Dialog, pk=dialog_id)
        phone = phone or current.client_phone
        external_id = external_id or current.client_external_id
        first_name = current.client_first_name
        last_name = current.client_last_name
    query = history_identity_query(
        phone=phone,
        external_id=external_id,
        first_name=first_name,
        last_name=last_name,
    )
    if not query:
        return JsonResponse({"ok": True, "items": [], "count": 0, "summary": ""})
    dialogs = (
        Dialog.objects.filter(query)
        .prefetch_related("messages")
        .order_by("-created_at")[:100]
    )
    items = [
        {
            "id": str(item.id),
            "channel": item.channel,
            "channel_label": channel_label(item.channel),
            "status": item.status,
            "outcome": item.outcome,
            "topic": item.close_topic,
            "operator_name": item.operator_name,
            "preview": item.preview,
            "created_at": item.created_at.isoformat(),
            "closed_at": item.closed_at.isoformat() if item.closed_at else None,
            "message_count": len(item.messages.all()),
        }
        for item in dialogs
    ]
    previous_dialogs = [
        item for item in dialogs if current is None or item.id != current.id
    ]
    previous_items = [
        item for item in items if current is None or item["id"] != str(current.id)
    ]
    current_channel = channel_label(current.channel) if current else (
        items[0]["channel_label"] if items else ""
    )

    from online_chat.summary_service import build_history_summaries

    packed = build_history_summaries(list(previous_dialogs))
    # previous_items is the source of truth for "first vs repeat".
    is_first = len(previous_items) == 0
    if is_first and current_channel:
        packed["detailed_summary"] = (
            f"Первое обращение клиента.\nКанал: {current_channel}."
        )
        packed["summary"] = "Первое обращение клиента."
    blocks = packed.get("detailed_blocks") or []
    for block in blocks:
        raw_channel = block.get("channel") or ""
        block["channel"] = channel_label(raw_channel) if raw_channel else "—"
    if blocks:
        packed["detailed_summary"] = "\n\n".join(
            (
                f"{block['date_label']}\n"
                f"Тема: {block['topic']}\n"
                f"{block['essence']}\n"
                f"Канал: {block['channel']} · Оператор: {block['operator_name']}"
            )
            for block in blocks
        )
    return JsonResponse(
        {
            "ok": True,
            "items": items,
            "count": len(items),
            "previous_count": len(previous_items),
            "summary": packed["summary"],
            "detailed_summary": packed["detailed_summary"],
            "summary_topics": packed.get("summary_topics") or [],
            "detailed_blocks": blocks,
            "is_first": is_first,
            "repeat_hint": "",
        }
    )


def _serialize_internal_message(item: InternalMessage) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "sender_id": str(item.sender_id),
        "sender_name": item.sender.display_name,
        "recipient_id": str(item.recipient_id),
        "recipient_name": item.recipient.display_name,
        "dialog_id": str(item.dialog_id) if item.dialog_id else None,
        "text": item.text,
        "read_at": item.read_at.isoformat() if item.read_at else None,
        "created_at": item.created_at.isoformat(),
    }


def _resolve_operator_profile(
    data: Mapping[str, Any],
    *,
    id_key: str,
    name_key: str,
) -> OperatorProfile:
    operator_id = data.get(id_key)
    if operator_id:
        return get_object_or_404(OperatorProfile, pk=operator_id)
    name = _str_field(data, name_key)
    if not name:
        raise OnlineChatApiError(f"{id_key} or {name_key} is required")
    profile = OperatorProfile.objects.filter(display_name=name, is_active=True).first()
    if profile:
        return profile
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower() or "operator"
    return OperatorProfile.objects.create(
        external_id=f"arm-{slug}-{uuid.uuid4().hex[:8]}",
        display_name=name,
        presence=OperatorProfile.Presence.ONLINE,
        role=OperatorProfile.Role.OPERATOR,
        is_active=True,
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
@_chat_permissions(PERM_SUFLER_CHAT, PERM_CC_ADMIN)
def internal_messages_collection(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        qs = InternalMessage.objects.select_related("sender", "recipient")
        operator_id = (request.GET.get("operator_id") or "").strip()
        peer_id = (request.GET.get("peer_id") or "").strip()
        operator_name = (request.GET.get("operator_name") or "").strip()
        if operator_name and not operator_id:
            profile = OperatorProfile.objects.filter(
                display_name=operator_name, is_active=True
            ).first()
            if profile:
                operator_id = str(profile.id)
        # Scope to an operator when name/id was provided (avoid leaking all threads).
        if (operator_name or request.GET.get("operator_id")) and not operator_id:
            return JsonResponse(
                {
                    "ok": True,
                    "items": [],
                    "count": 0,
                    "unread_count": 0,
                    "operator_id": None,
                }
            )
        if operator_id:
            qs = qs.filter(Q(sender_id=operator_id) | Q(recipient_id=operator_id))
        if peer_id and operator_id:
            qs = qs.filter(
                (Q(sender_id=operator_id) & Q(recipient_id=peer_id))
                | (Q(sender_id=peer_id) & Q(recipient_id=operator_id))
            )
        elif peer_id:
            qs = qs.filter(Q(sender_id=peer_id) | Q(recipient_id=peer_id))
        # Chronological for chat UI (model default is newest-first).
        items = [
            _serialize_internal_message(item)
            for item in qs.order_by("created_at")[:500]
        ]
        unread_count = 0
        if operator_id:
            unread_count = InternalMessage.objects.filter(
                recipient_id=operator_id, read_at__isnull=True
            ).count()
        return JsonResponse(
            {
                "ok": True,
                "items": items,
                "count": len(items),
                "unread_count": unread_count,
                "operator_id": operator_id or None,
            }
        )
    try:
        data = _json_body(request)
        text = _str_field(data, "text")
        if not text:
            raise OnlineChatApiError("text is required")
        sender = _resolve_operator_profile(data, id_key="sender_id", name_key="sender_name")
        recipient = _resolve_operator_profile(
            data, id_key="recipient_id", name_key="recipient_name"
        )
        if sender.id == recipient.id:
            raise OnlineChatApiError("cannot send message to yourself")
        item = InternalMessage.objects.create(
            sender=sender,
            recipient=recipient,
            dialog=(
                get_object_or_404(Dialog, pk=data["dialog_id"]) if data.get("dialog_id") else None
            ),
            text=text,
        )
        payload = _serialize_internal_message(item)
        broadcast(ARM_GROUP, "internal.message.created", payload)
        return JsonResponse({"ok": True, "message": payload}, status=201)
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
@_chat_permissions(PERM_SUFLER_CHAT, PERM_CC_ADMIN)
def internal_messages_mark_read(request: HttpRequest) -> HttpResponse:
    try:
        from django.utils import timezone

        data = _json_body(request)
        recipient = _resolve_operator_profile(
            data, id_key="operator_id", name_key="operator_name"
        )
        qs = InternalMessage.objects.filter(recipient=recipient, read_at__isnull=True)
        peer_id = data.get("peer_id")
        if peer_id:
            qs = qs.filter(sender_id=peer_id)
        updated = qs.update(read_at=timezone.now())
        unread_count = InternalMessage.objects.filter(
            recipient=recipient, read_at__isnull=True
        ).count()
        broadcast(
            ARM_GROUP,
            "internal.messages.read",
            {
                "operator_id": str(recipient.id),
                "peer_id": str(peer_id) if peer_id else None,
                "updated": updated,
                "unread_count": unread_count,
            },
        )
        return JsonResponse(
            {"ok": True, "updated": updated, "unread_count": unread_count}
        )
    except OnlineChatApiError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
@_chat_permissions(PERM_CC_ADMIN)
def routing_run(request: HttpRequest) -> HttpResponse:
    assigned = run_assignments()
    return JsonResponse({
        "ok": True, "assigned": len(assigned),
        "dialog_ids": [str(item.id) for item in assigned],
    })


@require_http_methods(["GET"])
def widget_config(request: HttpRequest, widget_id: str) -> HttpResponse:
    item = get_object_or_404(WidgetPlacement, widget_id=widget_id, is_active=True)
    source = request.headers.get("Origin") or request.headers.get("Referer") or ""
    source_host = (urlparse(source).hostname or "").casefold()
    allowed = {
        str(domain).strip().casefold()
        for domain in item.allowed_domains
        if str(domain).strip()
    }
    if allowed and source_host and source_host not in allowed:
        return JsonResponse(
            {"ok": False, "error": "origin_not_allowed"},
            status=403,
        )
    return JsonResponse({"ok": True, "config": _placement_dict(item, public=True)})


def _debug_only() -> JsonResponse | None:
    if not settings.DEBUG:
        return JsonResponse({"detail": "Not found"}, status=404)
    return None


_SEED_OPERATOR_NAMES = (
    "Иванов И.И.",
    "Петрова А.С.",
    "Сидоров М.В.",
    "Козлова Е.Н.",
    "Морозов Д.А.",
    "Васильева Н.П.",
    "Новиков А.В.",
    "Фёдорова О.Л.",
    "Смирнов К.С.",
    "Орлова Т.М.",
)


def _seed_operator_name(index: int) -> str:
    if index < len(_SEED_OPERATOR_NAMES):
        return _SEED_OPERATOR_NAMES[index]
    return f"Оператор {index + 1}"


def _seed_client_phone(index: int) -> str:
    # Matches widget.js sim_client phone pattern: +375 29 + last 7 of (1000000 + N)
    return f"+375 29 {str(1000000 + index + 1)[-7:]}"


@csrf_exempt
@require_http_methods(["POST"])
def dev_reset(request: HttpRequest) -> HttpResponse:
    denied = _debug_only()
    if denied:
        return denied
    Dialog.objects.all().delete()
    RoutingRule.objects.all().delete()
    BotConfiguration.objects.all().delete()
    WidgetPlacement.objects.all().delete()
    ChannelConnection.objects.all().delete()
    OperatorProfile.objects.all().delete()
    Department.objects.all().delete()
    return JsonResponse({"ok": True, "summary": {"reset": True}})


@csrf_exempt
@require_http_methods(["POST"])
def dev_seed(request: HttpRequest) -> HttpResponse:
    denied = _debug_only()
    if denied:
        return denied
    try:
        data = _json_body(request)
        operator_count = int(data.get("operators", 3))
        client_count = int(data.get("clients", 10))
        message_count = int(data.get("messages_per_dialog", 1))
        should_assign = _bool_field(data, "auto_assign", True)
        should_reset = _bool_field(data, "reset", False)
        if not 0 <= operator_count <= 100 or not 0 <= client_count <= 1000:
            raise OnlineChatApiError("seed counts are out of range")
        if should_reset:
            Dialog.objects.all().delete()
            OperatorProfile.objects.filter(external_id__startswith="dev-operator-").delete()
            WidgetPlacement.objects.filter(
                widget_id__in=("dev-widget", "site-belarusbank")
            ).delete()
            ChannelConnection.objects.filter(external_id__startswith="dev-").delete()
            RoutingRule.objects.filter(name__startswith="Dev ").delete()
            BotConfiguration.objects.filter(name__startswith="Dev ").delete()
            Department.objects.filter(code="dev-support").delete()
        department, _ = Department.objects.update_or_create(
            code="dev-support",
            defaults={
                "name": "Поддержка КЦ",
                "priority": 10,
                "description": "Отдел для локальной симуляции онлайн-чата",
                "max_queue_size": 200,
                "is_active": True,
            },
        )
        placement, _ = WidgetPlacement.objects.update_or_create(
            widget_id="site-belarusbank",
            defaults={
                "name": "Сайт Беларусбанка",
                "department": department,
                "is_active": True,
                "welcome_message": "Здравствуйте! Чем можем помочь?",
                "queue_message": "Ожидайте ответа оператора…",
                "offline_message": "Сейчас операторы недоступны. Оставьте сообщение — ответим позже.",
                "require_phone": True,
                "allowed_domains": ["localhost", "127.0.0.1"],
                "theme": {"accent": "#2E7D52"},
                "form_fields": [
                    {"key": "name", "label": "Имя", "required": True, "type": "text"},
                    {"key": "last_name", "label": "Фамилия", "required": False, "type": "text"},
                    {"key": "phone", "label": "Телефон", "required": True, "type": "tel"},
                ],
            },
        )
        ChannelConnection.objects.update_or_create(
            channel=ChannelConnection.Channel.WIDGET,
            external_id="dev-widget-site",
            defaults={
                "name": "Виджет сайта",
                "department": department,
                "is_active": True,
                "health_status": "ok",
            },
        )
        ChannelConnection.objects.update_or_create(
            channel=ChannelConnection.Channel.TELEGRAM,
            external_id="dev-telegram",
            defaults={
                "name": "Telegram (demo)",
                "department": department,
                "is_active": True,
                "health_status": "not_configured",
                "config": {"note": "Токен задаётся через TELEGRAM_BOT_TOKEN"},
            },
        )
        RoutingRule.objects.update_or_create(
            name="Dev widget → Поддержка КЦ",
            defaults={
                "priority": 10,
                "channel": "widget",
                "placement": placement,
                "department": department,
                "conditions": {"max_load": 5},
                "is_active": True,
            },
        )
        RoutingRule.objects.update_or_create(
            name="Dev telegram → Поддержка КЦ",
            defaults={
                "priority": 10,
                "channel": "telegram",
                "placement": None,
                "department": department,
                "conditions": {"max_load": 5},
                "is_active": True,
            },
        )
        BotConfiguration.objects.update_or_create(
            name="Dev бот FAQ",
            department=department,
            defaults={
                "is_active": False,
                "welcome_message": "Здравствуйте! Я виртуальный помощник. Напишите «карта» или «вклад».",
                "fallback_message": "Передаю обращение оператору.",
                "handoff_message": "Подключаю оператора. Пожалуйста, ожидайте.",
                "trigger_responses": {
                    "карт": "Уточните, пожалуйста, вопрос по карте.",
                    "вклад": "Какой вклад вас интересует?",
                },
                "max_bot_turns": 3,
            },
        )
        operators = []
        for index in range(operator_count):
            display_name = _seed_operator_name(index)
            operator, _ = OperatorProfile.objects.update_or_create(
                external_id=f"dev-operator-{index + 1}",
                defaults={
                    "display_name": display_name,
                    "email": f"operator{index + 1}@dev.local",
                    "presence": OperatorProfile.Presence.ONLINE,
                    "auto_assign": should_assign,
                    "max_active_dialogs": 3,
                    "is_active": True,
                    "role": OperatorProfile.Role.OPERATOR,
                },
            )
            operator.departments.set([department])
            operators.append(operator)
        supervisor, _ = OperatorProfile.objects.update_or_create(
            external_id="dev-supervisor-1",
            defaults={
                "display_name": "Козлова Е.В.",
                "email": "supervisor@dev.local",
                "presence": OperatorProfile.Presence.ONLINE,
                "auto_assign": False,
                "max_active_dialogs": 99,
                "is_active": True,
                "role": OperatorProfile.Role.SUPERVISOR,
            },
        )
        supervisor.departments.set([department])
        BaseMessage.objects.get_or_create(
            title="Вне графика",
            defaults={
                "message_type": BaseMessage.MessageType.OFFLINE,
                "send_phase": BaseMessage.SendPhase.OFFLINE,
                "text": (
                    "Сейчас нерабочее время, операторов на линии нет. "
                    "Оставьте сообщение — ответим в начале следующего рабочего дня."
                ),
                "is_active": True,
                "sort_order": 50,
            },
        )
        # A couple of dialogs left over from a previous shift (unassigned, older
        # timestamps) — demonstrates that the shared queue keeps them ahead of
        # anything that arrives later while offline, purely via FIFO ordering.
        leftover_previews = (
            "Не успели подтвердить лимит по карте до закрытия смены.",
            "Клиент ждал перевод на карту — диалог остался в очереди.",
        )
        leftover_payload = []
        yesterday = timezone.now() - timedelta(hours=14)
        Dialog.objects.filter(
            client_external_id__startswith="queue-leftover-"
        ).delete()
        for index, preview in enumerate(leftover_previews, start=1):
            leftover, leftover_msg = create_dialog_with_message(
                text=preview,
                widget_id=placement.widget_id,
                placement="website",
                client_first_name="Клиент",
                client_last_name=f"очередь {index}",
                client_phone=_seed_client_phone(700 + index),
                client_external_id=f"queue-leftover-{index}",
                skip_auto_assign=True,
            )
            leftover.created_at = yesterday
            leftover.last_client_message_at = yesterday
            leftover.client_online = False
            leftover.client_last_seen_at = yesterday
            leftover.save(
                update_fields=[
                    "created_at",
                    "last_client_message_at",
                    "client_online",
                    "client_last_seen_at",
                    "updated_at",
                ]
            )
            leftover_msg.created_at = yesterday
            leftover_msg.save(update_fields=["created_at"])
            leftover_payload.append(
                {
                    "id": f"queue-leftover-{index}",
                    "dialog_id": str(leftover.id),
                    "name": leftover.client_display_name(),
                    "widget_url": (
                        f"/widget/sample.html"
                        f"?sim_client={quote(f'queue-leftover-{index}')}"
                    ),
                    "status": leftover.status,
                }
            )
        assignment = AssignmentSettings.get_solo()
        if assignment.mode != AssignmentSettings.Mode.MANUAL_PLUS_AUTO:
            assignment.mode = AssignmentSettings.Mode.MANUAL_PLUS_AUTO
            assignment.save(update_fields=["mode", "updated_at"])
        schedule = WorkScheduleSettings.get_solo()
        schedule.enabled = True
        if schedule.manual_override != WorkScheduleSettings.Override.AUTO:
            schedule.manual_override = WorkScheduleSettings.Override.AUTO
        schedule.save(update_fields=["enabled", "manual_override", "updated_at"])
        dialogs = []
        clients_payload = []
        for index in range(client_count):
            sim_id = f"sim-{index + 1}"
            phone = _seed_client_phone(index)
            dialog, _ = create_dialog_with_message(
                text=f"Тестовое обращение клиента {index + 1}: нужна консультация.",
                widget_id=placement.widget_id,
                placement="website",
                client_first_name="Клиент",
                client_last_name=str(index + 1),
                client_phone=phone,
                client_external_id=sim_id,
            )
            for message_index in range(1, message_count):
                append_message(
                    dialog,
                    speaker=DialogMessage.Speaker.CLIENT,
                    text=f"Дополнение {message_index + 1} от клиента {index + 1}",
                )
            dialogs.append(dialog)
            widget_url = (
                f"/widget/sample.html?sim_client={quote(sim_id)}"
                f"&dialog_id={quote(str(dialog.id))}"
            )
            clients_payload.append(
                {
                    "id": sim_id,
                    "dialog_id": str(dialog.id),
                    "name": f"Клиент {index + 1}",
                    "phone": phone,
                    "widget_url": widget_url,
                    "status": dialog.status,
                    "operator_name": dialog.operator_name,
                }
            )
        counts = dict(
            Dialog.objects.filter(id__in=[item.id for item in dialogs])
            .values_list("status")
            .annotate(count=Count("id"))
        )
        return JsonResponse(
            {
                "ok": True,
                "summary": {
                    "departments": 1,
                    "placements": 1,
                    "operators": len(operators),
                    "clients": len(dialogs),
                    "dialogs": len(dialogs),
                    "messages": len(dialogs) * max(message_count, 1),
                    "waiting": counts.get(Dialog.Status.WAITING, 0),
                    "active": counts.get(Dialog.Status.ACTIVE, 0),
                    "auto_assign": should_assign,
                    "reset": should_reset,
                    "widget_id": placement.widget_id,
                },
                "operator_names": [item.display_name for item in operators],
                "operators": [_operator_dict(item) for item in operators],
                "client_ids": [item["id"] for item in clients_payload],
                "clients": clients_payload,
                "widget_id": placement.widget_id,
                "queue_leftovers": leftover_payload,
            },
            status=201,
        )
    except (OnlineChatApiError, ValueError, TypeError) as exc:
        return _error(OnlineChatApiError(str(exc)))

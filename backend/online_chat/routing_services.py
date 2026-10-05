from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import Count, F, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from online_chat.models import (
    AssignmentSettings,
    Department,
    Dialog,
    DialogEvent,
    OperatorAssignmentHold,
    OperatorPresenceLog,
    OperatorProfile,
    RoutingRule,
    WidgetPlacement,
    WorkScheduleSettings,
)


def line_is_open(now=None) -> bool:
    """Whether the online-chat line currently distributes dialogs to operators."""
    try:
        return WorkScheduleSettings.get_solo().is_open(now)
    except Exception:  # pragma: no cover - never block on settings lookup
        return True


def record_event(
    dialog: Dialog, event_type: str, *, actor_name: str = "", payload: dict[str, Any] | None = None
) -> DialogEvent:
    return DialogEvent.objects.create(
        dialog=dialog, type=event_type, actor_name=actor_name, payload=payload or {}
    )


def _conditions_match(conditions: object, context: dict[str, Any]) -> bool:
    if not isinstance(conditions, dict):
        return False
    for key, expected in conditions.items():
        if key == "max_load":
            continue
        actual = context.get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _rule_max_load(conditions: object) -> int | None:
    if not isinstance(conditions, dict):
        return None
    raw = conditions.get("max_load")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def select_department(
    *,
    widget_id: str = "",
    channel: str = "widget",
    context: dict[str, Any] | None = None,
) -> tuple[Department | None, WidgetPlacement | None, str]:
    placement = WidgetPlacement.objects.filter(widget_id=widget_id, is_active=True).first()
    rules = RoutingRule.objects.filter(is_active=True, department__is_active=True).select_related(
        "department", "placement"
    )
    rules = rules.filter(Q(channel="") | Q(channel=channel))
    if placement:
        rules = rules.filter(Q(placement__isnull=True) | Q(placement=placement))
    else:
        rules = rules.filter(placement__isnull=True)
    rule_context = {"widget_id": widget_id, "channel": channel, **(context or {})}
    for rule in rules:
        if _conditions_match(rule.conditions, rule_context):
            return rule.department, placement, f"routing_rule:{rule.name}"
    if placement and placement.department and placement.department.is_active:
        return placement.department, placement, f"placement:{placement.widget_id}"
    fallback = Department.objects.filter(is_active=True).order_by("priority", "name").first()
    return fallback, placement, "default_department" if fallback else "unrouted"


def department_queue_is_full(department: Department | None) -> bool:
    """True when department waiting queue already reached its configured limit."""
    if department is None or not department.max_queue_size:
        return False
    waiting = Dialog.objects.filter(
        department=department,
        status=Dialog.Status.WAITING,
    ).count()
    return waiting >= department.max_queue_size


def operator_has_capacity(operator: OperatorProfile, *, exclude_dialog_id: object | None = None) -> bool:
    """Supervisors have no concurrent-dialog limit; operators use max_active_dialogs."""
    if operator.role == OperatorProfile.Role.SUPERVISOR:
        return True
    qs = Dialog.objects.filter(operator=operator, status=Dialog.Status.ACTIVE)
    if exclude_dialog_id is not None:
        qs = qs.exclude(pk=exclude_dialog_id)
    return qs.count() < operator.max_active_dialogs


def _held_operator_ids() -> set[Any]:
    now = timezone.now()
    return set(
        OperatorAssignmentHold.objects.filter(until__gt=now).values_list(
            "operator_id", flat=True
        )
    )


def start_post_close_grace(operator: OperatorProfile | None) -> OperatorAssignmentHold | None:
    """In manual+auto mode, give the operator time to pick before auto-assign.

    Grace applies when closing freed a slot that was at capacity. If the operator
    already had spare capacity (limit raised / underloaded), skip the hold so
    auto-assign can fill immediately.
    """
    if operator is None:
        return None
    settings = AssignmentSettings.get_solo()
    if settings.mode != AssignmentSettings.Mode.MANUAL_PLUS_AUTO:
        return None
    if operator.role == OperatorProfile.Role.SUPERVISOR:
        return None
    # Dialog is already closed → current active count is post-close.
    active_now = Dialog.objects.filter(
        operator=operator,
        status=Dialog.Status.ACTIVE,
    ).count()
    capacity = max(1, int(getattr(operator, "max_active_dialogs", None) or 1))
    # Before close they had active_now + 1. Need grace only if that was >= capacity.
    if active_now + 1 < capacity:
        return None
    until = timezone.now() + timedelta(seconds=AssignmentSettings.GRACE_SECONDS)
    OperatorAssignmentHold.objects.filter(operator=operator, until__gt=timezone.now()).delete()
    hold = OperatorAssignmentHold.objects.create(operator=operator, until=until)
    operator_id = str(operator.id)
    delay = AssignmentSettings.GRACE_SECONDS + 1
    scheduled = False
    try:
        from online_chat.tasks import run_assignments_after_delay

        run_assignments_after_delay.apply_async(
            countdown=delay,
            kwargs={"operator_id": operator_id},
        )
        scheduled = True
    except Exception:  # noqa: BLE001 — celery may be unavailable
        scheduled = False
    if not scheduled:
        # Local / no-worker fallback so grace still ends with auto-assign.
        import threading

        def _fallback() -> None:
            try:
                from online_chat.tasks import run_assignments_after_delay

                run_assignments_after_delay(operator_id=operator_id)
            except Exception:  # noqa: BLE001
                pass

        threading.Timer(delay, _fallback).start()
    return hold


def clear_assignment_hold(operator: OperatorProfile | None) -> None:
    if operator is None:
        return
    OperatorAssignmentHold.objects.filter(
        operator=operator, until__gt=timezone.now()
    ).delete()


def _eligible_operators(dialog: Dialog, *, max_load: int | None = None):
    """Operators only — supervisors never receive auto-assigned dialogs."""
    held = _held_operator_ids()
    qs = OperatorProfile.objects.filter(
        is_active=True,
        auto_assign=True,
        presence=OperatorProfile.Presence.ONLINE,
        role=OperatorProfile.Role.OPERATOR,
    )
    if held:
        qs = qs.exclude(pk__in=held)
    if dialog.department_id:
        qs = qs.filter(departments=dialog.department)
    annotated = qs.annotate(
        active_count=Count(
            "dialogs",
            filter=Q(dialogs__status=Dialog.Status.ACTIVE),
            distinct=True,
        )
    ).filter(active_count__lt=F("max_active_dialogs"))
    if max_load is not None:
        annotated = annotated.filter(active_count__lt=max_load)
    return annotated.order_by("active_count", "last_seen_at", "display_name")


@transaction.atomic
def accept_waiting_dialog(
    dialog_id: object,
    *,
    operator: OperatorProfile | None = None,
    operator_name: str = "",
) -> Dialog:
    dialog = Dialog.objects.select_for_update().get(pk=dialog_id)
    if dialog.status != Dialog.Status.WAITING:
        raise ValueError("dialog is not waiting")
    if operator:
        locked_operator = OperatorProfile.objects.select_for_update().get(pk=operator.pk)
        if not operator_has_capacity(locked_operator):
            raise ValueError("operator capacity reached")
        operator = locked_operator
        operator_name = operator.display_name
        clear_assignment_hold(operator)
    operator_name = operator_name.strip()
    if not operator_name:
        raise ValueError("operator is required")
    now = timezone.now()
    dialog.status = Dialog.Status.ACTIVE
    dialog.operator = operator
    dialog.operator_name = operator_name
    dialog.accepted_at = now
    dialog.save(
        update_fields=["status", "operator", "operator_name", "accepted_at", "updated_at"]
    )
    record_event(
        dialog,
        "accepted",
        actor_name=operator_name,
        payload={"operator_id": str(operator.id) if operator else None},
    )
    return dialog


def _max_load_for_dialog(dialog: Dialog) -> int | None:
    reason = dialog.routing_reason or ""
    if not reason.startswith("routing_rule:"):
        return None
    rule_name = reason.split(":", 1)[1]
    rule = (
        RoutingRule.objects.filter(name=rule_name, is_active=True)
        .order_by("priority", "created_at")
        .first()
    )
    if rule is None:
        return None
    return _rule_max_load(rule.conditions)


def auto_assign_dialog(dialog: Dialog) -> Dialog | None:
    if dialog.status != Dialog.Status.WAITING:
        return None
    # Offline-parked dialogs (arrived outside working hours) are not distributed
    # until the working day opens and releases the backlog.
    if dialog.outcome == Dialog.Outcome.OFFLINE:
        return None
    # Outside working hours the line does not auto-distribute at all.
    if not line_is_open():
        return None
    max_load = _max_load_for_dialog(dialog)
    candidates = list(_eligible_operators(dialog, max_load=max_load)[:20])
    for candidate in candidates:
        try:
            return accept_waiting_dialog(dialog.pk, operator=candidate)
        except ValueError:
            continue
    return None

def waiting_queue_queryset(*, department: Department | None = None):
    """FIFO by last client activity — newest writers go to the end of the queue."""
    qs = (
        Dialog.objects.filter(status=Dialog.Status.WAITING)
        .annotate(
            queue_key=Coalesce("last_client_message_at", "created_at"),
        )
        .order_by("queue_key", "created_at")
    )
    if department:
        qs = qs.filter(department=department)
    return qs


def release_offline_queue() -> int:
    """Move parked offline dialogs back into the live waiting queue.

    Called when the line opens (calendar or manual). Dialogs keep their
    original ``created_at`` / ``last_client_message_at`` so FIFO ordering
    still places them ahead of anything created after the line reopened.
    """
    updated = Dialog.objects.filter(
        status=Dialog.Status.WAITING,
        outcome=Dialog.Outcome.OFFLINE,
    ).update(outcome="")
    return int(updated)


def run_assignments(*, department: Department | None = None) -> list[Dialog]:
    # Outside working hours nothing is distributed (offline queue only).
    if not line_is_open():
        return []
    # Drop expired holds opportunistically.
    OperatorAssignmentHold.objects.filter(until__lte=timezone.now()).delete()
    release_offline_queue()
    qs = waiting_queue_queryset(department=department)
    assigned: list[Dialog] = []
    for dialog in qs[:500]:
        result = auto_assign_dialog(dialog)
        if result:
            assigned.append(result)
    return assigned


@transaction.atomic
def close_working_day() -> dict[str, int]:
    """End-of-shift transition: everything active goes back to the shared queue.

    - Every ACTIVE dialog (operator or supervisor) returns to WAITING, keeping
      its original ``created_at`` / ``last_client_message_at`` so it re-enters
      the queue at its previous chronological position — ahead of any dialog
      that arrives later while the line is closed (offline intake).
    - Every operator goes ``presence=OFFLINE`` so nobody can take dialogs and
      auto-assign has no eligible candidates until ``open_working_day()`` runs.
    - Any pending post-close grace holds are cleared (irrelevant once closed).
    """
    now = timezone.now()
    returned = 0
    for dialog in Dialog.objects.select_for_update().filter(status=Dialog.Status.ACTIVE):
        previous_operator = dialog.operator_name
        dialog.status = Dialog.Status.WAITING
        dialog.operator = None
        dialog.operator_name = ""
        dialog.accepted_at = None
        dialog.save(
            update_fields=["status", "operator", "operator_name", "accepted_at", "updated_at"]
        )
        record_event(
            dialog,
            "returned_to_queue",
            actor_name=previous_operator,
            payload={"reason": "shift_end"},
        )
        returned += 1
    offlined_qs = list(
        OperatorProfile.objects.filter(is_active=True).exclude(
            presence=OperatorProfile.Presence.OFFLINE
        )
    )
    offlined = 0
    for operator in offlined_qs:
        _record_presence_interval(operator, OperatorProfile.Presence.OFFLINE, at=now)
        operator.presence = OperatorProfile.Presence.OFFLINE
        operator.last_seen_at = now
        operator.save(update_fields=["presence", "last_seen_at", "updated_at"])
        offlined += 1
    OperatorAssignmentHold.objects.all().delete()
    from online_chat.services import park_waiting_dialogs_offline

    parked = park_waiting_dialogs_offline()
    return {
        "returned_to_queue": returned,
        "operators_offlined": offlined,
        "parked": parked.get("parked", 0),
        "offline_notices": parked.get("offline_notices", 0),
    }


def open_working_day() -> dict[str, int]:
    """Start-of-shift transition: bring operators online and flush backlog."""
    now = timezone.now()
    onlined_qs = list(
        OperatorProfile.objects.filter(is_active=True).exclude(
            presence=OperatorProfile.Presence.ONLINE
        )
    )
    onlined = 0
    for operator in onlined_qs:
        _record_presence_interval(operator, OperatorProfile.Presence.ONLINE, at=now)
        operator.presence = OperatorProfile.Presence.ONLINE
        operator.last_seen_at = now
        operator.save(update_fields=["presence", "last_seen_at", "updated_at"])
        onlined += 1
    release_offline_queue()
    assigned = run_assignments()
    from online_chat.services import enqueue_hold_for_waiting_dialogs

    holds_queued = enqueue_hold_for_waiting_dialogs()
    return {
        "assigned": len(assigned),
        "operators_onlined": int(onlined),
        "holds_queued": holds_queued,
    }


def sync_schedule_state(obj: "WorkScheduleSettings | None" = None) -> dict[str, Any]:
    """Detect open⇄closed transitions and apply the matching side effects.

    Safe to call repeatedly (from a request handler or a periodic beat task):
    it is a no-op unless the resolved ``is_open()`` value actually changed
    since the last call, so both the demo simulator toggle and the automatic
    schedule-based clock crossing share one source of truth.
    """
    obj = obj or WorkScheduleSettings.get_solo()
    now_open = obj.is_open()
    previous = obj.last_open_state
    result: dict[str, Any] = {"changed": False, "is_open": now_open}
    if previous is None:
        # First observation ever (fresh install) — record without side effects.
        obj.last_open_state = now_open
        obj.save(update_fields=["last_open_state"])
        return result
    if now_open == previous:
        return result
    if now_open:
        result.update(open_working_day())
    else:
        result.update(close_working_day())
    obj.last_open_state = now_open
    obj.save(update_fields=["last_open_state"])
    result["changed"] = True
    return result


def _record_presence_interval(operator: OperatorProfile, presence: str, *, at=None) -> None:
    now = at or timezone.now()
    open_log = (
        OperatorPresenceLog.objects.filter(operator=operator, ended_at__isnull=True)
        .order_by("-started_at")
        .first()
    )
    if open_log and open_log.presence == presence:
        return
    if open_log:
        open_log.ended_at = now
        open_log.save(update_fields=["ended_at"])
    elif operator.presence != presence:
        started = operator.last_seen_at or now
        if started < now:
            OperatorPresenceLog.objects.create(
                operator=operator,
                presence=operator.presence,
                started_at=started,
                ended_at=now,
            )
    OperatorPresenceLog.objects.create(
        operator=operator,
        presence=presence,
        started_at=now,
    )


def update_operator_presence(operator: OperatorProfile, presence: str) -> OperatorProfile:
    if presence not in OperatorProfile.Presence.values:
        raise ValueError("invalid presence")
    now = timezone.now()
    if operator.presence != presence:
        _record_presence_interval(operator, presence, at=now)
    operator.presence = presence
    operator.last_seen_at = now
    operator.save(update_fields=["presence", "last_seen_at", "updated_at"])
    if (
        presence == OperatorProfile.Presence.ONLINE
        and operator.auto_assign
        and operator.role == OperatorProfile.Role.OPERATOR
    ):
        for department in operator.departments.filter(is_active=True):
            run_assignments(department=department)
    return operator


@transaction.atomic
def transfer_to_operator(
    dialog: Dialog,
    *,
    operator_id: object | None = None,
    operator_name: str = "",
    enforce_capacity: bool = False,
) -> Dialog:
    """Hand dialog to another operator/supervisor.

    Transfers may exceed soft capacity (supervisor/manual routing). Auto-accept
    still enforces capacity via ``accept_waiting_dialog``.
    """
    dialog = Dialog.objects.select_for_update().get(pk=dialog.pk)
    target = None
    if operator_id:
        target = OperatorProfile.objects.select_for_update().get(pk=operator_id, is_active=True)
    elif operator_name:
        target = (
            OperatorProfile.objects.select_for_update()
            .filter(display_name=operator_name, is_active=True)
            .first()
        )
    name = target.display_name if target else operator_name.strip()
    if not name:
        raise ValueError("target operator is required")
    if (
        enforce_capacity
        and target
        and not operator_has_capacity(target, exclude_dialog_id=dialog.pk)
    ):
        raise ValueError("operator capacity reached")
    previous = dialog.operator_name
    dialog.operator = target
    dialog.operator_name = name
    dialog.status = Dialog.Status.ACTIVE
    if not dialog.accepted_at:
        dialog.accepted_at = timezone.now()
    dialog.save(
        update_fields=["operator", "operator_name", "status", "accepted_at", "updated_at"]
    )
    if target:
        clear_assignment_hold(target)
    record_event(
        dialog,
        "transferred",
        actor_name=previous,
        payload={"from": previous, "to": name, "operator_id": str(target.id) if target else None},
    )
    return dialog

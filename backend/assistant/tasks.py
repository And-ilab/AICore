"""Regular assistant report snapshots. The broker is optional.

On-demand reports do not use this task. If the worker is down, the schedule
row stores an error and the analyst can still open a report by request.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from celery import shared_task
from django.utils import timezone

from assistant.models import AssistantReportSchedule
from assistant.monitoring_query import snapshot_for_schedule


logger = logging.getLogger("assistant.monitoring")
MINSK = ZoneInfo("Europe/Minsk")


def schedule_is_due(schedule: AssistantReportSchedule, now: datetime) -> bool:
    if schedule.last_run_at is None:
        return True
    local_now = now.astimezone(MINSK)
    local_last = schedule.last_run_at.astimezone(MINSK)
    if schedule.cadence == AssistantReportSchedule.CADENCE_DAILY:
        return local_last.date() < local_now.date()
    if schedule.cadence == AssistantReportSchedule.CADENCE_WEEKLY:
        return local_last.isocalendar()[:2] != local_now.isocalendar()[:2]
    return (local_last.year, local_last.month) != (local_now.year, local_now.month)


@shared_task(name="assistant.tasks.run_due_report_schedules")
def run_due_report_schedules(schedule_id: int | None = None) -> dict[str, int]:
    queryset = AssistantReportSchedule.objects.filter(enabled=True)
    if schedule_id is not None:
        queryset = queryset.filter(pk=schedule_id)
    now = timezone.now()
    done = 0
    failed = 0
    for schedule in queryset:
        if schedule_id is None and not schedule_is_due(schedule, now):
            continue
        try:
            schedule.last_summary = snapshot_for_schedule(schedule)
            schedule.last_run_at = now
            schedule.last_status = AssistantReportSchedule.STATUS_OK
            schedule.last_error = ""
            done += 1
        except Exception:
            logger.exception(
                "schedule_run_failed schedule_id=%s",
                schedule.pk,
            )
            schedule.last_status = AssistantReportSchedule.STATUS_ERROR
            schedule.last_error = "aggregation_error"
            failed += 1
        schedule.save(
            update_fields=[
                "last_summary",
                "last_run_at",
                "last_status",
                "last_error",
                "updated_at",
            ]
        )
    return {"done": done, "failed": failed}

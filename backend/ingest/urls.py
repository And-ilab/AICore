from django.urls import path

from ingest.views import (
    knowledge_events,
    knowledge_reconcile_run,
    knowledge_reconcile_status,
)

urlpatterns = [
    path("events", knowledge_events, name="suz_knowledge_events"),
    path(
        "reconcile/",
        knowledge_reconcile_status,
        name="suz_reconcile_status",
    ),
    path(
        "reconcile/run/",
        knowledge_reconcile_run,
        name="suz_reconcile_run",
    ),
]

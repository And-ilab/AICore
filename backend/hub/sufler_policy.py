"""Singleton sufler operator-hint policy (II.3.5.2)."""

from __future__ import annotations

from typing import Any, Mapping

from django.db import transaction

from hub.models import SuflerPolicy

POLICY_PK = 1


def get_sufler_policy() -> SuflerPolicy:
    instance, _ = SuflerPolicy.objects.get_or_create(
        pk=POLICY_PK,
        defaults={
            "telephony_min_relevance_percent": 20,
            "clarify_min_relevance_percent": 15,
            "max_hints": 1,
            "default_mode": SuflerPolicy.MODE_CONSULTATION,
        },
    )
    return instance


@transaction.atomic
def update_sufler_policy(
    payload: Mapping[str, Any],
    *,
    username: str = "",
) -> SuflerPolicy:
    instance = get_sufler_policy()
    for field in (
        "telephony_min_relevance_percent",
        "clarify_min_relevance_percent",
        "max_hints",
        "default_mode",
    ):
        if field in payload and payload[field] is not None:
            setattr(instance, field, payload[field])
    instance.updated_by = username
    instance.save()
    return instance


def serialize_sufler_policy(instance: SuflerPolicy | None = None) -> dict[str, Any]:
    item = instance or get_sufler_policy()
    return {
        "telephony_min_relevance_percent": item.telephony_min_relevance_percent,
        "clarify_min_relevance_percent": item.clarify_min_relevance_percent,
        "max_hints": item.max_hints,
        "default_mode": item.default_mode,
        "updated_at": item.updated_at.isoformat() if item.updated_at else "",
        "updated_by": item.updated_by,
        "model_params_path": "/ai-hub/admin/model_params/cc",
        "chat_templates_path": "/online-chat/admin",
    }

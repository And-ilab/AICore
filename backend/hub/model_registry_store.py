from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from django.conf import settings
from django.db import transaction

from core.model_registry import DEFAULT_REGISTRY_PATH, ModelRegistry
from hub.models import ModelRegistrySettings


PROFILE_TO_SLOT = {
    ModelRegistrySettings.PROFILE_ASSISTANT: "llm_assistant_bank",
    ModelRegistrySettings.PROFILE_SUFLER_CC: "llm_sufler_cc",
}

EDITABLE_FIELDS = frozenset(
    {
        "temperature",
        "top_p",
        "max_tokens",
        "response_chars_max",
        "preset",
        "chunk_size_tokens",
        "chunk_overlap_tokens",
        "context_inclusion_threshold",
        "deterministic_answer_threshold",
    }
)

# Generation presets (§3.3.2): краткий / стандарт / развёрнутый.
GENERATION_PRESETS: dict[str, dict[str, dict[str, Any]]] = {
    ModelRegistrySettings.PROFILE_ASSISTANT: {
        ModelRegistrySettings.PRESET_SHORT: {
            "temperature": 0.2,
            "top_p": 0.85,
            "max_tokens": 512,
            "response_chars_max": 400,
        },
        ModelRegistrySettings.PRESET_STANDARD: {
            "temperature": 0.35,
            "top_p": 0.9,
            "max_tokens": 1200,
            "response_chars_max": 1200,
        },
        ModelRegistrySettings.PRESET_LONG: {
            "temperature": 0.5,
            "top_p": 0.95,
            "max_tokens": 2048,
            "response_chars_max": 2000,
        },
    },
    ModelRegistrySettings.PROFILE_SUFLER_CC: {
        ModelRegistrySettings.PRESET_SHORT: {
            "temperature": 0.15,
            "top_p": 0.85,
            "max_tokens": 256,
            "response_chars_max": 300,
        },
        ModelRegistrySettings.PRESET_STANDARD: {
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 500,
            "response_chars_max": 500,
        },
        ModelRegistrySettings.PRESET_LONG: {
            "temperature": 0.25,
            "top_p": 0.92,
            "max_tokens": 800,
            "response_chars_max": 500,
        },
    },
}


def registry_path() -> Path:
    return Path(
        getattr(settings, "MODEL_REGISTRY_PATH", DEFAULT_REGISTRY_PATH)
    )


def defaults_for_profile(profile: str) -> dict[str, Any]:
    try:
        slot_name = PROFILE_TO_SLOT[profile]
    except KeyError as exc:
        raise ValueError(f"Unknown model profile: {profile}") from exc

    registry = ModelRegistry.load(registry_path())
    slot = registry.get_slot(slot_name)
    knowledge_base = registry.get_profile("kb_cc_production")
    default_preset = (
        ModelRegistrySettings.PRESET_SHORT
        if profile == ModelRegistrySettings.PROFILE_SUFLER_CC
        else ModelRegistrySettings.PRESET_STANDARD
    )
    preset_values = GENERATION_PRESETS[profile][default_preset]
    return {
        "temperature": slot.kpi.get(
            "temperature", preset_values["temperature"]
        ),
        "top_p": slot.kpi.get("top_p", preset_values["top_p"]),
        "max_tokens": slot.kpi.get("max_tokens", preset_values["max_tokens"]),
        "response_chars_max": slot.kpi.get(
            "response_chars_max", preset_values["response_chars_max"]
        ),
        "preset": default_preset,
        "chunk_size_tokens": knowledge_base.chunk_size_tokens,
        "chunk_overlap_tokens": knowledge_base.chunk_overlap_tokens,
        "context_inclusion_threshold": (
            knowledge_base.context_inclusion_threshold
        ),
        "deterministic_answer_threshold": (
            knowledge_base.deterministic_answer_threshold
        ),
    }


def apply_generation_preset(
    profile: str,
    preset: str,
) -> dict[str, Any]:
    try:
        return dict(GENERATION_PRESETS[profile][preset])
    except KeyError as exc:
        raise ValueError(f"Unknown preset for profile {profile}: {preset}") from exc


def get_model_settings(profile: str) -> ModelRegistrySettings:
    defaults = defaults_for_profile(profile)
    instance, _ = ModelRegistrySettings.objects.get_or_create(
        profile=profile,
        defaults=defaults,
    )
    return instance


@transaction.atomic
def update_model_settings(
    profile: str,
    payload: Mapping[str, Any],
    *,
    username: str,
) -> ModelRegistrySettings:
    unknown_fields = set(payload) - EDITABLE_FIELDS
    if unknown_fields:
        fields = ", ".join(sorted(unknown_fields))
        raise ValueError(f"Unknown fields: {fields}")

    get_model_settings(profile)
    instance = ModelRegistrySettings.objects.select_for_update().get(
        profile=profile
    )
    for field_name, value in payload.items():
        setattr(instance, field_name, value)
    instance.updated_by = username
    instance.revision += 1
    instance.save()
    return instance


@transaction.atomic
def reset_model_settings_to_platform(
    profile: str,
    *,
    username: str,
) -> ModelRegistrySettings:
    defaults = defaults_for_profile(profile)
    return update_model_settings(profile, defaults, username=username)


def serialize_model_settings(instance: ModelRegistrySettings) -> dict[str, Any]:
    slot_name = PROFILE_TO_SLOT[instance.profile]
    slot = ModelRegistry.load(registry_path()).get_slot(slot_name)
    display_model = (
        "sufler-v1"
        if instance.profile == ModelRegistrySettings.PROFILE_SUFLER_CC
        else "assist-v2"
    )
    if slot.dev_model:
        display_model = slot.dev_model
    response_max = (
        500
        if instance.profile == ModelRegistrySettings.PROFILE_SUFLER_CC
        else 4000
    )
    response_min = (
        1
        if instance.profile == ModelRegistrySettings.PROFILE_SUFLER_CC
        else 10
    )
    if instance.profile == ModelRegistrySettings.PROFILE_ASSISTANT:
        preset_choices = (
            (ModelRegistrySettings.PRESET_STANDARD, "По умолчанию"),
            (ModelRegistrySettings.PRESET_LONG, "Подробнее"),
        )
    else:
        preset_choices = ModelRegistrySettings.PRESET_CHOICES
    return {
        "profile": instance.profile,
        "slot": slot_name,
        "generation": {
            "temperature": instance.temperature,
            "top_p": instance.top_p,
            "max_tokens": instance.max_tokens,
            "response_chars_max": instance.response_chars_max,
            "preset": instance.preset,
        },
        "rag": {
            "chunk_size_tokens": instance.chunk_size_tokens,
            "chunk_overlap_tokens": instance.chunk_overlap_tokens,
            "context_inclusion": instance.context_inclusion_threshold,
            "deterministic_answer": (
                instance.deterministic_answer_threshold
            ),
        },
        "read_only": {
            "dev_model": slot.dev_model,
            "prod_candidate": slot.prod_candidate,
            "status": slot.status,
            "context_window": "≥8200",
            "llm_model_label": display_model,
        },
        "presets": {
            key: {
                "label": label,
                "values": GENERATION_PRESETS[instance.profile][key],
            }
            for key, label in preset_choices
        },
        "platform_defaults": defaults_for_profile(instance.profile),
        "constraints": {
            "temperature": {
                "min": 0.1 if instance.profile == "sufler_cc" else 0,
                "max": 0.25 if instance.profile == "sufler_cc" else 1,
                "step": 0.01,
            },
            "top_p": {"min": 0.01, "max": 1, "step": 0.01},
            "max_tokens": {"min": 1, "max": 32768},
            "response_chars_max": {"min": response_min, "max": response_max},
        },
        "revision": instance.revision,
        "updated_at": instance.updated_at.isoformat(),
        "updated_by": instance.updated_by,
    }

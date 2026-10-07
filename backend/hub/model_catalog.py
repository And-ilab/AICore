"""Runtime model catalogs and the admin's saved choice per slot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hub.models import ModelRegistrySettings, SlotModelSelection

SLOT_ASSISTANT = SlotModelSelection.SLOT_ASSISTANT
SLOT_SUFLER = SlotModelSelection.SLOT_SUFLER
SLOT_SPEECH = SlotModelSelection.SLOT_SPEECH
SLOT_ANSWER = SlotModelSelection.SLOT_ANSWER
SLOT_OCR = SlotModelSelection.SLOT_OCR

PROFILE_LLM_SLOT = {
    ModelRegistrySettings.PROFILE_ASSISTANT: SLOT_ASSISTANT,
    ModelRegistrySettings.PROFILE_SUFLER_CC: SLOT_SUFLER,
    "docs_ocr": SLOT_OCR,
}

SPEECH_PRESETS: tuple[tuple[str, str], ...] = (
    ("vosk-model-small-ru-0.22", "Речь · компактная"),
    ("vosk-model-ru-0.22", "Речь · стандарт"),
    ("vosk-model-ru-0.42", "Речь · расширенная"),
)


def public_model_label(model_id: str, label: str = "") -> str:
    """Visible name. A vendor cloud model is shown as модель1."""
    blob = f"{model_id} {label}".lower()
    if "deepseek" in blob or "дипсик" in blob:
        return "модель1"
    text = (label or model_id).strip()
    return text or model_id


def selected_model(slot: str) -> str:
    try:
        row = (
            SlotModelSelection.objects.filter(slot=slot)
            .only("model_id")
            .first()
        )
    except Exception:
        return ""
    if row is None:
        return ""
    return (row.model_id or "").strip()


def selected_llm_for_profile(profile: str) -> str:
    slot = PROFILE_LLM_SLOT.get(profile, "")
    if not slot:
        return ""
    return selected_model(slot)


def _mask_option(model_id: str, label: str, *, available: bool = True) -> dict[str, Any]:
    return {
        "id": model_id,
        "label": public_model_label(model_id, label),
        "available": available,
    }


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        model_id = str(row.get("id") or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        result.append(
            _mask_option(
                model_id,
                str(row.get("label") or model_id),
                available=bool(row.get("available", True)),
            )
        )
    return result


def llm_options() -> list[dict[str, Any]]:
    from assistant import local_llm

    rows: list[dict[str, Any]] = []
    try:
        status = local_llm.get_models_status()
        rows.extend(status.get("models") or [])
    except Exception:
        status = {}
    if local_llm.is_deepseek_assistant():
        try:
            rows.extend(local_llm._list_pulled_models(timeout=1.5))
        except Exception:
            pass
    options = _dedupe(rows)
    if options:
        return options
    fallback = ""
    try:
        fallback = (local_llm.active_model_id() or "").strip()
    except Exception:
        fallback = ""
    if not fallback:
        fallback = "qwen2.5-1.5b-instruct"
    return [_mask_option(fallback, fallback)]


def _speech_roots() -> list[Path]:
    backend = Path(__file__).resolve().parents[1]
    return [
        backend / "var",
        backend / "services" / "asr" / "model",
        backend.parent / "recognizer" / "model",
    ]


def speech_options() -> list[dict[str, Any]]:
    found: set[str] = set()
    for root in _speech_roots():
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and "vosk" in child.name.lower():
                found.add(child.name)
    options = [
        _mask_option(model_id, label, available=model_id in found or not found)
        for model_id, label in SPEECH_PRESETS
    ]
    known = {item["id"] for item in options}
    for name in sorted(found):
        if name not in known:
            options.append(_mask_option(name, name, available=True))
    return options


def ensure_option(
    options: list[dict[str, Any]],
    model_id: str,
) -> list[dict[str, Any]]:
    model_id = (model_id or "").strip()
    if not model_id:
        return options
    if any(item["id"] == model_id for item in options):
        return options
    return [_mask_option(model_id, model_id), *options]


def _default_llm_id(profile: str, options: list[dict[str, Any]]) -> str:
    import os

    candidates: list[str] = []
    if profile == ModelRegistrySettings.PROFILE_SUFLER_CC:
        candidates.append(os.environ.get("SUFLER_LLM_MODEL") or "")
    elif profile == "docs_ocr":
        candidates.append(os.environ.get("OCR_LLM_MODEL") or "")
        candidates.append(os.environ.get("SUFLER_LLM_MODEL") or "")
    else:
        candidates.append(os.environ.get("ASSISTANT_LLM_MODEL") or "")
    try:
        from assistant.local_llm import active_model_id

        candidates.append(active_model_id() or "")
    except Exception:
        pass
    ids = {str(item["id"]) for item in options}
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate and (not ids or candidate in ids):
            return candidate
    return str(options[0]["id"]) if options else ""


def choices_for_profile(profile: str) -> dict[str, Any]:
    options = llm_options()
    slot = PROFILE_LLM_SLOT[profile]
    selected = selected_model(slot) or _default_llm_id(profile, options)
    payload: dict[str, Any] = {
        "llm": {
            "selected": selected,
            "options": ensure_option(options, selected),
        }
    }
    if profile == ModelRegistrySettings.PROFILE_SUFLER_CC:
        speech = speech_options()
        speech_selected = selected_model(SLOT_SPEECH) or (
            speech[0]["id"] if speech else ""
        )
        answer_selected = selected_model(SLOT_ANSWER) or selected
        payload["speech"] = {
            "selected": speech_selected,
            "options": ensure_option(speech, speech_selected),
        }
        payload["answer"] = {
            "selected": answer_selected,
            "options": ensure_option(options, answer_selected),
        }
    return payload


def choices_for_ocr() -> dict[str, Any]:
    options = llm_options()
    selected = selected_model(SLOT_OCR) or _default_llm_id("docs_ocr", options)
    return {
        "slot": SLOT_OCR,
        "selected_model": selected,
        "models": ensure_option(options, selected),
    }


def save_model(slot: str, model_id: str, *, username: str) -> str:
    model_id = (model_id or "").strip()
    if not model_id:
        raise ValueError("model_id is required")
    if slot == SLOT_SPEECH:
        allowed = speech_options()
    elif slot in {SLOT_ASSISTANT, SLOT_SUFLER, SLOT_ANSWER, SLOT_OCR}:
        allowed = llm_options()
    else:
        raise ValueError(f"Unknown model slot: {slot}")
    allowed = ensure_option(allowed, selected_model(slot))
    if model_id not in {item["id"] for item in allowed}:
        raise ValueError("Модель не найдена в списке")
    SlotModelSelection.objects.update_or_create(
        slot=slot,
        defaults={"model_id": model_id, "updated_by": username[:150]},
    )
    return model_id


def apply_profile_selection(
    profile: str,
    selection: dict[str, str],
    *,
    username: str,
) -> None:
    if profile != ModelRegistrySettings.PROFILE_SUFLER_CC and (
        selection.get("speech") or selection.get("answer")
    ):
        raise ValueError("speech and answer belong to the sufler profile")
    llm = (selection.get("llm") or "").strip()
    if llm:
        save_model(PROFILE_LLM_SLOT[profile], llm, username=username)
    if profile != ModelRegistrySettings.PROFILE_SUFLER_CC:
        return
    speech = (selection.get("speech") or "").strip()
    if speech:
        save_model(SLOT_SPEECH, speech, username=username)
    answer = (selection.get("answer") or "").strip()
    if answer:
        save_model(SLOT_ANSWER, answer, username=username)


def prioritize_speech_paths(paths: list[Path]) -> list[Path]:
    name = selected_model(SLOT_SPEECH)
    if not name:
        return paths
    head = [path for path in paths if path.name == name]
    tail = [path for path in paths if path.name != name]
    return head + tail

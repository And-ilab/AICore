"""Assistant chat model catalog: DeepSeek when configured, else Ollama."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def ollama_base_url() -> str:
    """Native Ollama API root (not /v1)."""
    raw = (
        os.environ.get("OLLAMA_BASE_URL")
        or os.environ.get("LOCAL_LLM_MANAGER_URL")  # legacy alias
        or "http://ollama:11434"
    ).rstrip("/")
    if raw.endswith("/v1"):
        raw = raw[: -len("/v1")]
    return raw


def assistant_remote_base_url() -> str:
    for key in ("ASSISTANT_LLM_BASE_URL", "SUFLER_LLM_BASE_URL"):
        raw = (os.environ.get(key) or "").strip().rstrip("/")
        if raw:
            return raw
    openai = (os.environ.get("OPENAI_BASE_URL") or "").strip().rstrip("/")
    if openai and "deepseek.com" in openai.lower():
        return openai
    return ""


def is_deepseek_assistant() -> bool:
    return "deepseek.com" in assistant_remote_base_url().lower()


def openai_base_url() -> str:
    remote = assistant_remote_base_url()
    if remote:
        return remote
    raw = (os.environ.get("OPENAI_BASE_URL") or "").strip().rstrip("/")
    if raw:
        return raw
    return f"{ollama_base_url()}/v1"


def _is_assistant_model(model_id: str) -> bool:
    return bool(model_id)


def _deepseek_model_id() -> str:
    return (
        (os.environ.get("ASSISTANT_LLM_MODEL") or "").strip()
        or (os.environ.get("SUFLER_LLM_MODEL") or "").strip()
        or "deepseek-chat"
    )


def _env_default_model() -> str:
    if is_deepseek_assistant():
        return _deepseek_model_id()
    openai_model = (os.environ.get("OPENAI_MODEL") or "").strip()
    if _is_assistant_model(openai_model):
        return openai_model
    return (os.environ.get("OLLAMA_MODEL") or "").strip()


def _state_path() -> Path:
    raw = os.environ.get("OLLAMA_ACTIVE_MODEL_PATH")
    if raw:
        return Path(raw)
    # Persist under backend tree (dev bind-mount) or /tmp in plain containers.
    here = Path(__file__).resolve()
    candidate = here.parents[1] / "var" / "active_openai_model"
    return candidate


def _read_runtime_model() -> str | None:
    path = _state_path()
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _write_runtime_model(model_id: str) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model_id.strip() + "\n", encoding="utf-8")


def active_model_id() -> str:
    """DeepSeek when configured; otherwise Ollama/UI selection."""
    if is_deepseek_assistant():
        return _deepseek_model_id()
    runtime = _read_runtime_model()
    if runtime and _is_assistant_model(runtime):
        return runtime
    return _env_default_model()


def _timeout() -> float:
    raw = os.environ.get("OLLAMA_TIMEOUT_SECONDS", "30")
    try:
        return max(3.0, float(raw))
    except ValueError:
        return 30.0


def _get_json(url: str, *, timeout: float | None = None) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout or _timeout()) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw or "{}")


def _list_pulled_models() -> list[dict[str, Any]]:
    payload = _get_json(f"{ollama_base_url()}/api/tags", timeout=5.0)
    models: list[dict[str, Any]] = []
    for item in payload.get("models") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model")
        if not isinstance(name, str) or not name.strip():
            continue
        size = item.get("size")
        desc = ""
        if isinstance(size, (int, float)) and size > 0:
            desc = f"{size / (1024 ** 3):.1f} GB"
        models.append(
            {
                "id": name.strip(),
                "label": name.strip(),
                "description": desc,
                "available": True,
            }
        )
    models.sort(key=lambda row: row["id"])
    return models


def offline_status(*, error: str | None = None) -> dict[str, Any]:
    model = active_model_id() or None
    return {
        "active_model_id": model,
        "switching": False,
        "llama_running": False,
        "manager_reachable": False,
        "openai_alias": model,
        "models": (
            [
                {
                    "id": model,
                    "label": model,
                    "description": "Задана локально / через OPENAI_MODEL",
                    "available": True,
                }
            ]
            if model
            else []
        ),
        "last_error": error
        or (
            "Ollama недоступна. Поднимите сервис ollama "
            "(COMPOSE_PROFILES=cpu-inference)."
        ),
    }


def _deepseek_status() -> dict[str, Any]:
    model = _deepseek_model_id()
    return {
        "active_model_id": model,
        "switching": False,
        "llama_running": True,
        "manager_reachable": True,
        "openai_alias": model,
        "models": [
            {
                "id": model,
                "label": "модель 1",
                "description": "",
                "available": True,
            }
        ],
        "last_error": None,
    }


def get_models_status() -> dict[str, Any]:
    if is_deepseek_assistant():
        return _deepseek_status()
    try:
        models = _list_pulled_models()
    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        return offline_status(error=f"Ollama недоступна ({exc})")

    ids = {item["id"] for item in models}
    runtime = _read_runtime_model()
    if runtime and not _is_assistant_model(runtime):
        runtime = None
    env_default = _env_default_model()
    active: str | None = None
    if runtime and runtime in ids:
        active = runtime
    elif env_default and env_default in ids:
        active = env_default
    elif runtime:
        # Selected but not currently listed (retag / unload) — still show as active.
        active = runtime
        if runtime not in ids:
            models.insert(
                0,
                {
                    "id": runtime,
                    "label": runtime,
                    "description": "выбрана, но нет в ollama list",
                    "available": False,
                },
            )
    elif models:
        active = models[0]["id"]

    return {
        "active_model_id": active,
        "switching": False,
        "llama_running": True,
        "manager_reachable": True,
        "openai_alias": active,
        "models": models,
        "last_error": None
        if models
        else (
            "В Ollama нет скачанных моделей. "
            "docker compose exec ollama ollama pull <name>"
        ),
    }


def select_model(model_id: str) -> dict[str, Any]:
    """Set active Ollama model for subsequent assistant chat requests."""
    model_id = model_id.strip()
    if not model_id:
        raise ValueError("model_id is required")
    if is_deepseek_assistant():
        active = _deepseek_model_id()
        if model_id != active:
            raise ValueError(
                f"Qwen/Ollama отключены. Активна облачная модель {active}."
            )
        return get_models_status()
    try:
        models = _list_pulled_models()
    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError(f"Ollama недоступна: {exc}") from exc

    ids = {item["id"] for item in models}
    # Allow exact tag or bare name match (llama3.2:3b vs llama3.2:3b-instruct-q4…)
    if model_id not in ids:
        prefix_hits = [
            item["id"] for item in models if item["id"].startswith(model_id + ":")
        ]
        if len(prefix_hits) == 1:
            model_id = prefix_hits[0]
        else:
            available = ", ".join(sorted(ids)) or "(пусто)"
            raise ValueError(
                f"Модель {model_id!r} не найдена среди скачанных в Ollama. "
                f"Доступно: {available}"
            )

    try:
        _write_runtime_model(model_id)
    except OSError as exc:
        raise RuntimeError(f"Не удалось сохранить выбор модели: {exc}") from exc

    return get_models_status()

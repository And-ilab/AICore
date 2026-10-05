"""Central OpenAI-compatible gateway for all LLM profiles.

Profile mapping:
    sufler_cc      -> ModelRegistry slot ``llm_sufler_cc``
    assistant_bank -> ModelRegistry slot ``llm_assistant_bank``
    docs_ocr       -> ModelRegistry slot ``llm_docs_ocr``
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import requests

from core.model_registry import (
    DEFAULT_REGISTRY_PATH,
    ModelRegistry,
    ModelSlot,
)


PROFILE_TO_SLOT = {
    "sufler_cc": "llm_sufler_cc",
    "assistant_bank": "llm_assistant_bank",
    "docs_ocr": "llm_docs_ocr",
}
DOCS_OCR_PROFILE = "docs_ocr"
SUPPORTED_MODES = frozenset({"stub", "openai"})
SUFLER_PROFILE = "sufler_cc"
RESERVED_PARAMETERS = frozenset({"model", "messages", "stream"})
STUB_RESPONSES = {
    "sufler_cc": (
        "ОТВЕТ:\n"
        "Уточните детали запроса клиента и опирайтесь на подтверждённые материалы СУЗ.\n"
        "СОВЕТ:\n"
        "Проверьте актуальность тарифа перед ответом."
    ),
    "assistant_bank": (
        "Ответ ассистента: запрос принят. Используйте подтверждённые "
        "банковские источники."
    ),
    "docs_ocr": json.dumps(
        {
            "document_type": "unknown",
            "fields": {},
            "validation": {
                "status": "stub",
                "missing_required_fields": [],
                "anomalies": [],
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ),
}
STUB_TOOL_ARGUMENTS = {
    "get_exchange_rate": {"currency": "USD"},
}


class ModelGatewayError(RuntimeError):
    """Base error for gateway configuration and transport failures."""


class ModelGatewayConfigurationError(ModelGatewayError):
    """Raised before a request when profile configuration is invalid."""


class ModelGatewayRequestError(ModelGatewayError):
    """Raised when an OpenAI-compatible endpoint request fails."""


@dataclass(frozen=True)
class GatewayProfile:
    profile: str
    slot_name: str
    model: str
    gateway_mode: str
    api_compatibility: str
    kpi: Mapping[str, Any]


def _validate_messages(
    messages: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(messages, Sequence) or isinstance(
        messages,
        (str, bytes),
    ):
        raise ModelGatewayConfigurationError(
            "messages must be a non-empty sequence"
        )
    validated: list[dict[str, Any]] = []
    for index, message in enumerate(messages, start=1):
        if not isinstance(message, Mapping):
            raise ModelGatewayConfigurationError(
                f"message #{index} must be an object"
            )
        role = message.get("role")
        content = message.get("content")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ModelGatewayConfigurationError(
                f"message #{index} has unsupported role"
            )
        if not isinstance(content, str):
            raise ModelGatewayConfigurationError(
                f"message #{index} content must be a string"
            )
        validated.append(dict(message))
    if not validated:
        raise ModelGatewayConfigurationError("messages cannot be empty")
    return validated


def _is_deepseek_url(url: str) -> bool:
    return "deepseek.com" in (url or "").lower()


def _ollama_openai_base() -> str:
    raw = (os.environ.get("OLLAMA_BASE_URL") or "").strip().rstrip("/")
    if not raw:
        return ""
    return raw if raw.endswith("/v1") else f"{raw}/v1"


def _sufler_base_url(fallback: str = "") -> str:
    dedicated = (os.environ.get("SUFLER_LLM_BASE_URL") or "").strip()
    if dedicated:
        return dedicated.rstrip("/")
    openai = (os.environ.get("OPENAI_BASE_URL") or fallback or "").strip()
    return openai.rstrip("/") if openai else ""


def _assistant_dedicated_base() -> str:
    for key in ("ASSISTANT_LLM_BASE_URL", "SUFLER_LLM_BASE_URL"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw.rstrip("/")
    return ""


def _assistant_base_url(fallback: str = "") -> str:
    dedicated = _assistant_dedicated_base()
    if dedicated:
        return dedicated
    openai = (os.environ.get("OPENAI_BASE_URL") or fallback or "").strip()
    if openai:
        return openai.rstrip("/")
    return _ollama_openai_base()


def _validate_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    reserved = RESERVED_PARAMETERS & parameters.keys()
    if reserved:
        names = ", ".join(sorted(reserved))
        raise ModelGatewayConfigurationError(
            f"Reserved request parameters cannot be overridden: {names}"
        )
    return dict(parameters)


def _profile_from_slot(
    profile: str,
    slot_name: str,
    slot: ModelSlot,
) -> GatewayProfile:
    configured_profile = slot.kpi.get("profile")
    if configured_profile != profile:
        raise ModelGatewayConfigurationError(
            f"Slot {slot_name!r} profile mismatch: {configured_profile!r}"
        )
    gateway_mode = slot.kpi.get("gateway_mode")
    if gateway_mode not in SUPPORTED_MODES:
        raise ModelGatewayConfigurationError(
            f"Slot {slot_name!r} has invalid gateway_mode"
        )
    api_compatibility = slot.kpi.get("api_compatibility")
    if api_compatibility != "openai":
        raise ModelGatewayConfigurationError(
            f"Slot {slot_name!r} must use OpenAI compatibility"
        )
    model = slot.prod_candidate or slot.dev_model
    if not isinstance(model, str) or not model:
        raise ModelGatewayConfigurationError(
            f"Slot {slot_name!r} has no configured model"
        )
    return GatewayProfile(
        profile=profile,
        slot_name=slot_name,
        model=model,
        gateway_mode=gateway_mode,
        api_compatibility=api_compatibility,
        kpi=slot.kpi,
    )


class ModelGateway:
    """Dispatch LLM chat and SSE streaming through one stable interface."""

    def __init__(
        self,
        registry: ModelRegistry,
        *,
        mode: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 30,
    ) -> None:
        if mode is not None and mode not in SUPPORTED_MODES:
            raise ModelGatewayConfigurationError(
                f"Unsupported gateway mode: {mode}"
            )
        if timeout_seconds <= 0:
            raise ModelGatewayConfigurationError(
                "timeout_seconds must be positive"
            )
        self._registry = registry
        self._mode_override = mode
        self._base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self._api_key = (
            api_key
            if api_key is not None
            else os.environ.get("OPENAI_API_KEY")
        )
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_registry(
        cls,
        registry_path: str | Path = DEFAULT_REGISTRY_PATH,
        **kwargs: Any,
    ) -> ModelGateway:
        registry = ModelRegistry.load(registry_path)
        mode = kwargs.pop("mode", None)
        if mode is None:
            mode = os.environ.get("MODEL_GATEWAY_MODE") or None
        if not mode:
            profile_name = os.environ.get("AI_INFERENCE_PROFILE", "test")
            try:
                mode = registry.get_deployment_profile(
                    profile_name
                ).llm_gateway_mode
            except KeyError:
                mode = None
        if "timeout_seconds" not in kwargs:
            raw_timeout = os.environ.get("OPENAI_TIMEOUT_SECONDS")
            if raw_timeout:
                try:
                    kwargs["timeout_seconds"] = float(raw_timeout)
                except ValueError:
                    pass
        return cls(registry, mode=mode, **kwargs)

    def get_profile(self, profile: str) -> GatewayProfile:
        try:
            slot_name = PROFILE_TO_SLOT[profile]
        except KeyError as exc:
            raise ModelGatewayConfigurationError(
                f"Unknown LLM profile: {profile}"
            ) from exc
        return _profile_from_slot(
            profile,
            slot_name,
            self._registry.get_slot(slot_name),
        )

    def get_runtime_model(self, profile: str) -> str:
        """Return the model identifier actually sent to the active provider."""
        return self._resolve_model(self.get_profile(profile))

    def _mode_for(self, profile: GatewayProfile) -> str:
        if profile.profile == SUFLER_PROFILE:
            if (os.environ.get("SUFLER_LLM_BASE_URL") or "").strip() or _is_deepseek_url(
                os.environ.get("OPENAI_BASE_URL") or self._base_url or ""
            ):
                return "openai"
            return self._mode_override or profile.gateway_mode
        if profile.profile == DOCS_OCR_PROFILE:
            if (
                (os.environ.get("OCR_LLM_BASE_URL") or "").strip()
                or (os.environ.get("SUFLER_LLM_BASE_URL") or "").strip()
                or _is_deepseek_url(self._base_url_for(profile))
            ):
                return "openai"
            return self._mode_override or profile.gateway_mode
        if _assistant_dedicated_base() or _is_deepseek_url(
            _assistant_base_url(self._base_url or "")
        ):
            return "openai"
        return self._mode_override or profile.gateway_mode

    def _base_url_for(self, profile: GatewayProfile) -> str:
        if profile.profile == SUFLER_PROFILE:
            return _sufler_base_url(self._base_url or "")
        if profile.profile == DOCS_OCR_PROFILE:
            dedicated = (os.environ.get("OCR_LLM_BASE_URL") or "").strip()
            if dedicated:
                return dedicated.rstrip("/")
            return _assistant_base_url(self._base_url or "")
        return _assistant_base_url(self._base_url or "")

    def _api_key_for(self, profile: GatewayProfile) -> str:
        if profile.profile == SUFLER_PROFILE:
            dedicated = (os.environ.get("SUFLER_LLM_API_KEY") or "").strip()
            if dedicated:
                return dedicated
            return self._api_key or os.environ.get("OPENAI_API_KEY") or ""
        if profile.profile == DOCS_OCR_PROFILE:
            dedicated = (os.environ.get("OCR_LLM_API_KEY") or "").strip()
            if dedicated:
                return dedicated
        assistant_key = (os.environ.get("ASSISTANT_LLM_API_KEY") or "").strip()
        if assistant_key:
            return assistant_key
        if _is_deepseek_url(self._base_url_for(profile)):
            sufler_key = (os.environ.get("SUFLER_LLM_API_KEY") or "").strip()
            if sufler_key:
                return sufler_key
        return self._api_key or os.environ.get("OPENAI_API_KEY") or ""

    def _openai_endpoint(self, profile: GatewayProfile) -> str:
        base_url = self._base_url_for(profile)
        if not base_url:
            if profile.profile == SUFLER_PROFILE:
                message = "OPENAI_BASE_URL is required in openai mode"
            elif profile.profile == DOCS_OCR_PROFILE:
                message = (
                    "OCR_LLM_BASE_URL, SUFLER_LLM_BASE_URL, "
                    "ASSISTANT_LLM_BASE_URL or OPENAI_BASE_URL is required "
                    "for docs_ocr openai mode"
                )
            else:
                message = (
                    "ASSISTANT_LLM_BASE_URL, SUFLER_LLM_BASE_URL, "
                    "OPENAI_BASE_URL or OLLAMA_BASE_URL is required "
                    "for assistant openai mode"
                )
            raise ModelGatewayConfigurationError(message)
        if self._resolve_model(profile).startswith("stub:"):
            raise ModelGatewayConfigurationError(
                f"Profile {profile.profile!r} requires a real model "
                "in openai mode"
            )
        return f"{base_url.rstrip('/')}/chat/completions"

    def _headers(self, profile: GatewayProfile | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = self._api_key_for(profile) if profile else (self._api_key or "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _resolve_model(self, profile: GatewayProfile) -> str:
        """Sufler and assistant prefer SUFLER_LLM_* / ASSISTANT_LLM_* (DeepSeek)."""
        if profile.profile == SUFLER_PROFILE:
            dedicated = (os.environ.get("SUFLER_LLM_MODEL") or "").strip()
            if dedicated:
                return dedicated
            if _is_deepseek_url(self._base_url_for(profile)):
                openai_model = (os.environ.get("OPENAI_MODEL") or "").strip()
                if openai_model and "deepseek" in openai_model.lower():
                    return openai_model
                return "deepseek-chat"
            return profile.model
        if profile.profile == DOCS_OCR_PROFILE:
            dedicated = (os.environ.get("OCR_LLM_MODEL") or "").strip()
            if dedicated:
                return dedicated
            if _is_deepseek_url(self._base_url_for(profile)):
                sufler_model = (os.environ.get("SUFLER_LLM_MODEL") or "").strip()
                if sufler_model:
                    return sufler_model
                openai_model = (os.environ.get("OPENAI_MODEL") or "").strip()
                if openai_model and "deepseek" in openai_model.lower():
                    return openai_model
                return "deepseek-chat"
            openai_model = (os.environ.get("OPENAI_MODEL") or "").strip()
            if openai_model and not openai_model.startswith("stub:"):
                return openai_model
            return profile.model
        assistant_model = (os.environ.get("ASSISTANT_LLM_MODEL") or "").strip()
        if assistant_model:
            return assistant_model
        if _is_deepseek_url(self._base_url_for(profile)):
            sufler_model = (os.environ.get("SUFLER_LLM_MODEL") or "").strip()
            if sufler_model:
                return sufler_model
            openai_model = (os.environ.get("OPENAI_MODEL") or "").strip()
            if openai_model and "deepseek" in openai_model.lower():
                return openai_model
            return "deepseek-chat"
        try:
            from assistant.local_llm import active_model_id

            runtime = (active_model_id() or "").strip()
            if runtime:
                return runtime
        except Exception:
            pass
        for key in ("OLLAMA_MODEL", "OPENAI_MODEL"):
            candidate = (os.environ.get(key) or "").strip()
            if candidate:
                return candidate
        return profile.model

    def _payload(
        self,
        profile: GatewayProfile,
        messages: Sequence[Mapping[str, Any]],
        *,
        stream: bool,
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "model": self._resolve_model(profile),
            "messages": _validate_messages(messages),
            "stream": stream,
            **_validate_parameters(parameters),
        }

    def chat(
        self,
        profile: str,
        messages: Sequence[Mapping[str, Any]],
        **parameters: Any,
    ) -> dict[str, Any]:
        configured = self.get_profile(profile)
        payload = self._payload(
            configured,
            messages,
            stream=False,
            parameters=parameters,
        )
        if self._mode_for(configured) == "stub":
            return self._stub_chat(
                configured,
                payload["messages"],
                payload,
            )

        endpoint = self._openai_endpoint(configured)
        timeout = self._timeout_seconds
        if configured.profile == SUFLER_PROFILE:
            timeout = min(timeout, 45.0)
        elif configured.profile == DOCS_OCR_PROFILE:
            timeout = min(max(timeout, 20.0), 60.0)
        try:
            response = requests.post(
                endpoint,
                headers=self._headers(configured),
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ModelGatewayRequestError(
                f"OpenAI-compatible chat request failed for {profile}"
            ) from exc
        if not isinstance(result, Mapping):
            raise ModelGatewayRequestError(
                "OpenAI-compatible response must be a JSON object"
            )
        return dict(result)

    def stream(
        self,
        profile: str,
        messages: Sequence[Mapping[str, Any]],
        **parameters: Any,
    ) -> Iterator[str]:
        configured = self.get_profile(profile)
        payload = self._payload(
            configured,
            messages,
            stream=True,
            parameters=parameters,
        )
        if self._mode_for(configured) == "stub":
            return iter(self._stub_stream(configured))
        return self._openai_stream(configured, payload)

    def _stub_docs_ocr_content(
        self,
        messages: Sequence[Mapping[str, Any]],
    ) -> str:
        """Return the canned docs_ocr stub (empty fields, no network)."""
        del messages
        return STUB_RESPONSES["docs_ocr"]

    def _stub_chat(
        self,
        profile: GatewayProfile,
        messages: Sequence[Mapping[str, Any]],
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if profile.profile == "docs_ocr":
            content = self._stub_docs_ocr_content(messages)
        else:
            content = STUB_RESPONSES[profile.profile]
        completion_id = f"chatcmpl-stub-{uuid.uuid4().hex}"
        prompt_words = sum(
            len(str(message["content"]).split()) for message in messages
        )
        completion_words = len(content.split())
        message: dict[str, Any] = {
            "role": "assistant",
            "content": content,
        }
        finish_reason = "stop"
        tools = payload.get("tools")
        if profile.profile == "assistant_bank" and tools:
            if not isinstance(tools, Sequence) or isinstance(
                tools,
                (str, bytes),
            ):
                raise ModelGatewayConfigurationError(
                    "tools must be a sequence"
                )
            try:
                function_name = tools[0]["function"]["name"]
            except (IndexError, KeyError, TypeError) as exc:
                raise ModelGatewayConfigurationError(
                    "tools require an OpenAI function definition"
                ) from exc
            if function_name in STUB_TOOL_ARGUMENTS:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_stub_{uuid.uuid4().hex[:12]}",
                            "type": "function",
                            "function": {
                                "name": function_name,
                                "arguments": json.dumps(
                                    STUB_TOOL_ARGUMENTS[function_name],
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            },
                        }
                    ],
                }
                finish_reason = "tool_calls"
                completion_words = 0
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": profile.model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": prompt_words,
                "completion_tokens": completion_words,
                "total_tokens": prompt_words + completion_words,
            },
        }

    def _stub_stream(
        self,
        profile: GatewayProfile,
    ) -> Iterable[str]:
        completion_id = f"chatcmpl-stub-{uuid.uuid4().hex}"
        created = int(time.time())

        def event(delta: Mapping[str, Any], finish: str | None) -> str:
            payload = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": profile.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": dict(delta),
                        "finish_reason": finish,
                    }
                ],
            }
            return (
                "data: "
                + json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n\n"
            )

        yield event({"role": "assistant"}, None)
        content = STUB_RESPONSES[profile.profile]
        for start in range(0, len(content), 24):
            yield event({"content": content[start : start + 24]}, None)
        yield event({}, "stop")
        yield "data: [DONE]\n\n"

    def _openai_stream(
        self,
        profile: GatewayProfile,
        payload: Mapping[str, Any],
    ) -> Iterator[str]:
        endpoint = self._openai_endpoint(profile)

        def generate() -> Iterator[str]:
            try:
                with requests.post(
                    endpoint,
                    headers=self._headers(profile),
                    json=dict(payload),
                    timeout=self._timeout_seconds,
                    stream=True,
                ) as response:
                    response.raise_for_status()
                    # llama.cpp often omits charset; requests would then
                    # decode SSE as ISO-8859-1 and corrupt Cyrillic.
                    response.encoding = "utf-8"
                    for raw in response.iter_lines(decode_unicode=False):
                        if not raw:
                            continue
                        line = (
                            raw.decode("utf-8")
                            if isinstance(raw, (bytes, bytearray))
                            else str(raw)
                        )
                        if line.startswith("data:"):
                            yield f"{line}\n\n"
            except requests.RequestException as exc:
                raise ModelGatewayRequestError(
                    "OpenAI-compatible SSE request failed for "
                    f"{profile.profile}"
                ) from exc

        return generate()

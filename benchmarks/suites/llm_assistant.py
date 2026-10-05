"""Assistant API contract benchmark for SSE, 8k context, and tool calls."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
for import_path in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from benchmarks.suites.base import build_stub_report  # noqa: E402
from core.model_gateway import ModelGateway  # noqa: E402


PROFILE = "assistant_bank"
REQUIREMENTS = (
    "FR-ASS-03",
    "FR-ASS-14",
    "FR-ASS-21",
    "FR-ASS-33",
    "FR-ASS-41",
)
TOOL_NAME = "get_exchange_rate"


class LlmAssistantInputError(ValueError):
    """Raised when an assistant response violates the API contract."""


def percentile(values: Sequence[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def build_context(token_count: int) -> str:
    """Build deterministic whitespace tokens without claiming model tokens."""
    return " ".join(f"context_{index:04d}" for index in range(token_count))


def _stream_metrics(
    gateway: ModelGateway,
    context: str,
) -> dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": "Ты внутренний ИИ-ассистент банка.",
        },
        {
            "role": "user",
            "content": (
                "Прими длинный контекст и подтверди потоковый ответ.\n"
                + context
            ),
        },
    ]
    started_at = time.perf_counter()
    previous_at = started_at
    first_event_ms: float | None = None
    first_content_ms: float | None = None
    frame_intervals_ms: list[float] = []
    parsed_events = 0
    content_chunks = 0
    content = ""
    done_received = False
    frames = 0

    for frame in gateway.stream(PROFILE, messages):
        now = time.perf_counter()
        frames += 1
        frame_intervals_ms.append((now - previous_at) * 1000)
        previous_at = now
        if first_event_ms is None:
            first_event_ms = (now - started_at) * 1000
        if not frame.startswith("data: ") or not frame.endswith("\n\n"):
            raise LlmAssistantInputError("Invalid SSE frame")
        payload_text = frame[len("data: ") :].strip()
        if payload_text == "[DONE]":
            done_received = True
            continue
        try:
            payload = json.loads(payload_text)
            choice = payload["choices"][0]
            delta = choice["delta"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LlmAssistantInputError(
                "Invalid OpenAI SSE chunk"
            ) from exc
        parsed_events += 1
        chunk = delta.get("content", "")
        if chunk:
            if first_content_ms is None:
                first_content_ms = (now - started_at) * 1000
            content_chunks += 1
            content += chunk

    total_latency_ms = (time.perf_counter() - started_at) * 1000
    return {
        "valid": (
            done_received
            and parsed_events > 0
            and first_content_ms is not None
        ),
        "frames": frames,
        "parsed_events": parsed_events,
        "content_chunks": content_chunks,
        "done_received": done_received,
        "first_event_latency_ms": round(first_event_ms or 0, 2),
        "first_content_latency_ms": round(first_content_ms or 0, 2),
        "total_latency_ms": round(total_latency_ms, 2),
        "frame_interval_p50_ms": round(
            percentile(frame_intervals_ms, 50),
            2,
        ),
        "frame_interval_p95_ms": round(
            percentile(frame_intervals_ms, 95),
            2,
        ),
        "reconstructed_content": content,
    }


def _tool_call_metrics(gateway: ModelGateway) -> dict[str, Any]:
    tools = [
        {
            "type": "function",
            "function": {
                "name": TOOL_NAME,
                "description": "Получить курс валюты из внутренней системы.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "currency": {
                            "type": "string",
                            "description": "ISO currency code",
                        }
                    },
                    "required": ["currency"],
                    "additionalProperties": False,
                },
            },
        }
    ]
    response = gateway.chat(
        PROFILE,
        [
            {
                "role": "user",
                "content": "Покажи курс доллара через банковский инструмент.",
            }
        ],
        tools=tools,
        tool_choice="auto",
    )
    try:
        choice = response["choices"][0]
        message = choice["message"]
        tool_call = message["tool_calls"][0]
        function = tool_call["function"]
        arguments = json.loads(function["arguments"])
    except (
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        choices = response.get("choices")
        finish_reason = (
            choices[0].get("finish_reason")
            if isinstance(choices, list)
            and choices
            and isinstance(choices[0], Mapping)
            else None
        )
        return {
            "valid": False,
            "tool_name": None,
            "arguments": None,
            "finish_reason": finish_reason,
            "error": str(exc),
        }
    return {
        "valid": (
            tool_call.get("type") == "function"
            and function.get("name") == TOOL_NAME
            and isinstance(arguments.get("currency"), str)
            and choice.get("finish_reason") == "tool_calls"
        ),
        "tool_call_id": tool_call.get("id"),
        "tool_name": function.get("name"),
        "arguments": arguments,
        "finish_reason": choice.get("finish_reason"),
        "error": None,
    }


def run(gateway: ModelGateway | None = None) -> dict[str, Any]:
    gateway = gateway or ModelGateway.from_registry()
    configured = gateway.get_profile(PROFILE)
    context_tokens = int(configured.kpi["context_tokens_min"])
    latency_limit_ms = int(configured.kpi["latency_p95_ms_max"])
    context = build_context(context_tokens)
    stream = _stream_metrics(gateway, context)
    tool_call = _tool_call_metrics(gateway)
    mode_for = getattr(gateway, "_mode_for", lambda profile: profile.gateway_mode)
    is_stub = mode_for(configured) == "stub"
    context_contract_passed = (
        len(context.split()) == context_tokens and stream["done_received"]
    )
    contract_passed = (
        context_contract_passed
        and stream["valid"]
        and tool_call["valid"]
    )

    report = build_stub_report("llm", ("assistant-api-contract-v1",))
    report["report_id"] = report["report_id"].replace(
        "llm-",
        "llm-assistant-",
        1,
    )
    report["runner_status"] = (
        "stub"
        if is_stub
        else "ready"
        if contract_passed
        else "partial"
    )
    report["requirements"] = list(REQUIREMENTS)
    report["metrics"]["latency_ms"] = {
        "p50": stream["frame_interval_p50_ms"],
        "p95": stream["frame_interval_p95_ms"],
        "status": "placeholder" if is_stub else "measured",
    }
    report["suite_details"] = {
        "test_type": "llm_assistant_api",
        "profile": PROFILE,
        "model": configured.model,
        "contract_passed": contract_passed,
        "kpi_evidence": not is_stub,
        "context": {
            "requested_tokens": context_tokens,
            "constructed_whitespace_tokens": len(context.split()),
            "characters": len(context),
            "accepted": context_contract_passed,
            "status": (
                "placeholder" if is_stub else "measured"
            ),
            "note": (
                "Whitespace token count is a dev contract fixture, not "
                "vendor tokenizer output."
            ),
        },
        "sse": {
            **stream,
            "target_p95_ms_max": latency_limit_ms,
            "target_passed": (
                stream["total_latency_ms"] <= latency_limit_ms
                if not is_stub
                else None
            ),
            "status": "placeholder" if is_stub else "measured",
        },
        "tool_call": {
            **tool_call,
            "status": "placeholder" if is_stub else "measured",
            "execution_performed": False,
            "note": (
                "The suite validates tool-call shape only and never "
                "executes a banking operation."
            ),
        },
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate assistant_bank SSE and tool-use contracts.",
    )
    parser.add_argument(
        "--mode",
        choices=("stub", "openai"),
        help="Optional ModelGateway mode override.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports"),
    )
    return parser


def write_report(report: Mapping[str, Any], output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{report['report_id']}.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    gateway = ModelGateway.from_registry(mode=args.mode)
    report = run(gateway)
    report_path = write_report(report, args.output)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

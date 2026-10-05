"""Fixed-rate LLM load test for the FR-LLM-07 platform SLO."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
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


DEFAULT_RPS = 10.0
DEFAULT_DURATION_SECONDS = 60.0
DEFAULT_PROFILE = "sufler_cc"
DEFAULT_TIMEOUT_SECONDS = 5.0
REQUIREMENT = "FR-LLM-07"


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


def _total_memory_bytes() -> int | None:
    if os.name == "nt":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(
                ctypes.byref(status)
            ):
                return int(status.total_physical)
        except (AttributeError, OSError, TypeError):
            return None
    try:
        return int(
            os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        )
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def hardware_snapshot() -> dict[str, Any]:
    total_memory = _total_memory_bytes()
    return {
        "os": platform.platform(),
        "machine": platform.machine(),
        "cpu_model": platform.processor() or platform.machine(),
        "logical_cpu_count": os.cpu_count(),
        "memory_total_gb": (
            round(total_memory / 1024**3, 2)
            if total_memory is not None
            else None
        ),
        "python_version": platform.python_version(),
        "accelerator": os.environ.get(
            "LLM_BENCH_ACCELERATOR",
            "not_declared",
        ),
        "vm_label": os.environ.get("LLM_BENCH_VM", "not_declared"),
    }


async def run_load_test(
    *,
    gateway: ModelGateway | None = None,
    profile: str = DEFAULT_PROFILE,
    requests_per_second: float = DEFAULT_RPS,
    duration_seconds: float = DEFAULT_DURATION_SECONDS,
    request_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if requests_per_second <= 0:
        raise ValueError("requests_per_second must be positive")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if request_timeout_seconds <= 0:
        raise ValueError("request_timeout_seconds must be positive")
    request_count = round(requests_per_second * duration_seconds)
    if request_count < 1:
        raise ValueError("Load test must schedule at least one request")

    gateway = gateway or ModelGateway.from_registry()
    configured = gateway.get_profile(profile)
    mode_for = getattr(gateway, "_mode_for", lambda profile: profile.gateway_mode)
    is_stub = mode_for(configured) == "stub"
    latency_limit_ms = float(configured.kpi["latency_p95_ms_max"])
    rps_target = float(configured.kpi["requests_per_second_min"])
    messages = [
        {
            "role": "system",
            "content": "Ответь кратко по подтверждённым данным банка.",
        },
        {
            "role": "user",
            "content": "Тестовый запрос нагрузочного профиля.",
        },
    ]

    started_at = time.perf_counter()
    in_flight = 0
    peak_in_flight = 0

    async def execute(request_id: int) -> dict[str, Any]:
        nonlocal in_flight, peak_in_flight
        scheduled_at = started_at + request_id / requests_per_second
        await asyncio.sleep(max(0.0, scheduled_at - time.perf_counter()))
        dispatched_at = time.perf_counter()
        schedule_lag_ms = max(0.0, (dispatched_at - scheduled_at) * 1000)
        in_flight += 1
        peak_in_flight = max(peak_in_flight, in_flight)
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    gateway.chat,
                    profile,
                    messages,
                ),
                timeout=request_timeout_seconds,
            )
            choices = (
                response.get("choices")
                if isinstance(response, Mapping)
                else None
            )
            if not isinstance(choices, list):
                raise ValueError("Gateway response requires choices list")
            return {
                "request_id": request_id,
                "status": "success",
                "latency_ms": (
                    time.perf_counter() - dispatched_at
                )
                * 1000,
                "schedule_lag_ms": schedule_lag_ms,
                "error": None,
            }
        except TimeoutError:
            status = "timeout"
            error = "request_timeout"
        except MemoryError:
            status = "oom"
            error = "memory_error"
        except Exception as exc:
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
        finally:
            in_flight -= 1
        return {
            "request_id": request_id,
            "status": status,
            "latency_ms": (time.perf_counter() - dispatched_at) * 1000,
            "schedule_lag_ms": schedule_lag_ms,
            "error": error,
        }

    tasks = [
        asyncio.create_task(execute(request_id))
        for request_id in range(request_count)
    ]
    results = await asyncio.gather(*tasks)
    elapsed_seconds = time.perf_counter() - started_at
    successful = [
        result for result in results if result["status"] == "success"
    ]
    latencies = [
        float(result["latency_ms"]) for result in successful
    ]
    schedule_lags = [
        float(result["schedule_lag_ms"]) for result in results
    ]
    timeouts = sum(result["status"] == "timeout" for result in results)
    oom_errors = sum(result["status"] == "oom" for result in results)
    other_errors = sum(result["status"] == "error" for result in results)
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    achieved_rps = (
        len(successful) / elapsed_seconds if elapsed_seconds else 0.0
    )
    completed_without_failures = len(successful) == request_count
    measured_target_met = (
        not is_stub
        and duration_seconds >= DEFAULT_DURATION_SECONDS
        and requests_per_second >= rps_target
        and achieved_rps >= rps_target * 0.95
        and p95 <= latency_limit_ms
        and completed_without_failures
    )

    report = build_stub_report("llm", ("llm-load-fixed-prompt",))
    report["report_id"] = report["report_id"].replace(
        "llm-",
        "llm-load-",
        1,
    )
    report["runner_status"] = (
        "stub"
        if is_stub and completed_without_failures
        else "ready"
        if measured_target_met
        else "partial"
    )
    report["requirements"] = [REQUIREMENT]
    report["metrics"]["latency_ms"] = {
        "p50": round(p50, 2),
        "p95": round(p95, 2),
        "status": "placeholder" if is_stub else "measured",
    }
    report["suite_details"] = {
        "test_type": "llm_fixed_rate_load",
        "profile": profile,
        "model": configured.model,
        "configured_rps": requests_per_second,
        "configured_duration_seconds": duration_seconds,
        "request_timeout_seconds": request_timeout_seconds,
        "scheduled_requests": request_count,
        "successful_requests": len(successful),
        "timeout_count": timeouts,
        "oom_count": oom_errors,
        "error_count": other_errors,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "achieved_success_rps": round(achieved_rps, 2),
        "peak_in_flight": peak_in_flight,
        "schedule_lag_ms": {
            "p50": round(percentile(schedule_lags, 50), 2),
            "p95": round(percentile(schedule_lags, 95), 2),
        },
        "completed_without_oom_or_timeout": (
            oom_errors == 0 and timeouts == 0
        ),
        "completed_without_failures": completed_without_failures,
        "fr_llm_07": {
            "target_rps_min": rps_target,
            "target_duration_seconds_min": DEFAULT_DURATION_SECONDS,
            "target_latency_p95_ms_max": latency_limit_ms,
            "target_met": measured_target_met,
            "kpi_evidence": not is_stub,
        },
        "hardware": hardware_snapshot(),
        "failures": [
            {
                "request_id": result["request_id"],
                "status": result["status"],
                "error": result["error"],
            }
            for result in results
            if result["status"] != "success"
        ],
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the FR-LLM-07 fixed-rate LLM load test.",
    )
    parser.add_argument(
        "--profile",
        choices=("sufler_cc", "assistant_bank", "docs_ocr"),
        default=DEFAULT_PROFILE,
    )
    parser.add_argument("--rps", type=float, default=DEFAULT_RPS)
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION_SECONDS,
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
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
    report = asyncio.run(
        run_load_test(
            gateway=gateway,
            profile=args.profile,
            requests_per_second=args.rps,
            duration_seconds=args.duration,
            request_timeout_seconds=args.request_timeout,
        )
    )
    report_path = write_report(report, args.output)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

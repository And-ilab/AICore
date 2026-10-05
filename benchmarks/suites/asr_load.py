"""Concurrent ASR load test for FR-ASR-03."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping, Sequence


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.suites.asr_streaming import (
    DEFAULT_DATASET_PATH,
    REPOSITORY_ROOT,
    _recognize_wav,
    discover_model_paths,
    load_samples,
    percentile,
    word_error_counts,
)
from benchmarks.suites.base import build_stub_report


DEFAULT_STREAM_COUNT = 70
REQUIREMENT = "FR-ASR-03"
STUB_CHUNKS_PER_STREAM = 10


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
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        return int(page_size * page_count)
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def hardware_snapshot() -> dict[str, Any]:
    """Return reproducibility metadata without requiring psutil."""
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
        "gpu": os.environ.get("ASR_BENCH_GPU", "not_declared"),
    }


def _find_runnable_sample(
    dataset_path: Path,
) -> tuple[Mapping[str, Any], Path, Path] | None:
    model_paths = discover_model_paths()
    for sample in load_samples(dataset_path):
        input_data = sample.get("input")
        if not isinstance(input_data, Mapping):
            continue
        language = input_data.get("language")
        audio_value = input_data.get("audio_path")
        model_path = model_paths.get(str(language))
        if not isinstance(audio_value, str) or model_path is None:
            continue
        audio_path = REPOSITORY_ROOT / audio_value
        if audio_path.is_file():
            return sample, audio_path, model_path
    return None


async def _run_stub_stream(
    stream_id: int,
    start_event: asyncio.Event,
) -> dict[str, Any]:
    await start_event.wait()
    chunk_latencies: list[float] = []
    started_at = time.perf_counter()
    for _ in range(STUB_CHUNKS_PER_STREAM):
        chunk_started_at = time.perf_counter()
        await asyncio.sleep(0)
        chunk_latencies.append(
            (time.perf_counter() - chunk_started_at) * 1000
        )
    return {
        "stream_id": stream_id,
        "status": "simulated",
        "stream_latency_ms": (time.perf_counter() - started_at) * 1000,
        "chunk_latencies_ms": chunk_latencies,
        "word_errors": None,
        "reference_words": None,
    }


def _run_vosk_stream(
    stream_id: int,
    audio_path: Path,
    model: Any,
    recognizer_class: Any,
    reference: str,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    hypothesis, chunk_latencies, sample_rate = _recognize_wav(
        audio_path,
        model,
        recognizer_class,
    )
    errors, reference_words = word_error_counts(reference, hypothesis)
    return {
        "stream_id": stream_id,
        "status": "measured",
        "stream_latency_ms": (time.perf_counter() - started_at) * 1000,
        "chunk_latencies_ms": chunk_latencies,
        "word_errors": errors,
        "reference_words": reference_words,
        "sample_rate_hz": sample_rate,
    }


async def _run_vosk_streams(
    stream_count: int,
    audio_path: Path,
    model_path: Path,
    reference: str,
) -> list[dict[str, Any] | BaseException]:
    from vosk import KaldiRecognizer, Model

    model = Model(str(model_path))
    loop = asyncio.get_running_loop()
    start_event = asyncio.Event()
    with ThreadPoolExecutor(max_workers=stream_count) as executor:
        async def run_one(stream_id: int) -> dict[str, Any]:
            await start_event.wait()
            return await loop.run_in_executor(
                executor,
                _run_vosk_stream,
                stream_id,
                audio_path,
                model,
                KaldiRecognizer,
                reference,
            )

        tasks = [
            asyncio.create_task(run_one(stream_id))
            for stream_id in range(1, stream_count + 1)
        ]
        await asyncio.sleep(0)
        start_event.set()
        return await asyncio.gather(*tasks, return_exceptions=True)


async def run_load_test(
    *,
    stream_count: int = DEFAULT_STREAM_COUNT,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    force_stub: bool | None = None,
) -> dict[str, Any]:
    if stream_count < 1:
        raise ValueError("stream_count must be at least 1")
    if force_stub is None:
        force_stub = os.environ.get("ASR_BENCH_FORCE_STUB") == "1"

    runnable = None if force_stub else _find_runnable_sample(dataset_path)
    mode = "async_stub"
    setup_error: str | None = None
    model_name: str | None = None
    sample_id: str | None = None

    if runnable is not None:
        sample, audio_path, model_path = runnable
        expected = sample.get("expected")
        reference = (
            expected.get("text")
            if isinstance(expected, Mapping)
            else None
        )
        if isinstance(reference, str) and reference.strip():
            try:
                results = await _run_vosk_streams(
                    stream_count,
                    audio_path,
                    model_path,
                    reference,
                )
                mode = "async_vosk"
                model_name = model_path.name
                sample_id = str(sample.get("id"))
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                setup_error = str(exc)
                runnable = None
        else:
            setup_error = "reference_text_missing"
            runnable = None

    if runnable is None:
        start_event = asyncio.Event()
        tasks = [
            asyncio.create_task(_run_stub_stream(stream_id, start_event))
            for stream_id in range(1, stream_count + 1)
        ]
        await asyncio.sleep(0)
        start_event.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [
        result for result in results if isinstance(result, dict)
    ]
    failures = [
        result for result in results if isinstance(result, BaseException)
    ]
    chunk_latencies = [
        latency
        for result in successes
        for latency in result["chunk_latencies_ms"]
    ]
    stream_latencies = [
        float(result["stream_latency_ms"]) for result in successes
    ]
    measured = mode == "async_vosk" and bool(successes)
    total_errors = sum(
        int(result["word_errors"])
        for result in successes
        if result["word_errors"] is not None
    )
    total_reference_words = sum(
        int(result["reference_words"])
        for result in successes
        if result["reference_words"] is not None
    )
    wer = (
        total_errors / total_reference_words * 100
        if measured and total_reference_words
        else None
    )

    report = build_stub_report("asr", ("asr-synthetic-samples",))
    report["report_id"] = report["report_id"].replace("asr-", "asr-load-", 1)
    report["runner_status"] = (
        "ready"
        if measured and len(successes) == stream_count and not failures
        else "stub"
        if not measured and not failures
        else "partial"
    )
    report["requirements"] = [REQUIREMENT]
    report["metrics"]["latency_ms"] = {
        "p50": round(percentile(chunk_latencies, 50), 2),
        "p95": round(percentile(chunk_latencies, 95), 2),
        "status": "measured" if measured else "placeholder",
    }
    report["metrics"]["wer_percent"] = {
        "value": round(wer, 2) if wer is not None else None,
        "status": "measured" if measured else "placeholder",
    }
    report["metrics"]["accuracy_percent"] = {
        "value": (
            round(max(0.0, 100 - wer), 2)
            if wer is not None
            else None
        ),
        "status": "measured" if measured else "placeholder",
    }
    report["suite_details"] = {
        "test_type": "asr_load",
        "mode": mode,
        "configured_streams": stream_count,
        "successful_streams": len(successes),
        "failed_streams": len(failures),
        "harness_completed_without_crashes": (
            len(successes) == stream_count and not failures
        ),
        "fr_asr_03_load_target_met": (
            measured
            and len(successes) == stream_count
            and not failures
        ),
        "model": model_name,
        "sample_id": sample_id,
        "setup_error": setup_error,
        "stream_latency_ms": {
            "p50": round(percentile(stream_latencies, 50), 2),
            "p95": round(percentile(stream_latencies, 95), 2),
        },
        "hardware": hardware_snapshot(),
        "failures": [str(failure) for failure in failures],
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the FR-ASR-03 concurrent-stream load test.",
    )
    parser.add_argument(
        "--streams",
        type=int,
        default=DEFAULT_STREAM_COUNT,
        help="Concurrent streams (default: 70).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports"),
        help="Report directory (default: reports/).",
    )
    return parser


def write_report(report: Mapping[str, Any], output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / f"{report['report_id']}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_path


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = asyncio.run(run_load_test(stream_count=args.streams))
    report_path = write_report(report, args.output)
    print(report_path)
    return 0 if report["suite_details"]["failed_streams"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

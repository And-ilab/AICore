"""Streaming ASR benchmark for FR-ASR-01, FR-ASR-04, and FR-ASR-07."""

from __future__ import annotations

import json
import math
import os
import re
import time
import unicodedata
import wave
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from benchmarks.suites.base import build_stub_report


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = (
    REPOSITORY_ROOT / "benchmarks" / "datasets" / "asr_samples.json"
)
REQUIREMENTS = ("FR-ASR-01", "FR-ASR-04", "FR-ASR-07")
SUPPORTED_LANGUAGES = ("ru", "en")
CHUNK_DURATION_MS = 100


class AsrStreamingInputError(ValueError):
    """Raised when the streaming benchmark dataset is malformed."""


def normalize_words(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("ё", "е")
    return re.findall(r"\w+", normalized, flags=re.UNICODE)


def word_error_counts(
    reference: str,
    hypothesis: str,
) -> tuple[int, int]:
    """Return Levenshtein word edits and reference word count."""
    reference_words = normalize_words(reference)
    hypothesis_words = normalize_words(hypothesis)
    previous = list(range(len(hypothesis_words) + 1))

    for row, reference_word in enumerate(reference_words, start=1):
        current = [row]
        for column, hypothesis_word in enumerate(
            hypothesis_words,
            start=1,
        ):
            substitution_cost = int(reference_word != hypothesis_word)
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + substitution_cost,
                )
            )
        previous = current

    return previous[-1], len(reference_words)


def percentile(values: Sequence[float], percent: float) -> float:
    """Calculate an interpolated percentile without external dependencies."""
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


def load_samples(
    path: Path = DEFAULT_DATASET_PATH,
) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AsrStreamingInputError(f"Dataset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AsrStreamingInputError(f"Invalid dataset JSON: {path}") from exc

    samples = payload.get("samples") if isinstance(payload, Mapping) else None
    if not isinstance(samples, list):
        raise AsrStreamingInputError("Dataset 'samples' must be a list")
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, Mapping):
            raise AsrStreamingInputError(
                f"Dataset sample #{index} must be an object"
            )
    return samples


def _existing_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return path.resolve() if path.is_dir() else None


def discover_model_paths() -> dict[str, Path]:
    """Discover per-language Vosk models without importing Vosk."""
    service_models = (
        REPOSITORY_ROOT / "backend" / "services" / "asr" / "model"
    )
    candidates = {
        "ru": (
            _existing_path(os.environ.get("VOSK_MODEL_PATH_RU")),
            _existing_path(os.environ.get("VOSK_MODEL_PATH")),
            service_models / "vosk-model-small-ru-0.22",
            service_models / "vosk-model-ru-0.22",
        ),
        "en": (
            _existing_path(os.environ.get("VOSK_MODEL_PATH_EN")),
            service_models / "vosk-model-small-en-us-0.15",
            service_models / "vosk-model-en-us-0.22",
        ),
    }
    result: dict[str, Path] = {}
    for language, language_candidates in candidates.items():
        for candidate in language_candidates:
            if candidate is not None and candidate.is_dir():
                result[language] = candidate.resolve()
                break
    return result


def _recognize_wav(
    audio_path: Path,
    model: Any,
    recognizer_class: Any,
) -> tuple[str, list[float], int]:
    transcripts: list[str] = []
    latencies_ms: list[float] = []

    with wave.open(str(audio_path), "rb") as audio:
        if audio.getnchannels() != 1:
            raise AsrStreamingInputError("WAV must be mono")
        if audio.getsampwidth() != 2:
            raise AsrStreamingInputError("WAV must use 16-bit PCM")
        if audio.getcomptype() != "NONE":
            raise AsrStreamingInputError("WAV must be uncompressed PCM")

        sample_rate = audio.getframerate()
        frames_per_chunk = max(
            1,
            sample_rate * CHUNK_DURATION_MS // 1000,
        )
        recognizer = recognizer_class(model, sample_rate)
        recognizer.SetWords(True)

        while chunk := audio.readframes(frames_per_chunk):
            started_at = time.perf_counter()
            accepted = recognizer.AcceptWaveform(chunk)
            latencies_ms.append(
                (time.perf_counter() - started_at) * 1000
            )
            if accepted:
                text = json.loads(recognizer.Result()).get("text", "")
                if text:
                    transcripts.append(text)

        final_text = json.loads(recognizer.FinalResult()).get("text", "")
        if final_text:
            transcripts.append(final_text)

    if not latencies_ms:
        raise AsrStreamingInputError("WAV contains no audio frames")
    return " ".join(transcripts), latencies_ms, sample_rate


def _metric(
    value: float | None,
    *,
    measured: bool,
) -> dict[str, Any]:
    return {
        "value": value,
        "status": "measured" if measured else "placeholder",
    }


def _language_metrics(
    totals: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for language in SUPPORTED_LANGUAGES:
        values = totals.get(language, {})
        reference_words = int(values.get("reference_words", 0))
        errors = int(values.get("errors", 0))
        latencies = list(values.get("latencies", []))
        measured = reference_words > 0
        wer = errors / reference_words * 100 if measured else None
        result[language] = {
            "measured_samples": int(values.get("samples", 0)),
            "wer_percent": round(wer, 2) if wer is not None else None,
            "latency_p95_ms": (
                round(percentile(latencies, 95), 2)
                if latencies
                else None
            ),
        }
    return result


def run(
    dataset_path: Path = DEFAULT_DATASET_PATH,
) -> dict[str, Any]:
    """Run Vosk when possible, otherwise return a valid stub report."""
    report = build_stub_report("asr", ("asr-synthetic-samples",))
    samples = load_samples(dataset_path)
    force_stub = os.environ.get("ASR_BENCH_FORCE_STUB") == "1"
    model_paths = {} if force_stub else discover_model_paths()
    sample_results: list[dict[str, Any]] = []
    totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "errors": 0,
            "reference_words": 0,
            "latencies": [],
            "samples": 0,
        }
    )
    model_cache: dict[Path, Any] = {}
    vosk_error: str | None = None

    try:
        if force_stub:
            raise ImportError("forced stub mode")
        from vosk import KaldiRecognizer, Model
    except (ImportError, OSError) as exc:
        KaldiRecognizer = None
        Model = None
        vosk_error = str(exc)

    for sample in samples:
        sample_id = str(sample.get("id", "unknown"))
        input_data = sample.get("input", {})
        expected = sample.get("expected", {})
        language = (
            input_data.get("language")
            if isinstance(input_data, Mapping)
            else None
        )
        audio_value = (
            input_data.get("audio_path")
            if isinstance(input_data, Mapping)
            else None
        )
        reference = (
            expected.get("text")
            if isinstance(expected, Mapping)
            else None
        )
        result: dict[str, Any] = {
            "id": sample_id,
            "language": language,
            "audio_path": audio_value,
        }

        audio_path = (
            REPOSITORY_ROOT / audio_value
            if isinstance(audio_value, str)
            else None
        )
        model_path = model_paths.get(str(language))
        if vosk_error is not None:
            result.update(status="skipped", reason="vosk_unavailable")
        elif language not in SUPPORTED_LANGUAGES:
            result.update(status="skipped", reason="unsupported_language")
        elif audio_path is None or not audio_path.is_file():
            result.update(status="skipped", reason="audio_not_found")
        elif model_path is None:
            result.update(status="skipped", reason="model_not_found")
        elif not isinstance(reference, str) or not reference.strip():
            result.update(status="skipped", reason="reference_text_missing")
        else:
            try:
                model = model_cache.get(model_path)
                if model is None:
                    model = Model(str(model_path))
                    model_cache[model_path] = model
                hypothesis, latencies, sample_rate = _recognize_wav(
                    audio_path,
                    model,
                    KaldiRecognizer,
                )
                errors, reference_words = word_error_counts(
                    reference,
                    hypothesis,
                )
                wer = (
                    errors / reference_words * 100
                    if reference_words
                    else 0.0
                )
                language_total = totals[str(language)]
                language_total["errors"] += errors
                language_total["reference_words"] += reference_words
                language_total["latencies"].extend(latencies)
                language_total["samples"] += 1
                result.update(
                    status="measured",
                    model=model_path.name,
                    sample_rate_hz=sample_rate,
                    reference=reference,
                    hypothesis=hypothesis,
                    word_errors=errors,
                    reference_words=reference_words,
                    wer_percent=round(wer, 2),
                    latency_p95_ms=round(percentile(latencies, 95), 2),
                )
            except (
                AsrStreamingInputError,
                EOFError,
                OSError,
                RuntimeError,
                ValueError,
                wave.Error,
            ) as exc:
                result.update(
                    status="skipped",
                    reason="invalid_audio_or_model",
                    error=str(exc),
                )
        sample_results.append(result)

    measured_results = [
        result for result in sample_results if result["status"] == "measured"
    ]
    all_errors = sum(
        int(values["errors"]) for values in totals.values()
    )
    all_reference_words = sum(
        int(values["reference_words"]) for values in totals.values()
    )
    all_latencies: list[float] = [
        latency
        for values in totals.values()
        for latency in values["latencies"]
    ]
    measured = bool(measured_results and all_reference_words)
    wer = (
        all_errors / all_reference_words * 100
        if measured
        else None
    )
    measured_languages = {
        str(result["language"]) for result in measured_results
    }

    report["runner_status"] = (
        "stub"
        if not measured
        else (
            "ready"
            if measured_languages == set(SUPPORTED_LANGUAGES)
            else "partial"
        )
    )
    report["requirements"] = list(REQUIREMENTS)
    report["metrics"]["latency_ms"] = {
        "p50": round(percentile(all_latencies, 50), 2),
        "p95": round(percentile(all_latencies, 95), 2),
        "status": "measured" if measured else "placeholder",
    }
    report["metrics"]["wer_percent"] = _metric(
        round(wer, 2) if wer is not None else None,
        measured=measured,
    )
    report["metrics"]["accuracy_percent"] = _metric(
        round(max(0.0, 100 - wer), 2) if wer is not None else None,
        measured=measured,
    )
    try:
        dataset_display_path = dataset_path.relative_to(REPOSITORY_ROOT)
    except ValueError:
        dataset_display_path = dataset_path

    report["suite_details"] = {
        "engine": "vosk" if vosk_error is None else "stub",
        "engine_error": vosk_error,
        "models": {
            language: path.name
            for language, path in model_paths.items()
        },
        "dataset_path": str(dataset_display_path).replace("\\", "/"),
        "chunk_duration_ms": CHUNK_DURATION_MS,
        "measured_samples": len(measured_results),
        "skipped_samples": len(sample_results) - len(measured_results),
        "language_breakdown": _language_metrics(totals),
        "samples": sample_results,
    }
    return report

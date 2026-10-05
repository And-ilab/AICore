"""Local STT for sufler imitation: Vosk on uploaded PCM WAV."""

from __future__ import annotations

import json
import os
import struct
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

MAX_AUDIO_BYTES = 2_000_000
VOSK_SMALL_RU = "vosk-model-small-ru-0.22"
VOSK_SMALL_RU_URL = (
    "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
)

_model_cache: Any = None


class TranscribeError(ValueError):
    """Raised when uploaded audio cannot be transcribed."""


def _read_wav_pcm16(data: bytes) -> tuple[bytes, int]:
    if len(data) < 44 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise TranscribeError("audio must be a PCM WAV file")
    offset = 12
    channels = 1
    sample_rate = 16000
    bits = 16
    pcm = b""
    while offset + 8 <= len(data):
        chunk_id = data[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
        start = offset + 8
        end = start + chunk_size
        if chunk_id == b"fmt " and chunk_size >= 16:
            audio_format, channels, sample_rate, _, _, bits = struct.unpack_from(
                "<HHIIHH",
                data,
                start,
            )
            if audio_format != 1:
                raise TranscribeError("WAV must be uncompressed PCM")
            if channels != 1:
                raise TranscribeError("WAV must be mono")
            if bits != 16:
                raise TranscribeError("WAV must be 16-bit")
        elif chunk_id == b"data":
            pcm = data[start:end]
            break
        offset = end + (chunk_size % 2)
    if not pcm:
        raise TranscribeError("WAV has no PCM data")
    if sample_rate not in {8000, 16000, 22050, 44100, 48000}:
        raise TranscribeError(f"unsupported sample rate: {sample_rate}")
    return pcm, sample_rate


def _looks_like_vosk_model(path: Path) -> bool:
    return path.is_dir() and (
        (path / "am" / "final.mdl").exists()
        or (path / "conf" / "model.conf").exists()
        or (path / "ivector" / "final.dubm").exists()
    )


def _vosk_model_path() -> Path | None:
    configured = os.environ.get("VOSK_MODEL_PATH", "").strip()
    var_dir = Path(__file__).resolve().parents[1] / "var"
    candidates = [
        Path(configured).expanduser() if configured else None,
        var_dir / "vosk-model-ru-0.42",
        var_dir / "vosk-model-ru-0.22",
        var_dir / VOSK_SMALL_RU,
        Path(__file__).resolve().parents[1]
        / "services"
        / "asr"
        / "model"
        / VOSK_SMALL_RU,
        Path(__file__).resolve().parents[2]
        / "recognizer"
        / "model"
        / "vosk-model-ru-0.22",
    ]
    for candidate in candidates:
        if candidate is not None and _looks_like_vosk_model(candidate):
            return candidate
    return None


def _download_enabled() -> bool:
    flag = os.environ.get("VOSK_MODEL_DOWNLOAD", "1").strip().lower()
    return flag not in {"0", "false", "no"}


def _ensure_vosk_model() -> Path | None:
    existing = _vosk_model_path()
    if existing is not None:
        return existing
    if not _download_enabled():
        return None
    dest_parent = Path(__file__).resolve().parents[1] / "var"
    dest = dest_parent / VOSK_SMALL_RU
    dest_parent.mkdir(parents=True, exist_ok=True)
    zip_path = dest_parent / f"{VOSK_SMALL_RU}.zip"
    try:
        urllib.request.urlretrieve(VOSK_SMALL_RU_URL, zip_path)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(dest_parent)
        zip_path.unlink(missing_ok=True)
    except OSError:
        zip_path.unlink(missing_ok=True)
        return None
    if _looks_like_vosk_model(dest):
        return dest
    return None


def _load_vosk_model(model_path: Path) -> Any:
    global _model_cache
    cached_path, cached_model = _model_cache or (None, None)
    if cached_model is not None and cached_path == str(model_path):
        return cached_model
    from vosk import Model, SetLogLevel

    SetLogLevel(-1)
    model = Model(str(model_path))
    _model_cache = (str(model_path), model)
    return model


def _import_kaldi():
    import sys

    try:
        from vosk import KaldiRecognizer
        return KaldiRecognizer
    except ImportError:
        sys.modules.pop("vosk", None)
        sys.modules.pop("vosk.vosk_cffi", None)
    try:
        from vosk import KaldiRecognizer
        return KaldiRecognizer
    except ImportError as exc:
        raise TranscribeError(f"не удалось загрузить vosk: {exc}") from exc


def _transcribe_vosk(pcm: bytes, sample_rate: int) -> str:
    KaldiRecognizer = _import_kaldi()
    model_path = _ensure_vosk_model()
    if model_path is None:
        raise TranscribeError(
            "модель Vosk не найдена. Нужен vosk-model-small-ru-0.22"
        )
    rec = KaldiRecognizer(_load_vosk_model(model_path), sample_rate)
    rec.SetWords(True)
    frame = 4000
    for offset in range(0, len(pcm), frame):
        rec.AcceptWaveform(pcm[offset : offset + frame])
    payload: dict[str, Any] = json.loads(rec.FinalResult())
    return str(payload.get("text") or "").strip()


def transcribe_wav(data: bytes) -> str:
    if not data:
        raise TranscribeError("audio is empty")
    if len(data) > MAX_AUDIO_BYTES:
        raise TranscribeError("audio is too large")
    pcm, sample_rate = _read_wav_pcm16(data)
    text = _transcribe_vosk(pcm, sample_rate)
    if text:
        return text
    raise TranscribeError("could not recognize speech")

"""On-prem ASR for assistant audio/video attachments (§5.1.38).

The original file is streamed to a temp path, compressed to a short-lived WAV,
fed to Vosk in chunks, then both files are deleted. Only the transcript text
leaves this module — no video/audio is kept in RAM or storage.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

from orchestrator.transcribe import (
    TranscribeError,
    _ensure_vosk_model,
    _import_kaldi,
    _load_vosk_model,
)

AUDIO_EXTENSIONS = frozenset(
    {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".flac", ".wma"}
)
VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
)
CHAT_MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
CHAT_MEDIA_MAX_BYTES = 200 * 1024 * 1024
_MAX_PCM_BYTES = 20 * 60 * 16000 * 2
_FFMPEG_TIMEOUT_SECONDS = 180
_SPILL_CHUNK = 1024 * 1024


class MediaAsrError(ValueError):
    """Uploaded audio/video cannot be transcribed."""


def media_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return "audio"


def _ffmpeg_bin() -> str | None:
    return shutil.which("ffmpeg")


def _ffmpeg_to_wav(source: Path, dest: Path) -> None:
    binary = _ffmpeg_bin()
    if not binary:
        raise MediaAsrError(
            "для сжатия видео/аудио нужен ffmpeg на сервере "
            "(WAV PCM можно без него)"
        )
    try:
        proc = subprocess.run(
            [
                binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(dest),
            ],
            capture_output=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaAsrError("слишком долгая обработка аудио/видео") from exc
    except OSError as exc:
        raise MediaAsrError(f"не удалось запустить ffmpeg: {exc}") from exc
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size == 0:
        detail = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise MediaAsrError(detail or "ffmpeg не смог сжать файл в аудио")


def _recognize_speech_from_wav(path: Path) -> str:
    """Feed WAV to Vosk in small frames so PCM is not held as one buffer."""
    try:
        with wave.open(str(path), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                raise MediaAsrError("ожидается моно PCM 16-bit")
            if wav.getcomptype() != "NONE":
                raise MediaAsrError("WAV must be uncompressed PCM")
            sample_rate = wav.getframerate()
            KaldiRecognizer = _import_kaldi()
            model_path = _ensure_vosk_model()
            if model_path is None:
                raise MediaAsrError(
                    "модель Vosk не найдена. Нужен vosk-model-small-ru-0.22"
                )
            rec = KaldiRecognizer(_load_vosk_model(model_path), sample_rate)
            rec.SetWords(True)
            max_frames = _MAX_PCM_BYTES // 2
            seen = 0
            while seen < max_frames:
                frames = wav.readframes(2000)
                if not frames:
                    break
                rec.AcceptWaveform(frames)
                seen += len(frames) // 2
            payload: dict[str, Any] = json.loads(rec.FinalResult())
    except wave.Error as exc:
        raise MediaAsrError("не удалось прочитать сжатое аудио") from exc
    except TranscribeError as exc:
        raise MediaAsrError(str(exc)) from exc
    return str(payload.get("text") or "").strip()


def _spill_upload(uploaded: Any, dest: Path) -> None:
    written = 0
    with dest.open("wb") as out:
        while True:
            chunk = uploaded.read(_SPILL_CHUNK)
            if not chunk:
                break
            written += len(chunk)
            if written > CHAT_MEDIA_MAX_BYTES:
                raise MediaAsrError(
                    f"файл слишком большой; максимум {CHAT_MEDIA_MAX_BYTES} байт"
                )
            out.write(chunk)
    if written == 0:
        raise MediaAsrError("файл пустой")


def _source_from_upload(uploaded: Any, filename: str) -> tuple[Path, bool]:
    """Return (path, owned). Owned temps are deleted by the caller."""
    size = getattr(uploaded, "size", None)
    if isinstance(size, int) and size > CHAT_MEDIA_MAX_BYTES:
        raise MediaAsrError(
            f"файл слишком большой; максимум {CHAT_MEDIA_MAX_BYTES} байт"
        )
    temp_path = getattr(uploaded, "temporary_file_path", None)
    if callable(temp_path):
        path = Path(temp_path())
        if path.is_file():
            return path, False
    suffix = Path(filename).suffix.lower() or ".bin"
    handle = tempfile.NamedTemporaryFile(prefix="asst-media-", suffix=suffix, delete=False)
    path = Path(handle.name)
    handle.close()
    try:
        _spill_upload(uploaded, path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path, True


def _transcribe_path(source: Path, filename: str) -> dict[str, str | bool]:
    kind = media_kind(filename)
    suffix = Path(filename).suffix.lower()
    wav_path: Path | None = None
    compressed = suffix != ".wav"
    try:
        if suffix == ".wav":
            try:
                text = _recognize_speech_from_wav(source)
            except MediaAsrError:
                wav_path = source.with_name(f"{source.name}.asr.wav")
                _ffmpeg_to_wav(source, wav_path)
                text = _recognize_speech_from_wav(wav_path)
                compressed = True
        else:
            wav_path = source.with_name(f"{source.name}.asr.wav")
            _ffmpeg_to_wav(source, wav_path)
            text = _recognize_speech_from_wav(wav_path)
            compressed = True
        if not text:
            raise MediaAsrError("не удалось распознать речь")
        return {
            "text": text,
            "kind": kind,
            "engine": "vosk",
            "compressed": compressed,
        }
    finally:
        if wav_path is not None:
            wav_path.unlink(missing_ok=True)


def transcribe_upload(uploaded: Any, filename: str) -> dict[str, str | bool]:
    """Transcribe an uploaded file without keeping media in memory or storage."""
    source, owned = _source_from_upload(uploaded, filename)
    try:
        return _transcribe_path(source, filename)
    finally:
        if owned:
            source.unlink(missing_ok=True)


def transcribe_media(data: bytes, filename: str) -> dict[str, str | bool]:
    """Test/helper path: spill bytes to a temp file, then same as upload."""
    if not data:
        raise MediaAsrError("файл пустой")
    if len(data) > CHAT_MEDIA_MAX_BYTES:
        raise MediaAsrError(
            f"файл слишком большой; максимум {CHAT_MEDIA_MAX_BYTES} байт"
        )
    suffix = Path(filename).suffix.lower() or ".bin"
    handle = tempfile.NamedTemporaryFile(prefix="asst-media-", suffix=suffix, delete=False)
    path = Path(handle.name)
    try:
        handle.write(data)
        handle.close()
        return _transcribe_path(path, filename)
    finally:
        handle.close()
        path.unlink(missing_ok=True)
        path.with_name(f"{path.name}.asr.wav").unlink(missing_ok=True)

"""Turn 8 kHz PCM from SIP RTP into live text for the sufler window."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

from django.conf import settings

from integrations.oktell.g711 import upsample_8k_to_16k

logger = logging.getLogger(__name__)

# ~300 ms of PCM16 @ 8 kHz. Short frames so the line grows during the call.
_CHUNK_BYTES_8K = 4800
# Drop ~2 s of ringback / IVR at the start of a barge (same window as the old 2×1 s skip).
_SKIP_START_CHUNKS = 7
_NUMBER_WORDS = {
    "ноль",
    "один",
    "одна",
    "два",
    "две",
    "три",
    "четыре",
    "пять",
    "шесть",
    "семь",
    "восемь",
    "девять",
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятьнадцать",
    "шестьнадцать",
    "семьнадцать",
    "восемьнадцать",
    "девятьнадцать",
    "двадцать",
    "тридцать",
    "сорок",
    "пятьдесят",
    "шестьдесят",
    "семьдесят",
    "восемьдесят",
    "девяносто",
    "сто",
}


def is_ivr_garbage(text: str) -> bool:
    tokens = [part for part in text.lower().replace("-", " ").split() if part]
    if not tokens:
        return True
    return all(token in _NUMBER_WORDS or token.isdigit() for token in tokens)


def _looks_like_vosk_model(path: Path) -> bool:
    return path.is_dir() and (
        (path / "am" / "final.mdl").exists()
        or (path / "conf" / "model.conf").exists()
        or (path / "ivector" / "final.dubm").exists()
    )


_MODEL: Any = None
_MODEL_KEY = ""
_MODEL_LOCK = threading.Lock()


def _candidate_paths() -> list[Path]:
    """Prefer the full Russian model. A missing configured path falls through to small."""
    configured = str(getattr(settings, "VOSK_MODEL_PATH", "") or "").strip()
    service_dir = Path(__file__).resolve().parents[2] / "services" / "asr"
    var_dir = Path(__file__).resolve().parents[2] / "var"
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    candidates.extend(
        [
            var_dir / "vosk-model-ru-0.42",
            var_dir / "vosk-model-ru-0.22",
            var_dir / "vosk-model-small-ru-0.22",
            service_dir / "model" / "vosk-model-ru-0.42",
            service_dir / "model" / "vosk-model-ru-0.22",
            service_dir / "model" / "vosk-model-small-ru-0.22",
            service_dir.parents[2] / "recognizer" / "model" / "vosk-model-ru-0.42",
            service_dir.parents[2] / "recognizer" / "model" / "vosk-model-ru-0.22",
        ]
    )
    try:
        from hub.model_catalog import prioritize_speech_paths

        return prioritize_speech_paths(candidates)
    except Exception:
        return candidates


def _model_path() -> Path | None:
    for path in _candidate_paths():
        if _looks_like_vosk_model(path):
            return path
    return None


def _shared_model() -> Any:
    global _MODEL, _MODEL_KEY
    path = _model_path()
    if path is None:
        return None
    key = str(path)
    if _MODEL is not None and _MODEL_KEY == key:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL is not None and _MODEL_KEY == key:
            return _MODEL
        from vosk import Model

        logger.info("Loading Vosk model %s", key)
        _MODEL = Model(key)
        _MODEL_KEY = key
        return _MODEL


class LegTranscriber:
    """Buffer RTP PCM and emit Vosk partials, then a final. No-op if the model is missing."""

    def __init__(self, on_text: Callable[[str, bool], None]) -> None:
        self.on_text = on_text
        self._buffer = bytearray()
        self._recognizer = None
        self._chunks = 0
        self._last_partial = ""
        model = _shared_model()
        if model is None:
            logger.warning("Vosk model missing; SIP audio will not become text")
            return
        try:
            from vosk import KaldiRecognizer

            self._recognizer = KaldiRecognizer(model, 16000)
            self._recognizer.SetWords(True)
        except Exception:  # noqa: BLE001 — live path must not kill the call
            logger.exception("could not start Vosk for SIP leg")
            self._recognizer = None

    @property
    def ready(self) -> bool:
        return self._recognizer is not None

    def feed(self, pcm8k: bytes) -> None:
        if not pcm8k or self._recognizer is None:
            return
        self._buffer.extend(pcm8k)
        while len(self._buffer) >= _CHUNK_BYTES_8K:
            chunk = bytes(self._buffer[:_CHUNK_BYTES_8K])
            del self._buffer[:_CHUNK_BYTES_8K]
            self._chunks += 1
            if self._chunks <= _SKIP_START_CHUNKS:
                continue
            self._accept(upsample_8k_to_16k(chunk))

    def _emit(self, text: str, *, is_final: bool) -> None:
        cleaned = text.strip()
        if not cleaned or is_ivr_garbage(cleaned):
            if is_final:
                self._last_partial = ""
            return
        if not is_final:
            if cleaned == self._last_partial:
                return
            self._last_partial = cleaned
        else:
            self._last_partial = ""
        self.on_text(cleaned, is_final)

    def _accept(self, pcm16k: bytes) -> None:
        assert self._recognizer is not None
        import json

        if self._recognizer.AcceptWaveform(pcm16k):
            payload = json.loads(self._recognizer.Result() or "{}")
            self._emit(str(payload.get("text") or ""), is_final=True)
            return
        payload = json.loads(self._recognizer.PartialResult() or "{}")
        self._emit(str(payload.get("partial") or ""), is_final=False)

    def close(self) -> None:
        if self._recognizer is None:
            return
        import json

        leftover = bytes(self._buffer)
        self._buffer.clear()
        if leftover:
            self._accept(upsample_8k_to_16k(leftover))
        payload = json.loads(self._recognizer.FinalResult() or "{}")
        self._emit(str(payload.get("text") or ""), is_final=True)
        self._recognizer = None

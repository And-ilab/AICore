import os
import struct
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

from unittest.mock import patch

from orchestrator.transcribe import TranscribeError, transcribe_wav  # noqa: E402


def _silent_wav(samples: int = 1600, sample_rate: int = 16000) -> bytes:
    pcm = b"\x00\x00" * samples
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        sample_rate * 2,
        2,
        16,
        b"data",
        len(pcm),
    )
    return header + pcm


class TranscribeWavTest(unittest.TestCase):
    def test_rejects_non_wav(self):
        with self.assertRaises(TranscribeError):
            transcribe_wav(b"not-a-wav")

    def test_silent_wav_has_no_speech(self):
        with patch("orchestrator.transcribe._transcribe_vosk", return_value=""):
            with self.assertRaises(TranscribeError) as raised:
                transcribe_wav(_silent_wav())
        self.assertIn("recognize", str(raised.exception).lower())

    def test_returns_recognized_text(self):
        with patch(
            "orchestrator.transcribe._transcribe_vosk",
            return_value="добрый день",
        ):
            self.assertEqual(transcribe_wav(_silent_wav()), "добрый день")


if __name__ == "__main__":
    unittest.main()

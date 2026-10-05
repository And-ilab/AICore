import json
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from benchmarks.suites.asr_streaming import (
    _recognize_wav,
    percentile,
    run,
    word_error_counts,
)


class FakeRecognizer:
    def __init__(self, _model, _sample_rate):
        self.chunks = 0

    def SetWords(self, _enabled):
        return None

    def AcceptWaveform(self, _chunk):
        self.chunks += 1
        return False

    def FinalResult(self):
        return json.dumps({"text": "тестовая фраза"})


class AsrStreamingBenchmarkTest(unittest.TestCase):
    def test_word_error_counts_uses_word_levenshtein_distance(self):
        errors, reference_words = word_error_counts(
            "one two three four",
            "one two tree four",
        )

        self.assertEqual(errors, 1)
        self.assertEqual(reference_words, 4)

    def test_percentile_interpolates_values(self):
        self.assertAlmostEqual(
            percentile([1.0, 2.0, 3.0, 4.0], 95),
            3.85,
        )
        self.assertEqual(percentile([], 95), 0.0)

    def test_streams_pcm_wav_in_chunks(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            audio_path = Path(temporary_directory) / "sample.wav"
            with wave.open(str(audio_path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b"\x00\x00" * 1600)

            transcript, latencies, sample_rate = _recognize_wav(
                audio_path,
                object(),
                FakeRecognizer,
            )

        self.assertEqual(transcript, "тестовая фраза")
        self.assertEqual(sample_rate, 16000)
        self.assertEqual(len(latencies), 1)
        self.assertGreaterEqual(latencies[0], 0)

    def test_stub_report_contains_bilingual_placeholders(self):
        with patch.dict(
            os.environ,
            {"ASR_BENCH_FORCE_STUB": "1"},
            clear=False,
        ):
            report = run()

        self.assertEqual(report["runner_status"], "stub")
        self.assertIsNone(report["metrics"]["wer_percent"]["value"])
        self.assertEqual(
            set(report["suite_details"]["language_breakdown"]),
            {"ru", "en"},
        )
        self.assertEqual(report["suite_details"]["measured_samples"], 0)
        self.assertEqual(report["suite_details"]["skipped_samples"], 12)


if __name__ == "__main__":
    unittest.main()

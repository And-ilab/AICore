import os
import struct
import sys
from pathlib import Path
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import Client, TestCase  # noqa: E402

from assistant.idp import SUMMARY_INSTRUCTION_MEDIA, build_attachment_prompt  # noqa: E402
from assistant.media_asr import MediaAsrError, transcribe_media  # noqa: E402
from auth.roles import ROLES_BY_CODE  # noqa: E402


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


class MediaAsrTest(TestCase):
    def test_transcribe_wav_uses_vosk(self):
        with patch(
            "assistant.media_asr._recognize_speech_from_wav",
            return_value="добрый день, это запись консультации",
        ):
            result = transcribe_media(_silent_wav(), "call.wav")
        self.assertEqual(result["kind"], "audio")
        self.assertEqual(result["engine"], "vosk")
        self.assertFalse(result["compressed"])
        self.assertIn("консультации", result["text"])

    def test_video_is_compressed_to_audio(self):
        def fake_ffmpeg(source, dest):
            dest.write_bytes(_silent_wav())

        with (
            patch("assistant.media_asr._ffmpeg_to_wav", side_effect=fake_ffmpeg),
            patch(
                "assistant.media_asr._recognize_speech_from_wav",
                return_value="обслуживание карты первый год бесплатно",
            ),
        ):
            result = transcribe_media(b"fake-mp4-bytes", "dialog.mp4")
        self.assertEqual(result["kind"], "video")
        self.assertTrue(result["compressed"])
        self.assertNotIn("audio_bytes", result)
        self.assertIn("бесплатно", result["text"])

    def test_empty_speech_is_an_error(self):
        with patch("assistant.media_asr._recognize_speech_from_wav", return_value=""):
            with self.assertRaises(MediaAsrError):
                transcribe_media(_silent_wav(), "silence.wav")

    def test_idp_media_summary_prompt(self):
        prompt = build_attachment_prompt(
            [
                {
                    "name": "meeting.mp4",
                    "type": "mp4",
                    "text": "Клиент просит автокредит на пять лет. Нужен паспорт.",
                    "media": {"kind": "video", "engine": "vosk"},
                }
            ],
            "",
        )
        self.assertIn(SUMMARY_INSTRUCTION_MEDIA[:40], prompt)
        self.assertIn("автокредит", prompt)
        self.assertIn("саммаризация", prompt)

    def test_extract_wav_returns_transcript(self):
        role = ROLES_BY_CODE["ai_assistant_user"]
        user = get_user_model().objects.create_user(
            username="media-asr-user",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        client = Client()
        client.force_login(user)
        with patch(
            "assistant.views.transcribe_upload",
            return_value={
                "text": "нужен паспорт и справка о доходах",
                "kind": "audio",
                "engine": "vosk",
                "compressed": False,
            },
        ):
            response = client.post(
                "/api/v1/assistant/attachments/extract",
                {
                    "file": SimpleUploadedFile(
                        "call.wav",
                        _silent_wav(),
                        content_type="audio/wav",
                    )
                },
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["text"], "нужен паспорт и справка о доходах")
        self.assertEqual(body["media"]["kind"], "audio")
        self.assertEqual(body["type"], "wav")

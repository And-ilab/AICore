"""Live Oktell ASR partials and non-blocking KB hints."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.test import SimpleTestCase, TestCase  # noqa: E402

from core.model_gateway import ModelGateway  # noqa: E402
from integrations.oktell.bridge import publish_transcript  # noqa: E402
from integrations.oktell.live_asr import (  # noqa: E402
    LegTranscriber,
    _CHUNK_BYTES_8K,
    _model_path,
)
from orchestrator.sufler import _build_messages, preview_hints, suggest  # noqa: E402


def _touch_model(path: Path) -> None:
    conf = path / "conf"
    conf.mkdir(parents=True, exist_ok=True)
    (conf / "model.conf").write_text("x", encoding="utf-8")


class _FakeRecognizer:
    def __init__(self) -> None:
        self.calls = 0

    def SetWords(self, enabled: bool) -> None:
        del enabled

    def AcceptWaveform(self, pcm: bytes) -> bool:
        del pcm
        self.calls += 1
        return self.calls >= 2

    def Result(self) -> str:
        return json.dumps({"text": "хочу кредит"})

    def PartialResult(self) -> str:
        return json.dumps({"partial": "хочу"})

    def FinalResult(self) -> str:
        return json.dumps({"text": ""})


class LiveAsrPathTests(SimpleTestCase):
    def test_missing_configured_model_falls_through_to_full_ru(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "vosk-model-ru-0.42"
            full = root / "installed-ru-0.42"
            small = root / "vosk-model-small-ru-0.22"
            _touch_model(full)
            _touch_model(small)
            with patch(
                "integrations.oktell.live_asr._candidate_paths",
                return_value=[missing, full, small],
            ):
                self.assertEqual(_model_path(), full)

    def test_partial_then_final_from_short_frames(self):
        heard: list[tuple[str, bool]] = []
        transcriber = LegTranscriber.__new__(LegTranscriber)
        transcriber.on_text = lambda text, is_final: heard.append((text, is_final))
        transcriber._buffer = bytearray()
        transcriber._recognizer = _FakeRecognizer()
        transcriber._chunks = 0
        transcriber._last_partial = ""
        with patch("integrations.oktell.live_asr._SKIP_START_CHUNKS", 0):
            transcriber.feed(b"\x00" * (_CHUNK_BYTES_8K * 2))
        self.assertEqual(heard, [("хочу", False), ("хочу кредит", True)])


class LiveHintDispatchTests(SimpleTestCase):
    def test_transcript_returns_before_suggest_and_raw_snippet_is_hidden(self):
        gate = threading.Event()
        payloads: list[dict] = []

        def capture(_call_id: str, payload: dict) -> None:
            payloads.append(payload)

        def slow_suggest(*_args, **_kwargs):
            gate.wait(3)
            return {
                "query": "хочу кредит",
                "hints": [{"text": "формулировка deepseek", "rank": 1}],
                "latency_ms": {"total": 1},
                "request_id": "req-1",
                "blocked_reason": None,
                "scenario": None,
                "suggested_scenario": None,
            }

        with (
            patch("integrations.oktell.bridge.publish_to_call", side_effect=capture),
            patch("integrations.oktell.bridge.suggest", side_effect=slow_suggest),
        ):
            started = time.perf_counter()
            publish_transcript(
                "live",
                speaker="client",
                text="хочу кредит",
                turn_id="live-client-1",
                is_final=True,
            )
            self.assertLess(time.perf_counter() - started, 0.4)
            time.sleep(0.3)
            self.assertFalse(
                any(
                    hint.get("text") == "формулировка deepseek"
                    for payload in payloads
                    for hint in (payload.get("hints") or [])
                )
            )
            gate.set()
            deadline = time.perf_counter() + 2
            while time.perf_counter() < deadline:
                if any(
                    hint.get("text") == "формулировка deepseek"
                    for payload in payloads
                    for hint in (payload.get("hints") or [])
                ):
                    break
                time.sleep(0.02)
        hint_texts = [
            hint.get("text")
            for payload in payloads
            if payload.get("type") == "hints"
            for hint in (payload.get("hints") or [])
        ]
        self.assertEqual(hint_texts, ["формулировка deepseek"])

    def test_slow_suggest_does_not_block_later_previews(self):
        release = threading.Event()
        payloads: list[dict] = []
        suggest_calls = {"n": 0}

        def capture(_call_id: str, payload: dict) -> None:
            payloads.append(payload)

        def slow_suggest(*_args, **_kwargs):
            suggest_calls["n"] += 1
            release.wait(3)
            return {
                "query": "один",
                "hints": [],
                "latency_ms": {"total": 1},
                "request_id": "req-slow",
                "blocked_reason": "no_relevant_knowledge",
            }

        with (
            patch("integrations.oktell.bridge.publish_to_call", side_effect=capture),
            patch("integrations.oktell.bridge.suggest", side_effect=slow_suggest),
            patch("integrations.oktell.bridge._SUGGEST_SECONDS", 0.2),
        ):
            for text in ("один", "два", "три"):
                publish_transcript(
                    "live",
                    speaker="client",
                    text=text,
                    turn_id=f"live-client-{text}",
                    is_final=True,
                )
            deadline = time.perf_counter() + 2
            while suggest_calls["n"] < 2 and time.perf_counter() < deadline:
                time.sleep(0.02)
            self.assertGreaterEqual(suggest_calls["n"], 2)
            release.set()
            finished = time.perf_counter() + 2
            while suggest_calls["n"] < 3 and time.perf_counter() < finished:
                time.sleep(0.02)
        self.assertEqual(suggest_calls["n"], 3)


_CREDIT_DOC = {
    "rank": 1,
    "article_id": 8802,
    "chunk_index": 0,
    "title": "Потребительский кредит",
    "content": "Чтобы взять деньги в кредит, клиент предъявляет паспорт в отделении.",
    "snippet": "Чтобы взять деньги в кредит, клиент предъявляет паспорт в отделении.",
    "permalink": "https://suz.local/articles/8802",
    "relevance_score": 0.81,
    "relevance_percent": 81,
}


class TelephonyFragmentTests(TestCase):
    def test_greeting_preview_stays_empty(self):
        preview = preview_hints("здравствуйте", channel="telephony")
        self.assertEqual(preview["hints"], [])
        self.assertEqual(preview["blocked_reason"], "no_hint_needed")

    def test_telephony_fragment_searches_and_plain_replica_does_not(self):
        def _fake_chat(self, profile, messages, **kwargs):
            del self, profile, messages, kwargs
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "ОТВЕТ:\nЧтобы взять деньги в кредит, клиент "
                                "предъявляет паспорт в отделении.\nСОВЕТ:\n"
                            )
                        }
                    }
                ]
            }

        with (
            patch(
                "orchestrator.sufler._retrieve_documents",
                return_value=({"documents": [_CREDIT_DOC]}, "cc_production"),
            ),
            patch.object(ModelGateway, "chat", _fake_chat),
        ):
            preview = preview_hints("Хочу взять деньги в.", channel="telephony")
            phone = suggest(
                "Хочу взять деньги в.",
                channel="telephony",
                session_id="tel-fragment",
                gateway=ModelGateway.from_registry(),
            )
            plain = suggest(
                "Хочу взять деньги в.",
                session_id="plain-fragment",
                gateway=ModelGateway.from_registry(),
            )
        self.assertTrue(preview["hints"])
        self.assertEqual(preview["hints"][0]["source_type"], "knowledge_base")
        self.assertNotEqual(phone["blocked_reason"], "no_hint_needed")
        self.assertTrue(phone["hints"])
        self.assertEqual(plain["blocked_reason"], "no_hint_needed")
        self.assertEqual(plain["hints"], [])


class CleanHintTests(TestCase):
    def test_ordinary_replica_does_not_search(self) -> None:
        with patch(
            "orchestrator.sufler._retrieve_documents",
            side_effect=AssertionError("ordinary replica must not search"),
        ):
            for phrase in ("не было этого", "а вот какие"):
                result = suggest(
                    phrase,
                    channel="telephony",
                    session_id=f"ordinary-{phrase}",
                    gateway=ModelGateway.from_registry(),
                )
                self.assertEqual(result["hints"], [])
                self.assertEqual(result["blocked_reason"], "no_hint_needed")

    def test_greeting_and_introduction_do_not_search(self) -> None:
        phrases = (
            "Здравствуйте",
            "Добрый день",
            "Добрый день, меня зовут Анна",
            "Меня зовут Иван Петрович",
        )
        with patch(
            "orchestrator.sufler._retrieve_documents",
            side_effect=AssertionError("social replica must not search"),
        ), patch(
            "orchestrator.sufler.resolve_scenario_turn",
            side_effect=AssertionError("social replica must not open a scenario"),
        ):
            for phrase in phrases:
                result = suggest(
                    phrase,
                    channel="telephony",
                    session_id=f"social-{phrase}",
                    gateway=ModelGateway.from_registry(),
                )
                self.assertEqual(result["hints"], [])
                self.assertEqual(result["blocked_reason"], "no_hint_needed")

    def test_junk_title_is_not_a_hint(self) -> None:
        junk = {
            **_CREDIT_DOC,
            "title": "503 агент 07.09 no send",
            "content": "Детальное описание",
            "snippet": "Детальное описание",
        }
        with patch(
            "orchestrator.sufler._retrieve_documents",
            return_value=({"documents": [junk]}, "cc_production"),
        ):
            result = suggest(
                "как оформить кредит на машину",
                channel="telephony",
                kb_slugs=["credits"],
                session_id="junk-title",
                gateway=ModelGateway.from_registry(),
            )
        knowledge = [
            hint for hint in result["hints"] if hint.get("source_type") != "scenario"
        ]
        self.assertEqual(knowledge, [])
        self.assertFalse(
            any("no send" in str(hint.get("text") or "").lower() for hint in result["hints"])
        )

    def test_title_only_document_is_dropped(self) -> None:
        echo = {
            **_CREDIT_DOC,
            "title": "Детальное описание",
            "content": "Детальное описание",
            "snippet": "Детальное описание",
        }
        with patch(
            "orchestrator.sufler._retrieve_documents",
            return_value=({"documents": [echo]}, "cc_production"),
        ):
            result = suggest(
                "как оформить кредит",
                channel="telephony",
                session_id="title-only",
                gateway=ModelGateway.from_registry(),
            )
        self.assertEqual(result["hints"], [])

    def test_telephony_kb_card_uses_a_short_model_call(self) -> None:
        seen: dict[str, int] = {}

        def _fake_chat(self, profile, messages, **kwargs):
            del self, profile, messages
            seen["max_tokens"] = int(kwargs["max_tokens"])
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "ОТВЕТ:\nЧтобы взять деньги в кредит, клиент "
                                "предъявляет паспорт в отделении.\n"
                                "ПОДРОБНЕЕ:\n\nСОВЕТ:\n"
                            )
                        }
                    }
                ]
            }

        with patch(
            "orchestrator.sufler._retrieve_documents",
            return_value=({"documents": [_CREDIT_DOC]}, "cc_production"),
        ), patch("orchestrator.sufler.ModelGateway.chat", _fake_chat):
            result = suggest(
                "как оформить кредит",
                channel="telephony",
                session_id="fast-kb",
                gateway=ModelGateway.from_registry(),
            )
        self.assertEqual(seen["max_tokens"], 200)
        self.assertTrue(result["hints"])
        self.assertIn("паспорт", result["hints"][0]["text"].lower())

    def test_live_prompt_uses_the_matching_clause_not_the_header(self) -> None:
        header = (
            "Материальная помощь оказывается в связи со смертью работника. "
            "Решение принимается по заявлению установленной формы. "
        )
        document = {
            **_CREDIT_DOC,
            "title": "Положение о материальной помощи",
            "content": header * 30
            + "Если банк с начала года работает в убытке, материальная помощь не выплачивается.",
            "snippet": "",
        }
        messages = _build_messages(
            "платят ли материальную помощь если банк с начала года в убытке",
            [document],
            brief=True,
        )
        prompt = messages[-1]["content"]
        self.assertIn("убытке", prompt)
        self.assertLess(prompt.count("смертью"), document["content"].count("смертью"))

    def test_real_question_without_a_document_says_nothing_matched(self) -> None:
        with patch(
            "orchestrator.sufler._retrieve_documents",
            return_value=({"documents": []}, "cc_production"),
        ):
            result = suggest(
                "как оформить материнский капитал",
                channel="telephony",
                session_id="no-doc",
                gateway=ModelGateway.from_registry(),
            )
        self.assertEqual(result["hints"], [])
        self.assertEqual(result["blocked_reason"], "sufler_unavailable")


class ProfanityAndCallerMemoryTests(TestCase):
    def test_swear_word_becomes_asterisks_of_the_same_length(self) -> None:
        from integrations.oktell.profanity import mask_profanity

        masked = mask_profanity("ну блять же")
        self.assertEqual(masked, "ну ***** же")
        self.assertNotIn("блять", masked)

    def test_publish_masks_the_replica_and_keeps_the_hint_query(self) -> None:
        seen: list[dict] = []
        queries: list[str] = []

        def _capture(_call_id: str, payload: dict) -> None:
            seen.append(payload)

        def _submit(fn, call_id, text, turn_id) -> None:
            del fn, call_id, turn_id
            queries.append(text)

        with (
            patch("integrations.oktell.bridge.publish_to_call", side_effect=_capture),
            patch("integrations.oktell.bridge._HINT_POOL.submit", side_effect=_submit),
        ):
            publish_transcript(
                "live",
                speaker="client",
                text="ну блять как кредит",
                turn_id="mask-1",
                is_final=True,
            )
        self.assertEqual(seen[0]["text"], "ну ***** как кредит")
        self.assertEqual(queries, ["ну блять как кредит"])

    def test_previous_question_is_kept_by_phone_and_not_by_placeholder(self) -> None:
        from integrations.oktell.caller_memory import (
            previous_call,
            remember_client_question,
        )

        remember_client_question("sufler", "хочу кредит на машину")
        self.assertEqual(previous_call("sufler"), ("", ""))
        remember_client_question("+375291112233", "хочу кредит на машину")
        question, asked_at = previous_call("375291112233")
        self.assertEqual(question, "хочу кредит на машину")
        self.assertTrue(asked_at)
        other, _other_at = previous_call("+375447770099")
        self.assertEqual(other, "")

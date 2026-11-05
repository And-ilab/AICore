import json
import logging
import os
import sys
import tempfile
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
from django.test import Client, SimpleTestCase, TestCase  # noqa: E402

from assistant.chat import AssistantChatError, iter_chat_sse  # noqa: E402
from assistant.path_log import log_path  # noqa: E402
from auth.roles import ROLES_BY_CODE  # noqa: E402
from core.model_gateway import ModelGatewayConfigurationError  # noqa: E402
from sufler.logging_config import _log_name, build_logging  # noqa: E402


QUESTION = "PATHLOG_QUESTION_MARKER как оформить вклад"
HISTORY = "PATHLOG_HISTORY_MARKER предыдущая реплика"
FRAGMENT = "PATHLOG_FRAGMENT_MARKER текст фрагмента базы"
ANSWER = "PATHLOG_ANSWER_MARKER ответ модели"


class _ListHandler(logging.Handler):
    def __init__(self, bucket: list[logging.LogRecord]) -> None:
        super().__init__(level=logging.INFO)
        self.bucket = bucket

    def emit(self, record: logging.LogRecord) -> None:
        self.bucket.append(record)


class PathLogCapture:
    def __init__(self) -> None:
        self.records: list[logging.LogRecord] = []
        self.logger = logging.getLogger("assistant.path")
        self._level = self.logger.level
        self._propagate = self.logger.propagate
        self.handler = _ListHandler(self.records)

    def __enter__(self) -> "PathLogCapture":
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(self.handler)
        return self

    def __exit__(self, *args: object) -> None:
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self._level)
        self.logger.propagate = self._propagate

    def payloads(self) -> list[dict]:
        return [json.loads(record.getMessage()) for record in self.records]


def _sse_text(frames: list[str]) -> str:
    text = ""
    for frame in frames:
        stripped = frame.lstrip()
        if not stripped.startswith("data:"):
            continue
        payload = stripped[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        chunk = json.loads(payload)
        delta = chunk["choices"][0].get("delta") or {}
        text += delta.get("content") or ""
    return text


def _stream_answer(profile, messages, **params):
    del profile, messages, params
    yield (
        "data: "
        + json.dumps(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": ANSWER},
                        "finish_reason": "stop",
                    }
                ]
            },
            ensure_ascii=False,
        )
        + "\n\n"
    )
    yield "data: [DONE]\n\n"


def _document() -> dict:
    return {
        "rank": 1,
        "title": "Вклад",
        "kb_slug": "assistant_hr",
        "article_id": 1,
        "chunk_index": 0,
        "permalink": "https://example.test/deposit",
        "content": FRAGMENT,
        "snippet": FRAGMENT,
        "relevance_score": 0.9,
        "relevance_percent": 90,
    }


class PathLogWriterTest(SimpleTestCase):
    def test_one_json_line_rounds_milliseconds(self):
        with PathLogCapture() as captured:
            log_path(
                {
                    "path": "preview",
                    "retrieval_ms": 1.26,
                    "total_ms": None,
                    "hint_chars": 4,
                }
            )
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].levelno, logging.INFO)
        self.assertEqual(captured.records[0].name, "assistant.path")
        payload = captured.payloads()[0]
        self.assertEqual(payload["retrieval_ms"], 1.3)
        self.assertIsNone(payload["total_ms"])
        self.assertEqual(payload["hint_chars"], 4)

    def test_logger_failure_does_not_propagate(self):
        with patch("assistant.path_log.logger.info", side_effect=RuntimeError("disk")):
            log_path({"path": "chat", "total_ms": 1})


class LoggingConfigTest(SimpleTestCase):
    def test_pytest_does_not_open_log_files(self):
        config = build_logging(base_dir=BACKEND_ROOT, debug=False)
        self.assertEqual(
            config,
            {"version": 1, "disable_existing_loggers": False},
        )

    def test_assistant_path_logger_is_separate_from_the_root_file(self):
        from sufler import logging_config

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(logging_config, "_running_tests", return_value=False):
                config = logging_config.build_logging(
                    base_dir=Path(tmp),
                    debug=False,
                )
        logger_cfg = config["loggers"]["assistant.path"]
        self.assertFalse(logger_cfg["propagate"])
        self.assertEqual(logger_cfg["level"], "INFO")
        self.assertEqual(logger_cfg["handlers"], ["assistant_path_file"])
        self.assertNotIn("assistant_path_file", config["root"]["handlers"])
        handler = config["handlers"]["assistant_path_file"]
        self.assertEqual(handler["class"], "logging.handlers.RotatingFileHandler")
        self.assertEqual(handler["maxBytes"], 5 * 1024 * 1024)
        self.assertEqual(handler["backupCount"], 5)
        self.assertEqual(handler["encoding"], "utf-8")
        self.assertEqual(handler["formatter"], "standard")
        self.assertEqual(handler["filters"], ["request_id"])
        self.assertTrue(
            handler["filename"].endswith(f"{_log_name()}.assistant-path.log")
        )


class AssistantChatPathLogTest(TestCase):
    def _messages(self):
        return [
            {"role": "assistant", "content": HISTORY},
            {"role": "user", "content": QUESTION},
        ]

    def _assert_no_text(self, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(QUESTION, raw)
        self.assertNotIn(HISTORY, raw)
        self.assertNotIn(FRAGMENT, raw)
        self.assertNotIn(ANSWER, raw)
        self.assertNotIn("tester", raw)

    def _assert_token_fields_empty(self, payload: dict) -> None:
        self.assertIsNone(payload["ttft_ms"])
        self.assertIsNone(payload["preview_text_ms"])
        self.assertIsNone(payload["first_text_ms"])
        self.assertIsInstance(payload["total_ms"], (int, float))

    def test_content_filter_skips_retrieval_and_tokens(self):
        with PathLogCapture() as captured:
            frames = list(
                iter_chat_sse(
                    [{"role": "user", "content": "Расскажи про выборы и депутатов"}],
                    request_id="req-filter",
                    actor="tester",
                )
            )
        self.assertTrue(frames)
        payload = captured.payloads()[-1]
        self.assertEqual(payload["path"], "chat")
        self.assertEqual(payload["outcome"], "content_filter")
        self.assertEqual(payload["request_id"], "req-filter")
        self.assertEqual(payload["profile"], "assistant_bank")
        self.assertIsNone(payload["retrieval_ms"])
        self.assertIsNone(payload["prompt_ms"])
        self.assertIsNone(payload["rag_chars"])
        self.assertIsNone(payload["prompt_chars"])
        self.assertIsNone(payload["max_tokens"])
        self._assert_token_fields_empty(payload)
        self.assertNotIn("Расскажи про выборы", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("tester", json.dumps(payload, ensure_ascii=False))

    def test_no_kb_records_retrieval_without_tokens(self):
        with PathLogCapture() as captured:
            with patch(
                "assistant.chat.retrieve_assistant_context",
                return_value=([], 0.2),
            ):
                frames = list(
                    iter_chat_sse(
                        self._messages(),
                        kb_slugs=["assistant_hr"],
                        request_id="req-empty",
                        expand=True,
                    )
                )
        self.assertTrue(any("нет информации" in frame for frame in frames))
        payload = captured.payloads()[-1]
        self.assertEqual(payload["outcome"], "no_kb")
        self.assertTrue(payload["expand"])
        self.assertEqual(payload["kb_count"], 1)
        self.assertEqual(payload["doc_count"], 0)
        self.assertEqual(payload["history_count"], 2)
        self.assertIsNone(payload["top_relevance"])
        self.assertIsInstance(payload["filter_ms"], (int, float))
        self.assertIsInstance(payload["retrieval_ms"], (int, float))
        self.assertIsInstance(payload["max_tokens"], int)
        self.assertIsNone(payload["prompt_ms"])
        self._assert_token_fields_empty(payload)
        self._assert_no_text(payload)

    def test_streamed_records_first_token_and_generation(self):
        gateway = type("Gateway", (), {"stream": staticmethod(_stream_answer)})()
        with PathLogCapture() as captured:
            with patch(
                "assistant.chat.retrieve_assistant_context",
                return_value=([_document()], 0.2),
            ):
                frames = list(
                    iter_chat_sse(
                        self._messages(),
                        kb_slugs=["assistant_hr", "cc_production"],
                        gateway=gateway,
                        request_id="req-stream",
                    )
                )
        self.assertIn(ANSWER, _sse_text(frames))
        payload = captured.payloads()[-1]
        self.assertEqual(payload["outcome"], "streamed")
        self.assertEqual(payload["doc_count"], 1)
        self.assertEqual(payload["kb_count"], 2)
        self.assertEqual(payload["top_relevance"], 90)
        self.assertIsInstance(payload["prompt_ms"], (int, float))
        self.assertIsInstance(payload["prompt_chars"], int)
        self.assertGreater(payload["prompt_chars"], 0)
        self.assertEqual(payload["rag_chars"], len(FRAGMENT))
        self.assertIsInstance(payload["llm_ms"], (int, float))
        self.assertEqual(payload["ttft_ms"], payload["preview_text_ms"])
        self.assertEqual(payload["ttft_ms"], payload["first_text_ms"])
        self.assertIsNotNone(payload["ttft_ms"])
        self.assertIsInstance(payload["preset"], str)
        self._assert_no_text(payload)

    def test_llm_error_keeps_the_sse_error_and_skips_token_time(self):
        def stream(profile, messages, **params):
            del profile, messages, params
            raise RuntimeError("PATHLOG_LLM_BOOM")

        gateway = type("Gateway", (), {"stream": staticmethod(stream)})()
        with PathLogCapture() as captured:
            with patch(
                "assistant.chat.retrieve_assistant_context",
                return_value=([_document()], 0.2),
            ):
                frames = list(
                    iter_chat_sse(
                        self._messages(),
                        gateway=gateway,
                        request_id="req-llm",
                    )
                )
        self.assertIn("PATHLOG_LLM_BOOM", _sse_text(frames))
        payload = captured.payloads()[-1]
        self.assertEqual(payload["outcome"], "llm_error")
        self._assert_token_fields_empty(payload)
        self.assertNotIn("PATHLOG_LLM_BOOM", json.dumps(payload, ensure_ascii=False))
        self._assert_no_text(payload)

    def test_gateway_configuration_error_is_logged_and_reraised(self):
        def stream(profile, messages, **params):
            del profile, messages, params
            raise ModelGatewayConfigurationError("model is not configured")

        gateway = type("Gateway", (), {"stream": staticmethod(stream)})()
        with PathLogCapture() as captured:
            with patch(
                "assistant.chat.retrieve_assistant_context",
                return_value=([_document()], 0.2),
            ):
                with self.assertRaises(AssistantChatError):
                    list(
                        iter_chat_sse(
                            self._messages(),
                            gateway=gateway,
                            request_id="req-config",
                        )
                    )
        payload = captured.payloads()[-1]
        self.assertEqual(payload["outcome"], "llm_error")
        self._assert_token_fields_empty(payload)

    def test_client_close_propagates_and_logs_client_closed(self):
        gateway = type("Gateway", (), {"stream": staticmethod(_stream_answer)})()
        with PathLogCapture() as captured:
            generator = iter_chat_sse(
                self._messages(),
                gateway=gateway,
                request_id="req-close",
            )
            next(generator)
            with self.assertRaises(GeneratorExit):
                generator.throw(GeneratorExit)
        payload = captured.payloads()[-1]
        self.assertEqual(payload["outcome"], "client_closed")
        self.assertEqual(payload["request_id"], "req-close")
        self._assert_token_fields_empty(payload)
        self._assert_no_text(payload)


class QuPreviewPathLogTest(TestCase):
    url = "/api/admin/qu/preview/"

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"path-log-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_successful_preview_logs_hint_length_not_text(self):
        hint = "PATHLOG_HINT_MARKER подсказка"
        client = Client()
        client.force_login(self.user_for_role("llm_knowledge_base_administrator"))
        with PathLogCapture() as captured:
            with patch(
                "hub.views.preview_admin_query",
                return_value={
                    "documents": [{"article_id": 1}, {"article_id": 2}],
                    "hint": {"text": hint},
                },
            ) as preview:
                response = client.post(
                    self.url,
                    data=json.dumps({"query": QUESTION, "limit": 3}),
                    content_type="application/json",
                )
        self.assertEqual(response.status_code, 200)
        preview.assert_called_once()
        self.assertEqual(preview.call_args.args[0], QUESTION)
        self.assertEqual(preview.call_args.kwargs["limit"], 3)
        payload = captured.payloads()[-1]
        self.assertEqual(payload["path"], "preview")
        self.assertEqual(payload["outcome"], "ok")
        self.assertEqual(payload["doc_count"], 2)
        self.assertEqual(payload["hint_chars"], len(hint))
        self.assertEqual(payload["retrieval_ms"], payload["total_ms"])
        self.assertIsInstance(payload["request_id"], str)
        self.assertNotIn("profile", payload)
        self.assertNotIn("ttft_ms", payload)
        raw = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(QUESTION, raw)
        self.assertNotIn(hint, raw)

    def test_validation_before_search_is_not_logged(self):
        client = Client()
        client.force_login(self.user_for_role("llm_knowledge_base_administrator"))
        with PathLogCapture() as captured:
            with patch("hub.views.preview_admin_query") as preview:
                broken = client.post(
                    self.url,
                    data="{not-json",
                    content_type="application/json",
                )
                empty = client.post(
                    self.url,
                    data=json.dumps({"query": "  "}),
                    content_type="application/json",
                )
        self.assertEqual(broken.status_code, 400)
        self.assertEqual(empty.status_code, 400)
        preview.assert_not_called()
        self.assertEqual(captured.payloads(), [])

    def test_preview_failure_is_logged_and_reraised(self):
        client = Client()
        client.force_login(self.user_for_role("llm_knowledge_base_administrator"))
        with PathLogCapture() as captured:
            with patch(
                "hub.views.preview_admin_query",
                side_effect=RuntimeError("preview failed"),
            ):
                with self.assertRaises(RuntimeError):
                    client.post(
                        self.url,
                        data=json.dumps({"query": QUESTION}),
                        content_type="application/json",
                    )
        payload = captured.payloads()[-1]
        self.assertEqual(payload["path"], "preview")
        self.assertEqual(payload["outcome"], "error")
        self.assertIsNone(payload["doc_count"])
        self.assertEqual(payload["hint_chars"], 0)
        self.assertEqual(payload["retrieval_ms"], payload["total_ms"])
        self.assertNotIn(QUESTION, json.dumps(payload, ensure_ascii=False))

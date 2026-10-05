import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from core.model_gateway import (  # noqa: E402
    GatewayProfile,
    ModelGateway,
    ModelGatewayConfigurationError,
    STUB_RESPONSES,
)


class ModelGatewayTest(unittest.TestCase):
    def setUp(self):
        self.gateway = ModelGateway.from_registry()
        self.messages = [{"role": "user", "content": "Тестовый запрос"}]

    def test_registry_maps_all_profiles_to_expected_slots(self):
        expected = {
            "sufler_cc": ("llm_sufler_cc", "qwen2.5-1.5b-instruct"),
            "assistant_bank": ("llm_assistant_bank", "qwen2.5-1.5b-instruct"),
            "docs_ocr": ("llm_docs_ocr", "stub:docs_ocr"),
        }

        for profile, (slot_name, model) in expected.items():
            with self.subTest(profile=profile):
                configured = self.gateway.get_profile(profile)
                self.assertEqual(configured.slot_name, slot_name)
                self.assertEqual(configured.gateway_mode, "stub")
                self.assertEqual(configured.model, model)

    def test_dev_stub_returns_profile_specific_openai_response(self):
        responses = {
            profile: self.gateway.chat(profile, self.messages)
            for profile in STUB_RESPONSES
        }

        for profile, response in responses.items():
            with self.subTest(profile=profile):
                self.assertEqual(response["object"], "chat.completion")
                self.assertEqual(
                    response["model"],
                    self.gateway.get_profile(profile).model,
                )
                if profile == "docs_ocr":
                    expected = self.gateway._stub_docs_ocr_content(
                        self.messages
                    )
                else:
                    expected = STUB_RESPONSES[profile]
                self.assertEqual(
                    response["choices"][0]["message"]["content"],
                    expected,
                )
                self.assertEqual(
                    response["choices"][0]["finish_reason"],
                    "stop",
                )
        self.assertEqual(
            len(
                {
                    response["choices"][0]["message"]["content"]
                    for response in responses.values()
                }
            ),
            3,
        )

    def test_stub_stream_is_valid_sse_and_reconstructs_content(self):
        events = list(self.gateway.stream("sufler_cc", self.messages))

        self.assertEqual(events[-1], "data: [DONE]\n\n")
        chunks = [
            json.loads(event.removeprefix("data: ").strip())
            for event in events[:-1]
        ]
        content = "".join(
            chunk["choices"][0]["delta"].get("content", "")
            for chunk in chunks
        )
        self.assertEqual(content, STUB_RESPONSES["sufler_cc"])
        self.assertEqual(
            chunks[0]["choices"][0]["delta"]["role"],
            "assistant",
        )
        self.assertEqual(
            chunks[-1]["choices"][0]["finish_reason"],
            "stop",
        )

    def test_assistant_stub_returns_openai_tool_call(self):
        response = self.gateway.chat(
            "assistant_bank",
            self.messages,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_exchange_rate",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            tool_choice="auto",
        )

        choice = response["choices"][0]
        tool_call = choice["message"]["tool_calls"][0]
        self.assertEqual(choice["finish_reason"], "tool_calls")
        self.assertEqual(tool_call["type"], "function")
        self.assertEqual(
            tool_call["function"]["name"],
            "get_exchange_rate",
        )
        self.assertEqual(
            json.loads(tool_call["function"]["arguments"]),
            {"currency": "USD"},
        )

    def test_unknown_profile_and_reserved_parameter_are_rejected(self):
        with self.assertRaises(ModelGatewayConfigurationError):
            self.gateway.chat("unknown", self.messages)
        with self.assertRaises(ModelGatewayConfigurationError):
            self.gateway.chat(
                "sufler_cc",
                self.messages,
                model="override",
            )

    def test_openai_mode_posts_compatible_payload(self):
        configured = GatewayProfile(
            profile="sufler_cc",
            slot_name="llm_sufler_cc",
            model="vendor-model",
            gateway_mode="openai",
            api_compatibility="openai",
            kpi={},
        )
        gateway = ModelGateway(
            self.gateway._registry,
            mode="openai",
            base_url="http://llm.internal/v1",
            api_key="test-key",
        )
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "id": "chatcmpl-real",
            "object": "chat.completion",
            "choices": [],
        }

        with (
            patch.object(
                gateway,
                "get_profile",
                return_value=configured,
            ),
            patch(
                "core.model_gateway.requests.post",
                return_value=response,
            ) as post,
        ):
            result = gateway.chat(
                "sufler_cc",
                self.messages,
                temperature=0.2,
            )

        self.assertEqual(result["id"], "chatcmpl-real")
        post.assert_called_once()
        call = post.call_args
        self.assertEqual(
            call.args[0],
            "http://llm.internal/v1/chat/completions",
        )
        self.assertEqual(call.kwargs["json"]["model"], "vendor-model")
        self.assertEqual(call.kwargs["json"]["messages"], self.messages)
        self.assertFalse(call.kwargs["json"]["stream"])
        self.assertEqual(call.kwargs["json"]["temperature"], 0.2)
        self.assertEqual(
            call.kwargs["headers"]["Authorization"],
            "Bearer test-key",
        )

    def test_sufler_and_assistant_share_deepseek_when_configured(self):
        env = {
            "MODEL_GATEWAY_MODE": "openai",
            "OPENAI_BASE_URL": "http://ollama:11434/v1",
            "OPENAI_API_KEY": "ollama",
            "OPENAI_MODEL": "qwen2.5:3b",
            "OLLAMA_BASE_URL": "http://ollama:11434",
            "SUFLER_LLM_BASE_URL": "https://api.deepseek.com/v1",
            "SUFLER_LLM_API_KEY": "test-sufler-key",
            "SUFLER_LLM_MODEL": "deepseek-chat",
        }
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "id": "chatcmpl-split",
            "object": "chat.completion",
            "choices": [],
        }
        with patch.dict("os.environ", env, clear=False):
            with patch(
                "assistant.local_llm.active_model_id",
                return_value="qwen2.5:3b",
            ):
                gateway = ModelGateway.from_registry()
                with patch(
                    "core.model_gateway.requests.post",
                    return_value=response,
                ) as post:
                    gateway.chat("sufler_cc", self.messages)
                    sufler_call = post.call_args
                    gateway.chat("assistant_bank", self.messages)
                    assistant_call = post.call_args
                    gateway.chat("docs_ocr", self.messages)
                    ocr_call = post.call_args

        self.assertEqual(
            sufler_call.args[0],
            "https://api.deepseek.com/v1/chat/completions",
        )
        self.assertEqual(sufler_call.kwargs["json"]["model"], "deepseek-chat")
        self.assertEqual(
            sufler_call.kwargs["headers"]["Authorization"],
            "Bearer test-sufler-key",
        )
        self.assertEqual(
            assistant_call.args[0],
            "https://api.deepseek.com/v1/chat/completions",
        )
        self.assertEqual(
            assistant_call.kwargs["json"]["model"],
            "deepseek-chat",
        )
        self.assertEqual(
            assistant_call.kwargs["headers"]["Authorization"],
            "Bearer test-sufler-key",
        )
        self.assertEqual(
            ocr_call.args[0],
            "https://api.deepseek.com/v1/chat/completions",
        )
        self.assertEqual(ocr_call.kwargs["json"]["model"], "deepseek-chat")
        self.assertEqual(
            ocr_call.kwargs["headers"]["Authorization"],
            "Bearer test-sufler-key",
        )

    def test_assistant_stays_on_ollama_without_deepseek(self):
        env = {
            "MODEL_GATEWAY_MODE": "openai",
            "OPENAI_BASE_URL": "http://ollama:11434/v1",
            "OPENAI_API_KEY": "ollama",
            "OPENAI_MODEL": "qwen2.5:3b",
            "OLLAMA_BASE_URL": "http://ollama:11434",
            "SUFLER_LLM_BASE_URL": "",
            "SUFLER_LLM_API_KEY": "",
            "SUFLER_LLM_MODEL": "",
            "ASSISTANT_LLM_BASE_URL": "",
            "ASSISTANT_LLM_API_KEY": "",
            "ASSISTANT_LLM_MODEL": "",
        }
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "id": "chatcmpl-ollama",
            "object": "chat.completion",
            "choices": [],
        }
        with patch.dict("os.environ", env, clear=False):
            with patch(
                "assistant.local_llm.active_model_id",
                return_value="qwen2.5:3b",
            ):
                gateway = ModelGateway.from_registry()
                with patch(
                    "core.model_gateway.requests.post",
                    return_value=response,
                ) as post:
                    gateway.chat("assistant_bank", self.messages)
                    assistant_call = post.call_args

        self.assertEqual(
            assistant_call.args[0],
            "http://ollama:11434/v1/chat/completions",
        )
        self.assertEqual(assistant_call.kwargs["json"]["model"], "qwen2.5:3b")
        self.assertEqual(
            assistant_call.kwargs["headers"]["Authorization"],
            "Bearer ollama",
        )

    def test_docs_ocr_prefers_dedicated_ocr_llm(self):
        env = {
            "MODEL_GATEWAY_MODE": "stub",
            "SUFLER_LLM_BASE_URL": "https://api.deepseek.com/v1",
            "SUFLER_LLM_API_KEY": "test-sufler-key",
            "SUFLER_LLM_MODEL": "deepseek-chat",
            "OCR_LLM_BASE_URL": "https://api.deepseek.com/v1",
            "OCR_LLM_API_KEY": "test-ocr-key",
            "OCR_LLM_MODEL": "deepseek-chat",
        }
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "id": "chatcmpl-ocr",
            "object": "chat.completion",
            "choices": [],
        }
        with patch.dict("os.environ", env, clear=False):
            gateway = ModelGateway.from_registry()
            with patch(
                "core.model_gateway.requests.post",
                return_value=response,
            ) as post:
                gateway.chat("docs_ocr", self.messages)

        self.assertEqual(
            post.call_args.args[0],
            "https://api.deepseek.com/v1/chat/completions",
        )
        self.assertEqual(post.call_args.kwargs["json"]["model"], "deepseek-chat")
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer test-ocr-key",
        )


if __name__ == "__main__":
    unittest.main()

"""DefaultProvider OpenRouter model routing.

OpenRouter catalog IDs retain their ``vendor/model`` form. Chat-compatible
models send that ID directly through the official SDK; Claude/Gemini retain
the LiteLLM exception path and its ``openrouter/`` routing prefix.
"""

from __future__ import annotations

import asyncio
import json
import os
from unittest import mock as unittest_mock

import httpx
import pytest


@pytest.fixture()
def provider():
    from siada.provider.default.default_provider import DefaultProvider

    return DefaultProvider()


class TestEnsureOpenrouterPrefix:
    def test_no_prefix_when_base_url_is_not_openrouter(self, provider):
        provider.base_url = "https://api.deepseek.com"
        assert provider._ensure_openrouter_prefix("anthropic/claude-3.7-sonnet") == (
            "anthropic/claude-3.7-sonnet"
        )

    def test_prefix_added_when_base_url_is_openrouter(self, provider):
        provider.base_url = "https://openrouter.ai/api/v1"
        assert provider._ensure_openrouter_prefix("anthropic/claude-3.7-sonnet") == (
            "openrouter/anthropic/claude-3.7-sonnet"
        )

    def test_existing_prefix_is_idempotent(self, provider):
        provider.base_url = "https://openrouter.ai/api/v1"
        assert provider._ensure_openrouter_prefix("openrouter/openai/gpt-4o") == (
            "openrouter/openai/gpt-4o"
        )

    def test_none_base_url_is_safe(self, provider):
        provider.base_url = None
        assert provider._ensure_openrouter_prefix("anthropic/claude-3.7-sonnet") == (
            "anthropic/claude-3.7-sonnet"
        )


def _capture_acompletion_kwargs(model_obj, model_settings):
    """Run _fetch_response with litellm.acompletion mocked; return its kwargs."""
    import litellm
    from litellm.types.utils import ModelResponse, Choices, Message
    from agents.models.interface import ModelTracing
    from unittest.mock import MagicMock

    captured = []

    async def fake_acompletion(**kwargs):
        captured.append(kwargs)
        return ModelResponse(
            id="test",
            choices=[Choices(message=Message(content="ok", role="assistant"),
                             finish_reason="stop")],
        )

    async def run():
        with unittest_mock.patch.object(litellm, "acompletion", fake_acompletion):
            await model_obj._fetch_response(
                "You are a test", [{"role": "user", "content": "hi"}],
                model_settings, [], None, [], MagicMock(),
                ModelTracing.DISABLED, stream=False,
            )

    asyncio.run(run())
    return captured[-1] if captured else None

class TestOpenRouterEndToEnd:
    """OpenRouter Chat models use the catalog model ID with the official SDK."""

    @pytest.mark.parametrize("model_name,expected_wire_model", [
        ("anthropic/claude-3.7-sonnet", "anthropic/claude-3.7-sonnet"),
        ("claude-sonnet-4.6", "anthropic/claude-sonnet-4.6"),
        ("gpt-4o", "openai/gpt-4o"),
        ("openrouter/openai/gpt-4o", "openai/gpt-4o"),
    ])
    def test_routes_through_openrouter_provider(
        self, model_name, expected_wire_model, monkeypatch
    ):
        from agents.models.interface import ModelTracing
        from agents import ModelSettings
        from siada.provider.default import chat_completions as chat_module
        from siada.provider.default.default_provider import DefaultProvider

        if "claude" in model_name:
            import siada.entrypoint

            from siada.models.model_run_config import ModelRunConfig
            from siada.models.model_setting_converter import ModelSettingsConverter

            monkeypatch.setenv("BASE_URL", "https://openrouter.ai/api/v1")
            monkeypatch.setenv("API_KEY", "sk-or-test")
            monkeypatch.setattr(siada.entrypoint, "_configure_litellm", lambda: None)
            model = DefaultProvider().get_model(model_name)
            assert model.model.startswith("openrouter/")
            kwargs = _capture_acompletion_kwargs(
                model, ModelSettingsConverter.convert_model_settings(
                    ModelRunConfig("claude-sonnet-4.6")
                )
            )
            assert kwargs is not None
            assert kwargs["model"] == f"openrouter/{expected_wire_model}"
            assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
            return

        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 1,
                    "model": expected_wire_model,
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }],
                },
                request=request,
            )

        original_async_openai = chat_module.AsyncOpenAI

        def create_client(**kwargs):
            return original_async_openai(
                **kwargs,
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            )

        monkeypatch.setenv("BASE_URL", "https://openrouter.ai/api/v1")
        monkeypatch.setenv("API_KEY", "sk-or-test")
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setattr(chat_module, "AsyncOpenAI", create_client)
        provider = DefaultProvider()
        model = provider.get_model(model_name)

        async def run():
            try:
                await model.get_response(
                    system_instructions=None,
                    input=[{"role": "user", "content": "hi"}],
                    model_settings=ModelSettings(),
                    tools=[],
                    output_schema=None,
                    handoffs=[],
                    tracing=ModelTracing.DISABLED,
                )
            finally:
                await provider.aclose()

        asyncio.run(run())
        assert len(requests) == 1
        assert requests[0].url == "https://openrouter.ai/api/v1/chat/completions"
        body = json.loads(requests[0].content)
        assert body["model"] == expected_wire_model
        assert requests[0].headers["authorization"] == "Bearer sk-or-test"
        assert os.environ.get("DEEPSEEK_API_KEY") != "sk-or-test"

    def test_non_openrouter_base_url_untouched(self, monkeypatch):
        import siada.entrypoint
        from siada.provider.default.default_provider import DefaultProvider
        from siada.provider.default.coverter import covert_to_litellm_model_name

        monkeypatch.setenv("BASE_URL", "https://my-gateway.example.com/v1")
        monkeypatch.setenv("API_KEY", "sk-test")
        monkeypatch.setattr(siada.entrypoint, "_configure_litellm", lambda: None)
        model = DefaultProvider().get_model("claude-sonnet-4.6")
        assert model.model == covert_to_litellm_model_name("claude-sonnet-4.6")

"""DefaultProvider OpenRouter auto-prefixing.

OpenRouter catalog ids (``vendor/model``) collide with litellm's provider
routing prefixes: a bare ``anthropic/claude-3.7-sonnet`` would be routed as a
DIRECT anthropic call (wrong protocol — ``/v1/v1/messages``), and
``google/gemini-...`` fails outright. When BASE_URL points at OpenRouter,
DefaultProvider must prefix model ids with ``openrouter/`` so litellm routes
them through its openrouter provider instead.
"""

from __future__ import annotations

import asyncio
import json
import os
from unittest import mock as unittest_mock

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
    """Run _fetch_response with litellm.acompletion mocked; return its kwargs.

    (The real URL/protocol routing against OpenRouter is covered by
    test_routes_through_openrouter_provider's live verification — see
    CLAUDE.local.md; here we assert the model/base_url kwargs the default
    path hands to litellm, without any network or auth interference.)
    """
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
    """Full DefaultProvider.get_model chain with BASE_URL=OpenRouter."""

    @pytest.mark.parametrize("model_name,expected_wire_model", [
        ("anthropic/claude-3.7-sonnet", "anthropic/claude-3.7-sonnet"),
        ("claude-sonnet-4.6", "anthropic/claude-sonnet-4.6"),
        ("gpt-4o", "openai/gpt-4o"),
        ("openrouter/openai/gpt-4o", "openai/gpt-4o"),
    ])
    def test_routes_through_openrouter_provider(self, model_name, expected_wire_model):
        from siada.models.model_run_config import ModelRunConfig
        from siada.models.model_setting_converter import ModelSettingsConverter
        from siada.provider.default.default_provider import DefaultProvider

        old = {k: os.environ.get(k) for k in ("BASE_URL", "API_KEY", "DEEPSEEK_API_KEY")}
        try:
            os.environ["BASE_URL"] = "https://openrouter.ai/api/v1"
            os.environ["API_KEY"] = "sk-or-test"
            os.environ.pop("DEEPSEEK_API_KEY", None)

            model = DefaultProvider().get_model(model_name)
            assert model.model.startswith("openrouter/")

            cfg = ModelRunConfig("claude-sonnet-4.6")
            settings = ModelSettingsConverter.convert_model_settings(cfg)
            kwargs = _capture_acompletion_kwargs(model, settings)
            assert kwargs is not None, "acompletion was not called"
            # litellm receives the openrouter-prefixed model and the
            # configured base_url; its openrouter provider then strips the
            # prefix and hits {base_url}/chat/completions with the catalog id
            # (verified live against openrouter.ai).
            assert kwargs["model"].startswith("openrouter/")
            assert kwargs["model"] == f"openrouter/{expected_wire_model}"
            assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
            # the OpenRouter key must NOT leak into vendor env vars
            assert os.environ.get("DEEPSEEK_API_KEY") != "sk-or-test"
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_non_openrouter_base_url_untouched(self):
        from siada.provider.default.default_provider import DefaultProvider
        from siada.provider.default.coverter import covert_to_litellm_model_name

        old = {k: os.environ.get(k) for k in ("BASE_URL", "API_KEY")}
        try:
            os.environ["BASE_URL"] = "https://my-gateway.example.com/v1"
            os.environ["API_KEY"] = "sk-test"
            model = DefaultProvider().get_model("claude-sonnet-4.6")
            assert model.model == covert_to_litellm_model_name("claude-sonnet-4.6")
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

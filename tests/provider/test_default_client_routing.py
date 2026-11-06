"""Offline regression coverage for default-client compaction routing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import litellm
import pytest
from agents import ModelResponse, Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText

from siada.agent_hub.context_filter.header_summary_compaction_strategy import (
    SummarizeWithHeaderCompaction,
)
from siada.provider.default.default_provider import DefaultClient


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_name", "expected_model", "expected_provider"),
    [
        ("azure-gpt-example", "azure-gpt-example", "openai"),
        ("gateway-model", "gateway-model", "openai"),
        ("gpt-4o-mini", "openai/gpt-4o-mini", None),
        ("claude-sonnet-4", "anthropic/claude-sonnet-4", None),
        ("gemini-2.5-pro", "gemini/gemini-2.5-pro", None),
        ("kimi-k2.5", "moonshot/kimi-k2.5", None),
        ("deepseek-chat", "deepseek/deepseek-chat", None),
        ("azure/deployment", "azure/deployment", None),
        ("openai/responses/gpt-5-codex", "openai/responses/gpt-5-codex", None),
    ],
)
async def test_completion_resolves_provider(
    monkeypatch, model_name, expected_model, expected_provider
):
    monkeypatch.setenv("BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("API_KEY", "sk-test")
    completion = AsyncMock()
    monkeypatch.setattr(litellm, "acompletion", completion)

    await DefaultClient().completion(model=model_name, messages=[])

    kwargs = completion.await_args.kwargs
    assert kwargs["model"] == expected_model
    assert kwargs.get("custom_llm_provider") == expected_provider
    # Exercise LiteLLM's actual provider resolver without making an API call.
    wire_model, provider, _, _ = litellm.get_llm_provider(
        model=kwargs["model"],
        custom_llm_provider=kwargs.get("custom_llm_provider"),
        api_base=kwargs["api_base"],
        api_key=kwargs["api_key"],
    )
    assert provider == (expected_provider or expected_model.split("/")[0])
    if expected_model.startswith("openai/responses/"):
        assert wire_model == expected_model.removeprefix("openai/")


@pytest.mark.asyncio
async def test_explicit_provider_takes_precedence(monkeypatch):
    monkeypatch.setenv("BASE_URL", "http://127.0.0.1:9/v1")
    completion = AsyncMock()
    monkeypatch.setattr(litellm, "acompletion", completion)

    await DefaultClient().completion(
        model="deployment", messages=[], custom_llm_provider="azure"
    )

    assert completion.await_args.kwargs["model"] == "deployment"
    assert completion.await_args.kwargs["custom_llm_provider"] == "azure"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_name", "expected_model"),
    [
        ("anthropic/claude-sonnet-4", "openrouter/anthropic/claude-sonnet-4"),
        ("gpt-4o-mini", "openrouter/openai/gpt-4o-mini"),
        ("openrouter/openai/gpt-4o-mini", "openrouter/openai/gpt-4o-mini"),
    ],
)
async def test_openrouter_uses_per_call_endpoint(
    monkeypatch, model_name, expected_model
):
    monkeypatch.setenv("BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("API_KEY", "sk-main")
    completion = AsyncMock()
    monkeypatch.setattr(litellm, "acompletion", completion)

    await DefaultClient().completion(
        model=model_name,
        messages=[],
        api_base="https://openrouter.ai/api/v1",
        api_key="sk-override",
    )

    kwargs = completion.await_args.kwargs
    assert kwargs["model"] == expected_model
    assert kwargs["api_base"] == "https://openrouter.ai/api/v1"
    assert kwargs["api_key"] == "sk-override"
    assert "custom_llm_provider" not in kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("override_model", [False, True])
async def test_compaction_with_gateway_alias(monkeypatch, override_model):
    monkeypatch.setenv("BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("API_KEY", "sk-test")
    alias = "azure-gpt-example"
    if override_model:
        monkeypatch.setenv("SIADA_COMPACT_MODEL", alias)
    else:
        monkeypatch.delenv("SIADA_COMPACT_MODEL", raising=False)
    config = SimpleNamespace(
        provider="default",
        model_name="gpt-4o-mini" if override_model else alias,
    )
    response = ModelResponse(
        output=[ResponseOutputMessage(
            id="summary", role="assistant", type="message", status="completed",
            content=[ResponseOutputText(type="output_text", text="<context>summary</context>", annotations=[])],
        )],
        usage=Usage(requests=1), response_id="summary",
    )

    async def completion(input, **kwargs):
        assert kwargs["model"] == alias
        assert kwargs["provider"] == "default"
        assert kwargs["system_instructions"]
        assert input[0] == {"role": "user", "content": "Summarize this task."}
        return response

    monkeypatch.setattr("siada.agent_hub.context_filter.compaction_strategy.one_shot_completion", completion)
    strategy = SummarizeWithHeaderCompaction()
    monkeypatch.setattr(strategy, "_count_tokens", lambda *args: 10)

    summary = await strategy.call_llm_to_compact(
        config, [{"role": "user", "content": "Summarize this task."}]
    )

    assert summary == "<context>summary</context>"
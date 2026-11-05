from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agents import Agent, RunConfig, Runner
from agents.decorators import function_tool
from google.genai import types

from siada.agent_hub.context_filter.request_token_estimator import RequestTokenBaseline
from siada.agent_hub.hooks.processors import cache_status_processor
from siada.agent_hub.hooks.processors.cache_status_processor import CacheStatusProcessor
from siada.agent_hub.hooks.siada_agent_hooks import SiadaAgentHooks
from siada.models import model_pricing
from siada.provider.gemini import GeminiModel
from siada.provider.gemini.stream_handler import GeminiResponseAssembly
from siada.services.model_wrapper import ModelWrapper
from siada.support.usage_utils import deserialize_usage, serialize_usage

from test_gemini_model import native_response, sse
from test_gemini_replay_boundary import native_provider


@pytest.mark.parametrize("cached_tokens", [None, 0, 9560, 10000])
@pytest.mark.parametrize("reported_total", [None, 10005])
def test_native_usage_separates_uncached_input_and_preserves_total(cached_tokens, reported_total):
    metadata = {
        "promptTokenCount": 10000, "candidatesTokenCount": 3,
        "thoughtsTokenCount": 2, "totalTokenCount": reported_total,
        "cachedContentTokenCount": cached_tokens,
    }
    assembly = GeminiResponseAssembly({"provider": "google", "model": "gemini-3.5-flash", "backend": "gemini_api"})
    assembly.usage = types.GenerateContentResponseUsageMetadata.model_validate(metadata)

    usage, response_usage = GeminiModel._usage(assembly)

    for normalized in (usage, response_usage):
        assert normalized.input_tokens == 10000 - (cached_tokens or 0)
        assert normalized.input_tokens_details.cached_tokens == (cached_tokens or 0)
        assert normalized.input_tokens_details.cache_write_tokens == 0
        assert normalized.output_tokens == 5
        assert normalized.output_tokens_details.reasoning_tokens == 2
        assert normalized.total_tokens == 10005
        assert normalized.input_tokens + normalized.input_tokens_details.cached_tokens + normalized.output_tokens == normalized.total_tokens
        assert CacheStatusProcessor._extract_token_data(normalized)["cache_write"] == 0
    assert assembly.usage.model_dump(mode="json", by_alias=True, include={
        "prompt_token_count", "cached_content_token_count", "total_token_count",
    }) == {"promptTokenCount": 10000, "cachedContentTokenCount": cached_tokens, "totalTokenCount": reported_total}
    assert serialize_usage(deserialize_usage(serialize_usage(usage))) == serialize_usage(usage)
    baseline = RequestTokenBaseline.from_response("synthetic-signature", [], usage, session_id="synthetic-session")
    assert baseline.input_tokens == 10000
    assert baseline.context_tokens == 10005


def test_missing_native_usage_remains_unknown():
    assembly = GeminiResponseAssembly({"provider": "google", "model": "gemini-3.5-flash", "backend": "gemini_api"})
    usage, response_usage = GeminiModel._usage(assembly)
    assert usage.requests == 1
    assert usage.input_tokens == usage.output_tokens == usage.total_tokens == 0
    assert response_usage is None


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_runner_cache_status_uses_weighted_tokens_and_resets_next_turn(native_provider, endpoint, monkeypatch, stream):
    _provider_name, provider = native_provider
    responses = [
        native_response([{"functionCall": {"name": "lookup", "args": {"value": 1}}, "thoughtSignature": "c2ln"}]),
        native_response([{"text": "first answer", "thoughtSignature": "c2ln"}]),
        native_response([{"text": "next answer", "thoughtSignature": "c2ln"}]),
    ]
    for response, prompt_tokens, cached_tokens in zip(responses, [10000, 100000, 120000], [0, 90000, 110000]):
        response["usageMetadata"].update(
            promptTokenCount=prompt_tokens, cachedContentTokenCount=cached_tokens,
            totalTokenCount=prompt_tokens + 5,
        )
    endpoint.responses = [(200, sse(response) if stream else response) for response in responses]
    calculate_cost = Mock(wraps=cache_status_processor.calculate_token_cost_breakdown)
    monkeypatch.setattr(cache_status_processor, "calculate_token_cost_breakdown", calculate_cost)
    monkeypatch.setattr(model_pricing, "get_model_pricing", Mock(return_value=model_pricing.ModelPricing(
        model_name="synthetic-model", input_price=2.0, output_price=8.0, cache_read_price=0.2,
    )))
    payloads = []

    def record_update(build):
        payloads.append(json.loads(build().params["content"]))

    context = SimpleNamespace(session=SimpleNamespace(
        state=SimpleNamespace(),
        siada_config=SimpleNamespace(
            llm_config=SimpleNamespace(model_name="gemini-3.5-flash"),
            io=SimpleNamespace(acp_enabled=True, acp_adapter=SimpleNamespace(_send_if_acp=record_update)),
        ),
    ))

    @function_tool
    async def lookup(value: int) -> str:
        return str(value)

    agent = Agent(
        name="synthetic", model=ModelWrapper(provider.get_model("gemini-3.5-flash")),
        tools=[lookup], hooks=SiadaAgentHooks(processors=[CacheStatusProcessor()]),
    )
    run_config = RunConfig(tracing_disabled=True)
    if stream:
        first = Runner.run_streamed(agent, "first question", context=context, run_config=run_config)
        async for _event in first.stream_events():
            pass
    else:
        first = await Runner.run(agent, "first question", context=context, run_config=run_config)
    assert first.final_output == "first answer"
    assert len(payloads) == 2
    assert payloads[0]["hit_rate"] == 0.0
    assert payloads[1]["input"] == 10000
    assert payloads[1]["cache_read"] == 90000
    assert payloads[1]["prompt_total"] == 100000
    assert payloads[1]["hit_rate"] == 90.0
    assert payloads[1]["accumulated_hit_rate"] == 81.82
    assert payloads[1]["accumulated_input"] == 20000
    assert payloads[1]["accumulated_cache_read"] == 90000
    assert payloads[1]["input_cost"] == 0.02
    assert payloads[1]["cache_read_cost"] == 0.018
    history = [*first.to_input_list(), {"role": "user", "content": "next question"}]
    if stream:
        second = Runner.run_streamed(agent, history, context=context, run_config=run_config)
        async for _event in second.stream_events():
            pass
    else:
        second = await Runner.run(agent, history, context=context, run_config=run_config)
    assert second.final_output == "next answer"
    assert len(payloads) == len(endpoint.requests) == 3
    assert payloads[-1]["hit_rate"] == payloads[-1]["accumulated_hit_rate"] == 91.67
    assert payloads[-1]["accumulated_input"] == 10000
    assert payloads[-1]["accumulated_cache_read"] == 110000
    assert payloads[-1]["accumulated_output"] == 5
    assert all(payload["cache_write"] == payload["accumulated_cache_write"] == 0 for payload in payloads)
    assert all(call.kwargs["input_tokens"] == 10000 for call in calculate_cost.call_args_list)
    assert second.context_wrapper.usage.input_tokens == 10000
    assert second.context_wrapper.usage.total_tokens == 120005
    for previous, current in zip(endpoint.requests, endpoint.requests[1:]):
        assert current[1]["contents"][:len(previous[1]["contents"])] == previous[1]["contents"]

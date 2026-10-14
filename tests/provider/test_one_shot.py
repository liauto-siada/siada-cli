"""Offline contracts for standalone SDK calls and input compatibility."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agents import ModelResponse, ModelSettings, ModelTracing
from agents.exceptions import ModelBehaviorError
from agents.models.chatcmpl_converter import Converter
from agents.usage import Usage
from openai.types.responses import (
    Response, ResponseCompletedEvent, ResponseOutputMessage, ResponseOutputText, ResponseReasoningItem,
)
from openai.types.responses.response_usage import ResponseUsage

from siada.foundation.context import AGENT_NAME, agent_name_scope, get_context_var
from siada.provider import one_shot


def response_with_text(text="answer"):
    return ModelResponse(
        output=[ResponseOutputMessage(
            id="msg-synthetic", type="message", role="assistant", status="completed",
            content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
        )],
        usage=Usage(), response_id="response-synthetic",
    )


@pytest.fixture
def provider(monkeypatch):
    model = SimpleNamespace(model="gpt-4o", get_response=AsyncMock(return_value=response_with_text()))
    provider = SimpleNamespace(get_model=Mock(return_value=model), aclose=AsyncMock())
    monkeypatch.setattr(one_shot, "get_provider", Mock(return_value=provider))
    return provider, model


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [None, False, True])
async def test_one_model_call_uses_wrapper_and_no_session_admission(provider, monkeypatch, stream):
    base, model = provider
    async def events(**kwargs):
        yield completed_event(output=model.get_response.return_value.output)

    model.stream_response = Mock(side_effect=events)
    process = Mock(side_effect=lambda items: items + [{"role": "user", "content": "processed"}])
    monkeypatch.setattr(one_shot, "process_input", process)
    input_items = [{"role": "user", "content": "original"}]
    response = await one_shot.one_shot_completion(
        input_items, model="gpt-4o", provider="default",
        **({"stream": stream} if stream is not None else {}),
    )
    assert isinstance(response, ModelResponse)
    assert response.output == model.get_response.return_value.output
    base.get_model.assert_called_once_with("gpt-4o")
    if stream is False:
        assert response is model.get_response.return_value
        model.get_response.assert_awaited_once()
        model.stream_response.assert_not_called()
        sent = model.get_response.await_args.kwargs
    else:
        model.stream_response.assert_called_once()
        model.get_response.assert_not_awaited()
        sent = model.stream_response.call_args.kwargs
    process.assert_called_once_with(input_items)
    assert sent["input"][-1]["content"] == "processed"
    assert sent["tools"] == sent["handoffs"] == []
    assert sent["output_schema"] is None
    assert sent["previous_response_id"] is sent["conversation_id"] is sent["prompt"] is None
    assert sent["tracing"] is ModelTracing.DISABLED
    assert input_items == [{"role": "user", "content": "original"}]
    base.aclose.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_agent_scope_covers_model_resolution_and_request(provider, failure):
    base, model = provider
    seen = []

    def resolve(name):
        seen.append(get_context_var(AGENT_NAME))
        return model

    async def fetch(**kwargs):
        seen.append(get_context_var(AGENT_NAME))
        if failure:
            raise RuntimeError("synthetic failure")
        return response_with_text()

    base.get_model.side_effect = resolve
    model.get_response.side_effect = fetch
    with agent_name_scope("parent"):
        if failure:
            with pytest.raises(RuntimeError, match="synthetic failure"):
                await one_shot.one_shot_completion("hello", model="gpt-4o", agent_name="auxiliary", stream=False)
        else:
            await one_shot.one_shot_completion("hello", model="gpt-4o", agent_name="auxiliary", stream=False)
        assert get_context_var(AGENT_NAME) == "parent"
    assert seen == ["auxiliary", "auxiliary"]
    base.aclose.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [False, True])
async def test_native_patch_history_is_normalized_only_for_chat(provider, native):
    _, model = provider
    model.supports_native_responses_items = native
    history = [
        {"role": "user", "content": "update a.py"},
        {"type": "apply_patch_call", "id": "apc", "call_id": "call-synthetic",
         "status": "completed", "operation": {"type": "update_file", "path": "a.py", "diff": "@@"}},
        {"type": "apply_patch_call_output", "id": "apco", "call_id": "call-synthetic",
         "status": "completed", "output": "done"},
    ]
    original = deepcopy(history)
    await one_shot.one_shot_completion(history, model="gpt-4o", stream=False)
    sent = model.get_response.await_args.kwargs["input"]
    assert sent[1]["type"] == ("apply_patch_call" if native else "function_call")
    assert sent[2]["type"] == ("apply_patch_call_output" if native else "function_call_output")
    assert history == original


@pytest.mark.asyncio
async def test_claude_reasoning_sanitization_is_retained(provider):
    _, model = provider
    model.model = "anthropic/claude-sonnet-4.6"
    history = [
        {"type": "reasoning", "summary": [{"type": "summary_text", "text": "not replayable"}]},
        {"role": "user", "content": "hello"},
    ]
    await one_shot.one_shot_completion(history, model=model.model, stream=False)
    assert model.get_response.await_args.kwargs["input"] == [history[1]]


@pytest.mark.asyncio
async def test_legacy_messages_keep_system_images_and_tool_pairs(provider):
    _, model = provider
    messages = [
        {"role": "system", "content": "summarize"},
        {"role": "user", "content": [
            {"type": "text", "text": "read image"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,c3ludGhldGlj", "detail": "low"}},
        ]},
        {"role": "assistant", "content": None, "tool_calls": [
            {"type": "function", "id": "call-synthetic", "function": {"name": "read", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "call-synthetic", "content": "done"},
    ]
    original = deepcopy(messages)
    await one_shot.one_shot_completion("ignored", model="gpt-4o", messages=messages, stream=False)
    sent = model.get_response.await_args.kwargs["input"]
    assert sent[0] == messages[0]
    assert sent[1]["content"][1]["type"] == "input_image"
    assert sent[2]["call_id"] == sent[3]["call_id"] == "call-synthetic"
    round_trip = Converter.items_to_messages(sent)
    assert round_trip[1]["content"] == messages[1]["content"]
    assert messages == original


@pytest.mark.asyncio
async def test_settings_mapping_preserves_options_without_mutation(provider):
    _, model = provider
    settings = ModelSettings(max_tokens=100, extra_args={"seed": 1}, extra_body={"keep": True})
    await one_shot.one_shot_completion(
        "hello", model="gpt-4o", model_settings=settings, stream=False,
        temperature=0.2, max_completion_tokens=256, reasoning_effort="low",
        timeout=1, extra_headers={"X-Synthetic": "auxiliary"}, extra_body={"reasoning_effort": "low"},
        extra_args={"seed": 2}, stop=["END"],
    )
    sent = model.get_response.await_args.kwargs["model_settings"]
    assert sent.temperature == 0.2
    assert sent.max_tokens == 256
    assert sent.reasoning.effort == "low"
    assert sent.timeout == 1
    assert sent.extra_args == {"seed": 2, "stop": ["END"], "timeout": 1}
    assert sent.extra_headers == {"X-Synthetic": "auxiliary"}
    assert sent.extra_body == {"reasoning_effort": "low"}
    assert settings.max_tokens == 100
    assert settings.extra_args == {"seed": 1}
    assert settings.extra_body == {"keep": True}


@pytest.mark.asyncio
async def test_timeout_cancels_request_without_closing_shared_provider(provider):
    base, model = provider
    cancelled = asyncio.Event()

    async def hang(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    model.get_response.side_effect = hang
    with pytest.raises(TimeoutError):
        await one_shot.one_shot_completion("hello", model="gpt-4o", timeout=0.01, stream=False)
    assert cancelled.is_set()
    base.aclose.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_propagates(provider):
    base, model = provider
    started = asyncio.Event()

    async def hang(**kwargs):
        started.set()
        await asyncio.Event().wait()

    model.get_response.side_effect = hang
    task = asyncio.create_task(one_shot.one_shot_completion("hello", model="gpt-4o", stream=False))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    base.aclose.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("options", [
    {"tools": ["synthetic"]}, {"handoffs": ["synthetic"]},
    {"extra_args": {"stream": True}}, {"extra_args": {"tools": ["synthetic"]}},
    {"model_settings": ModelSettings(extra_args={"api_key": "synthetic-key"})},
])
async def test_rejects_non_standalone_options_before_provider_lookup(provider, options):
    base, model = provider
    with pytest.raises(ValueError):
        await one_shot.one_shot_completion("hello", model="gpt-4o", **options)
    base.get_model.assert_not_called()
    model.get_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_endpoint_override_fails_without_request(provider):
    base, model = provider
    with pytest.raises(ValueError, match="request-local endpoint"):
        await one_shot.one_shot_completion("hello", model="gpt-4o", api_base="https://synthetic.test/v1")
    base.get_model.assert_not_called()
    model.get_response.assert_not_awaited()


def test_extracts_all_text_blocks_but_not_reasoning_or_refusal():
    response = response_with_text("first")
    response.output.insert(0, ResponseReasoningItem(
        id="reasoning-synthetic", type="reasoning", summary=[{"type": "summary_text", "text": "secret reasoning"}],
    ))
    response.output.append(ResponseOutputMessage(
        id="msg-second", type="message", role="assistant", status="completed",
        content=[{"type": "refusal", "refusal": "refused"},
                 {"type": "output_text", "text": "second", "annotations": []}],
    ))
    assert one_shot.extract_response_text(response) == "firstsecond"
    assert one_shot.extract_response_text(None) == ""
    assert one_shot.extract_response_text(ModelResponse(output=[], usage=Usage(), response_id=None)) == ""


def completed_event(output=None, usage=None, status="completed"):
    response = Response.model_construct(
        id="resp-stream-synthetic", status=status,
        output=response_with_text("final answer").output if output is None else output,
        usage=usage,
    )
    return ResponseCompletedEvent.model_construct(
        type="response.completed", response=response, sequence_number=2,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["gpt-4o", "gpt-5.4", "claude-sonnet-4.6"])
@pytest.mark.parametrize("stream", [None, True])
async def test_stream_returns_final_body_with_wrapper_and_request_local_scope(provider, monkeypatch, model_name, stream):
    base, model = provider
    model.model = model_name
    model.supports_native_responses_items = model_name == "gpt-5.4"
    process = Mock(side_effect=lambda items: items + [{"role": "user", "content": "processed"}])
    monkeypatch.setattr(one_shot, "process_input", process)
    closed = asyncio.Event()
    usage = ResponseUsage.model_validate({
        "input_tokens": 80, "output_tokens": 25, "total_tokens": 125,
        "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 4},
        "output_tokens_details": {"reasoning_tokens": 10},
    })
    final = completed_event(usage=usage)
    final.response._request_id = "req-stream-synthetic"
    reasoning = ResponseReasoningItem(
        id="reasoning-synthetic", type="reasoning",
        summary=[{"type": "summary_text", "text": "reasoning only"}],
    )
    final.response.output.insert(0, reasoning)
    seen = []

    async def events(**kwargs):
        seen.append(get_context_var(AGENT_NAME))
        try:
            yield SimpleNamespace(type="response.output_text.delta", delta="not the final body")
            yield final
            pytest.fail("The completed response must not wait for further events")
        finally:
            closed.set()

    model.stream_response = Mock(side_effect=events)
    with agent_name_scope("parent"):
        result = await one_shot.one_shot_completion(
            [{"role": "user", "content": "hello"}],
            model=model_name, provider="default", agent_name="auxiliary",
            model_settings=ModelSettings(preserve_raw_usage=True),
            **({"stream": stream} if stream is not None else {}),
        )
        assert get_context_var(AGENT_NAME) == "parent"
    assert isinstance(result, ModelResponse)
    assert one_shot.extract_response_text(result) == "final answer"
    assert result.response_id == "resp-stream-synthetic"
    assert result.request_id == "req-stream-synthetic"
    assert result.output[0] is reasoning
    assert (result.usage.requests, result.usage.input_tokens, result.usage.output_tokens) == (1, 80, 25)
    assert result.usage.input_tokens_details.cached_tokens == 20
    assert result.usage.input_tokens_details.cache_write_tokens == 4
    assert result.usage.output_tokens_details.reasoning_tokens == 10
    assert result.raw_usage["input_tokens"] == 80
    assert closed.is_set() and seen == ["auxiliary"]
    model.get_response.assert_not_awaited()
    sent = model.stream_response.call_args.kwargs
    assert sent["input"][-1]["content"] == "processed"
    assert sent["tools"] == sent["handoffs"] == []
    assert sent["previous_response_id"] is sent["conversation_id"] is sent["prompt"] is None
    process.assert_called_once()
    base.aclose.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_uses_completed_items_only_when_terminal_body_omits_output(provider):
    _, model = provider
    first = response_with_text("first").output[0]
    second = response_with_text("second").output[0]

    async def events(**kwargs):
        yield SimpleNamespace(type="response.output_item.done", output_index=1, item=second)
        yield SimpleNamespace(type="response.output_item.done", output_index=0, item=first)
        yield SimpleNamespace(type="response.output_item.done", output_index=0, item=first)
        yield completed_event(output=[])

    model.stream_response = Mock(side_effect=events)
    response = await one_shot.one_shot_completion("hello", model="gpt-4o", stream=True)
    assert response.output == [first, second]
    assert one_shot.extract_response_text(response) == "firstsecond"
    assert response.usage.requests == 1 and response.usage.total_tokens == 0
    assert response.raw_usage is None


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [
    None, "response.failed", "response.incomplete", "error", "response.error",
    "invalid-completed-body", "missing-completed-body",
])
async def test_stream_rejects_partial_or_failed_responses_and_closes_iterator(provider, terminal):
    base, model = provider
    closed = asyncio.Event()

    async def events(**kwargs):
        try:
            yield SimpleNamespace(type="response.output_text.delta", delta="partial text")
            if terminal == "invalid-completed-body":
                yield completed_event(status="incomplete")
            elif terminal == "missing-completed-body":
                yield SimpleNamespace(type="response.completed", response=None)
            elif terminal:
                yield SimpleNamespace(type=terminal)
        finally:
            closed.set()

    model.stream_response = Mock(side_effect=events)
    with pytest.raises(ModelBehaviorError, match="(?i)model.*stream"):
        await one_shot.one_shot_completion("hello", model="gpt-4o")
    assert closed.is_set()
    model.get_response.assert_not_awaited()
    base.aclose.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_stream_timeout_or_cancellation_closes_request_but_not_provider(provider, cancel):
    base, model = provider
    started, closed = asyncio.Event(), asyncio.Event()

    async def events(**kwargs):
        try:
            started.set()
            yield SimpleNamespace(type="response.output_text.delta", delta="partial")
            await asyncio.Event().wait()
        finally:
            closed.set()

    model.stream_response = Mock(side_effect=events)
    task = asyncio.create_task(one_shot.one_shot_completion(
        "hello", model="gpt-4o", timeout=None if cancel else 0.01,
    ))
    await started.wait()
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
        await task
    assert closed.is_set()
    base.aclose.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_transport_failure_propagates_without_non_streaming_retry(provider):
    base, model = provider

    async def events(**kwargs):
        assert get_context_var(AGENT_NAME) == "auxiliary"
        yield SimpleNamespace(type="response.output_text.delta", delta="partial")
        raise OSError("synthetic disconnect")

    model.stream_response = Mock(side_effect=events)
    with agent_name_scope("parent"):
        with pytest.raises(OSError, match="synthetic disconnect"):
            await one_shot.one_shot_completion("hello", model="gpt-4o", agent_name="auxiliary")
        assert get_context_var(AGENT_NAME) == "parent"
    model.stream_response.assert_called_once()
    model.get_response.assert_not_awaited()
    base.aclose.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [False, True])
async def test_interleaved_completed_tool_pairs_are_repaired_only_for_chat(provider, native):
    _, model = provider
    model.supports_native_responses_items = native
    history = [
        {"type": "function_call", "call_id": "call-synthetic", "name": "read", "arguments": "{}"},
        {"role": "assistant", "content": "interleaved text"},
        {"type": "function_call_output", "call_id": "call-synthetic", "output": "done"},
    ]
    original = deepcopy(history)
    await one_shot.one_shot_completion(history, model="gpt-4o", stream=False)
    sent = model.get_response.await_args.kwargs["input"]
    assert sent[1].get("type") == (None if native else "function_call_output")
    assert history == original
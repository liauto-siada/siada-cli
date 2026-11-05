from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agents import Agent, RunConfig, Runner
from agents.decorators import function_tool
from agents.exceptions import UserError

from siada.agent_hub.context_filter.header_summary_compaction_strategy import SummarizeWithHeaderCompaction
from siada.agent_hub.context_filter.turn_prune_compaction_strategy import TurnPruneSummaryCompaction
from siada.provider import one_shot
from siada.provider.gemini import GeminiModel
from siada.provider.gemini.replay import decode_replay, encode_replay
from siada.services.file_session import FileSession
from siada.services.model_wrapper import ModelWrapper
from siada.support.provider_metadata import without_provider_metadata

from test_gemini_model import native_response, request_args, sse
from test_gemini_replay_boundary import native_provider


def imported_history(layout: str = "grouped") -> list[dict]:
    calls = [
        {
            "type": "function_call", "id": f"foreign-item-{value}",
            "call_id": f"foreign-call-{value}", "name": "lookup",
            "arguments": json.dumps({"value": value}),
            "provider_data": {"another": {"model": "synthetic-model"}},
        }
        for value in (1, 2)
    ]
    results = [
        {"type": "function_call_output", "call_id": f"foreign-call-{value}", "output": f"old result {value}"}
        for value in (1, 2)
    ]
    tools = [*calls, *reversed(results)] if layout == "grouped" else [calls[0], results[0], calls[1], results[1]]
    return [
        {"role": "user", "content": "old user"},
        {"type": "reasoning", "id": "foreign-reasoning", "summary": [{"type": "summary_text", "text": "old reasoning"}]},
        {"role": "assistant", "content": "before"},
        *tools,
        {"role": "assistant", "content": "old final"},
        {"role": "user", "content": "next user"},
    ]


def expected_imported_contents() -> list[dict]:
    return [
        {"role": "user", "parts": [{"text": "old user"}]},
        {"role": "model", "parts": [{"text": "before"}]},
        {"role": "model", "parts": [
            {"functionCall": {"name": "lookup", "args": {"value": 1}}, "thoughtSignature": "skip_thought_signature_validator"},
            {"functionCall": {"name": "lookup", "args": {"value": 2}}, "thoughtSignature": "skip_thought_signature_validator"},
        ]},
        {"role": "user", "parts": [
            {"functionResponse": {"name": "lookup", "response": {"output": "old result 1"}}},
            {"functionResponse": {"name": "lookup", "response": {"output": "old result 2"}}},
        ]},
        {"role": "model", "parts": [{"text": "old final"}]},
        {"role": "user", "parts": [{"text": "next user"}]},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("layout", ["grouped", "interleaved"])
@pytest.mark.parametrize("model_name", ["gemini-3.5-flash", "gemini-4-synthetic"])
async def test_foreign_parallel_history_is_grouped_with_literal_bypass(
    native_provider, endpoint, stream, layout, model_name,
):
    _provider_name, provider = native_provider
    history = imported_history(layout)
    original = copy.deepcopy(history)
    final = native_response([{"text": "done", "thoughtSignature": "ZG9uZQ=="}])
    endpoint.responses = [(200, sse(final) if stream else final)]
    model = ModelWrapper(provider.get_model(model_name))
    if stream:
        events = [event async for event in model.stream_response(**request_args(history))]
        output = events[-1].response.output
    else:
        output = (await model.get_response(**request_args(history))).output
    assert endpoint.requests[0][1]["contents"] == expected_imported_contents()
    assert "provider_data" not in json.dumps(endpoint.requests[0][1])
    assert decode_replay(output[0])["parts"][0]["part"]["thought_signature"] == "ZG9uZQ=="
    assert history == original
    assert len(endpoint.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_one_shot_imports_interleaved_chat_tool_history(native_provider, endpoint, monkeypatch, stream):
    provider_name, provider = native_provider
    final = native_response([{"text": "done"}])
    endpoint.responses = [(200, sse(final) if stream else final)]
    messages = [
        {"role": "user", "content": "old user"},
        {"role": "assistant", "content": "before", "tool_calls": [
            {"type": "function", "id": "foreign-call-1", "function": {"name": "lookup", "arguments": '{"value": 1}'}},
        ]},
        {"role": "tool", "tool_call_id": "foreign-call-1", "content": "old result 1"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"type": "function", "id": "foreign-call-2", "function": {"name": "lookup", "arguments": '{"value": 2}'}},
        ]},
        {"role": "tool", "tool_call_id": "foreign-call-2", "content": "old result 2"},
        {"role": "assistant", "content": "old final"},
        {"role": "user", "content": "next user"},
    ]
    original = copy.deepcopy(messages)
    monkeypatch.setattr(one_shot, "get_provider", lambda _: provider)
    response = await one_shot.one_shot_completion(
        [], messages=messages, model="gemini-3.5-flash", provider=provider_name, stream=stream, timeout=5,
    )
    assert one_shot.extract_response_text(response) == "done"
    assert endpoint.requests[0][1]["contents"] == expected_imported_contents()
    assert "tools" not in endpoint.requests[0][1]
    assert messages == original


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_runner_switch_and_reload_keep_imported_history_and_native_signatures(endpoint, client, tmp_path, stream):
    old = imported_history()[:-1]
    original = copy.deepcopy(old)
    signed_call = [{"functionCall": {"name": "lookup", "args": {"value": 3}}, "thoughtSignature": "bmV3"}]
    final = [{"text": "done", "thoughtSignature": "ZmluYWw="}]
    endpoint.responses = [
        (200, sse(native_response(parts)) if stream else native_response(parts))
        for parts in (signed_call, final)
    ] + [(200, native_response([{"text": "next"}]))]
    executed = []

    @function_tool
    def lookup(value: int) -> str:
        executed.append(value)
        return str(value)

    store = FileSession("imported-history", sessions_dir=tmp_path)
    await store.add_items(old)
    await store.migrate_legacy_context(allow_history_only=True)
    model = ModelWrapper(GeminiModel("gemini-3.5-flash", client=client))
    agent = Agent(name="synthetic", model=model, tools=[lookup])
    config = RunConfig(tracing_disabled=True)
    if stream:
        result = Runner.run_streamed(agent, "next user", session=store, run_config=config)
        async for _ in result.stream_events():
            pass
    else:
        result = await Runner.run(agent, "next user", session=store, run_config=config)
    assert result.final_output == "done"
    assert executed == [3]
    assert endpoint.requests[0][1]["contents"] == expected_imported_contents()
    assert endpoint.requests[1][1]["contents"][6] == {"role": "model", "parts": signed_call}
    restored = FileSession("imported-history", sessions_dir=tmp_path)
    history = restored.get_context_snapshot_sync()["items"]
    assert history[:len(old)] == original
    await ModelWrapper(GeminiModel("gemini-3.5-flash", client=client)).get_response(
        **request_args([*history, {"role": "user", "content": "after reload"}]),
    )
    body = endpoint.requests[2][1]
    assert body["contents"][:6] == expected_imported_contents()
    assert body["contents"][6] == {"role": "model", "parts": signed_call}
    assert body["contents"][8] == {"role": "model", "parts": final}
    assert old == original
    assert len(endpoint.requests) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy_type", [SummarizeWithHeaderCompaction, TurnPruneSummaryCompaction])
@pytest.mark.parametrize("tool_type", ["function", "apply_patch", "custom"])
async def test_compaction_uses_the_same_strategy_for_imported_and_signed_items(
    endpoint, client, monkeypatch, strategy_type, tool_type,
):
    endpoint.responses = [(200, native_response([
        {"functionCall": {"name": "lookup", "args": {"value": 3}}, "thoughtSignature": "bmV3"},
    ]))]
    response = await GeminiModel("gemini-3.5-flash", client=client).get_response(**request_args())
    active = [
        {"role": "user", "content": "next user"}, *response.to_input_items(),
        {"type": "function_call_output", "call_id": response.output[0].call_id, "output": "new result"},
    ]
    old = imported_history()[:-1]
    if tool_type == "apply_patch":
        old = [
            {"role": "user", "content": "old user"},
            {"type": "apply_patch_call", "call_id": "foreign", "operation": {"type": "update_file", "path": "synthetic.py", "diff": "@@"}},
            {"type": "apply_patch_call_output", "call_id": "foreign", "output": "old result 1"},
            {"role": "assistant", "content": "old final"},
        ]
    elif tool_type == "custom":
        old = [
            {"role": "user", "content": "old user"},
            {"type": "custom_tool_call", "call_id": "foreign", "name": "custom_lookup", "input": "synthetic input"},
            {"type": "custom_tool_call_output", "call_id": "foreign", "output": "old result 1"},
            {"role": "assistant", "content": "old final"},
        ]
    history = [*old] * 8 + active
    original = copy.deepcopy(history)
    summarize = AsyncMock(return_value="summary")
    strategy = strategy_type()
    monkeypatch.setattr(strategy, "call_llm_to_compact", summarize)
    monkeypatch.setenv("BASE_URL", endpoint.url)
    config = SimpleNamespace(model_name="gemini-3.5-flash", provider="default", context_window=100_000)
    plain = without_provider_metadata(history)
    plain_strategy = strategy_type()
    monkeypatch.setattr(plain_strategy, "call_llm_to_compact", AsyncMock(return_value="summary"))
    expected = await plain_strategy.compact(config, plain)
    result = await strategy.compact(config, history)
    assert result.compacted == expected.compacted
    assert without_provider_metadata(result.messages) == expected.messages
    summarized = summarize.call_args.args[1] if len(summarize.call_args.args) > 1 else summarize.call_args.kwargs["history_to_compact"]
    assert "old result 1" in json.dumps(summarized)
    assert history == original


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("boundary", ["message", "reasoning"])
async def test_imported_sequential_steps_keep_explicit_boundaries(endpoint, client, stream, boundary):
    step_boundary = (
        {"role": "assistant", "content": "next step"} if boundary == "message"
        else {"type": "reasoning", "id": "step-reasoning", "summary": []}
    )
    history = [
        {"role": "user", "content": "start"},
        {"type": "function_call", "call_id": "first", "name": "lookup", "arguments": '{"value": 1}'},
        {"type": "function_call_output", "call_id": "first", "output": "first result"},
        step_boundary,
        {"type": "function_call", "call_id": "second", "name": "lookup", "arguments": '{"value": 2}'},
        {"type": "function_call_output", "call_id": "second", "output": "second result"},
        {"role": "user", "content": "continue"},
    ]
    original = copy.deepcopy(history)
    final = native_response([{"text": "done"}])
    endpoint.responses = [(200, sse(final) if stream else final)]
    model = ModelWrapper(GeminiModel("gemini-3.5-flash", client=client))
    if stream:
        async for _ in model.stream_response(**request_args(history)):
            pass
    else:
        await model.get_response(**request_args(history))
    expected = [
        {"role": "user", "parts": [{"text": "start"}]},
        {"role": "model", "parts": [{
            "functionCall": {"name": "lookup", "args": {"value": 1}},
            "thoughtSignature": "skip_thought_signature_validator",
        }]},
        {"role": "user", "parts": [{
            "functionResponse": {"name": "lookup", "response": {"output": "first result"}},
        }]},
    ]
    if boundary == "message":
        expected.append({"role": "model", "parts": [{"text": "next step"}]})
    expected.extend([
        {"role": "model", "parts": [{
            "functionCall": {"name": "lookup", "args": {"value": 2}},
            "thoughtSignature": "skip_thought_signature_validator",
        }]},
        {"role": "user", "parts": [{
            "functionResponse": {"name": "lookup", "response": {"output": "second result"}},
        }]},
        {"role": "user", "parts": [{"text": "continue"}]},
    ])
    assert endpoint.requests[0][1]["contents"] == expected
    assert history == original


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_imported_assistant_text_inside_pending_calls_stays_in_the_call_group(endpoint, client, stream):
    history = [
        {"role": "user", "content": "start"},
        {"type": "function_call", "call_id": "first", "name": "lookup", "arguments": '{"value": 1}'},
        {"role": "assistant", "content": "between"},
        {"type": "function_call", "call_id": "second", "name": "lookup", "arguments": '{"value": 2}'},
        {"type": "function_call_output", "call_id": "second", "output": "second result"},
        {"type": "function_call_output", "call_id": "first", "output": "first result"},
    ]
    final = native_response([{"text": "done"}])
    endpoint.responses = [(200, sse(final) if stream else final)]
    model = ModelWrapper(GeminiModel("gemini-3.5-flash", client=client))
    if stream:
        async for _ in model.stream_response(**request_args(history)):
            pass
    else:
        await model.get_response(**request_args(history))
    assert endpoint.requests[0][1]["contents"][1:3] == [
        {"role": "model", "parts": [
            {"functionCall": {"name": "lookup", "args": {"value": 1}}, "thoughtSignature": "skip_thought_signature_validator"},
            {"text": "between"},
            {"functionCall": {"name": "lookup", "args": {"value": 2}}, "thoughtSignature": "skip_thought_signature_validator"},
        ]},
        {"role": "user", "parts": [
            {"functionResponse": {"name": "lookup", "response": {"output": "first result"}}},
            {"functionResponse": {"name": "lookup", "response": {"output": "second result"}}},
        ]},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("tool_type", ["apply_patch", "custom"])
async def test_imported_responses_tools_use_existing_function_proxies(endpoint, client, stream, tool_type):
    if tool_type == "apply_patch":
        payload = {"operation": {"type": "update_file", "path": "synthetic.py", "diff": "@@"}}
        name = "apply_patch"
        call = {"type": "apply_patch_call", "call_id": "foreign", "id": "patch", **payload}
        result = {"type": "apply_patch_call_output", "call_id": "foreign", "output": "saved"}
    else:
        payload = {"input": "synthetic input"}
        name = "custom_lookup"
        call = {"type": "custom_tool_call", "call_id": "foreign", "name": name, "input": "synthetic input"}
        result = {"type": "custom_tool_call_output", "call_id": "foreign", "output": "saved"}
    history = [{"role": "user", "content": "start"}, call, result]
    original = copy.deepcopy(history)
    final = native_response([{"text": "done"}])
    endpoint.responses = [(200, sse(final) if stream else final)]
    model = ModelWrapper(GeminiModel("gemini-3.5-flash", client=client))
    if stream:
        async for _ in model.stream_response(**request_args(history)):
            pass
    else:
        await model.get_response(**request_args(history))
    assert endpoint.requests[0][1]["contents"][1:3] == [
        {"role": "model", "parts": [{
            "functionCall": {"name": name, "args": payload},
            "thoughtSignature": "skip_thought_signature_validator",
        }]},
        {"role": "user", "parts": [{
            "functionResponse": {"name": name, "response": {"output": "saved"}},
        }]},
    ]
    assert history == original


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("problem", [
    "missing_result", "orphan_result", "duplicate_result", "duplicate_call",
    "duplicate_call_across_steps", "empty_call_id", "missing_name",
    "invalid_json", "non_object_json", "unsupported_result_content",
])
async def test_invalid_imported_tool_history_fails_before_http(endpoint, client, stream, problem):
    call = {"type": "function_call", "call_id": "foreign", "name": "lookup", "arguments": '{"value": 1}'}
    result = {"type": "function_call_output", "call_id": "foreign", "output": "result"}
    tools = [call, result]
    if problem == "missing_result":
        tools.pop()
    elif problem == "orphan_result":
        result["call_id"] = "unknown"
    elif problem == "duplicate_result":
        tools.append(copy.deepcopy(result))
    elif problem == "duplicate_call":
        tools.insert(1, copy.deepcopy(call))
    elif problem == "duplicate_call_across_steps":
        tools.extend([{"role": "assistant", "content": "next step"}, copy.deepcopy(call), copy.deepcopy(result)])
    elif problem == "empty_call_id":
        call["call_id"] = ""
    elif problem == "missing_name":
        call.pop("name")
    elif problem == "invalid_json":
        call["arguments"] = '{"synthetic-secret":'
    elif problem == "non_object_json":
        call["arguments"] = "[]"
    elif problem == "unsupported_result_content":
        result["output"] = [{"type": "input_file", "file_id": "synthetic-file"}]
    history = [{"role": "user", "content": "start"}, *tools, {"role": "user", "content": "continue"}]
    original = copy.deepcopy(history)
    model = ModelWrapper(GeminiModel("gemini-3.5-flash", client=client))
    with pytest.raises(UserError) as caught:
        if stream:
            async for _ in model.stream_response(**request_args(history)):
                pass
        else:
            await model.get_response(**request_args(history))
    assert "synthetic-secret" not in str(caught.value)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert endpoint.requests == []
    assert history == original


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("problem", ["origin", "invalid_payload", "split", "view"])
async def test_import_compatibility_preserves_native_history_checks(endpoint, client, stream, problem):
    parts = [
        {"text": "native", "thoughtSignature": "bmF0aXZl"},
        {"functionCall": {"name": "lookup", "args": {"value": 3}}, "thoughtSignature": "bmV3"},
    ]
    endpoint.responses = [(200, native_response(parts))]
    model = ModelWrapper(GeminiModel("gemini-3.5-flash", client=client))
    native = (await model.get_response(**request_args())).to_input_items()
    call_id = native[-1]["call_id"]
    if problem == "origin":
        payload = decode_replay(native[0])
        payload["origin"]["model"] = "different-model"
        native[0]["provider_data"]["gemini"] = encode_replay(payload)
    elif problem == "invalid_payload":
        native[0]["provider_data"]["gemini"]["replay"] = "invalid"
    elif problem == "split":
        native.insert(1, {"role": "assistant", "content": "foreign insertion"})
    elif problem == "view":
        native[-1]["arguments"] = "{}"
    history = [
        *imported_history(), *native,
        {"type": "function_call_output", "call_id": call_id, "output": "new result"},
    ]
    original = copy.deepcopy(history)
    with pytest.raises(UserError):
        if stream:
            async for _ in model.stream_response(**request_args(history)):
                pass
        else:
            await model.get_response(**request_args(history))
    assert len(endpoint.requests) == 1
    assert history == original

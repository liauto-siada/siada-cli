from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import httpx
from agents import OpenAIChatCompletionsModel
from agents.exceptions import UserError
from google.genai import types
from openai import AsyncOpenAI

from siada.agent_hub.context_filter.header_summary_compaction_strategy import SummarizeWithHeaderCompaction
from siada.agent_hub.context_filter.turn_prune_compaction_strategy import TurnPruneSummaryCompaction
from siada.provider.gemini.replay import decode_replay
from siada.provider import one_shot
from siada.services.file_session import FileSession
from siada.services.model_wrapper import ModelWrapper
from siada.support.provider_metadata import without_provider_metadata

from test_gemini_model import native_response, request_args, sse
from test_gemini_replay_boundary import native_provider


async def collect_output(model, input, stream):
    if stream:
        events = [event async for event in model.stream_response(**request_args(input))]
        return [item.model_dump(mode="json", exclude_unset=True) for item in events[-1].response.output]
    return (await model.get_response(**request_args(input))).to_input_items()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("strategy_type", [SummarizeWithHeaderCompaction, TurnPruneSummaryCompaction])
async def test_unified_compaction_reload_and_checkpoint_replay_signed_text_and_tools(
    native_provider, endpoint, tmp_path, monkeypatch, stream, strategy_type,
):
    _provider_name, provider = native_provider
    model = ModelWrapper(provider.get_model("gemini-3.5-flash"))
    history = [{"role": "user", "content": "Original task"}]
    snapshots = {}
    for step in range(9):
        parts = [
            {"text": f"thought {step}", "thought": True, "thoughtSignature": "cmVhc29u"},
            {"text": f"text {step}", "thoughtSignature": "dGV4dA=="},
            {"functionCall": {"name": "lookup", "args": {"step": step, "value": 1}}, "thoughtSignature": "dG9vbA=="},
            {"functionCall": {"name": "lookup", "args": {"step": step, "value": 2}}},
            {"text": "", "thoughtSignature": "dGFpbA=="},
        ]
        fragments = [[part] for part in parts] if stream else [parts]
        responses = [native_response(fragment, finish="STOP" if index == len(fragments) - 1 else None)
                     for index, fragment in enumerate(fragments)]
        endpoint.responses = [(200, sse(*responses) if stream else responses[0])]
        items = await collect_output(model, "synthetic request", stream)
        for item in items:
            metadata = item["provider_data"]["gemini"]
            assert set(metadata) == {"version", "replay"}
            assert isinstance(metadata["replay"], str)
            snapshots[item["id"]] = copy.deepcopy(decode_replay(item))
        history.extend(items)
        for item in reversed(items):
            if item["type"] == "function_call":
                history.append({"type": "function_call_output", "call_id": item["call_id"], "output": f"result {step}: " + "x" * 200})
    original = copy.deepcopy(history)
    config = SimpleNamespace(model_name="gemini-3.5-flash", provider=_provider_name, context_window=100_000)
    strategy = strategy_type()
    summary = AsyncMock(return_value="<context>Continue the original task.</context>")
    monkeypatch.setattr(strategy, "call_llm_to_compact", summary)
    plain_strategy = strategy_type()
    monkeypatch.setattr(plain_strategy, "call_llm_to_compact", AsyncMock(return_value=summary.return_value))
    expected = await plain_strategy.compact(config, without_provider_metadata(history))
    compacted = await strategy.compact(config, history)
    assert compacted.compacted and expected.compacted
    assert without_provider_metadata(compacted.messages) == expected.messages
    assert len(compacted.messages) < len(history)
    assert history == original
    for item in compacted.messages:
        if item.get("id") in snapshots:
            assert decode_replay(item) == snapshots[item["id"]]

    store = FileSession("signed-compaction", sessions_dir=tmp_path)
    await store.add_items(compacted.messages)
    await store.migrate_legacy_context(allow_history_only=True)
    checkpoint = store.get_checkpoint_snapshot_sync()
    await store.append_context_items([{"role": "user", "content": "abandoned"}], message_ids=["abandoned"])
    store.restore_checkpoint_sync(
        checkpoint["history_items"], checkpoint["context_snapshot"],
        expected_version=store.get_context_snapshot_sync()["context_version"], before_commit=lambda: None,
    )
    restored = FileSession("signed-compaction", sessions_dir=tmp_path).get_context_snapshot_sync()["items"]
    assert restored == compacted.messages
    final = native_response([{"text": "done", "thoughtSignature": "ZmluYWw="}])
    endpoint.responses = [(200, sse(final) if stream else final)]
    await collect_output(ModelWrapper(provider.get_model("gemini-3.5-flash")), restored, stream)
    body = endpoint.requests[-1][1]
    expected_groups = {}
    for item in restored:
        payload = snapshots.get(item.get("id"))
        if payload is None:
            continue
        groups = expected_groups.setdefault(payload["response_group_id"], {})
        for record in payload["parts"]:
            groups.setdefault(record["content_index"], {})[record["part_index"]] = record["part"]
    expected_contents = [
        {"role": "model", "parts": [parts[index] for _content_index, parts in sorted(groups.items()) for index in sorted(parts)]}
        for groups in expected_groups.values()
    ]
    expected_wire = [types.Content.model_validate(content).model_dump(mode="json", by_alias=True, exclude_none=True)
                     for content in expected_contents]
    assert [content for content in body["contents"] if content["role"] == "model"] == expected_wire
    for content in body["contents"]:
        calls = [part for part in content["parts"] if "functionCall" in part]
        if calls:
            assert len(calls) == 2
            assert calls[0]["thoughtSignature"] == "dG9vbA=="
            assert "thoughtSignature" not in calls[1]
    assert "provider_data" not in json.dumps(body)
    assert "abandoned" not in json.dumps(body)
    assert summary.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_tool_items_replay_without_a_text_owner(native_provider, endpoint, stream):
    _provider_name, provider = native_provider
    parts = [
        {"text": "display", "thoughtSignature": "dGV4dA=="},
        {"functionCall": {"name": "lookup", "args": {"value": 1}}, "thoughtSignature": "Zmlyc3Q="},
        {"functionCall": {"name": "lookup", "args": {"value": 2}}},
    ]
    response = native_response(parts)
    final = native_response([{"text": "done"}])
    endpoint.responses = [(200, sse(response) if stream else response), (200, sse(final) if stream else final)]
    model = ModelWrapper(provider.get_model("gemini-3.5-flash"))
    items = await collect_output(model, "start", stream)
    calls = [item for item in items if item["type"] == "function_call"]
    history = [{"role": "user", "content": "summary"}, *calls,
               *[{"type": "function_call_output", "call_id": item["call_id"], "output": item["arguments"]} for item in reversed(calls)]]
    await collect_output(model, history, stream)
    assert endpoint.requests[-1][1]["contents"][1] == {"role": "model", "parts": parts[1:]}
    results = endpoint.requests[-1][1]["contents"][2]["parts"]
    assert [part["functionResponse"]["response"]["output"] for part in results] == [item["arguments"] for item in calls]
    broken = [history[0], calls[1], history[3]]
    with pytest.raises(UserError, match="split"):
        await collect_output(model, broken, stream)
    assert len(endpoint.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("layout", ["mixed", "tools_only"])
async def test_legacy_envelopes_replay_all_signed_parts_inside_provider(native_provider, endpoint, stream, layout):
    _provider_name, provider = native_provider
    parts = [
        {"functionCall": {"name": "lookup", "args": {"value": 1}}, "thoughtSignature": "Zmlyc3Q="},
        {"functionCall": {"name": "lookup", "args": {"value": 2}}},
        {"thoughtSignature": "dGFpbA=="},
    ]
    if layout == "mixed":
        parts[:0] = [
            {"text": "thinking", "thought": True, "thoughtSignature": "cmVhc29u"},
            {"text": "display", "thoughtSignature": "dGV4dA=="},
        ]
    response = native_response(parts)
    final = native_response([{"text": "done"}])
    endpoint.responses = [(200, sse(response) if stream else response), (200, sse(final) if stream else final)]
    model = ModelWrapper(provider.get_model("gemini-3.5-flash"))
    items = await collect_output(model, "start", stream)
    snapshots = [decode_replay(item) for item in items]
    for item, snapshot in zip(items, snapshots):
        metadata = {"version": 1, "origin": snapshot["origin"], "response_group_id": snapshot["response_group_id"]}
        if item["type"] == "function_call":
            call_part = next(record for record in snapshot["parts"] if "function_call" in record["part"])
            metadata["part_position"] = [call_part["content_index"], call_part["part_index"]]
        item["provider_data"]["gemini"] = metadata
    items[0]["provider_data"]["gemini"].update(
        contents=[types.Content.model_validate({"role": "model", "parts": parts}).model_dump(mode="json", exclude_none=True)],
        item_ids=[item["id"] for item in items],
    )
    history = [{"role": "user", "content": "start"}, *items,
               *[{"type": "function_call_output", "call_id": item["call_id"], "output": "result"}
                 for item in items if item["type"] == "function_call"]]
    original = copy.deepcopy(history)
    await collect_output(model, history, stream)
    assert endpoint.requests[-1][1]["contents"][1] == {"role": "model", "parts": parts}
    assert history == original


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("kind", ["message", "reasoning"])
async def test_signed_text_changes_are_rejected_without_http(native_provider, endpoint, stream, kind):
    _provider_name, provider = native_provider
    response = native_response([
        {"text": "thinking", "thought": True, "thoughtSignature": "cmVhc29u"},
        {"text": "display", "thoughtSignature": "dGV4dA=="},
    ])
    endpoint.responses = [(200, sse(response) if stream else response)]
    model = ModelWrapper(provider.get_model("gemini-3.5-flash"))
    items = await collect_output(model, "start", stream)
    item = next(item for item in items if item["type"] == kind)
    if kind == "message":
        item["content"][0]["text"] = "changed"
    else:
        item["summary"][0]["text"] = "changed"
    with pytest.raises(UserError, match="text view"):
        await collect_output(model, items, stream)
    assert len(endpoint.requests) == 1


@pytest.mark.asyncio
async def test_shared_summarizer_can_use_a_chat_model_without_forwarding_native_metadata(native_provider, endpoint, monkeypatch):
    _provider_name, provider = native_provider
    response = native_response([
        {"text": "thinking", "thought": True, "thoughtSignature": "cmVhc29u"},
        {"text": "display", "thoughtSignature": "dGV4dA=="},
        {"functionCall": {"name": "lookup", "args": {"value": 1}}, "thoughtSignature": "dG9vbA=="},
    ])
    endpoint.responses = [(200, response)]
    items = await collect_output(ModelWrapper(provider.get_model("gemini-3.5-flash")), "start", False)
    call = next(item for item in items if item["type"] == "function_call")
    history = [{"role": "user", "content": "start"}, *items,
               {"type": "function_call_output", "call_id": call["call_id"], "output": "saved result"}]
    original = copy.deepcopy(history)
    chunks = [
        {"id": "chat-summary", "object": "chat.completion.chunk", "created": 0, "model": "gpt-4o", "choices": [
            {"index": 0, "delta": {"role": "assistant", "content": "<context>summary</context>"}, "finish_reason": None},
        ]},
        {"id": "chat-summary", "object": "chat.completion.chunk", "created": 0, "model": "gpt-4o", "choices": [
            {"index": 0, "delta": {}, "finish_reason": "stop"},
        ]},
    ]
    endpoint.responses = [(200, sse(*chunks) + b"data: [DONE]\n\n")]
    client = AsyncOpenAI(api_key="synthetic-key", base_url=endpoint.url + "/v1", http_client=httpx.AsyncClient(trust_env=False))
    chat = OpenAIChatCompletionsModel("gpt-4o", client)
    monkeypatch.setattr(one_shot, "get_provider", lambda _: SimpleNamespace(get_model=lambda _: chat))
    monkeypatch.setenv("SIADA_COMPACT_MODEL", "gpt-4o")
    config = SimpleNamespace(model_name="gemini-3.5-flash", provider="default")
    try:
        summary = await SummarizeWithHeaderCompaction().call_llm_to_compact(config, history)
    finally:
        await client.close()
    assert summary == "<context>summary</context>"
    path, body, _headers = endpoint.requests[-1]
    assert path == "/v1/chat/completions"
    assert "display" in json.dumps(body)
    assert "saved result" in json.dumps(body)
    assert "provider_data" not in json.dumps(body)
    assert "thought_signature" not in json.dumps(body)
    assert "thoughtSignature" not in json.dumps(body)
    assert history == original

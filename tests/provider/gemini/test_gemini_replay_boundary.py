from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from agents import Agent, RunConfig, Runner
from agents.decorators import function_tool

from siada.provider import one_shot
from siada.provider.default.default_provider import DefaultProvider
from siada.provider.gemini import GeminiModel
from siada.provider.gemini.replay import decode_replay
from siada.services.file_session import FileSession
from siada.services.model_wrapper import ModelWrapper

from test_gemini_model import native_response, request_args, sse


@pytest_asyncio.fixture(params=["default"])
async def native_provider(request, endpoint, monkeypatch):
    monkeypatch.setenv("BASE_URL", endpoint.url)
    monkeypatch.setenv("GEMINI_BASE_URL", endpoint.url)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-api-key")
    provider = DefaultProvider()
    try:
        yield request.param, provider
    finally:
        await provider.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_runner_fragments_survive_reload_and_checkpoint(
    native_provider, endpoint, tmp_path, stream,
):
    _provider_name, provider = native_provider
    tool_parts = [
        {"text": "plan", "thought": True, "thoughtSignature": "cGxhbg=="},
        {"text": "before", "thoughtSignature": "YmVmb3Jl"},
        {"functionCall": {"name": "lookup", "args": {"value": 1}}, "thoughtSignature": "Zmlyc3Q="},
        {"functionCall": {"name": "lookup", "args": {"value": 2}}},
    ]
    tool_tail = {"text": "", "thoughtSignature": "dG9vbC10YWls"}
    final_parts = [
        {"text": "first", "thoughtSignature": "Zmlyc3Q="},
        {"text": "second", "thoughtSignature": "c2Vjb25k"},
        {"text": "", "thoughtSignature": "ZmluYWwtdGFpbA=="},
    ]
    if stream:
        tool_responses = [
            native_response(tool_parts[:2], finish=None),
            native_response([tool_parts[2]], finish=None),
            native_response([tool_parts[3]], finish=None),
            native_response([tool_tail]),
        ]
        final_responses = [
            native_response([part], finish=None if index < 2 else "STOP")
            for index, part in enumerate(final_parts)
        ]
    else:
        tool_responses = [native_response([*tool_parts, tool_tail])]
        final_responses = [native_response(final_parts)]
    endpoint.responses = [
        (200, sse(*tool_responses) if stream else tool_responses[0]),
        (200, sse(*final_responses) if stream else final_responses[0]),
        (200, native_response([{"text": "next"}])),
    ]
    executed = []

    @function_tool
    async def lookup(value: int) -> str:
        executed.append(value)
        await asyncio.sleep(0)
        return str(value)

    model_name = "gemini-3.5-flash"
    agent = Agent(
        name="synthetic", model=ModelWrapper(provider.get_model(model_name)),
        tools=[lookup],
    )
    store = FileSession("fragment-checkpoint", sessions_dir=tmp_path)
    run_config = RunConfig(tracing_disabled=True)
    if stream:
        result = Runner.run_streamed(agent, "start", session=store, run_config=run_config)
        async for _ in result.stream_events():
            pass
    else:
        result = await Runner.run(agent, "start", session=store, run_config=run_config)
    assert result.final_output == "firstsecond"
    assert sorted(executed) == [1, 2]

    restored = FileSession("fragment-checkpoint", sessions_dir=tmp_path)
    await restored.migrate_legacy_context(allow_history_only=True)
    checkpoint = restored.get_checkpoint_snapshot_sync()
    original = copy.deepcopy(checkpoint)
    await restored.append_context_items(
        [{"role": "user", "content": "abandoned"}], message_ids=["later"],
    )
    restored.restore_checkpoint_sync(
        checkpoint["history_items"], checkpoint["context_snapshot"],
        expected_version=restored.get_context_snapshot_sync()["context_version"],
        before_commit=lambda: None,
    )
    fresh_store = FileSession("fragment-checkpoint", sessions_dir=tmp_path)
    history = fresh_store.get_context_snapshot_sync()["items"]
    assert history == original["context_snapshot"]["items"]
    await ModelWrapper(provider.get_model(model_name)).get_response(
        **request_args([*history, {"role": "user", "content": "next user"}]),
    )

    body = endpoint.requests[-1][1]
    expected = [
        {"role": "model", "parts": [*tool_parts, tool_tail]},
        {"role": "model", "parts": final_parts},
    ]
    assert [content for content in body["contents"] if content["role"] == "model"] == expected
    results = [
        part["functionResponse"]
        for content in body["contents"] for part in content["parts"]
        if "functionResponse" in part
    ]
    assert results == [
        {"name": "lookup", "response": {"output": "1"}},
        {"name": "lookup", "response": {"output": "2"}},
    ]
    assert len(endpoint.requests) == 3
    assert "abandoned" not in json.dumps(body)
    assert "provider_data" not in json.dumps(body)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_one_shot_replays_signed_parallel_history_without_chat_reordering(
    native_provider, endpoint, monkeypatch, stream,
):
    provider_name, provider = native_provider
    parts = [
        {"text": "before", "thoughtSignature": "YmVmb3Jl"},
        {"functionCall": {"name": "lookup", "args": {"value": 1}}, "thoughtSignature": "Zmlyc3Q="},
        {"functionCall": {"name": "lookup", "args": {"value": 2}}},
    ]
    final = native_response([{"text": "done", "thoughtSignature": "ZG9uZQ=="}])
    endpoint.responses = [
        (200, native_response(parts)),
        (200, sse(final) if stream else final),
    ]
    response = await provider.get_model("gemini-3.5-flash").get_response(**request_args())
    items = response.to_input_items()
    calls = [item for item in items if item["type"] == "function_call"]
    history = [
        {"role": "user", "content": "start"}, *items,
        *[
            {"type": "function_call_output", "call_id": call["call_id"], "output": str(index)}
            for index, call in reversed(list(enumerate(calls, start=1)))
        ],
        {"role": "user", "content": "next"},
    ]
    original = copy.deepcopy(history)
    monkeypatch.setattr(one_shot, "get_provider", lambda _: provider)
    result = await one_shot.one_shot_completion(
        history, model="gemini-3.5-flash", provider=provider_name, stream=stream, timeout=5,
    )

    body = endpoint.requests[-1][1]
    assert body["contents"][1] == {"role": "model", "parts": parts}
    assert body["contents"][2] == {
        "role": "user",
        "parts": [
            {"functionResponse": {"name": "lookup", "response": {"output": "1"}}},
            {"functionResponse": {"name": "lookup", "response": {"output": "2"}}},
        ],
    }
    assert body["contents"][3] == {"role": "user", "parts": [{"text": "next"}]}
    assert "tools" not in body
    assert history == original
    assert one_shot.extract_response_text(result) == "done"
    assert decode_replay(result.output[0])["parts"][0]["part"]["thought_signature"] == "ZG9uZQ=="
    assert len(endpoint.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_legacy_tool_history_uses_the_documented_signature_bypass(endpoint, client, stream):
    history = [
        {"role": "user", "content": "start"},
        {"type": "function_call", "call_id": "legacy-call", "name": "lookup", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "legacy-call", "output": "old result"},
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
    assert endpoint.requests[0][1]["contents"] == [
        {"role": "user", "parts": [{"text": "start"}]},
        {"role": "model", "parts": [{
            "functionCall": {"name": "lookup", "args": {}},
            "thoughtSignature": "skip_thought_signature_validator",
        }]},
        {"role": "user", "parts": [{
            "functionResponse": {"name": "lookup", "response": {"output": "old result"}},
        }]},
    ]
    assert history == original


@pytest.mark.asyncio
async def test_streamed_tail_replays_from_disk_in_a_fresh_process(endpoint, client, tmp_path):
    chunks = [
        native_response([{"text": "first", "thoughtSignature": "Zmlyc3Q="}], finish=None),
        native_response([{"text": "second"}]),
        native_response([{"text": "", "thoughtSignature": "dGFpbA=="}], finish=None),
    ]
    endpoint.responses = [(200, sse(*chunks)), (200, native_response([{"text": "next"}]))]
    model = ModelWrapper(GeminiModel("gemini-3.5-flash", client=client))
    events = [event async for event in model.stream_response(**request_args())]
    store = FileSession("process-replay", sessions_dir=tmp_path)
    await store.add_items([
        item.model_dump(mode="json", exclude_unset=True)
        for item in events[-1].response.output
    ])
    await store.migrate_legacy_context(allow_history_only=True)
    script = """
import asyncio
import sys
import httpx
from agents import ModelSettings, ModelTracing
from google import genai
from google.genai import types
from siada.provider.gemini import GeminiModel
from siada.services.file_session import FileSession
from siada.services.model_wrapper import ModelWrapper

async def main():
    history = FileSession("process-replay", sessions_dir=sys.argv[1]).get_context_snapshot_sync()["items"]
    client = genai.Client(vertexai=False, api_key="synthetic-api-key", http_options=types.HttpOptions(
        base_url=sys.argv[2], retry_options=types.HttpRetryOptions(attempts=1),
        httpx_async_client=httpx.AsyncClient(trust_env=False),
    ))
    try:
        await ModelWrapper(GeminiModel("gemini-3.5-flash", client=client)).get_response(
            system_instructions=None, input=[*history, {"role": "user", "content": "next user"}],
            model_settings=ModelSettings(), tools=[], output_schema=None, handoffs=[],
            tracing=ModelTracing.DISABLED, previous_response_id=None, conversation_id=None, prompt=None,
        )
    finally:
        await client.aio.aclose()
        client.close()

asyncio.run(main())
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", script, str(tmp_path), endpoint.url,
        env={
            **os.environ, "SIADA_REMOTE_MODEL_CONFIG": "0", "LITELLM_LOCAL_MODEL_COST_MAP": "True",
            "SIADA_CLI_LOG_DIR": str(tmp_path / "child-logs"),
        },
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert process.returncode == 0, stderr.decode()
    assert len(endpoint.requests) == 2
    assert endpoint.requests[-1][1]["contents"][0] == {
        "role": "model", "parts": [part for chunk in chunks for part in chunk["candidates"][0]["content"]["parts"]],
    }

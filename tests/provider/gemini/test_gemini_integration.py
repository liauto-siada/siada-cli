from __future__ import annotations

import asyncio
import copy
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agents import Agent, AgentOutputSchema, ModelSettings, RunConfig, Runner
from agents.decorators import function_tool
from agents.exceptions import ModelBehaviorError, UserError
from pydantic import BaseModel

from siada.agent_hub.context_filter.header_summary_compaction_strategy import SummarizeWithHeaderCompaction
from siada.agent_hub.context_filter.turn_prune_compaction_strategy import TurnPruneSummaryCompaction
from siada.models.model_run_config import ModelRunConfig
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.provider import one_shot
from siada.provider.default.default_provider import DefaultProvider
from siada.provider.gemini import GeminiModel
from siada.provider.gemini.replay import decode_replay, encode_replay
from siada.provider.token_counting import token_counting_info_from_model
from siada.services.file_session import FileSession
from siada.services.model_wrapper import ModelWrapper
from siada.session.session_manager import RunningSessionManager
from siada.support.provider_metadata import without_provider_metadata

from test_gemini_model import native_response, request_args, sse


@pytest.mark.asyncio
async def test_native_stream_tool_arguments_reach_terminal(endpoint, client, monkeypatch):
    from agents import RawResponsesStreamEvent
    from tests.entrypoint.interaction.test_conversation_turn_native_apply_patch import _FakeResult, _RecordingIO, _turn

    arguments = {"command": "echo 完成"}
    endpoint.responses = [(200, sse(native_response([
        {"functionCall": {"name": "run_cmd", "args": arguments}, "thoughtSignature": "c3ludGhldGlj"},
    ])))]
    model = GeminiModel("gemini-3.5-flash", client=client)
    events = [event async for event in model.stream_response(**request_args())]
    io = _RecordingIO()
    turn = _turn(io)
    monkeypatch.setattr(turn, "_print_context_usage", Mock())

    await turn.output_stream_content(_FakeResult([RawResponsesStreamEvent(data=event) for event in events]))

    assert len(endpoint.requests) == 1
    argument_deltas = [event.delta for event in events if event.type == "response.function_call_arguments.delta"]
    assert len(argument_deltas) == 1
    assert json.loads(argument_deltas[0]) == arguments
    completed = next(event.item for event in events if event.type == "response.output_item.done")
    assert json.loads(completed.arguments) == arguments
    assert turn.tool_calls[completed.call_id]["arguments"] == completed.arguments
    assert len(io.tool_calls) == 1
    assert "echo 完成" in io.tool_calls[0][0]
    assert "failed to parse arguments" not in io.tool_calls[0][0]
    replay = decode_replay(events[-1].response.output[0])
    assert replay["parts"][0]["part"]["thought_signature"] == "c3ludGhldGlj"


@pytest.mark.asyncio
async def test_native_stream_tool_arguments_reach_lark(endpoint, client):
    from agents import RawResponsesStreamEvent
    from siada.im.feishu.stream_consumer import LarkStreamConsumer
    from tests.im.test_stream_consumer import _MockRunResultStreaming, _make_card_sender

    arguments = {"command": "echo 完成", "cwd": "/workspace/completed"}
    endpoint.responses = [(200, sse(native_response([
        {"functionCall": {"name": "run_cmd", "args": arguments}, "thoughtSignature": "c3ludGhldGlj"},
    ])))]
    events = [RawResponsesStreamEvent(data=event) async for event in GeminiModel("gemini-3.5-flash", client=client).stream_response(**request_args())]
    sender = _make_card_sender()

    await LarkStreamConsumer(sender, "direct").consume_stream(
        _MockRunResultStreaming(events), "synthetic-request", "synthetic-chat", "/workspace",
    )

    assert len(endpoint.requests) == 1
    assert sender.send_card_get_id.call_count == 1
    content = sender.send_card_get_id.call_args.args[1]
    assert "echo 完成" in content
    assert "failed to parse arguments" not in content


@pytest.mark.asyncio
async def test_default_provider_scopes_credentials_and_borrows_connections(endpoint, monkeypatch):
    monkeypatch.setenv("GEMINI_BASE_URL", endpoint.url)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-global-key")
    endpoint.responses = [(200, native_response([{"text": "done"}]))] * 3
    provider = DefaultProvider()
    first = provider.get_model("gemini-3.5-flash")
    second = provider.get_model("google/gemini-3.5-flash")
    assert first is not second and first._transport is second._transport
    assert provider.get_token_counting_info("gemini-3.5-flash") == token_counting_info_from_model(first)

    async def call(key):
        with provider.request_scope(base_url=endpoint.url, api_key=key):
            await provider.get_model("gemini-3.5-flash").get_response(**request_args(key))

    try:
        await asyncio.gather(call("synthetic-first-key"), call("synthetic-second-key"))
        await first.close()
        await second.get_response(**request_args("global"))
        requests = {body["contents"][0]["parts"][0]["text"]: headers for _path, body, headers in endpoint.requests}
        assert requests["synthetic-first-key"]["x-goog-api-key"] == "synthetic-first-key"
        assert requests["synthetic-second-key"]["x-goog-api-key"] == "synthetic-second-key"
        assert requests["global"]["x-goog-api-key"] == "synthetic-global-key"
        assert len(first._transport._clients) == 3
        with pytest.raises(RuntimeError, match="event loop"):
            await asyncio.to_thread(lambda: asyncio.run(provider.aclose()))
        assert not first._transport._closed
        assert provider.get_model("gemini-3.5-flash")._transport is first._transport
    finally:
        await provider.aclose()
    assert first._transport._closed
    assert first._transport._clients == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_one_shot_native_gemini_borrows_provider(endpoint, monkeypatch, stream):
    monkeypatch.setenv("GEMINI_BASE_URL", endpoint.url)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    provider = DefaultProvider()
    monkeypatch.setattr(one_shot, "get_provider", lambda _: provider)
    response = native_response([{"text": "done", "thoughtSignature": "c2ln"}])
    endpoint.responses = [(200, sse(response) if stream else response)]
    try:
        result = await one_shot.one_shot_completion("hello", model="gemini-3.5-flash", provider="default", stream=stream, timeout=5)
        assert one_shot.extract_response_text(result) == "done"
        assert decode_replay(result.output[0])["parts"][0]["part"]["thought_signature"] == "c2ln"
        assert not provider._gemini_transport._closed
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_settings_tools_schema_images_and_reasoning_use_native_fields(endpoint, client):
    class Output(BaseModel):
        answer: str

    @function_tool
    def lookup(value: int) -> str:
        return str(value)

    endpoint.responses = [(200, native_response([{"text": '{"answer":"done"}'}]))]
    config = ModelRunConfig("gemini-3.5-flash")
    config.set_reasoning_effort("low")
    settings = ModelSettingsConverter.convert_model_settings(config).resolve({"max_tokens": 40})
    args = request_args([{"role": "user", "content": [{"type": "input_text", "text": "image"}, {"type": "input_image", "image_url": "data:image/jpeg;base64,aW1hZ2U="}]}], settings=settings)
    args.update(tools=[lookup], output_schema=AgentOutputSchema(Output), system_instructions="synthetic system")
    await GeminiModel("gemini-3.5-flash", client=client).get_response(**args)
    body = endpoint.requests[0][1]
    assert body["generationConfig"]["thinkingConfig"] == {"thinking_level": "LOW", "include_thoughts": True}
    assert body["generationConfig"]["maxOutputTokens"] == 40
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["systemInstruction"]["parts"] == [{"text": "synthetic system"}]
    assert body["contents"][0]["parts"][1] == {"inlineData": {"mimeType": "image/jpeg", "data": "aW1hZ2U="}}
    assert body["tools"][0]["functionDeclarations"][0]["name"] == "lookup"
    assert "parameters_json_schema" in body["tools"][0]["functionDeclarations"][0]


@pytest.mark.asyncio
async def test_invalid_settings_and_truncated_tools_do_not_execute(endpoint, client):
    model = GeminiModel("gemini-3.5-flash", client=client)
    with pytest.raises(UserError):
        await model.get_response(**request_args(settings=ModelSettings(extra_args={"thinking_typo": "synthetic"})))
    assert endpoint.requests == []
    endpoint.responses = [(200, native_response([{"functionCall": {"name": "lookup", "args": {}}}], finish="MAX_TOKENS"))]
    executed = Mock()

    @function_tool
    def lookup() -> str:
        executed()
        return "unexpected"

    with pytest.raises(ModelBehaviorError, match="output limit"):
        await Runner.run(Agent(name="synthetic", model=model, tools=[lookup]), "hello", run_config=RunConfig(tracing_disabled=True))
    executed.assert_not_called()


@pytest.mark.asyncio
async def test_tool_native_id_and_reordered_results_survive_checkpoint(endpoint, client, tmp_path):
    parts = [{"text": "before", "thoughtSignature": "dGV4dA=="},
             {"functionCall": {"id": "native-first", "name": "lookup", "args": {"value": 1}}, "thoughtSignature": "Zmlyc3Q="},
             {"functionCall": {"id": "native-second", "name": "lookup", "args": {"value": 2}}, "thoughtSignature": "c2Vjb25k"}]
    endpoint.responses = [(200, native_response(parts)), (200, native_response([{"text": "again"}]))]
    model = GeminiModel("gemini-3.5-flash", client=client)
    response = await model.get_response(**request_args())
    items = response.to_input_items()
    calls = [item for item in items if item["type"] == "function_call"]
    history = [{"role": "user", "content": "start"}, *items,
               *[{"type": "function_call_output", "call_id": call["call_id"], "output": call["name"] + call["arguments"]} for call in reversed(calls)]]
    store = FileSession("synthetic-checkpoint", sessions_dir=tmp_path)
    await store.add_items(history)
    await store.migrate_legacy_context(allow_history_only=True)
    snapshot = store.get_checkpoint_snapshot_sync()
    await store.append_context_items([{"role": "user", "content": "abandoned"}], message_ids=["abandoned"])
    version = store.get_context_snapshot_sync()["context_version"]
    store.restore_checkpoint_sync(snapshot["history_items"], snapshot["context_snapshot"], expected_version=version, before_commit=lambda: None)
    restored = FileSession("synthetic-checkpoint", sessions_dir=tmp_path).get_context_snapshot_sync()["items"]
    assert restored == history
    await model.get_response(**request_args(restored))
    body = endpoint.requests[1][1]
    assert body["contents"][1] == {"role": "model", "parts": parts}
    results = body["contents"][2]["parts"]
    assert [part["functionResponse"]["id"] for part in results] == ["native-first", "native-second"]
    assert "abandoned" not in json.dumps(body)


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy_type", [SummarizeWithHeaderCompaction, TurnPruneSummaryCompaction])
async def test_compaction_matches_standard_items_and_preserves_retained_signatures(endpoint, client, monkeypatch, strategy_type):
    model = GeminiModel("gemini-3.5-flash", client=client)
    endpoint.responses = [(200, native_response([{"text": "old final", "thoughtSignature": "b2xk"}])),
                          (200, native_response([{"functionCall": {"name": "lookup", "args": {"value": 1}}, "thoughtSignature": "Zmlyc3Q="}])),
                          (200, native_response([{"functionCall": {"name": "lookup", "args": {"value": 2}}, "thoughtSignature": "c2Vjb25k"}]))]
    old = await model.get_response(**request_args())
    first = await model.get_response(**request_args())
    second = await model.get_response(**request_args())
    active = [{"role": "user", "content": "active user"}, *first.to_input_items(),
              {"type": "function_call_output", "call_id": first.output[0].call_id, "output": "first result"},
              {"role": "user", "content": "synthetic reminder"}, *second.to_input_items(),
              {"type": "function_call_output", "call_id": second.output[0].call_id, "output": "second result"}]
    history = [{"role": "user", "content": "old user"}, *old.to_input_items()]
    for index in range(8):
        history.extend([
            {"role": "user", "content": f"old task {index}"},
            {"type": "message", "id": f"old-answer-{index}", "role": "assistant", "content": "old answer"},
        ])
    history.extend(active)
    original = copy.deepcopy(history)
    strategy = strategy_type()
    summarize = AsyncMock(return_value="synthetic summary")
    monkeypatch.setattr(strategy, "call_llm_to_compact", summarize)
    monkeypatch.setenv("BASE_URL", endpoint.url)
    config = SimpleNamespace(model_name="gemini-3.5-flash", provider="default", context_window=100_000)
    plain_strategy = strategy_type()
    monkeypatch.setattr(plain_strategy, "call_llm_to_compact", AsyncMock(return_value="synthetic summary"))
    expected = await plain_strategy.compact(config, without_provider_metadata(history))
    result = await strategy.compact(config, history)
    assert result.compacted
    assert without_provider_metadata(result.messages) == expected.messages
    assert history == original
    assert summarize.call_count == 1
    endpoint.responses = [(200, native_response([{"text": "next"}]))]
    await model.get_response(**request_args(result.messages))
    replayed = [part for content in endpoint.requests[-1][1]["contents"] for part in content["parts"]]
    retained_ids = {item.get("id") for item in result.messages}
    expected_signatures = {signature for item_id, signature in (
        (old.output[0].id, "b2xk"), (first.output[0].id, "Zmlyc3Q="), (second.output[0].id, "c2Vjb25k"),
    ) if item_id in retained_ids}
    assert {part["thoughtSignature"] for part in replayed if "thoughtSignature" in part} == expected_signatures


def test_telemetry_excludes_opaque_provider_metadata():
    item = {"type": "function_call", "name": "synthetic", "arguments": "{}", "provider_data": {"gemini": {"contents": [{"parts": [{"thought_signature": "sensitive-carrier"}]}]}, "another": {"model": "keep"}}}
    assert "provider_data" not in without_provider_metadata(item)
    assert item["provider_data"]["gemini"]
    assert "sensitive-carrier" not in json.dumps(RunningSessionManager._format_history_for_telemetry([item]))


@pytest.mark.asyncio
async def test_borrowed_client_is_not_closed_and_closed_providers_cannot_reopen(client):
    model = GeminiModel("gemini-3.5-flash", client=client)
    await model.close()
    assert not client._api_client._async_httpx_client.is_closed
    for provider in (DefaultProvider(),):
        await provider.aclose()
        with pytest.raises(RuntimeError, match="closed"):
            provider.get_model("gemini-3.5-flash")


@pytest.mark.asyncio
async def test_cancellation_closes_only_current_stream_and_allows_reuse():
    from google.genai import types
    from siada.provider.gemini.transport import GeminiTransport

    started = asyncio.Event()
    never_finish = asyncio.Event()
    closed = []

    class Transport(GeminiTransport):
        async def stream(self, model, contents, config):
            text = contents[0].parts[0].text
            try:
                yield types.GenerateContentResponse.model_validate(native_response([{"text": text, "thoughtSignature": "c2ln"}], finish=None))
                if text == "first":
                    started.set()
                    await never_finish.wait()
                yield types.GenerateContentResponse.model_validate(native_response([], finish="STOP"))
            finally:
                closed.append(text)

    model = GeminiModel("gemini-3.5-flash", transport=Transport())

    async def collect(text):
        return [event async for event in model.stream_response(**request_args(text))]

    first = asyncio.create_task(collect("first"))
    await started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = await collect("second")
    assert second[-1].response.output[0].content[0].text == "second"
    assert closed == ["first", "second"]


@pytest.mark.asyncio
async def test_standard_signature_items_can_cross_model_wrappers(endpoint, client):
    endpoint.responses = [(200, native_response([{"text": "done", "thoughtSignature": "c2ln"}]))]
    response = await GeminiModel("gemini-3.5-flash", client=client).get_response(**request_args())
    underlying = SimpleNamespace(model="synthetic-chat", get_response=AsyncMock())
    items = response.to_input_items()
    await ModelWrapper(underlying).get_response(**request_args(items))
    underlying.get_response.assert_called_once()
    assert underlying.get_response.call_args.kwargs["input"] == items


def test_native_budget_fingerprint_changes_with_protocol_and_ignores_signature_size(client):
    from siada.agent_hub.context_filter.request_token_estimator import request_token_signature
    from siada.agent_hub.context_filter.utils import calculate_tokens

    model = GeminiModel("gemini-3.5-flash", client=client)
    agent = Agent(name="synthetic", model=model)
    context = SimpleNamespace(provider="default", model_run_config=SimpleNamespace(model_name=model.model))
    native_signature = request_token_signature(context, agent, "system")
    assert native_signature
    agent.model = SimpleNamespace(model=model.model)
    assert request_token_signature(context, agent, "system") != native_signature
    payload = {"parts": [{"content_index": 0, "part_index": 0, "part": {"text": "answer", "thought_signature": "c2ln"}}]}
    item = {"type": "message", "role": "assistant", "provider_data": {"gemini": encode_replay(payload)}}
    count = calculate_tokens(model.model, [item], counting_info=token_counting_info_from_model(model))
    payload["parts"][0]["part"]["thought_signature"] *= 1000
    item["provider_data"]["gemini"] = encode_replay(payload)
    assert calculate_tokens(model.model, [item], counting_info=token_counting_info_from_model(model)) == count

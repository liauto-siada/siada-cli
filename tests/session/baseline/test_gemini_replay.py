import copy
import json
from unittest.mock import AsyncMock

import pytest
from agents.decorators import function_tool
from google.genai import types

from siada.provider.gemini import GeminiModel
from siada.provider.gemini.transport import GeminiTransport
from siada.provider.gemini.stream_handler import GeminiResponseAssembly
from siada.agent_hub.context_filter.header_summary_compaction_strategy import SummarizeWithHeaderCompaction
from siada.agent_hub.context_filter.turn_prune_compaction_strategy import TurnPruneSummaryCompaction
from siada.support.provider_metadata import without_provider_metadata
from siada.services.effective_context_session import EffectiveContextSession

from test_effective_context_session import run_bridge


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_effective_context_checkpoint_and_new_model_preserve_native_chain(baseline, stream):
    session = baseline.session()
    store = session.openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    raw_steps = [
        [{"text": "step one", "thoughtSignature": "dGV4dA=="}, {"functionCall": {"name": "lookup", "args": {"value": 1}}, "thoughtSignature": "Zmlyc3Q="}],
        [{"functionCall": {"name": "lookup", "args": {"value": 2}}, "thoughtSignature": "c2Vjb25k"}],
        [{"text": "final", "thoughtSignature": "ZmluYWw="}],
    ]

    class Transport(GeminiTransport):
        def __init__(self, steps):
            super().__init__()
            self.steps = list(steps)
            self.requests = []

        async def generate(self, model, contents, config):
            self.requests.append(copy.deepcopy(contents))
            return types.GenerateContentResponse.model_validate({"candidates": [{"content": {"role": "model", "parts": self.steps.pop(0)}, "finishReason": "STOP"}]})

        async def stream(self, model, contents, config):
            yield await self.generate(model, contents, config)

    executed = []

    @function_tool
    def lookup(value: int) -> str:
        executed.append(value)
        return str(value)

    transport = Transport(raw_steps)
    model = GeminiModel("gemini-3.5-flash", transport=transport)
    result = await run_bridge(baseline, session, model, stream=stream, tools=[lookup])
    assert result.final_output == "final"
    assert executed == [1, 2]
    assert transport.requests[2][1].parts[0].thought_signature == b"text"
    assert transport.requests[2][1].parts[1].thought_signature == b"first"
    assert transport.requests[2][3].parts[0].thought_signature == b"second"
    saved = store.get_checkpoint_snapshot_sync()
    await store.append_context_items([{"role": "user", "content": "abandoned"}], message_ids=["later"])
    store.restore_checkpoint_sync(saved["history_items"], saved["context_snapshot"], expected_version=store.get_context_snapshot_sync()["context_version"], before_commit=lambda: None)
    fresh_transport = Transport([[{"text": "next"}]])
    fresh_model = GeminiModel("gemini-3.5-flash", transport=fresh_transport)
    fresh_bridge = EffectiveContextSession(store)
    await run_bridge(baseline, session, fresh_model, stream=stream, input="next user", bridge=fresh_bridge)
    request = fresh_transport.requests[0]
    assert request[1].parts[0].thought_signature == b"text"
    assert request[3].parts[0].thought_signature == b"second"
    assert request[5].parts[0].thought_signature == b"final"
    assert not any(part.text == "abandoned" for content in request for part in content.parts)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("strategy_type", [SummarizeWithHeaderCompaction, TurnPruneSummaryCompaction])
async def test_effective_context_compacts_standard_items_and_replays_retained_signatures(baseline, monkeypatch, stream, strategy_type):
    from siada.agent_hub.context_filter.api_message_transfer_filter import ApiMessageTransferFilter

    session = baseline.session()
    session.siada_config.llm_config.model_name = "gemini-3.5-flash"
    store = session.openai_session
    origin = {"provider": "google", "model": "gemini-3.5-flash", "backend": "gemini_api"}
    history = []
    for turn in range(9):
        assembly = GeminiResponseAssembly(origin)
        assembly.add(types.GenerateContentResponse.model_validate({
            "candidates": [{"content": {"role": "model", "parts": [
                {"text": f"answer {turn}", "thoughtSignature": "dGV4dA=="},
                {"functionCall": {"name": "lookup", "args": {"value": turn}}, "thoughtSignature": "dG9vbA=="},
                {"text": "", "thoughtSignature": "dGFpbA=="},
            ]}, "finishReason": "STOP"}],
        }))
        items = [item.model_dump(mode="json", exclude_unset=True) for item in assembly.finalize()]
        history.extend([
            {"role": "user", "content": f"old task {turn}"}, *items,
            {"type": "function_call_output", "call_id": items[1]["call_id"], "output": f"old result {turn}"},
        ])
    await store.add_items(history)
    await store.migrate_legacy_context(allow_history_only=True)
    strategy = strategy_type()
    monkeypatch.setattr(strategy, "call_llm_to_compact", AsyncMock(return_value="<context>Continue the task.</context>"))
    compactions = []

    async def compact_once(_filter, **kwargs):
        if compactions:
            return kwargs["real_api_messages"]
        result = await strategy.compact(kwargs["model_config"], kwargs["real_api_messages"])
        assert result.compacted
        compactions.append(copy.deepcopy(result.messages))
        return result.messages

    monkeypatch.setattr(ApiMessageTransferFilter, "_try_compact_real_api_messages", compact_once)

    class Transport(GeminiTransport):
        def __init__(self):
            super().__init__()
            self.requests = []

        async def generate(self, model, contents, config):
            self.requests.append(copy.deepcopy(contents))
            return types.GenerateContentResponse.model_validate({
                "candidates": [{"content": {"role": "model", "parts": [
                    {"text": "done", "thoughtSignature": "ZmluYWw="},
                ]}, "finishReason": "STOP"}],
            })

        async def stream(self, model, contents, config):
            yield await self.generate(model, contents, config)

    transport = Transport()
    model = GeminiModel("gemini-3.5-flash", transport=transport)
    result = await run_bridge(baseline, session, model, stream=stream)
    assert result.final_output == "done"
    assert len(compactions) == 1
    assert store.get_context_snapshot_sync()["items"][:-1] == compactions[0]
    assert (await store.get_history_items())[:len(history)] == history
    retained_ids = {item.get("id") for item in compactions[0]}
    retained_calls = [item for item in history if item.get("type") == "function_call" and item["id"] in retained_ids]
    native_calls = [part for content in transport.requests[0] for part in content.parts if part.function_call]
    assert [part.function_call.args for part in native_calls] == [json.loads(item["arguments"]) for item in retained_calls]
    assert all(part.thought_signature == b"tool" for part in native_calls)
    native_text = [part for content in transport.requests[0] for part in content.parts if part.thought_signature and part.function_call is None]
    assert native_text and {part.thought_signature for part in native_text} == {b"text", b"tail"}
    assert len(without_provider_metadata(compactions[0])) < len(history)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_effective_context_model_switch_imports_history_and_preserves_checkpoint(baseline, stream):
    session = baseline.session()
    store = session.openai_session
    await store.migrate_legacy_context(allow_history_only=True)
    executed = []

    @function_tool
    def lookup(value: int) -> str:
        executed.append(value)
        return str(value)

    previous_model = baseline.model(session, [
        [baseline.call("foreign-call", "lookup", {"value": 1})],
        [baseline.text("old final", "foreign-final")],
    ])
    await run_bridge(baseline, session, previous_model, input="old user", stream=stream, tools=[lookup])
    imported = copy.deepcopy(store.get_context_snapshot_sync()["items"])
    assert executed == [1]
    assert all("provider_data" not in item for item in imported)

    class Transport(GeminiTransport):
        def __init__(self, steps):
            super().__init__()
            self.steps = list(steps)
            self.requests = []

        async def generate(self, model, contents, config):
            self.requests.append(copy.deepcopy(contents))
            return types.GenerateContentResponse.model_validate({
                "candidates": [{"content": {"role": "model", "parts": self.steps.pop(0)}, "finishReason": "STOP"}],
            })

        async def stream(self, model, contents, config):
            yield await self.generate(model, contents, config)

    transport = Transport([
        [{"functionCall": {"name": "lookup", "args": {"value": 2}}, "thoughtSignature": "bmV3"}],
        [{"text": "final", "thoughtSignature": "ZmluYWw="}],
    ])
    model = GeminiModel("gemini-3.5-flash", transport=transport)
    result = await run_bridge(baseline, session, model, input="new user", stream=stream, tools=[lookup])
    assert result.final_output == "final"
    assert executed == [1, 2]
    imported_part = transport.requests[0][1].parts[0].model_dump(mode="json", by_alias=True, exclude_none=True)
    assert imported_part == {
        "functionCall": {"name": "lookup", "args": {"value": 1}},
        "thoughtSignature": "skip_thought_signature_validator",
    }
    assert transport.requests[0][2].parts[0].function_response.response == {"output": "1"}
    assert transport.requests[1][5].parts[0].thought_signature == b"new"
    saved = store.get_checkpoint_snapshot_sync()
    assert saved["context_snapshot"]["items"][:len(imported)] == imported
    assert saved["history_items"][:len(imported)] == imported
    await store.append_context_items(
        [{"role": "user", "content": "abandoned"}], message_ids=["abandoned"],
    )
    store.restore_checkpoint_sync(
        saved["history_items"], saved["context_snapshot"],
        expected_version=store.get_context_snapshot_sync()["context_version"], before_commit=lambda: None,
    )
    fresh_transport = Transport([[{"text": "next"}]])
    fresh_model = GeminiModel("gemini-3.5-flash", transport=fresh_transport)
    await run_bridge(
        baseline, session, fresh_model, input="after restore", stream=stream, bridge=EffectiveContextSession(store),
    )
    request = fresh_transport.requests[0]
    assert request[1].parts[0].model_dump(mode="json", by_alias=True, exclude_none=True) == imported_part
    assert request[5].parts[0].thought_signature == b"new"
    assert request[7].parts[0].thought_signature == b"final"
    assert not any(part.text == "abandoned" for content in request for part in content.parts)

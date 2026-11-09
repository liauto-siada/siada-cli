"""Regression coverage for model-scoped tool argument repair."""

import json
from types import SimpleNamespace

import pytest

from siada.agent_hub.context_filter import malformed_tool_call_filter as repair
from siada.services.file_session import FileSession


DEEPSEEK = "baidu-deepseek-v4.1-flash"


def _history(arguments):
    return [
        {
            "type": "function_call",
            "call_id": "synthetic_call",
            "name": "fact_store",
            "arguments": arguments,
        },
        {
            "type": "function_call_output",
            "call_id": "synthetic_call",
            "output": "Invalid JSON input for tool fact_store",
        },
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [DEEPSEEK, DEEPSEEK.upper(), "lpai-glm-5.3"])
async def test_repairs_truncated_history_before_request(model, tmp_path, monkeypatch):
    from agents.models.chatcmpl_converter import Converter

    monkeypatch.setattr(repair, "_resolve_offload_dir", lambda _: tmp_path)
    original = _history('{"threshold": null')
    data = SimpleNamespace(input=original)
    context = SimpleNamespace(model_run_config=SimpleNamespace(model_name=model))

    await repair.MalformedToolCallFilter().filter(data, None, context)

    assert json.loads(data.input[0]["arguments"]) == {"threshold": None}
    assert original[0]["arguments"] == '{"threshold": null'
    assert data.input[1] is original[1]
    assert len(data.input) == 2
    evidence = list(tmp_path.glob("*.txt"))
    assert len(evidence) == 1
    assert evidence[0].read_text().endswith(original[0]["arguments"])
    messages = Converter.items_to_messages(data.input, model=model)
    calls = [call for msg in messages for call in msg.get("tool_calls", [])]
    assert len(calls) == 1
    assert json.loads(calls[0]["function"]["arguments"]) == {"threshold": None}
    assert messages[-1]["tool_call_id"] == "synthetic_call"
    assert messages[-1]["content"] == original[1]["output"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model",
    ["kivy-kimi-k3", "baidu-deepseek-v4.1", DEEPSEEK + "-other", None, ""],
)
async def test_other_models_keep_original_history(model, monkeypatch):
    def unexpected_offload(_):
        pytest.fail("Unselected models must not enter the repair path")

    monkeypatch.setattr(repair, "_resolve_offload_dir", unexpected_offload)
    original = _history('{"threshold": null')
    data = SimpleNamespace(input=original)
    context = SimpleNamespace(model_run_config=SimpleNamespace(model_name=model))

    await repair.MalformedToolCallFilter().filter(data, None, context)

    assert data.input is original
    assert FileSession._filter_invalid_tool_calls(original, model) is original


@pytest.mark.asyncio
async def test_valid_deepseek_arguments_and_results_are_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, "_resolve_offload_dir", lambda _: tmp_path)
    original = _history('{ "threshold": null, "content": "keep formatting" }')
    data = SimpleNamespace(input=original)
    context = SimpleNamespace(model_run_config=SimpleNamespace(model_name=DEEPSEEK))

    await repair.MalformedToolCallFilter().filter(data, None, context)

    assert data.input is original
    persisted = FileSession._filter_invalid_tool_calls(original, DEEPSEEK)
    assert all(left is right for left, right in zip(persisted, original))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("model", [DEEPSEEK, "lpai-glm-5.3"])
@pytest.mark.parametrize(
    ("arguments", "expected"),
    [('{"threshold": null', {"threshold": None}), ("not json {{{", {})],
)
def test_persistence_uses_same_repair_scope(model, arguments, expected):
    original = _history(arguments)

    persisted = FileSession._filter_invalid_tool_calls(original, model)

    assert json.loads(persisted[0]["arguments"]) == expected
    assert original[0]["arguments"] == arguments
    assert persisted[1] is original[1]
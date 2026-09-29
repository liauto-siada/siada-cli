"""``ResponsesModel._build_request_params`` include-assembly tests.

The responses wire asks for ``reasoning.encrypted_content`` on
reasoning-capable families so the opaque encrypted reasoning tokens come back
and can be replayed verbatim on the next turn (see
``sanitize_input_reasoning_items``).  Non-reasoning families must stay
untouched, because reasoning-specific request fields error out there.
"""

from __future__ import annotations

import types

from agents import ModelSettings

import siada.provider.responses.responses_model as responses_model_module
from siada.provider.responses.responses_model import ResponsesModel


class _DummyTransport:
    """Stand-in: ``_build_request_params`` never touches the transport."""


def _build(model: str, *, model_settings: ModelSettings | None = None, tools=None):
    model_object = ResponsesModel(model=model, transport=_DummyTransport())
    return model_object._build_request_params(
        system_instructions=None,
        input=[{"role": "user", "content": "hi"}],
        model_settings=model_settings or ModelSettings(),
        tools=tools or [],
        output_schema=None,
        handoffs=[],
        previous_response_id=None,
        conversation_id=None,
        prompt=None,
    )


def test_include_requests_encrypted_reasoning_for_gpt5():
    params = _build("gpt-5")
    assert params["include"] == ["reasoning.encrypted_content"]


def test_include_requests_encrypted_reasoning_for_o_series():
    params = _build("o3-mini")
    assert params["include"] == ["reasoning.encrypted_content"]


def test_include_omitted_for_non_reasoning_model():
    params = _build("gpt-4o")
    assert "include" not in params


def test_include_added_when_reasoning_is_explicitly_configured():
    params = _build("gpt-4o", model_settings=ModelSettings(reasoning={"effort": "medium"}))
    assert params["include"] == ["reasoning.encrypted_content"]


def test_tool_includes_are_merged_not_overwritten(monkeypatch):
    fake = types.SimpleNamespace(tools=[], includes=["file_search_call.results"])
    monkeypatch.setattr(
        responses_model_module.OpenAIResponsesConverter,
        "convert_tools",
        lambda *a, **k: fake,
    )

    params = _build("gpt-5", tools=[object()])

    assert params["include"] == [
        "file_search_call.results",
        "reasoning.encrypted_content",
    ]

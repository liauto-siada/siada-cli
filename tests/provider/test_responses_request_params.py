"""Responses requests use full-turn reasoning replay without server storage."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from agents import ModelSettings
from agents.models.interface import ModelTracing
from openai import AsyncOpenAI
from openai.types.shared import Reasoning

from siada.provider.default.responses_transport import DefaultResponsesTransport
from siada.provider.responses.responses_model import ResponsesModel


def _build(model: str = "gpt-5.4", *, settings: ModelSettings | None = None) -> dict[str, Any]:
    return ResponsesModel(model=model, transport=MagicMock())._build_request_params(
        system_instructions=None,
        input=[{"role": "user", "content": "synthetic prompt"}],
        model_settings=settings or ModelSettings(),
        tools=[],
        output_schema=None,
        handoffs=[],
        previous_response_id="resp_previous",
        conversation_id=None,
        prompt=None,
    )


@pytest.mark.parametrize("model", ["gpt-5.4", "gpt-6", "o3-mini"])
def test_reasoning_models_default_to_full_turn_stateless_replay(model):
    params = _build(model)

    assert params["reasoning"] == {
        "effort": "low", "summary": "detailed", "context": "all_turns",
    }
    assert params["store"] is False
    assert params["include"] == ["reasoning.encrypted_content"]
    assert "previous_response_id" not in params


@pytest.mark.parametrize("source", ["reasoning", "extra_body", "extra_args"])
def test_full_turn_context_preserves_reasoning_settings_and_caller_state(source):
    reasoning = {"effort": "high", "context": "current_turn", "summary": "auto"}
    if source == "reasoning":
        settings = ModelSettings(reasoning=Reasoning(**reasoning))
    else:
        settings = ModelSettings(**{source: {"reasoning": reasoning, "custom_option": "keep"}})
    before = deepcopy(settings)

    params = _build(settings=settings)

    assert params["reasoning"] == {
        "effort": "high", "summary": "detailed", "context": "all_turns",
    }
    assert settings == before
    if source == "extra_body":
        assert params["extra_body"] == {"custom_option": "keep"}
    elif source == "extra_args":
        assert params["custom_option"] == "keep"


@pytest.mark.parametrize(
    "settings",
    [
        ModelSettings(),
        ModelSettings(store=False),
        ModelSettings(store=True),
        ModelSettings(extra_args={"store": True}),
        ModelSettings(extra_body={"store": True}),
        ModelSettings(extra_body={"store": True, "custom_option": "keep"}),
        ModelSettings(extra_args={"extra_body": {"store": True, "custom_option": "keep"}}),
    ],
)
def test_stateless_storage_cannot_be_overridden_by_model_settings(settings):
    before = deepcopy(settings)

    params = _build(settings=settings)

    assert params["store"] is False
    assert "store" not in params.get("extra_body", {})
    assert settings == before
    if "custom_option" in (settings.extra_body or (settings.extra_args or {}).get("extra_body", {})):
        assert params["extra_body"]["custom_option"] == "keep"


def test_disabling_reasoning_preserves_full_turn_context_without_summary():
    params = _build(settings=ModelSettings(reasoning={"effort": "none", "summary": "auto"}))

    assert params["reasoning"] == {"effort": "none", "context": "all_turns"}
    assert params["store"] is False


def test_empty_reasoning_config_still_requests_full_turn_context():
    params = _build(settings=ModelSettings(reasoning={}))

    assert params["reasoning"] == {"context": "all_turns"}
    assert params["include"] == ["reasoning.encrypted_content"]


def test_nested_extra_args_cannot_override_full_turn_context():
    settings = ModelSettings(extra_args={
        "extra_body": {
            "reasoning": {"effort": "high", "context": "current_turn"},
            "store": True, "custom_option": "keep",
        },
        "include": None,
    })
    before = deepcopy(settings)

    params = _build(settings=settings)

    assert params["reasoning"] == {
        "effort": "high", "summary": "detailed", "context": "all_turns",
    }
    assert params["store"] is False
    assert params["extra_body"] == {"custom_option": "keep"}
    assert params["include"] == ["reasoning.encrypted_content"]
    assert settings == before


def test_non_reasoning_model_does_not_receive_reasoning_fields():
    params = _build("gpt-4o")

    assert "reasoning" not in params
    assert "include" not in params
    assert params["store"] is False


@pytest.mark.parametrize("source", ["extra_body", "extra_args"])
def test_explicit_reasoning_requests_encrypted_content_from_all_sources(source):
    params = _build("gpt-4o", settings=ModelSettings(**{source: {"reasoning": {"effort": "medium"}}}))

    assert params["reasoning"]["context"] == "all_turns"
    assert params["include"] == ["reasoning.encrypted_content"]


def test_caller_include_is_merged_with_encrypted_reasoning():
    params = _build(settings=ModelSettings(extra_args={"include": ["file_search_call.results"]}))

    assert params["include"] == ["file_search_call.results", "reasoning.encrypted_content"]


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_real_sdk_sends_stateless_full_turn_params_and_replays_history(monkeypatch, streaming):
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        turn = len(requests)
        response = {
            "id": f"resp_synthetic_{turn}", "created_at": 1, "object": "response",
            "model": "gpt-5.4", "status": "completed", "parallel_tool_calls": False,
            "tool_choice": "auto", "tools": [],
            "output": [
                {
                    "id": f"rs_synthetic_{turn}", "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "synthetic summary"}],
                    "encrypted_content": f"synthetic_encrypted_{turn}",
                },
                {
                    "id": f"msg_synthetic_{turn}", "type": "message", "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "synthetic reply", "annotations": []}],
                },
            ],
            "usage": {
                "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 3},
            },
        }
        if streaming:
            event = {"type": "response.completed", "sequence_number": 0, "response": response}
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"},
                content=f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n",
            )
        return httpx.Response(200, json=response)

    async with AsyncOpenAI(
        api_key="synthetic-key", base_url="https://responses.example/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    ) as client:
        transport = DefaultResponsesTransport()
        monkeypatch.setattr(transport, "_get_client", lambda: client)
        model = ResponsesModel(model="gpt-5.4", transport=transport)
        history = [{"role": "user", "content": "synthetic first prompt"}]
        for turn in range(3):
            kwargs = {
                "system_instructions": None, "input": history, "model_settings": ModelSettings(),
                "tools": [], "output_schema": None, "handoffs": [],
                "tracing": ModelTracing.DISABLED, "previous_response_id": None,
                "conversation_id": None, "prompt": None,
            }
            if streaming:
                events = [event async for event in model.stream_response(**kwargs)]
                response = events[-1].response
            else:
                response = await model.get_response(**kwargs)
            history.extend(item.model_dump(exclude_none=True) for item in response.output)
            history.append({"role": "user", "content": f"synthetic follow-up {turn}"})

    assert len(requests) == 3
    for turn, body in enumerate(requests):
        assert body["reasoning"] == {
            "effort": "low", "summary": "detailed", "context": "all_turns",
        }
        assert body["store"] is False
        assert body["include"] == ["reasoning.encrypted_content"]
        assert body.get("stream", False) is streaming
        assert "previous_response_id" not in body
        reasoning_items = [item for item in body["input"] if item.get("type") == "reasoning"]
        assert [item["encrypted_content"] for item in reasoning_items] == [
            f"synthetic_encrypted_{index + 1}" for index in range(turn)
        ]

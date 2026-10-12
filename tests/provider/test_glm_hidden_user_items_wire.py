"""Wire-role contract of the hidden runtime items on the chat protocol.

The Git snapshot (U1) is merged into a user's content parts (legacy sessions
may contain a standalone item); the repeated-tool reminder (R1) and the todo
reminder are standalone ``role=user`` items. This checks every layer they pass
through on the public default provider's Chat Completions path: the SDK's
Responses->chat conversion and the actual HTTP request body the official SDK
sends to the configured endpoint. The ``<system-reminder>`` text is an
application-level boundary only: no mid-conversation ``role=system`` may be
produced, and the tool call/result pairing must stay intact.

The request is captured at the transport boundary of the client the provider
builds (``httpx.MockTransport``), so the complete public transport --
``DefaultProvider`` -> ``DefaultOpenAIChatCompletionsModel`` -> official SDK
serialization -> request body -- runs for real, without opening a socket and
without any live endpoint. Only the transport is substituted: the endpoint
name below is synthetic and is never resolved.
"""
import json
from typing import Any

import httpx
import pytest
from agents import ModelSettings
from agents.models.chatcmpl_converter import Converter
from agents.models.interface import ModelTracing

from siada.agent_hub.hooks.processors.repeated_tool_reminder_processor import (
    build_repeated_tool_reminder_text,
)
from siada.agent_hub.hooks.processors.todo_reminder_processor import (
    _build_reminder_text,
)
from siada.services.git_snapshot import (
    GitSnapshot,
    build_git_snapshot_item,
    merge_git_snapshot_into_input,
)

# Synthetic endpoint / credentials for the mocked transport: no real host.
_BASE_URL = "https://synthetic-public-gateway.test/v1"
_API_KEY = "sk-test-public-build-wire"
_WIRE_MODEL = "glm-5.3"


def _hidden_item_input(merged_snapshot=False):
    snapshot = build_git_snapshot_item(GitSnapshot(
        branch="main", head="abc1234", upstream="", ahead=0, behind=0, entries=(),
        total_changes=0, staged=0, unstaged=0, untracked=0, captured_at="2026-01-02T03:04:05Z",
    ))
    items = (
        merge_git_snapshot_into_input("fix the failing test", snapshot)
        if merged_snapshot else [snapshot, {"role": "user", "content": "fix the failing test"}]
    )
    for call_id in ("c1", "c2", "c3"):
        items += [
            {"type": "function_call", "call_id": call_id, "name": "run_cmd",
             "arguments": '{"command": "pytest -q"}'},
            {"type": "function_call_output", "call_id": call_id, "output": "1 failed"},
        ]
    items += [
        {"role": "user", "content": build_repeated_tool_reminder_text("run_cmd")},
        {"role": "user", "content": _build_reminder_text([])},
    ]
    return items


def _assert_chat_contract(messages):
    roles = [message["role"] for message in messages]
    assert "system" not in roles and "developer" not in roles
    assert roles == ["user", "user"] + ["assistant", "tool"] * 3 + ["user", "user"]
    assert messages[0]["content"].startswith("<system-reminder>\n[Siada Git snapshot |")
    assert messages[1]["content"] == "fix the failing test"
    assert messages[-2]["content"].startswith('<system-reminder source="siada.runtime.repeated-tool">')
    assert messages[-1]["content"].startswith("<system-reminder>")
    for assistant, tool in zip(messages[2:8:2], messages[3:8:2]):
        assert assistant["tool_calls"][0]["id"] == tool["tool_call_id"]


def _assert_merged_chat_contract(messages):
    assert [message["role"] for message in messages] == [
        "user", *[role for _ in range(3) for role in ("assistant", "tool")], "user", "user",
    ]
    assert messages[0]["content"][0] == {"type": "text", "text": "fix the failing test"}
    assert messages[0]["content"][1]["text"].startswith(
        "<system-reminder>\n[Siada Git snapshot |"
    )
    for assistant, tool in zip(messages[1:7:2], messages[2:7:2]):
        assert assistant["tool_calls"][0]["id"] == tool["tool_call_id"]


def test_sdk_chat_conversion_keeps_hidden_items_as_user_messages():
    _assert_chat_contract(Converter.items_to_messages(_hidden_item_input()))
    _assert_merged_chat_contract(Converter.items_to_messages(_hidden_item_input(merged_snapshot=True)))


def _completion_body() -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": _WIRE_MODEL,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "ok"},
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


@pytest.fixture
def chat_wire_requests(monkeypatch):
    """Capture the HTTP requests the public provider's SDK client sends.

    ``DefaultProvider.get_model`` builds its Chat Completions client through
    ``DefaultChatClientFactory``; only that client's transport is replaced, so
    the factory's credential lookup, the official SDK's request serialization
    and the response parsing all run for real.
    """
    from siada.provider.default import chat_completions as chat_module

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_completion_body(), request=request)

    real_async_openai = chat_module.AsyncOpenAI

    def create_client(**kwargs: Any) -> Any:
        # An explicit transport short-circuits the network; trust_env=False
        # keeps ambient HTTP(S)_PROXY / CA settings from rerouting the request
        # the test is inspecting.
        return real_async_openai(
            **kwargs,
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler), trust_env=False
            ),
        )

    monkeypatch.setattr(chat_module, "AsyncOpenAI", create_client)
    monkeypatch.setenv("BASE_URL", _BASE_URL)
    monkeypatch.setenv("API_KEY", _API_KEY)
    return requests


@pytest.fixture
def litellm_acompletion_calls(monkeypatch):
    """The retained LiteLLM entry point: this public path must not use it."""
    import litellm

    calls: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        raise AssertionError(
            "the default chat-completions path must not call litellm.acompletion"
        )

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("merged_snapshot", [False, True])
async def test_chat_completions_request_body_carries_hidden_items_as_user(
    chat_wire_requests, litellm_acompletion_calls, merged_snapshot
):
    from siada.provider.default.default_provider import DefaultProvider

    provider = DefaultProvider()
    try:
        model = provider.get_model(_WIRE_MODEL)
        assert model.model == _WIRE_MODEL

        await model.get_response(
            system_instructions="SYSTEM PROMPT",
            input=_hidden_item_input(merged_snapshot=merged_snapshot),
            model_settings=ModelSettings(
                extra_body={"thinking": {"type": "enabled", "clear_thinking": False}}
            ),
            tools=[],
            output_schema=None,
            handoffs=[],
            tracing=ModelTracing.DISABLED,
        )
    finally:
        await provider.aclose()

    assert litellm_acompletion_calls == []

    assert len(chat_wire_requests) == 1
    request = chat_wire_requests[0]
    assert str(request.url) == f"{_BASE_URL}/chat/completions"
    assert request.headers["authorization"] == f"Bearer {_API_KEY}"

    body = json.loads(request.content)
    assert body["model"] == _WIRE_MODEL
    # The per-call settings channel rides the body verbatim.
    assert body["thinking"] == {"type": "enabled", "clear_thinking": False}

    messages = body["messages"]
    # The only system message is the leading system prompt.
    assert messages[0] == {"role": "system", "content": "SYSTEM PROMPT"}
    if merged_snapshot:
        _assert_merged_chat_contract(messages[1:])
    else:
        _assert_chat_contract(messages[1:])

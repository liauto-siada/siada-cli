"""Wire-role contract of the hidden runtime items on the chat protocol.

The Git snapshot (U1) is merged into a user's content parts (legacy sessions
may contain a standalone item); the repeated-tool reminder (R1) and the todo
reminder are standalone ``role=user`` items. This checks every layer they pass
through on the default (LiteLLM, chat completions) path:
the SDK's Responses->chat conversion and the actual HTTP request body a
mock OpenAI-compatible server receives. The ``<system-reminder>`` text is an
application-level boundary only: no mid-conversation ``role=system`` may be
produced, and the tool call/result pairing must stay intact.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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


class _CaptureHandler(BaseHTTPRequestHandler):
    bodies: list = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        _CaptureHandler.bodies.append(json.loads(self.rfile.read(length)))
        body = json.dumps({
            "id": "chatcmpl-test", "object": "chat.completion", "created": 0,
            "model": "glm-5.3",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@pytest.fixture
def capture_server():
    _CaptureHandler.bodies = []
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
@pytest.mark.parametrize("merged_snapshot", [False, True])
async def test_litellm_request_body_carries_hidden_items_as_user(capture_server, monkeypatch, merged_snapshot):
    from siada.provider.default.default_provider import DefaultProvider

    host, port = capture_server.server_address
    monkeypatch.setenv("BASE_URL", f"http://{host}:{port}/v1")
    monkeypatch.setenv("API_KEY", "test-key")

    model = DefaultProvider().get_model("glm-5.3")
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

    assert len(_CaptureHandler.bodies) == 1
    messages = _CaptureHandler.bodies[0]["messages"]
    # The only system message is the leading system prompt.
    assert messages[0] == {"role": "system", "content": "SYSTEM PROMPT"}
    if merged_snapshot:
        _assert_merged_chat_contract(messages[1:])
    else:
        _assert_chat_contract(messages[1:])

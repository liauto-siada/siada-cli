"""History replay keeps internal context and tool previews out of chat text."""

import asyncio
import copy
import socket
from types import SimpleNamespace

import pytest
from acp.agent.connection import AgentSideConnection
from acp.client.connection import ClientSideConnection

from siada.acp_server.acp_agent import SiadaAcpAgent
from siada.acp_server.runtime import AcpRuntimeSession, SiadaTurnRunner
from siada.services.file_session import FileSession
from siada.support.message_classifier import format_native_items_for_display


PAGE = (
    "<browser-context>\nCurrent tab: Example\nURL: https://example.com\n"
    "Page content excerpt:\nHidden page data\n</browser-context>\n\n"
)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("parts", [False, True])
def test_legacy_browser_preamble_is_hidden(newline, wrapped, parts):
    text = PAGE.replace("\n", newline) + "Explain this page."
    if wrapped:
        text = f"<user_input>{text}</user_input>"
    content = [{"type": "input_text", "text": text}] if parts else text
    items = [{"role": "user", "content": content}]
    original = copy.deepcopy(items)
    assert format_native_items_for_display(items) == [
        {"role": "user", "content": "Explain this page."},
    ]
    assert items == original


@pytest.mark.parametrize("heading", [
    "Current tab: Example", "\nSelected text on the page:\nSelection",
    "\nPage content excerpt:\nExcerpt",
])
def test_legacy_browser_preamble_for_each_context_toggle(heading):
    text = f"<browser-context>\n{heading}\n</browser-context>\n\nQuestion"
    assert format_native_items_for_display([{"role": "user", "content": text}]) == [
        {"role": "user", "content": "Question"},
    ]


@pytest.mark.parametrize("text", [
    f"Explain this syntax: {PAGE}Keep the tag.",
    "<browser-context>literal example</browser-context>\n\nKeep the tag.",
    "<browser-context>\nCurrent tab: incomplete example",
])
def test_user_authored_browser_tag_is_preserved(text):
    assert format_native_items_for_display([{
        "role": "user", "content": f"<user_input>{text}</user_input>",
    }]) == [{"role": "user", "content": text}]


def test_load_history_over_real_acp_connection(tmp_path):
    """Exercise restored file history through the SDK wire used by Chrome."""
    session_id = "synthetic-history"
    storage = FileSession(session_id, tmp_path)
    items = [
        {"role": "user", "content": f"<user_input>{PAGE}Explain this page.</user_input>"},
        {"role": "user", "content": "<system-reminder>Hidden reminder</system-reminder>"},
        {"role": "system", "content": "Hidden system prompt"},
        {"role": "developer", "content": "Hidden developer prompt"},
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "I will check."},
        ]},
        {"type": "function_call", "call_id": "synthetic-tool", "name": "run_cmd",
         "arguments": '{"command":"echo synthetic","timeout":20}'},
        {"type": "function_call_output", "call_id": "synthetic-tool", "output": "Hidden raw output"},
        {"type": "apply_patch_call", "id": "synthetic-patch", "operation": {
            "type": "update_file", "path": "example.txt", "diff": "@@\n-old\n+new\n",
        }},
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "Done."},
        ]},
    ]
    asyncio.run(storage.add_items(items))
    runner = SiadaTurnRunner(agent_name="test-agent")
    restored = FileSession(session_id, tmp_path)
    runner._sessions[session_id] = AcpRuntimeSession(
        workspace=str(tmp_path),
        session=SimpleNamespace(openai_session=restored),
    )

    class RecordingClient:
        def __init__(self):
            self.updates = []

        async def session_update(self, session_id, update, **_kwargs):
            self.updates.append((session_id, update))

    recording = RecordingClient()
    agent = SiadaAcpAgent(
        turn_runner=lambda *_args: [],
        session_restorer=lambda *_args: None,
        history_lister=runner.load_history_messages,
    )

    async def load():
        agent_sock, client_sock = socket.socketpair()
        agent_read, agent_write = await asyncio.open_connection(sock=agent_sock)
        client_read, client_write = await asyncio.open_connection(sock=client_sock)
        connection = AgentSideConnection(agent, agent_write, agent_read, listening=False)
        listener = asyncio.create_task(connection.listen())
        client = ClientSideConnection(recording, client_write, client_read)
        try:
            await client.initialize(protocol_version=1)
            await client.load_session(session_id=session_id, cwd=str(tmp_path), mcp_servers=[])
        finally:
            await connection.close()
            client_write.close()
            await asyncio.wait_for(listener, timeout=5)

    asyncio.run(load())
    updates = [update for sid, update in recording.updates if sid == session_id]
    assert [update.session_update for update in updates] == [
        "user_message_chunk", "agent_message_chunk", "tool_call", "tool_call", "agent_message_chunk",
    ]
    assert [update.content.text for update in updates if update.session_update.endswith("message_chunk")] == [
        "Explain this page.", "I will check.", "Done.",
    ]
    tools = [update for update in updates if update.session_update == "tool_call"]
    assert [tool.tool_call_id for tool in tools] == ["synthetic-tool", "synthetic-patch"]
    assert tools[0].title == "run_cmd"
    assert tools[0].raw_input == {"command": "echo synthetic", "timeout": 20}
    assert tools[1].raw_input == items[7]["operation"]
    assert all(tool.content is None and tool.raw_output is None for tool in tools)
    assert restored.get_history_items_sync() == storage.get_history_items_sync()


def test_tool_preview_without_metadata_has_unique_fallback_ids():
    agent = SiadaAcpAgent(
        turn_runner=lambda *_args: [],
        history_lister=lambda _sid: [
            {"role": "assistant", "subtype": "tool_use", "content": "First preview"},
            {"role": "assistant", "subtype": "tool_use", "content": "Second preview"},
        ],
    )

    class RecordingClient:
        def __init__(self):
            self.updates = []

        async def session_update(self, _sid, update):
            self.updates.append(update)

    client = RecordingClient()
    agent.on_connect(client)
    asyncio.run(agent._replay_history("synthetic"))
    assert [update.tool_call_id for update in client.updates] == [
        "history-synthetic-0", "history-synthetic-1",
    ]
    assert [update.raw_input for update in client.updates] == ["First preview", "Second preview"]
import asyncio
import socket

import siada
from acp import RequestError
from acp.agent.connection import AgentSideConnection
from acp.client.connection import ClientSideConnection
from acp.helpers import update_agent_message_text, update_agent_thought_text
from acp.schema import TextContentBlock

from siada.acp_server.acp_agent import SiadaAcpAgent


class RecordingClient:
    def __init__(self):
        self.updates = []

    async def session_update(self, session_id, update):
        self.updates.append((session_id, update))


def _run_prompt_against_real_client(agent, *, request_id=None):
    """Drive ``agent`` through a real SDK client connection over a socketpair.

    Both sides of the ACP connection are the SDK's own, so whatever this
    returns is what a real client (chrome-acp sidepanel, editor plugin, Node
    TUI) observes — including how the SDK re-shapes a failed request.
    """

    class _StubClient:
        async def session_update(self, *_args, **_kwargs):
            pass

    async def run():
        agent_sock, client_sock = socket.socketpair()
        agent_read, agent_write = await asyncio.open_connection(sock=agent_sock)
        client_read, client_write = await asyncio.open_connection(sock=client_sock)
        connection = AgentSideConnection(agent, agent_write, agent_read, listening=False)
        listener = asyncio.create_task(connection.listen())
        client = ClientSideConnection(_StubClient(), client_write, client_read)
        try:
            await client.initialize(protocol_version=1)
            session = await client.new_session(cwd="/tmp", mcp_servers=[])
            return await client.prompt(
                session_id=session.session_id,
                prompt=[TextContentBlock(type="text", text="hi")],
                **({"_meta": {"siadaLog": {"requestId": request_id}}} if request_id else {}),
            )
        finally:
            await connection.close()
            client_write.close()
            await asyncio.wait_for(listener, timeout=5)

    return asyncio.run(run())


def test_acp_agent_emits_sdk_session_update_and_ends_prompt():
    agent = SiadaAcpAgent(turn_runner=lambda _session_id, _text: [update_agent_message_text("hello")])
    client = RecordingClient()
    agent.on_connect(client)

    initialized = asyncio.run(agent.initialize(protocol_version=1))
    session = asyncio.run(agent.new_session(cwd="/tmp"))
    response = asyncio.run(agent.prompt(session.session_id, prompt=[]))

    assert initialized.agent_info.name == "siada"
    assert initialized.agent_info.version == siada.__version__
    assert response.stop_reason == "end_turn"
    assert len(client.updates) == 1


def test_acp_update_carries_request_metadata_without_mutating_original():
    from siada.foundation.log_context import log_fields

    original = update_agent_message_text("synthetic")
    agent = SiadaAcpAgent(turn_runner=lambda _session_id, _text: [original])
    client = RecordingClient()
    agent.on_connect(client)

    async def request():
        session = await agent.new_session(cwd="/tmp")
        await agent.prompt(
            session.session_id, prompt=[],
            _meta={"siadaLog": {"requestId": "synthetic-request"}},
        )
        assert log_fields()["requestId"] == "-"
        return session.session_id

    session_id = asyncio.run(request())
    fields = client.updates[0][1].model_dump(by_alias=True)["_meta"]["siadaLog"]
    assert fields["sessionId"] == session_id
    assert fields["requestId"] == "synthetic-request"
    assert original.field_meta is None


def test_request_metadata_survives_real_sdk_transport():
    from siada.foundation.log_context import log_fields

    fields = []
    def turn_runner(_session_id, _text):
        fields.append(log_fields())
        return [update_agent_message_text("synthetic")]

    response = _run_prompt_against_real_client(
        SiadaAcpAgent(turn_runner=turn_runner),
        request_id="wire-request",
    )
    assert response.stop_reason == "end_turn"
    assert fields[0]["requestId"] == "wire-request"
    assert fields[0]["sessionId"] != "-"


def test_acp_agent_accepts_async_turn_runner():
    async def turn_runner(_session_id, _text):
        return [update_agent_message_text("async hello")]

    agent = SiadaAcpAgent(turn_runner=turn_runner)
    client = RecordingClient()
    agent.on_connect(client)

    async def run_prompt():
        session = await agent.new_session(cwd="/tmp")
        return await agent.prompt(session.session_id, prompt=[])

    response = asyncio.run(run_prompt())

    assert response.stop_reason == "end_turn"
    assert client.updates[0][1].content.text == "async hello"


def test_acp_agent_streams_async_turn_runner_chunks():
    async def turn_runner(_session_id, _text):
        yield update_agent_message_text("first")
        yield update_agent_thought_text("second")

    agent = SiadaAcpAgent(turn_runner=turn_runner)
    client = RecordingClient()
    agent.on_connect(client)

    async def run_prompt():
        session = await agent.new_session(cwd="/tmp")
        return await agent.prompt(session.session_id, prompt=[])

    response = asyncio.run(run_prompt())

    assert response.stop_reason == "end_turn"
    assert [(update.session_update, update.content.text) for _, update in client.updates] == [
        ("agent_message_chunk", "first"),
        ("agent_thought_chunk", "second"),
    ]


def test_initialize_advertises_session_list_capability():
    agent = SiadaAcpAgent(turn_runner=lambda _session_id, _text: [])

    initialized = asyncio.run(agent.initialize(protocol_version=1))

    assert initialized.agent_capabilities.session_capabilities.list is not None


def test_list_sessions_returns_created_sessions_filtered_by_cwd():
    agent = SiadaAcpAgent(turn_runner=lambda _session_id, _text: [])

    session_a = asyncio.run(agent.new_session(cwd="/workspace/a"))
    session_b = asyncio.run(agent.new_session(cwd="/workspace/b"))

    all_sessions = asyncio.run(agent.list_sessions())
    assert {s.session_id for s in all_sessions.sessions} == {session_a.session_id, session_b.session_id}

    filtered = asyncio.run(agent.list_sessions(cwd="/workspace/a"))
    assert [s.session_id for s in filtered.sessions] == [session_a.session_id]


def test_new_session_exposes_model_config_option_when_model_hooks_provided():
    agent = SiadaAcpAgent(
        turn_runner=lambda _session_id, _text: [],
        model_lister=lambda: ["model-a", "model-b"],
        model_getter=lambda _session_id: "model-a",
    )

    session = asyncio.run(agent.new_session(cwd="/tmp"))

    assert len(session.config_options) == 1
    option = session.config_options[0]
    assert option.id == "model"
    assert option.current_value == "model-a"
    assert [o.value for o in option.options] == ["model-a", "model-b"]


def test_new_session_omits_config_options_without_model_hooks():
    agent = SiadaAcpAgent(turn_runner=lambda _session_id, _text: [])

    session = asyncio.run(agent.new_session(cwd="/tmp"))

    assert session.config_options is None


def test_set_config_option_switches_model_and_reports_new_current_value():
    set_calls = []
    agent = SiadaAcpAgent(
        turn_runner=lambda _session_id, _text: [],
        model_lister=lambda: ["model-a", "model-b"],
        model_getter=lambda _session_id: "model-b",
        model_setter=lambda session_id, model: set_calls.append((session_id, model)),
    )
    session = asyncio.run(agent.new_session(cwd="/tmp"))

    response = asyncio.run(agent.set_config_option(config_id="model", session_id=session.session_id, value="model-b"))

    assert set_calls == [(session.session_id, "model-b")]
    assert response.config_options[0].current_value == "model-b"


def test_new_session_delegates_workspace_to_runtime_creator():
    created = []
    agent = SiadaAcpAgent(
        turn_runner=lambda _session_id, _text: (),
        session_creator=lambda session_id, cwd: created.append((session_id, cwd)),
    )

    session = asyncio.run(agent.new_session(cwd="/workspace"))

    assert created == [(session.session_id, "/workspace")]


def test_cancel_closes_active_async_stream():
    closed = False

    async def turn_runner(_session_id, _text):
        nonlocal closed
        try:
            yield update_agent_message_text("first")
            await asyncio.Event().wait()
        finally:
            closed = True

    agent = SiadaAcpAgent(turn_runner=turn_runner)
    client = RecordingClient()
    agent.on_connect(client)

    async def run_prompt():
        session = await agent.new_session(cwd="/tmp")
        task = asyncio.create_task(agent.prompt(session.session_id, prompt=[]))
        while not client.updates:
            await asyncio.sleep(0)
        await agent.cancel(session.session_id)
        return await task

    response = asyncio.run(run_prompt())

    assert response.stop_reason == "cancelled"
    assert closed


def test_prompt_failure_reaches_the_client_with_the_actual_cause():
    def failing_turn_runner(_session_id, _text):
        raise RuntimeError("BadGatewayError: Error code: 502 LiteLLM Retried: 3 times")

    agent = SiadaAcpAgent(turn_runner=failing_turn_runner)

    try:
        _run_prompt_against_real_client(agent)
    except RequestError as error:
        assert error.code == -32603
        assert "BadGatewayError: Error code: 502 LiteLLM Retried: 3 times" in str(error)
    else:
        raise AssertionError("prompt() should have failed")


def test_prompt_failure_without_a_message_reports_the_exception_type():
    class _NoMessageError(Exception):
        pass

    def failing_turn_runner(_session_id, _text):
        raise _NoMessageError

    agent = SiadaAcpAgent(turn_runner=failing_turn_runner)

    try:
        _run_prompt_against_real_client(agent)
    except RequestError as error:
        assert error.code == -32603
        assert str(error) == "_NoMessageError"
    else:
        raise AssertionError("prompt() should have failed")


def test_prompt_preserves_an_existing_request_error():
    def failing_turn_runner(_session_id, _text):
        raise RequestError(-32602, "Invalid model selection")

    agent = SiadaAcpAgent(turn_runner=failing_turn_runner)

    try:
        _run_prompt_against_real_client(agent)
    except RequestError as error:
        assert error.code == -32602
        assert str(error) == "Invalid model selection"
    else:
        raise AssertionError("prompt() should have failed")





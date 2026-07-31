import asyncio

from acp.helpers import update_agent_message_text, update_agent_thought_text

from siada.acp_server.acp_agent import SiadaAcpAgent


class RecordingClient:
    def __init__(self):
        self.updates = []

    async def session_update(self, session_id, update):
        self.updates.append((session_id, update))


def test_acp_agent_emits_sdk_session_update_and_ends_prompt():
    agent = SiadaAcpAgent(turn_runner=lambda _session_id, _text: [update_agent_message_text("hello")])
    client = RecordingClient()
    agent.on_connect(client)

    initialized = asyncio.run(agent.initialize(protocol_version=1))
    session = asyncio.run(agent.new_session(cwd="/tmp"))
    response = asyncio.run(agent.prompt(session.session_id, prompt=[]))

    assert initialized.agent_info.name == "siada"
    assert response.stop_reason == "end_turn"
    assert len(client.updates) == 1


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





import asyncio
import socket
from types import SimpleNamespace

import pytest
from acp import RequestError
from acp.agent.connection import AgentSideConnection
from acp.client.connection import ClientSideConnection
from acp.helpers import update_agent_message_text
from acp.schema import TextContentBlock

from siada.acp_server.acp_agent import SiadaAcpAgent
from siada.acp_server.runtime import SiadaTurnRunner
from siada.agent_hub.context_filter.pending_user_input_filter import PendingUserInputInjector
from siada.services.steering import SteeringQueue, current_steering


@pytest.mark.asyncio
async def test_real_sdk_steering_while_prompt_is_in_flight():
    entered, finish = asyncio.Event(), asyncio.Event()
    received = []

    async def run_turn(session_id, text):
        entered.set()
        await finish.wait()
        yield update_agent_message_text("done")

    def steer(session_id, text):
        received.append((session_id, text))

    class Client:
        async def session_update(self, *args, **kwargs):
            pass

    agent = SiadaAcpAgent(run_turn, steerer=steer)
    a, b = socket.socketpair()
    ar, aw = await asyncio.open_connection(sock=a)
    br, bw = await asyncio.open_connection(sock=b)
    connection = AgentSideConnection(agent, aw, ar, listening=False)
    listener = asyncio.create_task(connection.listen())
    client = ClientSideConnection(Client(), bw, br)
    try:
        initialized = await client.initialize(protocol_version=1)
        assert initialized.agent_capabilities.field_meta["siada"]["steering"] is True
        session = await client.new_session(cwd="/tmp", mcp_servers=[])
        prompt = asyncio.create_task(client.prompt(
            session_id=session.session_id, prompt=[TextContentBlock(type="text", text="start")],
        ))
        await asyncio.wait_for(entered.wait(), 2)
        result = await client.ext_method("session/steer", {
            "sessionId": session.session_id,
            "prompt": [{"type": "text", "text": "change direction"}],
        })
        assert result == {"accepted": True}
        assert received == [(session.session_id, "change direction")]
        assert not prompt.done()
        with pytest.raises(RequestError, match="active prompt"):
            await client.prompt(session_id=session.session_id, prompt=[])
        assert session.session_id in agent._active_prompts
        finish.set()
        assert (await prompt).stop_reason == "end_turn"
        with pytest.raises(RequestError, match="No active prompt"):
            await client.ext_method("session/steer", {
                "sessionId": session.session_id, "prompt": [{"type": "text", "text": "late"}],
            })
    finally:
        finish.set()
        await connection.close()
        bw.close()
        await asyncio.wait_for(listener, 5)


@pytest.mark.asyncio
async def test_injection_is_session_scoped_and_storage_failure_retains_input():
    queue = SteeringQueue("one")
    queue.append("correction")
    token = current_steering.set(queue)
    context = SimpleNamespace(session=SimpleNamespace(session_id="two"))
    data = SimpleNamespace(input=[])
    saved = []

    async def persist(items, identities):
        saved.extend(items)
        assert identities[0].startswith("steer:")

    try:
        await PendingUserInputInjector().filter(data, None, context, persist_items=persist)
        assert data.input == [] and queue.pending
        context.session.session_id = "one"

        async def fail(items, identities):
            raise OSError("synthetic storage failure")

        with pytest.raises(OSError):
            await PendingUserInputInjector().filter(data, None, context, persist_items=fail)
        assert data.input == [] and queue.pending
        await PendingUserInputInjector().filter(data, None, context, persist_items=persist)
        assert data.input == [{"role": "user", "content": "<user_input>correction</user_input>"}]
        assert saved == data.input and not queue.pending
        await PendingUserInputInjector().filter(data, None, context, persist_items=persist)
        assert len(saved) == 1
    finally:
        current_steering.reset(token)


@pytest.mark.asyncio
async def test_runtime_handles_steering_received_during_final_response():
    runner = SiadaTurnRunner()
    entered, finish = asyncio.Event(), asyncio.Event()
    prompts, saved = [], []
    context = SimpleNamespace(session=SimpleNamespace(session_id="test"))

    async def stream(session_id, prompt):
        prompts.append(prompt)
        if prompt:
            entered.set()
            await finish.wait()
        data = SimpleNamespace(input=[])

        async def persist(items, identities):
            saved.extend(items)

        await PendingUserInputInjector().filter(data, None, context, persist_items=persist)
        yield update_agent_message_text("answer")

    # Simulate a final response that already crossed its request boundary.
    async def first_stream(session_id, prompt):
        if prompt:
            prompts.append(prompt)
            entered.set()
            await finish.wait()
            yield update_agent_message_text("first answer")
        else:
            async for update in stream(session_id, prompt):
                yield update

    runner._stream_turn = first_stream

    async def collect():
        return [update async for update in runner("test", "start")]

    task = asyncio.create_task(collect())
    await entered.wait()
    runner.steer("test", "late correction")
    finish.set()
    assert len(await task) == 2
    assert prompts == ["start", ""]
    assert saved == [{"role": "user", "content": "<user_input>late correction</user_input>"}]
    assert current_steering.get() is None
    with pytest.raises(RuntimeError, match="No active"):
        runner.steer("test", "too late")
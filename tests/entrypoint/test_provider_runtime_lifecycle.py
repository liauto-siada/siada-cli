"""Runtime exits drain model users before closing their loop-owned providers."""

import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from siada.provider import provider_factory
from siada.tools.agent.subagent_async import (
    has_pending_background_subtasks,
    register_background_subtask,
)


@pytest.fixture
def lifecycle(monkeypatch):
    events = []
    instances = []

    class Provider:
        def __init__(self):
            self.aclose = AsyncMock(side_effect=self.close)
            self.close_loop = None
            instances.append(self)

        async def close(self):
            self.close_loop = asyncio.get_running_loop()
            events.append("provider closed")

    prototype = Provider()
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {"synthetic": prototype})
    return events, instances


def test_acp_eof_drains_registered_child_before_provider_close(lifecycle, monkeypatch):
    main_module = importlib.import_module("siada.acp_server.main")
    events, instances = lifecycle

    async def eof(*args, **kwargs):
        provider_factory.get_provider("synthetic")
        started = asyncio.Event()

        async def child():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                events.append("child drained")

        register_background_subtask(
            SimpleNamespace(session_id="synthetic-acp-lifecycle", session=None), child
        )
        await started.wait()

    monkeypatch.setattr(main_module, "_configure_file_logging", lambda: None)
    monkeypatch.setattr(main_module, "run_agent", eof)
    main_module.main()
    assert events == ["child drained", "provider closed"]
    assert not has_pending_background_subtasks("synthetic-acp-lifecycle")
    assert instances[1].close_loop.is_closed()
    instances[0].aclose.assert_not_called()


@pytest.mark.parametrize("failure", [False, True])
def test_vision_bridge_sync_releases_its_temporary_provider(lifecycle, monkeypatch, failure):
    from siada.services import vision_bridge

    events, instances = lifecycle

    async def transcribe(*args):
        provider_factory.get_provider("synthetic")
        if failure:
            raise ValueError("synthetic transcription failure")
        return [("synthetic.png", "synthetic evidence")]

    monkeypatch.setattr(vision_bridge, "transcribe_images", transcribe)
    output = vision_bridge.transcribe_images_sync(["synthetic.png"], "synthetic hint")
    assert output == (None if failure else [("synthetic.png", "synthetic evidence")])
    assert events == ["provider closed"]
    assert instances[1].close_loop.is_closed()
    instances[0].aclose.assert_not_called()


@pytest.mark.parametrize("failure", [False, True])
def test_noninteractive_exit_drains_children_before_provider_close(
    lifecycle, monkeypatch, tmp_path, failure
):
    from siada.entrypoint import siadahub
    from siada.entrypoint.interaction.nointeractive_controller import NoInteractiveController
    from siada.services.siada_runner import SiadaRunner

    events, instances = lifecycle
    monkeypatch.setattr(siadahub, "_ensure_litellm_ready", lambda: None)
    monkeypatch.setattr(siadahub, "_ensure_agents_ready", lambda: None)

    async def run_agent(**kwargs):
        provider_factory.get_provider("synthetic")
        started = asyncio.Event()

        async def child():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                events.append("child drained")

        asyncio.create_task(child())
        await started.wait()
        if failure:
            raise ValueError("synthetic CLI failure")
        return "synthetic answer"

    monkeypatch.setattr(SiadaRunner, "run_agent", run_agent)
    config = SimpleNamespace(agent_name="coder", workspace=str(tmp_path), io=MagicMock())
    controller = NoInteractiveController(config, SimpleNamespace())
    assert controller.run("synthetic question") == int(failure)
    assert events == ["child drained", "provider closed"]
    assert instances[1].close_loop.is_closed()
    instances[0].aclose.assert_not_called()


@pytest.mark.asyncio
async def test_im_task_completion_does_not_schedule_work_after_stop():
    from siada.im.feishu.lark_agent_executor import LarkAgentExecutor

    controller = SimpleNamespace(
        _config={}, _active_entries={}, is_running=True,
        _card_sender=SimpleNamespace(send_im=AsyncMock()),
        _drain_pending_ipc_messages=AsyncMock(),
    )
    executor = LarkAgentExecutor(controller)
    executor.run_agent_for_message = AsyncMock(side_effect=lambda *args: None)
    message = SimpleNamespace(chat_id="synthetic-chat", request_id="synthetic-request", chat_type="p2p")
    executor.dispatch_task(message, SimpleNamespace(session_id="synthetic-session"), "synthetic-key")
    task = controller._active_entries["synthetic-key"].task
    controller.is_running = False
    await task
    await asyncio.sleep(0)
    assert not controller._active_entries
    controller._card_sender.send_im.assert_not_called()
    controller._drain_pending_ipc_messages.assert_not_called()


def test_registered_subtask_shutdown_leaves_foreign_loop_tasks_running():
    from siada.tools.agent.subagent_async import shutdown_loop_background_subtasks

    async def start(session_id):
        tasks = []
        started = asyncio.Event()

        async def child():
            tasks.append(asyncio.current_task())
            started.set()
            await asyncio.Event().wait()

        register_background_subtask(SimpleNamespace(session_id=session_id, session=None), child)
        await started.wait()
        return tasks[0]

    with asyncio.Runner() as first, asyncio.Runner() as second:
        own = first.run(start("synthetic-first-loop"))
        foreign = second.run(start("synthetic-second-loop"))
        try:
            first.run(shutdown_loop_background_subtasks())
            assert own.cancelled()
            assert not foreign.done()
        finally:
            second.run(shutdown_loop_background_subtasks())
        assert foreign.cancelled()


def test_daemon_im_loop_drains_tasks_then_closes_only_its_provider(lifecycle):
    from siada.agent_hub.proactive.daemon import SiadaDaemon

    events, instances = lifecycle
    daemon = object.__new__(SiadaDaemon)
    daemon.logger = MagicMock()
    loop = asyncio.new_event_loop()

    async def child():
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            events.append("child drained")

    async def start():
        provider_factory.get_provider("synthetic")
        asyncio.create_task(child())
        loop.call_later(0.01, loop.stop)

    try:
        daemon._run_im_loop(loop, SimpleNamespace(start=start))
        assert events == ["child drained", "provider closed"]
        assert loop.is_closed()
        assert instances[1].close_loop is loop
        instances[0].aclose.assert_not_called()
        daemon.logger.exception.assert_not_called()
    finally:
        asyncio.set_event_loop(None)
        if not loop.is_closed():
            loop.close()


@pytest.mark.asyncio
async def test_lark_stop_drains_active_stream_and_background_child_before_disconnect():
    from siada.entrypoint.interaction.lark_controller import LarkController
    from siada.im.feishu.lark_agent_executor import ActiveTaskEntry

    events = []
    controller = object.__new__(LarkController)
    controller._running = True
    controller._task = asyncio.create_task(asyncio.Event().wait())

    async def child(label):
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            events.append(label)

    parent = asyncio.create_task(child("active drained"))
    register_background_subtask(
        SimpleNamespace(session_id="synthetic-im-lifecycle", session=None),
        lambda: child("background drained"),
    )
    result = MagicMock()
    result.cancel.side_effect = lambda: events.append("stream cancelled")
    controller._active_entries = {"synthetic-chat": ActiveTaskEntry(task=parent, result=result)}
    controller._transport = SimpleNamespace(
        disconnect=AsyncMock(side_effect=lambda: events.append("disconnected"))
    )
    await asyncio.sleep(0)
    await controller.stop()
    assert events == ["stream cancelled", "active drained", "background drained", "disconnected"]
    assert parent.cancelled()
    assert not controller._active_entries
    assert not has_pending_background_subtasks("synthetic-im-lifecycle")
    assert not controller.is_running


def test_legacy_tui_loop_finalizer_drains_children_and_closes_provider(lifecycle):
    from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn

    class IsolatedTurn(ConversationTurn):
        _dedicated_loop = None
        _dedicated_thread = None

    events, instances = lifecycle
    IsolatedTurn._ensure_dedicated_loop()
    loop = IsolatedTurn._dedicated_loop

    async def start():
        provider_factory.get_provider("synthetic")
        started = asyncio.Event()

        async def child():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                events.append("child drained")

        asyncio.create_task(child())
        await started.wait()

    try:
        asyncio.run_coroutine_threadsafe(start(), loop).result(timeout=3)
    finally:
        IsolatedTurn._cleanup_dedicated_loop()
    assert events == ["child drained", "provider closed"]
    assert loop.is_closed()
    assert not IsolatedTurn._dedicated_thread.is_alive()
    assert instances[1].close_loop is loop
    instances[0].aclose.assert_not_called()


@pytest.mark.parametrize("failure", [False, True])
def test_legacy_btw_releases_temporary_loop_provider(lifecycle, monkeypatch, tmp_path, failure):
    from siada.services import side_question

    events, instances = lifecycle
    session = SimpleNamespace(
        siada_config=SimpleNamespace(llm_config=object(), workspace=str(tmp_path), agent_name="coder"),
        openai_session=None,
        task_message_state=SimpleNamespace(get_real_messages=lambda: [], get_messages=lambda: []),
    )
    monkeypatch.setattr(
        side_question, "_BtwReadonlySession",
        lambda session: SimpleNamespace(session_id="synthetic-btw-lifecycle"),
    )

    async def run(*args):
        provider_factory.get_provider("synthetic")
        if failure:
            raise ValueError("synthetic side question failure")
        return "synthetic answer"

    monkeypatch.setattr(side_question, "_run_async", run)
    if failure:
        with pytest.raises(ValueError, match="synthetic side question failure"):
            side_question.run_side_question(session, "synthetic question")
    else:
        assert side_question.run_side_question(session, "synthetic question") == "synthetic answer"
    assert events == ["provider closed"]
    assert instances[1].close_loop.is_closed()
    instances[0].aclose.assert_not_called()

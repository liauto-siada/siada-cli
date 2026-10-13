"""Real SDK Runner behavior against the current main-agent FileSession."""

import asyncio

import pytest
from agents import function_tool

from siada.agent_hub.hooks.siada_run_hooks import SiadaRunHooks
from siada.services.session_management import SessionManager
from siada.support.resume_service import ResumeService


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True], ids=["run", "streamed"])
@pytest.mark.parametrize("auto_compact", [False, True], ids=["raw", "snapshot"])
async def test_two_turns_persist_input_and_reply_once(baseline, stream, auto_compact):
    session = baseline.session()
    session.siada_config.auto_compact = auto_compact
    model = baseline.model(session, [[baseline.text("first reply")], [baseline.text("second reply")]])
    result, context, events = await baseline.run(session, model, stream=stream, input="first request")
    first_history = await session.openai_session.get_items()
    assert first_history == result.to_input_list()
    assert model.requests[0]["input"] == [{"role": "user", "content": "first request"}]
    assert model.requests[0]["history"] == model.requests[0]["input"]
    assert result.final_output == "first reply"
    if stream:
        assert any(getattr(event, "data", None) is not None for event in events)

    result, _, _ = await baseline.run(
        session, model, stream=stream, input="second request", context=context,
    )
    history = await session.openai_session.get_items()
    assert len(history) == 4
    assert history == result.to_input_list()
    assert model.requests[1]["input"] == first_history + [{"role": "user", "content": "second request"}]
    assert await session.openai_session.get_effective_messages() == history
    assert session.openai_session.native_item_count == len(history)
    if auto_compact:
        snapshot, index = await session.openai_session.get_api_messages()
        assert snapshot == model.requests[1]["input"]
        assert index == 2
        assert snapshot != history  # The legacy snapshot is written before the reply.
    else:
        assert await session.openai_session.get_api_messages() == (None, -1)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_tool_calls_outputs_and_usage_are_persisted_once(baseline, stream):
    session = baseline.session()
    calls = []

    @function_tool
    def record(note: str) -> str:
        """Record a synthetic tool invocation."""
        calls.append(note)
        return f"result:{note}"

    usages = [baseline.usage(100, 20), baseline.usage(200, 40)]
    model = baseline.model(session, [
        [baseline.call("call-1", "record", {"note": "one"})],
        [baseline.text("done")],
    ], usages)
    result, _, _ = await baseline.run(session, model, stream=stream, tools=[record])
    history = await session.openai_session.get_items()
    assert calls == ["one"]
    assert [item.get("type", item.get("role")) for item in history] == [
        "user", "function_call", "function_call_output", "message",
    ]
    assert history[1]["call_id"] == history[2]["call_id"] == "call-1"
    assert history[2]["output"] == "result:one"
    assert model.requests[1]["input"] == history[:-1]
    assert result.final_output == "done"
    assert result.context_wrapper.usage.requests == 2
    assert result.context_wrapper.usage.total_tokens == 360
    assert session.state.usage.requests == 1
    assert session.state.usage.total_tokens == 240  # Latest response, not cumulative usage.
    assert await session.openai_session.get_effective_messages() == history


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_mid_tool_loop_compaction_keeps_full_ui_history(baseline, stream):
    session = baseline.session()
    baseline.compact_at = 5

    @function_tool
    def echo(value: str) -> str:
        """Return a deterministic tool result."""
        return value

    model = baseline.model(session, [
        [baseline.call("call-1", "echo", {"value": "one"})],
        [baseline.call("call-2", "echo", {"value": "two"})],
        [baseline.text("compacted final")],
        [baseline.text("continued final")],
    ])
    result, context, _ = await baseline.run(session, model, stream=stream, tools=[echo])
    summary = [{"role": "user", "content": "[baseline compaction summary]"}]
    history = await session.openai_session.get_all_items()
    assert [len(request["input"]) for request in model.requests] == [1, 3, 1]
    assert model.requests[2]["input"] == summary
    assert len(baseline.compactions) == 1
    assert len(history) == 6
    assert history[0]["content"] == "start"
    assert not any(item.get("content") == summary[0]["content"] for item in history)
    assert await session.openai_session.get_effective_messages() == summary + history[-1:]
    assert result.final_output == "compacted final"

    await baseline.run(session, model, stream=stream, input="continue", context=context)
    assert model.requests[3]["input"] == summary + history[-1:] + [{"role": "user", "content": "continue"}]
    assert len(await session.openai_session.get_all_items()) == 8


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_resume_uses_compacted_snapshot_and_unsent_tail(baseline, stream):
    original = baseline.session("original")
    first_model = baseline.model(original, [[baseline.text("previous reply")]])
    await baseline.run(original, first_model, input="previous request")
    history = await original.openai_session.get_items()
    summary = [{"role": "user", "content": "[saved summary]"}, history[0]]
    SessionManager.sync_api_messages(
        original.openai_session.session_folder, original.session_id, summary,
        tokens_count=70, last_index=0,
        last_signature=original.task_message_state.get_real_message_last_signature(),
    )
    fresh = baseline.session("fresh")
    resume = ResumeService(original.siada_config.workspace)
    data = resume.session_manager.load_session(original.session_id)
    resume.restore_to_running_session(data, fresh)
    model = baseline.model(fresh, [[baseline.text("resumed reply")]])
    await baseline.run(fresh, model, stream=stream, input="next request")
    assert fresh.session_id == original.session_id
    assert model.requests[0]["input"] == summary + history[-1:] + [{"role": "user", "content": "next request"}]
    restored_history = await fresh.openai_session.get_all_items()
    assert restored_history[:2] == history
    assert len(restored_history) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("failure", ["error", "cancel"])
async def test_failed_request_keeps_input_and_can_continue_without_duplicate(baseline, stream, failure):
    session = baseline.session()
    error = RuntimeError("synthetic model failure") if failure == "error" else asyncio.CancelledError()
    model = baseline.model(session, [error, [baseline.text("recovered")]])
    if failure == "cancel" and stream:
        # The SDK treats model-side stream cancellation as a completed empty run.
        result, _, _ = await baseline.run(session, model, stream=True, input="original input")
        assert result.final_output is None and result.is_complete
    else:
        with pytest.raises(type(error)):
            await baseline.run(session, model, stream=stream, input="original input")
    assert await session.openai_session.get_items() == [{"role": "user", "content": "original input"}]
    assert session.state.usage is None
    # An empty delta resumes the saved input rather than submitting it twice.
    await baseline.run(session, model, stream=stream, input=[])
    history = await session.openai_session.get_items()
    assert len(history) == 2
    assert model.requests[1]["input"] == [{"role": "user", "content": "original input"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_caller_cancellation_cleans_up_model_and_preserves_input(baseline, monkeypatch, stream):
    session = baseline.session()
    model = baseline.model(session, [])
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def wait_for_cancel(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(model, "_next", wait_for_cancel)
    task = asyncio.create_task(baseline.run(session, model, stream=stream, input="saved input"))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(stopped.wait(), timeout=2)
        assert await session.openai_session.get_items() == [{"role": "user", "content": "saved input"}]
        assert session.state.usage is None
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_todo_reminder_is_durable_without_duplication(baseline, stream):
    from siada.agent_hub.hooks.processors.todo_reminder_processor import (
        TURNS_BETWEEN_REMINDERS_THRESHOLD,
        TURNS_SINCE_WRITE_THRESHOLD,
        TodoReminderProcessor,
    )
    from siada.tools.todo.models import TodoItem
    from siada.tools.todo.todo_write_tool import todo_write

    session = baseline.session()
    history = [{"role": "user", "content": "original task"}]
    for index in range(TURNS_SINCE_WRITE_THRESHOLD):
        history.extend([
            baseline.text(f"progress {index}", f"progress-{index}").model_dump(exclude_none=True),
            {"role": "user", "content": f"continue {index}"},
        ])
    session.openai_session.add_items_sync(history)
    context = baseline.context(session)
    context.todos = [TodoItem(content="Add tests", active_form="Adding tests", status="in_progress")]
    context.todo_turns_since_reminder = TURNS_BETWEEN_REMINDERS_THRESHOLD
    model = baseline.model(session, [[baseline.text("first")], [baseline.text("second")]])
    hooks = SiadaRunHooks(processors=[TodoReminderProcessor()])
    await baseline.run(session, model, stream=stream, context=context, hooks=hooks, tools=[todo_write])
    sent_reminders = [item for item in model.requests[0]["input"] if "<system-reminder>" in str(item)]
    assert len(sent_reminders) == 1
    assert (await session.openai_session.get_items()).count(sent_reminders[0]) == 1
    assert context.pending_reminder_items == []
    await baseline.run(session, model, stream=stream, context=context, hooks=hooks, tools=[todo_write], input="next")
    assert (await session.openai_session.get_items()).count(sent_reminders[0]) == 1
    assert model.requests[1]["input"].count(sent_reminders[0]) == 1


@pytest.mark.asyncio
async def test_pre_filter_pending_input_is_consumed_and_saved_once(baseline, monkeypatch):
    from siada.io import stdin_interrupt_monitor

    session = baseline.session()
    pending = [("queued-1", "additional input", None)]

    def drain():
        items = list(pending)
        pending.clear()
        return items

    monkeypatch.setattr(stdin_interrupt_monitor, "drain_pending_injections", drain)
    notifications = []
    monkeypatch.setattr(stdin_interrupt_monitor, "_send_queue_notification", lambda *a, **k: notifications.append((a, k)))
    model = baseline.model(session, [[baseline.text("first")], [baseline.text("second")]])
    _, context, _ = await baseline.run(session, model)
    await baseline.run(session, model, input="next", context=context)
    history = await session.openai_session.get_all_items()
    queued = [item for item in history if "additional input" in str(item.get("content"))]
    assert len(queued) == 1
    assert queued[0] in model.requests[0]["input"]
    assert len(notifications) == 1


@pytest.mark.asyncio
async def test_post_filter_notification_is_sent_once_but_not_saved(baseline):
    session = baseline.session()
    context = baseline.context(session)
    context.hook_pending_contexts = ["[background task completed]"]
    model = baseline.model(session, [[baseline.text("first")], [baseline.text("second")]])
    hooks = SiadaRunHooks(processors=[])
    await baseline.run(session, model, hooks=hooks, context=context)
    await baseline.run(session, model, hooks=hooks, context=context, input="next")
    notice = {"role": "system", "content": "[background task completed]"}
    assert model.requests[0]["input"].count(notice) == 1
    assert notice not in model.requests[1]["input"]
    assert notice not in await session.openai_session.get_all_items()
    assert context.hook_pending_contexts == []


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="G01: post-filter additionalContext is cleared before success and not durable")
async def test_failed_request_retains_pending_notification_for_retry(baseline):
    session = baseline.session()
    context = baseline.context(session)
    context.hook_pending_contexts = ["[must survive failure]"]
    model = baseline.model(session, [RuntimeError("synthetic failure"), [baseline.text("retried")]])
    hooks = SiadaRunHooks(processors=[])
    with pytest.raises(RuntimeError):
        await baseline.run(session, model, hooks=hooks, context=context)
    await baseline.run(session, model, hooks=hooks, context=context, input=[])
    assert model.requests[1]["input"].count({"role": "system", "content": "[must survive failure]"}) == 1


@pytest.mark.asyncio
async def test_noop_native_filter_does_not_drop_existing_history(baseline):
    session = baseline.session()
    await session.openai_session.add_items([{"role": "user", "content": "saved input"}])

    async def noop(data):
        return data.model_data

    model = baseline.model(session, [[baseline.text("answer")]])
    await baseline.run(session, model, input="new input", input_filter=noop)
    assert [item["content"] for item in model.requests[0]["input"]] == ["saved input", "new input"]
    assert len(await session.openai_session.get_items()) == 3


@pytest.mark.asyncio
async def test_snapshot_write_failure_keeps_successful_history(baseline, monkeypatch):
    from siada.agent_hub.context_filter.api_message_transfer_filter import ApiMessageTransferFilter

    session = baseline.session()

    def fail(*args, **kwargs):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(ApiMessageTransferFilter, "_sync_api_message_to_file", fail)
    model = baseline.model(session, [[baseline.text("answer")]])
    result, _, _ = await baseline.run(session, model)
    assert result.final_output == "answer"
    assert len(await session.openai_session.get_items()) == 2
    assert await session.openai_session.get_api_messages() == (None, -1)
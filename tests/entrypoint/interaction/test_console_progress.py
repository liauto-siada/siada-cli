"""Progress delivery is run-local and terminal I/O belongs to presentation."""

import asyncio
import contextvars
import threading

import pytest

from siada.entrypoint.interaction.console_progress import ConsoleProgressPresenter
from siada.foundation.execution_progress import execution_progress_scope, publish_execution_progress


def test_unowned_messages_do_not_print(capsys):
    publish_execution_progress("unowned")
    assert capsys.readouterr().out == ""


def test_presenter_preserves_message_bytes_and_flushes():
    messages = []
    with ConsoleProgressPresenter(messages.append) as presenter:
        with execution_progress_scope(presenter.channel):
            publish_execution_progress("\n\033[94mMODEL CALL\033[0m")
            publish_execution_progress("line one\nline two")
            presenter.flush()
            assert messages == ["\n\033[94mMODEL CALL\033[0m", "line one\nline two"]
    assert not presenter._thread.is_alive()


def test_progress_is_visible_before_execution_finishes():
    visible = threading.Event()
    with ConsoleProgressPresenter(lambda message: visible.set()) as presenter:
        with execution_progress_scope(presenter.channel):
            publish_execution_progress("model started")
            assert visible.wait(timeout=2), "Progress was buffered until run completion"


def test_default_console_writer_flushes_redirected_output(monkeypatch):
    from unittest.mock import Mock

    writer = Mock()
    monkeypatch.setattr("builtins.print", writer)
    with ConsoleProgressPresenter() as presenter:
        with execution_progress_scope(presenter.channel):
            publish_execution_progress("goal started")
            presenter.flush()

    writer.assert_called_once_with("goal started", flush=True)


@pytest.mark.asyncio
async def test_concurrent_and_nested_tasks_keep_their_own_presenters():
    first = []
    second = []
    with ConsoleProgressPresenter(first.append) as first_presenter, ConsoleProgressPresenter(second.append) as second_presenter:
        async def run(presenter, prefix):
            with execution_progress_scope(presenter.channel):
                publish_execution_progress(prefix + " start")
                async def nested():
                    await asyncio.sleep(0)
                    publish_execution_progress(prefix + " nested")
                await asyncio.create_task(nested())
                publish_execution_progress(prefix + " end")
        await asyncio.gather(run(first_presenter, "first"), run(second_presenter, "second"))
    assert first == ["first start", "first nested", "first end"]
    assert second == ["second start", "second nested", "second end"]


def test_scope_restores_outer_owner_and_closed_channels_reject_late_messages():
    outer = []
    inner = []
    with ConsoleProgressPresenter(outer.append) as outer_presenter:
        with execution_progress_scope(outer_presenter.channel):
            with ConsoleProgressPresenter(inner.append) as inner_presenter:
                with execution_progress_scope(inner_presenter.channel):
                    inherited = contextvars.copy_context()
                    publish_execution_progress("inner")
            inherited.run(publish_execution_progress, "late inner")
            publish_execution_progress("outer")
    assert outer == ["outer"]
    assert inner == ["inner"]
    assert inner_presenter.channel._messages.empty()


@pytest.mark.parametrize("error", [RuntimeError("failed"), KeyboardInterrupt(), asyncio.CancelledError()])
def test_failure_and_cancellation_close_and_flush(error):
    messages = []
    with pytest.raises(type(error)):
        with ConsoleProgressPresenter(messages.append) as presenter:
            with execution_progress_scope(presenter.channel):
                publish_execution_progress("before failure")
                raise error
    assert messages == ["before failure"]
    assert not presenter._thread.is_alive()


def test_writer_failure_does_not_deadlock_flush(monkeypatch):
    from siada.entrypoint.interaction import console_progress

    warnings = []
    monkeypatch.setattr(console_progress.logger, "warning", lambda *args, **kwargs: warnings.append(args[0]))
    def broken_writer(message):
        raise BrokenPipeError("synthetic pipe failure")
    with ConsoleProgressPresenter(broken_writer) as presenter:
        with execution_progress_scope(presenter.channel):
            publish_execution_progress("message")
            presenter.flush()
    assert warnings == ["Failed to write execution progress"]
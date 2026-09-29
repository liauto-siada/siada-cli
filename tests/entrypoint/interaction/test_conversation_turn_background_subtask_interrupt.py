"""
Regression test for: Ctrl+C interrupting the parent turn did not stop a
still-running run_subtask(async=True) background sub-agent.

Root cause: register_background_subtask() schedules the sub-agent via
asyncio.create_task() on ConversationTurn's dedicated background-loop
thread, as a SIBLING of the parent turn's own coroutine -- not a
descendant of it. keyboard_interrupt()'s existing cancellation
(cancel_current_command() + self.current_result.cancel() + future.cancel())
only reaches the parent turn's coroutine tree, so it never touched these
sibling tasks; they kept running (and kept streaming tool-call UI updates)
after the user interrupted.

This test reproduces the actual threading topology: it starts
ConversationTurn's real dedicated loop (the same one production code uses),
registers a background sub-agent task on it exactly like
run_subtask(async=True) would, then calls
cancel_session_background_subtasks() from THIS thread (standing in for the
main thread's keyboard_interrupt() handler) and verifies the task actually
gets cancelled on its own (different) thread/loop.
"""
import asyncio
import time
import unittest

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.tools.agent.subagent_async import (
    cancel_session_background_subtasks,
    has_pending_background_subtasks,
    register_background_subtask,
)


class _FakeAgentContext:
    """Minimal stand-in exposing only what register_background_subtask touches."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.hook_pending_contexts: list = []


class TestConversationTurnBackgroundSubtaskInterrupt(unittest.TestCase):
    def tearDown(self):
        # Leave no dedicated loop/thread running across test files.
        ConversationTurn._cleanup_dedicated_loop()
        ConversationTurn._dedicated_loop = None
        ConversationTurn._dedicated_thread = None

    def test_ctrl_c_style_cancel_stops_background_subagent_on_dedicated_loop(self):
        session_id = "interrupt-test-session"
        ctx = _FakeAgentContext(session_id)

        started = asyncio.Event()
        cancelled_seen = {"value": False}

        async def _fake_subagent_run():
            started.set()
            try:
                # Stands in for a real sub-agent LLM/tool loop that would run
                # far longer than the test should ever wait.
                await asyncio.sleep(60)
                return "should never complete"
            except asyncio.CancelledError:
                cancelled_seen["value"] = True
                raise

        # This is exactly what ConversationTurn.execute() does before
        # dispatching the parent turn's own work onto the dedicated loop.
        ConversationTurn._ensure_dedicated_loop()
        dedicated_loop = ConversationTurn._dedicated_loop
        self.assertIsNotNone(dedicated_loop)

        # Schedule the "sub-agent" task onto the dedicated loop, from THIS
        # (main test) thread -- mirroring run_subtask(async=True) being
        # invoked as a tool call during the parent turn's run on that loop.
        register_future = asyncio.run_coroutine_threadsafe(
            _wrap_register(ctx, _fake_subagent_run), dedicated_loop
        )
        register_future.result(timeout=5.0)

        # Wait for the fake sub-agent to actually start running.
        started_future = asyncio.run_coroutine_threadsafe(
            _wait_for_event(started), dedicated_loop
        )
        started_future.result(timeout=5.0)

        self.assertTrue(has_pending_background_subtasks(session_id))

        # This is the fix under test: simulate keyboard_interrupt() running
        # on the MAIN thread (this test method's thread), which is NOT the
        # dedicated loop's own thread.
        requested = cancel_session_background_subtasks(session_id)
        self.assertEqual(requested, 1)

        # Poll (from the main thread) until the task is gone from the
        # registry -- proving the cancellation actually reached and stopped
        # the task running on the other thread's loop.
        deadline = time.monotonic() + 5.0
        while has_pending_background_subtasks(session_id) and time.monotonic() < deadline:
            time.sleep(0.05)

        self.assertFalse(
            has_pending_background_subtasks(session_id),
            "background sub-agent task should be gone from the registry after cancellation",
        )
        self.assertTrue(
            cancelled_seen["value"],
            "the sub-agent coroutine itself should have observed CancelledError",
        )
        # Cancelled tasks must not produce a spurious completion notification.
        self.assertEqual(len(ctx.hook_pending_contexts), 0)


async def _wrap_register(ctx, coro_factory):
    # register_background_subtask is sync but calls asyncio.create_task(),
    # which requires a running loop -- must itself run ON the dedicated loop.
    return register_background_subtask(ctx, coro_factory)


async def _wait_for_event(event: asyncio.Event):
    await event.wait()


if __name__ == "__main__":
    unittest.main(verbosity=2)

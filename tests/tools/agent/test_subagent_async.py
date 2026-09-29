"""
Unit tests for the background sub-agent task registry (subagent_async.py).
"""
import asyncio
import time
import unittest

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.agent.subagent_async import (
    cancel_session_background_subtasks,
    has_pending_background_subtasks,
    register_background_subtask,
    shutdown_session_background_subtasks,
    wait_for_session_background_subtasks,
)


class TestSubagentAsyncRegistry(unittest.IsolatedAsyncioTestCase):
    async def test_completed_task_appends_notification_to_hook_pending_contexts(self):
        ctx = CodeAgentContext(root_dir="/tmp")
        ctx.session = None  # session_id resolves to None -> "unknown-session" bucket

        async def _fake_run():
            return "the sub-agent did X"

        task_id = register_background_subtask(ctx, _fake_run)
        self.assertTrue(has_pending_background_subtasks("unknown-session"))

        # Let the background task run to completion.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        self.assertEqual(len(ctx.hook_pending_contexts), 1)
        note = ctx.hook_pending_contexts[0]
        self.assertIn(task_id, note)
        self.assertIn("the sub-agent did X", note)

        # Registry entry must be cleaned up after completion (done-callback).
        self.assertFalse(has_pending_background_subtasks("unknown-session"))

    async def test_failed_task_appends_failure_notification(self):
        ctx = CodeAgentContext(root_dir="/tmp")
        ctx.session = None

        async def _fake_run():
            raise RuntimeError("boom")

        register_background_subtask(ctx, _fake_run)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        self.assertEqual(len(ctx.hook_pending_contexts), 1)
        self.assertIn("failed", ctx.hook_pending_contexts[0])
        self.assertIn("boom", ctx.hook_pending_contexts[0])

    async def test_shutdown_awaits_pending_tasks(self):
        ctx = CodeAgentContext(root_dir="/tmp")
        ctx.session = None

        started = asyncio.Event()

        async def _fake_run():
            started.set()
            await asyncio.sleep(0.05)
            return "done late"

        register_background_subtask(ctx, _fake_run)
        await started.wait()

        await shutdown_session_background_subtasks("unknown-session", timeout=5.0)

        self.assertEqual(len(ctx.hook_pending_contexts), 1)
        self.assertIn("done late", ctx.hook_pending_contexts[0])
        self.assertFalse(has_pending_background_subtasks("unknown-session"))

    async def test_shutdown_with_no_tasks_is_noop(self):
        # Must not raise for a session with nothing tracked.
        await shutdown_session_background_subtasks("never-used-session", timeout=1.0)

    async def test_wait_returns_true_immediately_when_no_tasks(self):
        finished = await wait_for_session_background_subtasks(
            "never-used-session", timeout=1.0
        )
        self.assertTrue(finished)

    async def test_wait_returns_true_once_task_completes_within_timeout(self):
        ctx = CodeAgentContext(root_dir="/tmp")
        ctx.session = None

        async def _fake_run():
            await asyncio.sleep(0.05)
            return "finished in time"

        register_background_subtask(ctx, _fake_run)

        finished = await wait_for_session_background_subtasks(
            "unknown-session", timeout=5.0
        )
        self.assertTrue(finished)
        self.assertEqual(len(ctx.hook_pending_contexts), 1)
        self.assertIn("finished in time", ctx.hook_pending_contexts[0])

    async def test_wait_returns_false_on_timeout_and_leaves_task_running(self):
        ctx = CodeAgentContext(root_dir="/tmp")
        ctx.session = None

        started = asyncio.Event()
        stop = asyncio.Event()

        async def _fake_run():
            started.set()
            await stop.wait()
            return "eventually finished"

        register_background_subtask(ctx, _fake_run)
        await started.wait()

        finished = await wait_for_session_background_subtasks(
            "unknown-session", timeout=0.1
        )
        self.assertFalse(finished)
        # Must NOT have been cancelled by the timeout -- still tracked/running.
        self.assertTrue(has_pending_background_subtasks("unknown-session"))
        self.assertEqual(len(ctx.hook_pending_contexts), 0)

        # Cleanup: let it actually finish so it doesn't leak into later tests.
        stop.set()
        await asyncio.sleep(0.05)

    async def test_cancel_requests_cancellation_and_task_reports_cancelled(self):
        ctx = CodeAgentContext(root_dir="/tmp")
        ctx.session = None

        started = asyncio.Event()

        async def _fake_run():
            started.set()
            await asyncio.sleep(60)  # would hang forever without cancellation
            return "should never get here"

        register_background_subtask(ctx, _fake_run)
        await started.wait()

        requested = cancel_session_background_subtasks("unknown-session")
        self.assertEqual(requested, 1)

        # Cancellation is scheduled via call_soon_threadsafe, not applied
        # synchronously -- give the loop a couple of iterations to process it.
        for _ in range(10):
            if not has_pending_background_subtasks("unknown-session"):
                break
            await asyncio.sleep(0.01)

        self.assertFalse(has_pending_background_subtasks("unknown-session"))
        # A cancelled task's own CancelledError re-raise means _wrapped()
        # never reaches its "stage completion note" step.
        self.assertEqual(len(ctx.hook_pending_contexts), 0)

    def test_cancel_from_a_different_thread_is_safe(self):
        # Regression guard for the actual bug: Ctrl+C handling runs on the
        # main thread while background sub-agent tasks live on
        # ConversationTurn's dedicated loop thread. Calling task.cancel()
        # directly across threads is unsafe; this must go through
        # call_soon_threadsafe instead, so invoking the sync entry point
        # itself from a plain (non-loop) thread must not raise.
        #
        # Uses its own session id (not "unknown-session", shared by every
        # other test in this file via ctx.session = None) because the task
        # this test creates on a short-lived thread's loop can only ever be
        # cleaned up on that same loop -- mixing it into the shared bucket
        # would leak a dead-loop task into later tests' shutdown/gather calls.
        import threading
        import uuid

        session_id = f"thread-cancel-test-{uuid.uuid4().hex[:8]}"
        loop = asyncio.new_event_loop()
        started = threading.Event()
        stop = threading.Event()

        async def _fake_run():
            started.set()
            try:
                while not stop.is_set():
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                raise
            return "done"

        # CodeAgentContext.session_id is a read-only property derived from
        # ``session``; there's no session fixture handy here, so register
        # directly under a fake CodeAgentContext-shaped stand-in that only
        # needs the two attributes register_background_subtask() touches.
        class _FakeContext:
            def __init__(self, sid):
                self.session_id = sid
                self.hook_pending_contexts: list = []

        ctx = _FakeContext(session_id)

        def _run_loop():
            asyncio.set_event_loop(loop)
            # register_background_subtask() calls asyncio.create_task(),
            # which requires a *running* loop -- schedule it to run once
            # run_forever() has actually started the loop.
            loop.call_soon(register_background_subtask, ctx, _fake_run)
            loop.run_forever()

        thread = threading.Thread(target=_run_loop, daemon=True)
        thread.start()
        try:
            started.wait(timeout=5.0)
            # Called from THIS (main) thread, not the loop's own thread.
            requested = cancel_session_background_subtasks(session_id)
            self.assertEqual(requested, 1)
            # Let the cancellation actually land on the task's own loop
            # before tearing it down, so the task's done-callback (which
            # pops it from the module-level registry) has a chance to run.
            time.sleep(0.1)
        finally:
            stop.set()
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=5.0)
            loop.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

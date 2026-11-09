"""Parent interruption must also cancel sibling background sub-agent tasks."""
import asyncio
import unittest

from siada.tools.agent.subagent_async import (
    cancel_session_background_subtasks,
    has_pending_background_subtasks,
    register_background_subtask,
    shutdown_session_background_subtasks,
)


class _FakeAgentContext:
    """Minimal stand-in exposing only what register_background_subtask touches."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.hook_pending_contexts: list = []


class TestConversationTurnBackgroundSubtaskInterrupt(unittest.IsolatedAsyncioTestCase):
    async def test_ctrl_c_style_cancel_stops_background_subagent_on_session_loop(self):
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

        register_background_subtask(ctx, _fake_subagent_run)
        await started.wait()

        self.assertTrue(has_pending_background_subtasks(session_id))

        requested = cancel_session_background_subtasks(session_id)
        self.assertEqual(requested, 1)

        await shutdown_session_background_subtasks(session_id)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)

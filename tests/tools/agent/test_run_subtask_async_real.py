"""
Real-LLM verification for run_subtask(async=True) — acceptance criterion #3:

"Async mode confirms observable background SubAgent execution, extra-cache
cleanup after completion, and the parent Agent receiving the Subagent
task-completion notification."

Drives the actual ``run_subtask`` tool function end to end (through
``on_invoke_tool``, exactly as the SDK would call it), against a real model,
and observes:

1. The tool call returns immediately (before the sub-agent's LLM call
   finishes) — i.e. the call does not block on the sub-agent's completion.
2. While the background task is running, ``has_pending_background_subtasks``
   is True for the parent's session id.
3. After awaiting completion, the task is gone from the registry (cleanup)
   AND ``CodeAgentContext.hook_pending_contexts`` has received the
   completion notification with the real sub-agent summary — this is what
   ``SiadaRunHooks.on_llm_start`` injects into the parent's next LLM call.

Requires network access and valid ``li`` provider credentials; skips instead
of failing when the model call cannot complete.

Run explicitly with:
    poetry run python -m pytest tests/tools/agent/test_run_subtask_async_real.py -v -s
"""
import asyncio
import json
import tempfile
import time
import unittest

from agents import RunContextWrapper

from siada.entrypoint import _configure_litellm, set_current_provider
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.foundation.code_agent_context import CodeAgentContext
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig
from siada.session.session_manager import RunningSessionManager
from siada.tools.agent.run_subtask import run_subtask
from siada.tools.agent.subagent_async import has_pending_background_subtasks


_PROVIDER = "li"
_MODEL = "claude-sonnet-4.6"


def _build_real_session(workspace: str):
    llm_config = ModelRunConfig(_MODEL)
    llm_config.provider = _PROVIDER

    siada_config = RunningConfig(
        llm_config=llm_config,
        io=InputOutput(),
        workspace=workspace,
        agent_name="coder",
        console_output=False,
        interactive=False,
        tracing_disabled=True,
    )
    return RunningSessionManager.create_session(siada_config)


def _make_tool_context(run_ctx: RunContextWrapper):
    from agents.tool_context import ToolContext

    return ToolContext.from_agent_context(
        run_ctx, "call_1", tool_name="run_subtask", tool_arguments="{}",
    )


class TestRunSubtaskAsyncReal(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        set_current_provider(_PROVIDER)
        _configure_litellm()

    async def test_async_mode_returns_immediately_then_notifies_parent(self):
        with tempfile.TemporaryDirectory() as workspace:
            session = _build_real_session(workspace)
            context = CodeAgentContext(session=session, root_dir=workspace)
            run_ctx = RunContextWrapper(context=context)

            # A task with a deliberately slow instruction (asks for a short
            # delay-simulating computation) so the "returns immediately"
            # assertion has room to be observed — but the key evidence is
            # the wall-clock: the tool call must return long before the
            # sub-agent's own LLM turnaround (seconds) would allow.
            instruction = (
                "Without using any tools, compute 6 * 7 and reply with a "
                "single short sentence stating the result."
            )

            t0 = time.monotonic()
            try:
                ack = await run_subtask.on_invoke_tool(
                    _make_tool_context(run_ctx),
                    json.dumps({"instruction": instruction, "async": True}),
                )
            except Exception as exc:  # noqa: BLE001 - integration guard
                self.skipTest(f"Real LLM unavailable: {exc}")
            elapsed_ack = time.monotonic() - t0

            print(f"\n[async ack] elapsed={elapsed_ack:.3f}s ack={ack!r}\n")

            # 1. Returns immediately: acknowledgement text, not the sub-agent's
            # actual answer, and well under a real LLM round-trip.
            self.assertIn("background", ack)
            self.assertNotIn("completed", ack)  # the ack is not the completion notification
            self.assertLess(elapsed_ack, 2.0, "run_subtask(async=True) should not block on the LLM call")

            # 2. Background task observably running.
            session_id = context.session_id
            self.assertTrue(
                has_pending_background_subtasks(session_id),
                "expected a tracked background task right after scheduling",
            )
            self.assertEqual(len(context.hook_pending_contexts), 0)

            # 3. Wait for real completion, then verify cleanup + notification.
            deadline = time.monotonic() + 60.0
            while has_pending_background_subtasks(session_id) and time.monotonic() < deadline:
                await asyncio.sleep(0.5)

            self.assertFalse(
                has_pending_background_subtasks(session_id),
                "background task should be cleaned up from the registry after completion",
            )

            self.assertEqual(len(context.hook_pending_contexts), 1)
            note = context.hook_pending_contexts[0]
            print(f"\n[completion notification]\n{note}\n")
            self.assertIn("completed", note)
            self.assertIn("42", note)  # 6*7 — the real sub-agent's actual answer


if __name__ == "__main__":
    unittest.main(verbosity=2)

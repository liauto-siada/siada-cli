"""
Unit tests for the fork / async_mode additions to run_subtask.

Covers:
1. ``_build_fork_materials`` correctly reads tools / system prompt / real
   message history off a live parent RunContextWrapper.
2. ``run_subtask_impl(fork=True, ...)`` passes the aligned materials through
   to ``SubTaskAgent`` and seeds the sub-agent's session with the parent's
   real messages.
3. The ``run_subtask`` tool function's recursion guard rejects execution
   when ``CodeAgentContext.is_subagent`` is True.
4. The ``run_subtask`` tool function's ``async_mode`` path schedules a
   background task via ``register_background_subtask`` and returns
   immediately instead of awaiting the sub-agent run.

All tests avoid real network/LLM calls — Runner.run_streamed and
SubTaskAgent are mocked, mirroring the style of test_run_subtask_display.py.
"""
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from agents import Agent, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.session.session_models import RunningSession
from siada.tools.agent import subagent_recursion
from siada.tools.agent.run_subtask import (
    _build_fork_materials,
    _clone_context_for_subagent,
    run_subtask,
    run_subtask_impl,
)


# ---------------------------------------------------------------------------
# 1. _build_fork_materials
# ---------------------------------------------------------------------------

class TestBuildForkMaterials(unittest.IsolatedAsyncioTestCase):
    async def test_reads_parent_tools_instructions_and_history(self):
        parent_agent = Agent(
            name="ParentAgent",
            instructions="PARENT SYSTEM PROMPT",
            tools=["tool_a", "tool_b"],
        )

        code_ctx = MagicMock(spec=CodeAgentContext)
        code_ctx.session = MagicMock()
        code_ctx.task_message_state.get_real_messages.return_value = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

        run_ctx = RunContextWrapper(context=code_ctx)
        # Simulate what ToolContext.from_agent_context sets: an .agent attribute.
        run_ctx.agent = parent_agent

        tools, instructions, history = await _build_fork_materials(run_ctx)

        self.assertEqual(tools, ["tool_a", "tool_b"])
        self.assertEqual(instructions, "PARENT SYSTEM PROMPT")
        self.assertEqual(len(history), 2)

    async def test_falls_back_when_agent_not_reachable(self):
        code_ctx = MagicMock(spec=CodeAgentContext)
        code_ctx.session = None
        run_ctx = RunContextWrapper(context=code_ctx)
        # No .agent set on a bare RunContextWrapper.

        tools, instructions, history = await _build_fork_materials(run_ctx)

        self.assertIsNone(tools)
        self.assertIsNone(instructions)
        self.assertEqual(history, [])

    async def test_history_read_failure_is_swallowed(self):
        parent_agent = Agent(name="ParentAgent", instructions="X", tools=[])
        code_ctx = MagicMock(spec=CodeAgentContext)
        code_ctx.session = MagicMock()
        code_ctx.task_message_state.get_real_messages.side_effect = RuntimeError("boom")

        run_ctx = RunContextWrapper(context=code_ctx)
        run_ctx.agent = parent_agent

        tools, instructions, history = await _build_fork_materials(run_ctx)

        # Tools/instructions still resolved; history degrades to empty list.
        self.assertEqual(tools, [])
        self.assertEqual(instructions, "X")
        self.assertEqual(history, [])


# ---------------------------------------------------------------------------
# 2. run_subtask_impl(fork=True) wiring
# ---------------------------------------------------------------------------

def _make_fake_streamed_result(summary: str = "fork summary"):
    fake_result = MagicMock()

    async def _stream():
        return
        yield  # pragma: no cover - makes this an async generator

    fake_result.stream_events = _stream
    fake_result.final_output = summary
    return fake_result


class TestRunSubtaskImplForkWiring(unittest.IsolatedAsyncioTestCase):
    async def test_fork_true_passes_aligned_materials_to_subtask_agent(self):
        parent_agent = Agent(
            name="ParentAgent",
            instructions="PARENT PROMPT",
            tools=["real_tool"],
        )

        code_ctx = MagicMock(spec=CodeAgentContext)
        code_ctx.root_dir = "/tmp"
        code_ctx.session = MagicMock()
        code_ctx.session.siada_config = None
        code_ctx.web_tools_enabled = None
        code_ctx.sub_agent_items = []
        code_ctx.allow_recursive_subagents = False
        code_ctx.root_session_id = None
        code_ctx.subagent_self_id = None
        code_ctx.task_message_state.get_real_messages.return_value = [
            {"role": "user", "content": "past message"},
        ]

        run_ctx = RunContextWrapper(context=code_ctx)
        run_ctx.agent = parent_agent

        fake_result = _make_fake_streamed_result()

        with patch(
            "siada.tools.agent.run_subtask.Runner.run_streamed",
            return_value=fake_result,
        ) as mock_run_streamed, patch(
            "siada.tools.agent.run_subtask.build_sub_agent_run_config",
            return_value=MagicMock(tracing_disabled=True),
        ), patch(
            "siada.tools.agent.run_subtask.SubTaskAgent"
        ) as mock_subtask_agent_cls:
            summary = await run_subtask_impl(
                instruction="do the thing",
                agent_context=code_ctx,
                fork=True,
                run_ctx=run_ctx,
            )

        self.assertEqual(summary, "fork summary")

        # SubTaskAgent must have been constructed with the parent's tools
        # and system prompt verbatim.
        _, kwargs = mock_subtask_agent_cls.call_args
        self.assertEqual(kwargs["fork_tools"], ["real_tool"])
        self.assertEqual(kwargs["fork_instructions"], "PARENT PROMPT")

        # The parent's real message history must have been seeded into the
        # session object passed to Runner.run_streamed.
        _, run_streamed_kwargs = mock_run_streamed.call_args
        seeded_session = run_streamed_kwargs["session"]
        items = await seeded_session.get_items()
        self.assertEqual(items, [{"role": "user", "content": "past message"}])

    async def test_fork_true_without_run_ctx_falls_back_to_non_fork(self):
        code_ctx = MagicMock(spec=CodeAgentContext)
        code_ctx.root_dir = "/tmp"
        code_ctx.session = None
        code_ctx.web_tools_enabled = None
        code_ctx.sub_agent_items = []
        code_ctx.allow_recursive_subagents = False
        code_ctx.root_session_id = None
        code_ctx.subagent_self_id = None

        fake_result = _make_fake_streamed_result("non-fork summary")

        with patch(
            "siada.tools.agent.run_subtask.Runner.run_streamed",
            return_value=fake_result,
        ) as mock_run_streamed, patch(
            "siada.tools.agent.run_subtask.build_sub_agent_run_config",
            return_value=MagicMock(tracing_disabled=True),
        ), patch(
            "siada.tools.agent.run_subtask.SubTaskAgent"
        ) as mock_subtask_agent_cls:
            summary = await run_subtask_impl(
                instruction="do the thing",
                agent_context=code_ctx,
                fork=True,
                run_ctx=None,
            )

        self.assertEqual(summary, "non-fork summary")
        _, kwargs = mock_subtask_agent_cls.call_args
        self.assertIsNone(kwargs["fork_tools"])
        self.assertIsNone(kwargs["fork_instructions"])


class TestCloneContextForSubagent(unittest.TestCase):
    def test_clone_marks_is_subagent_true(self):
        parent_ctx = CodeAgentContext(root_dir="/tmp", is_subagent=False)
        clone = _clone_context_for_subagent(parent_ctx)
        self.assertTrue(clone.is_subagent)
        self.assertEqual(clone.root_dir, "/tmp")

    def test_clone_defaults_to_depth_1_with_no_self_id(self):
        parent_ctx = CodeAgentContext(root_dir="/tmp")
        clone = _clone_context_for_subagent(parent_ctx)
        self.assertEqual(clone.subagent_depth, 1)
        self.assertIsNone(clone.subagent_self_id)

    def test_clone_propagates_recursion_fields(self):
        parent_ctx = CodeAgentContext(
            root_dir="/tmp",
            root_session_id="root-sess-1",
            allow_recursive_subagents=True,
        )
        clone = _clone_context_for_subagent(parent_ctx, depth=2, self_id="sa_child")
        self.assertEqual(clone.subagent_depth, 2)
        self.assertEqual(clone.root_session_id, "root-sess-1")
        self.assertTrue(clone.allow_recursive_subagents)
        self.assertEqual(clone.subagent_self_id, "sa_child")

    def test_clone_when_recursion_disabled_carries_false_flag(self):
        parent_ctx = CodeAgentContext(root_dir="/tmp", allow_recursive_subagents=False)
        clone = _clone_context_for_subagent(parent_ctx)
        self.assertFalse(clone.allow_recursive_subagents)

    def test_clone_propagates_session_when_recursion_enabled(self):
        # Regression test: a depth-1 sub-agent context must carry a live
        # `session` when recursion is on, because build_sub_agent_run_config
        # (invoked if this sub-agent itself calls run_subtask to spawn a
        # depth-2 sub-sub-agent) hard-requires context.session to source the
        # LLM config. Without this, nested spawning fails at runtime with
        # "[build_sub_agent_run_config] An active session is required."
        fake_session = MagicMock(spec=RunningSession)
        parent_ctx = CodeAgentContext(
            root_dir="/tmp",
            session=fake_session,
            allow_recursive_subagents=True,
        )
        clone = _clone_context_for_subagent(parent_ctx, depth=1, self_id="sa_parent")
        self.assertIs(clone.session, fake_session)

    def test_clone_does_not_propagate_session_when_recursion_disabled(self):
        # Default (off) path must stay byte-for-byte identical to
        # pre-existing behaviour: the cloned sub-agent context never carries
        # a live session.
        fake_session = MagicMock(spec=RunningSession)
        parent_ctx = CodeAgentContext(
            root_dir="/tmp",
            session=fake_session,
            allow_recursive_subagents=False,
        )
        clone = _clone_context_for_subagent(parent_ctx)
        self.assertIsNone(clone.session)


# ---------------------------------------------------------------------------
# 3 & 4. run_subtask tool function: recursion guard + async_mode scheduling
# ---------------------------------------------------------------------------

class TestRunSubtaskToolFunction(unittest.IsolatedAsyncioTestCase):
    async def test_recursion_guard_rejects_when_is_subagent(self):
        code_ctx = CodeAgentContext(root_dir="/tmp", is_subagent=True)
        run_ctx = RunContextWrapper(context=code_ctx)

        result = await run_subtask.on_invoke_tool(
            _make_tool_context(run_ctx),
            '{"instruction": "do something"}',
        )

        self.assertIn("not available", result)

    async def test_async_mode_schedules_background_task_and_returns_immediately(self):
        code_ctx = CodeAgentContext(root_dir="/tmp", is_subagent=False)
        run_ctx = RunContextWrapper(context=code_ctx)

        with patch(
            "siada.tools.agent.run_subtask.register_background_subtask",
            return_value="abc123",
        ) as mock_register:
            result = await run_subtask.on_invoke_tool(
                _make_tool_context(run_ctx),
                '{"instruction": "do something", "async": true}',
            )

        mock_register.assert_called_once()
        self.assertIn("abc123", result)
        self.assertIn("background", result)

    async def test_non_async_mode_awaits_run_subtask_impl(self):
        code_ctx = CodeAgentContext(root_dir="/tmp", is_subagent=False)
        run_ctx = RunContextWrapper(context=code_ctx)

        with patch(
            "siada.tools.agent.run_subtask.run_subtask_impl",
            new=AsyncMock(return_value="synchronous summary"),
        ) as mock_impl:
            result = await run_subtask.on_invoke_tool(
                _make_tool_context(run_ctx),
                '{"instruction": "do something"}',
            )

        mock_impl.assert_awaited_once()
        self.assertEqual(result, "synchronous summary")

    async def test_recursion_off_never_touches_concurrency_registry(self):
        # allow_recursive_subagents defaults to False: the run_subtask tool
        # function must not consult subagent_recursion at all -- child_depth
        # stays at the hardcoded default (1) and no alive-count bookkeeping
        # happens, exactly matching pre-existing behaviour.
        session_id = f"off-{uuid.uuid4().hex[:8]}"
        code_ctx = CodeAgentContext(
            root_dir="/tmp", is_subagent=False,
            root_session_id=session_id, allow_recursive_subagents=False,
        )
        run_ctx = RunContextWrapper(context=code_ctx)

        with patch(
            "siada.tools.agent.run_subtask.run_subtask_impl",
            new=AsyncMock(return_value="ok"),
        ) as mock_impl:
            await run_subtask.on_invoke_tool(
                _make_tool_context(run_ctx),
                '{"instruction": "do something"}',
            )

        self.assertEqual(subagent_recursion.alive_count(session_id), 0)
        _, kwargs = mock_impl.call_args
        self.assertEqual(kwargs["child_depth"], 1)

    async def test_recursion_on_main_agent_spawns_depth_1_and_releases_slot(self):
        session_id = f"on-{uuid.uuid4().hex[:8]}"
        code_ctx = CodeAgentContext(
            root_dir="/tmp", is_subagent=False, subagent_depth=0,
            root_session_id=session_id, allow_recursive_subagents=True,
        )
        run_ctx = RunContextWrapper(context=code_ctx)

        with patch(
            "siada.tools.agent.run_subtask.run_subtask_impl",
            new=AsyncMock(return_value="ok"),
        ) as mock_impl:
            result = await run_subtask.on_invoke_tool(
                _make_tool_context(run_ctx),
                '{"instruction": "do something"}',
            )

        self.assertEqual(result, "ok")
        _, kwargs = mock_impl.call_args
        self.assertEqual(kwargs["child_depth"], 1)
        # Slot must be released after the (mocked) run completes.
        self.assertEqual(subagent_recursion.alive_count(session_id), 0)

    async def test_recursion_on_depth_2_sub_subagent_call_is_rejected_by_guard(self):
        # A depth-2 sub-sub-agent has is_subagent=True and is already AT the
        # nesting cap, so subagent_guard.is_blocked_for_subagent rejects it
        # before check_can_spawn is even consulted (see subagent_guard.py's
        # depth-aware branch).
        session_id = f"depth2-{uuid.uuid4().hex[:8]}"
        code_ctx = CodeAgentContext(
            root_dir="/tmp", is_subagent=True, subagent_depth=2,
            root_session_id=session_id, allow_recursive_subagents=True,
        )
        run_ctx = RunContextWrapper(context=code_ctx)

        with patch(
            "siada.tools.agent.run_subtask.run_subtask_impl",
            new=AsyncMock(),
        ) as mock_impl:
            result = await run_subtask.on_invoke_tool(
                _make_tool_context(run_ctx),
                '{"instruction": "do something"}',
            )

        mock_impl.assert_not_awaited()
        self.assertIn("not available", result)
        self.assertEqual(subagent_recursion.alive_count(session_id), 0)

    async def test_recursion_on_depth_1_subagent_reaching_own_depth_cap(self):
        # Directly exercises check_can_spawn's depth-cap branch inside the
        # tool function (as opposed to the guard's own depth check above):
        # a depth-1 sub-agent (is_subagent=True, not yet at the cap) whose
        # OWN run_subtask call would spawn a depth-2 child is allowed through
        # by the guard, and check_can_spawn correctly computes child_depth=2.
        # A follow-up call FROM that depth-2 child is what the guard blocks
        # (covered above) -- this test isolates check_can_spawn's own logic
        # by calling it directly at parent_depth=MAX_NESTING_DEPTH.
        decision = subagent_recursion.check_can_spawn(
            parent_depth=subagent_recursion.MAX_NESTING_DEPTH, root_session_id=None
        )
        self.assertFalse(decision.allowed)
        self.assertIn("Nesting depth", decision.reason)

    async def test_recursion_on_rejects_when_concurrency_cap_reached(self):
        session_id = f"cap-{uuid.uuid4().hex[:8]}"
        # main(1) + alive(MAX-1) + new(1) == MAX+1 -> must be rejected.
        for _ in range(subagent_recursion.MAX_CONCURRENT_AGENTS - 1):
            subagent_recursion.register_alive(session_id)

        code_ctx = CodeAgentContext(
            root_dir="/tmp", is_subagent=False, subagent_depth=0,
            root_session_id=session_id, allow_recursive_subagents=True,
        )
        run_ctx = RunContextWrapper(context=code_ctx)

        try:
            with patch(
                "siada.tools.agent.run_subtask.run_subtask_impl",
                new=AsyncMock(),
            ) as mock_impl:
                result = await run_subtask.on_invoke_tool(
                    _make_tool_context(run_ctx),
                    '{"instruction": "do something"}',
                )
            mock_impl.assert_not_awaited()
            self.assertIn("Maximum concurrent agent count", result)
        finally:
            for _ in range(subagent_recursion.MAX_CONCURRENT_AGENTS - 1):
                subagent_recursion.release_alive(session_id)
        self.assertEqual(subagent_recursion.alive_count(session_id), 0)


def _make_tool_context(run_ctx: RunContextWrapper):
    """Build a minimal ToolContext wrapping *run_ctx* for on_invoke_tool calls."""
    from agents.tool_context import ToolContext

    return ToolContext.from_agent_context(
        run_ctx,
        "call_1",
        tool_name="run_subtask",
        tool_arguments="{}",
    )


if __name__ == "__main__":
    unittest.main(verbosity=2)

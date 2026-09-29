"""
Tests for TurnPolicy._maybe_await_background_subtask_summary.

See design rationale in turn_policy.py's docstring on that method: when a
conversation turn's model output looks like a final ("I'm done"), no-more-
tool-calls completion while the session still has run_subtask(async=True)
background sub-agent task(s) outstanding, this gives them a bounded grace
period to land their real result and, if they do, auto-injects that result
via the existing SwitchEvent(ai_analysis_prompt=...) mechanism instead of
silently handing control back to the user as if nothing were still running.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

# Import turn_policy first: it pulls in siada.session before turn.models /
# slash_commands, avoiding a circular import (checkpoint_tracker <->
# session_manager) that the old controller import used to mask.
from siada.entrypoint.interaction.turn_policy import TurnPolicy
from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.entrypoint.interaction.turn.models import TurnOutput, TurnType
from siada.foundation.code_agent_context import CodeAgentContext
from siada.services.file_session import FileSession
from siada.services.goal import goal_storage
from siada.services.goal.models import GOAL_MAX_TURNS, Goal, GoalVerdict
from siada.support.slash_commands import SwitchEvent
from siada.tools.agent.subagent_async import register_background_subtask
# Imported so "siada.services.siada_runner" is registered as an attribute of
# the "siada.services" package before `patch("siada.services.siada_runner
# .SiadaRunner._context_cache", ...)` below tries to resolve it -- otherwise
# mock.patch's dotted-path resolution raises AttributeError on a
# not-yet-imported submodule.
import siada.services.siada_runner  # noqa: F401


def _make_controller():
    return TurnPolicy(
        config=SimpleNamespace(io=SimpleNamespace(pretty=False)),
        slash_commands=SimpleNamespace(),
        send_notification=None,
    )


def _make_turn(turn_type=TurnType.CONVERSATION):
    return SimpleNamespace(get_turn_type=lambda: turn_type)


def _make_session(session_id="sess-1", workspace="/ws"):
    return SimpleNamespace(
        session_id=session_id,
        siada_config=SimpleNamespace(workspace=workspace),
    )


class TestMaybeAwaitBackgroundSubtaskSummary:
    def teardown_method(self):
        ConversationTurn._cleanup_dedicated_loop()
        ConversationTurn._dedicated_loop = None
        ConversationTurn._dedicated_thread = None

    def test_skips_non_conversation_turns(self):
        ctrl = _make_controller()
        turn = _make_turn(TurnType.COMMAND)
        result = TurnOutput(output="done", metadata={}, next_action=None)
        out = ctrl._maybe_await_background_subtask_summary(turn, _make_session(), result)
        assert out is result

    def test_skips_when_result_is_none(self):
        ctrl = _make_controller()
        turn = _make_turn()
        out = ctrl._maybe_await_background_subtask_summary(turn, _make_session(), None)
        assert out is None

    def test_skips_when_output_is_not_a_plain_string(self):
        # Retry/goal-verifier already turned this into a SwitchEvent --
        # don't stack another auto-continuation on top.
        ctrl = _make_controller()
        turn = _make_turn()
        result = TurnOutput(
            output=SwitchEvent(ai_analysis_prompt="retry"), metadata={}, next_action=None
        )
        out = ctrl._maybe_await_background_subtask_summary(turn, _make_session(), result)
        assert out is result

    def test_skips_when_no_pending_background_tasks(self):
        ctrl = _make_controller()
        turn = _make_turn()
        session = _make_session(session_id="sess-no-tasks")
        result = TurnOutput(output="all done", metadata={}, next_action=None)
        out = ctrl._maybe_await_background_subtask_summary(turn, session, result)
        assert out is result

    def test_returns_unchanged_when_no_dedicated_loop_available(self):
        ctrl = _make_controller()
        turn = _make_turn()
        session = _make_session(session_id="sess-loopless")

        with patch(
            "siada.tools.agent.subagent_async.has_pending_background_subtasks",
            return_value=True,
        ):
            ConversationTurn._dedicated_loop = None
            result = TurnOutput(output="all done", metadata={}, next_action=None)
            out = ctrl._maybe_await_background_subtask_summary(turn, session, result)
        assert out is result

    def test_task_finishes_within_grace_period_injects_switch_event(self):
        ctrl = _make_controller()
        turn = _make_turn()
        session_id = "sess-finishes-in-time"
        session = _make_session(session_id=session_id)

        ConversationTurn._ensure_dedicated_loop()
        dedicated_loop = ConversationTurn._dedicated_loop

        ctx = CodeAgentContext(root_dir="/tmp")
        ctx.session = SimpleNamespace(session_id=session_id)

        async def _fake_subagent_run():
            await asyncio.sleep(0.05)
            return "sub-agent found and fixed the bug"

        register_future = asyncio.run_coroutine_threadsafe(
            _wrap_register(ctx, _fake_subagent_run), dedicated_loop
        )
        register_future.result(timeout=5.0)

        fake_cache = {("agent", "/ws"): ctx}
        with patch(
            "siada.services.siada_runner.SiadaRunner._context_cache", fake_cache
        ), patch.object(
            TurnPolicy, "_BACKGROUND_SUBTASK_AWAIT_TIMEOUT", 5.0
        ):
            result = TurnOutput(output="I'm all done here", metadata={}, next_action=None)
            out = ctrl._maybe_await_background_subtask_summary(turn, session, result)

        assert isinstance(out.output, SwitchEvent)
        feedback = out.output.kwargs["ai_analysis_prompt"]
        assert "sub-agent found and fixed the bug" in feedback
        # The queue must have been drained so the same note isn't also
        # re-injected later via the normal on_llm_start path.
        assert ctx.hook_pending_contexts == []

    def test_background_completion_does_not_resume_goal_blocked_by_verifier(self, tmp_path):
        ctrl = _make_controller()
        ctrl._send_acp_notification = lambda method, params: None
        turn = _make_turn()
        session_id = "sess-goal-blocked"
        session = _make_session(session_id=session_id)
        file_session = FileSession(session_id=session_id, sessions_dir=tmp_path)
        session.openai_session = file_session
        goal = Goal.create("bounded goal")
        goal.consecutive_failures = GOAL_MAX_TURNS - 1
        goal_storage.save_goal(file_session.session_folder, goal)

        ctx = CodeAgentContext(root_dir=str(tmp_path))
        ctx.session = SimpleNamespace(session_id=session_id)
        ctx.goal = goal

        async def _fake_subagent_run():
            await asyncio.sleep(0.05)
            return "background task completed"

        ConversationTurn._ensure_dedicated_loop()
        loop = ConversationTurn._dedicated_loop
        register_future = asyncio.run_coroutine_threadsafe(
            _wrap_register(ctx, _fake_subagent_run), loop,
        )
        register_future.result(timeout=5.0)

        result = TurnOutput(output="still working", metadata={}, next_action=None)
        verdict = GoalVerdict(
            passed=False, reason="not done", nextAction="review task results",
        )
        fake_cache = {("agent", "/ws"): ctx}
        with patch(
            "siada.services.siada_runner.SiadaRunner._context_cache", fake_cache,
        ), patch(
            "siada.services.goal.verifier.run_goal_verification",
            new=AsyncMock(return_value=verdict),
        ) as verifier, patch(
            "siada.notifications.show_completion_notification",
        ), patch.object(TurnPolicy, "_BACKGROUND_SUBTASK_AWAIT_TIMEOUT", 5.0):
            blocked_result = ctrl._maybe_run_goal_verifier(
                turn, session, file_session.session_folder, result,
            )
            assert blocked_result is result
            assert goal.status == "blocked"

            continuation = ctrl._maybe_await_background_subtask_summary(
                turn, session, blocked_result,
            )
            assert isinstance(continuation.output, SwitchEvent)
            assert "background task completed" in continuation.output.kwargs["ai_analysis_prompt"]

            ctrl._maybe_reset_goal_on_new_turn(
                turn, session, file_session.session_folder, user_initiated=False,
            )
            assert goal.status == "blocked"
            assert ctrl._maybe_run_goal_verifier(
                turn, session, file_session.session_folder, result,
            ) is result
            verifier.assert_awaited_once()
            assert goal_storage.load_goal(file_session.session_folder).status == "blocked"

            ctrl._maybe_reset_goal_on_new_turn(
                turn, session, file_session.session_folder, user_initiated=True,
            )
            assert goal.status == "active"
            assert goal.consecutive_failures == 0

    def test_task_still_running_after_timeout_returns_unchanged_and_task_survives(self):
        ctrl = _make_controller()
        turn = _make_turn()
        session_id = "sess-still-running"
        session = _make_session(session_id=session_id)

        ConversationTurn._ensure_dedicated_loop()
        dedicated_loop = ConversationTurn._dedicated_loop

        ctx = CodeAgentContext(root_dir="/tmp")
        ctx.session = SimpleNamespace(session_id=session_id)
        stop = asyncio.Event()

        async def _fake_subagent_run():
            await stop.wait()
            return "finished eventually"

        register_future = asyncio.run_coroutine_threadsafe(
            _wrap_register(ctx, _fake_subagent_run), dedicated_loop
        )
        register_future.result(timeout=5.0)

        fake_cache = {("agent", "/ws"): ctx}
        try:
            with patch(
                "siada.services.siada_runner.SiadaRunner._context_cache", fake_cache
            ), patch.object(TurnPolicy, "_BACKGROUND_SUBTASK_AWAIT_TIMEOUT", 0.2):
                result = TurnOutput(output="I'm all done here", metadata={}, next_action=None)
                out = ctrl._maybe_await_background_subtask_summary(turn, session, result)

            assert out is result
            assert ctx.hook_pending_contexts == []

            from siada.tools.agent.subagent_async import has_pending_background_subtasks
            assert has_pending_background_subtasks(session_id)
        finally:
            # Let the still-running task actually finish so it doesn't leak.
            async def _set_stop():
                stop.set()

            asyncio.run_coroutine_threadsafe(_set_stop(), dedicated_loop).result(timeout=5.0)


async def _wrap_register(ctx, coro_factory):
    return register_background_subtask(ctx, coro_factory)

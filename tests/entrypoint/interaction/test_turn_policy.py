"""
Tests for TurnPolicy: session lifecycle (start_session / end_session) and the
turn-level policy around execute() -- hook ordering, retry priority over the
goal verifier, exception/cancellation cleanup, and ownership conflicts.

TurnPolicy owns no UI: notifications go through the injected callback, a
WaitingSpinner was removed from the background-await path, and an ownership
conflict makes execute() return None (stop-animation is the controller's job).
"""
import concurrent.futures
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

# Import turn_policy first: it pulls in siada.session before turn.models /
# slash_commands, avoiding a circular import (checkpoint_tracker <->
# session_manager) that the old controller import used to mask.
from siada.entrypoint.interaction.turn_policy import TurnPolicy
from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.entrypoint.interaction.turn.models import (
    TurnOutput,
    TurnType,
    RETRY_REASON_METADATA_KEY,
    RETRY_REASON_TRUNCATED_REASONING_ONLY,
)
from siada.session.ownership import OwnershipError
from siada.support.slash_commands import SwitchEvent


class _FakeHookRunner:
    """Records hook events; UserPromptSubmit/Stop return hook responses."""

    def __init__(self, responses=None):
        self.events = []  # (event, kind, context)
        self.workspace = None
        self._responses = responses or []

    def set_workspace(self, workspace):
        self.workspace = workspace

    def run(self, event, context=None):
        self.events.append((event, "run", context))

    def run_with_result_sync(self, event, context=None):
        self.events.append((event, "sync", context))
        return self._responses


def _make_policy(hook_runner=None, send_notification=None, acp_mode=False):
    config = SimpleNamespace(acp_mode=acp_mode, io=SimpleNamespace(acp_adapter=None, print_error=Mock(), print_warning=Mock()))
    slash_commands = (
        SimpleNamespace(hook_runner=hook_runner)
        if hook_runner is not None
        else SimpleNamespace()
    )
    return TurnPolicy(
        config=config,
        slash_commands=slash_commands,
        send_notification=send_notification,
    )


def _make_turn(execute_result=None, exc=None, turn_type=TurnType.CONVERSATION):
    turn = Mock()
    turn.get_turn_type.return_value = turn_type
    if exc is not None:
        turn.execute.side_effect = exc
    else:
        turn.execute.return_value = execute_result
    return turn


def _make_session(session_id="sess-1", workspace="/ws"):
    return SimpleNamespace(
        session_id=session_id,
        siada_config=SimpleNamespace(workspace=workspace),
        state=SimpleNamespace(openai_session=None),
    )


@contextmanager
def _ignored_monitor_and_hooks():
    """Patch out the stdin monitor and global hook-runner registry."""
    with patch("siada.io.stdin_interrupt_monitor.is_monitor_active", return_value=False), \
         patch("siada.services.plugins.hook_runner.set_active") as set_active:
        yield set_active


class TestExecuteHooksOrder:
    @pytest.mark.parametrize("user_initiated", [False, True])
    def test_execute_passes_input_origin_to_goal_reset(self, user_initiated):
        policy = _make_policy()
        session = _make_session()
        result = TurnOutput(output="done", metadata={}, next_action=None)
        turn = _make_turn(execute_result=result)
        with patch.object(TurnPolicy, "_maybe_reset_goal_on_new_turn") as reset, patch.object(
            TurnPolicy, "_maybe_run_goal_verifier", return_value=result,
        ), patch.object(
            TurnPolicy, "_maybe_await_background_subtask_summary", return_value=result,
        ), _ignored_monitor_and_hooks():
            assert policy.execute(turn, "feedback", session, user_initiated=user_initiated) is result

        reset.assert_called_once_with(turn, session, None, user_initiated=user_initiated)

    def test_execute_runs_hooks_in_order_and_returns_result(self):
        runner = _FakeHookRunner()
        policy = _make_policy(hook_runner=runner)
        result = TurnOutput(output="a real answer", metadata={"k": "v"}, next_action=None)
        turn = _make_turn(execute_result=result)
        session = _make_session()

        with patch.object(TurnPolicy, "_maybe_run_goal_verifier", return_value=result) as verifier, \
             patch.object(
                 TurnPolicy, "_maybe_await_background_subtask_summary", return_value=result
             ) as await_bg, \
             _ignored_monitor_and_hooks() as set_active:
            out = policy.execute(turn, "hello", session)

        assert out is result
        assert runner.events == [
            ("PreTurn", "run", None),
            ("UserPromptSubmit", "sync", {"user_prompt": "hello"}),
            ("Stop", "sync", {"hook_event_name": "Stop", "tool_input": {"content": ""}}),
            ("PostTurn", "run", None),
        ]
        # Hooks run against the session workspace.
        assert runner.workspace == "/ws"
        # The global active hook runner is set before the turn and cleared after.
        set_active.assert_any_call(runner)
        set_active.assert_any_call(None)
        verifier.assert_called_once()
        await_bg.assert_called_once()

    def test_execute_skips_user_prompt_submit_for_non_string_input(self):
        runner = _FakeHookRunner()
        policy = _make_policy(hook_runner=runner)
        result = TurnOutput(output="ok", metadata={}, next_action=None)
        turn = _make_turn(execute_result=result)

        with patch.object(TurnPolicy, "_maybe_run_goal_verifier", return_value=result), \
             patch.object(
                 TurnPolicy, "_maybe_await_background_subtask_summary", return_value=result
             ), \
             _ignored_monitor_and_hooks():
            out = policy.execute(turn, ["pending", "input"], _make_session())

        assert out is result
        events = [e for e, _, _ in runner.events]
        assert events == ["PreTurn", "Stop", "PostTurn"]

    def test_execute_retry_takes_priority_over_goal_verifier(self):
        """A retry-triggering result must skip both the goal verifier and the
        background-await strategy and go straight to PostTurn (the retry's own
        SwitchEvent is the single auto-continuation queued for next round)."""
        runner = _FakeHookRunner()
        policy = _make_policy(hook_runner=runner)
        flagged = TurnOutput(
            output="reasoning only",
            metadata={RETRY_REASON_METADATA_KEY: RETRY_REASON_TRUNCATED_REASONING_ONLY},
            next_action=None,
        )
        turn = _make_turn(execute_result=flagged)

        with patch.object(TurnPolicy, "_maybe_run_goal_verifier") as verifier, \
             patch.object(TurnPolicy, "_maybe_await_background_subtask_summary") as await_bg, \
             _ignored_monitor_and_hooks():
            out = policy.execute(turn, "hello", _make_session())

        assert isinstance(out.output, SwitchEvent)
        verifier.assert_not_called()
        await_bg.assert_not_called()
        assert ("PostTurn", "run", None) in runner.events


class TestExecuteExceptionCleanup:
    def _run_with_exc(self, exc):
        runner = _FakeHookRunner()
        policy = _make_policy(hook_runner=runner)
        turn = _make_turn(exc=exc)
        with patch(
            "siada.io.stdin_interrupt_monitor.is_monitor_active", return_value=True
        ), patch("siada.io.stdin_interrupt_monitor.set_agent_running") as set_running, \
             patch("siada.services.plugins.hook_runner.set_active") as set_active:
            with pytest.raises(type(exc)):
                policy.execute(turn, "hello", _make_session())
        return runner, set_running, set_active

    def test_exception_runs_on_error_hook_and_cleans_up(self):
        runner, set_running, set_active = self._run_with_exc(RuntimeError("boom"))

        assert ("OnError", "run", None) in runner.events
        # The failed turn never reaches PostTurn.
        assert not any(e[0] == "PostTurn" for e in runner.events)
        # Monitor flag toggled on at turn start and off in finally.
        set_running.assert_has_calls([call(True), call(False)])
        # Active hook runner cleared even on failure.
        set_active.assert_called_with(None)

    def test_cancellation_propagates_but_finally_still_cleans_up(self):
        """KeyboardInterrupt is a BaseException: it bypasses the OnError hook
        (only `except Exception` triggers it) but the finally block must still
        clear the monitor flag and the active hook runner."""
        runner, set_running, set_active = self._run_with_exc(KeyboardInterrupt())

        assert not any(e[0] == "OnError" for e in runner.events)
        set_running.assert_has_calls([call(True), call(False)])
        set_active.assert_called_with(None)


class TestExecuteOwnershipConflict:
    def test_ownership_conflict_returns_none_and_cleans_up(self):
        runner = _FakeHookRunner()
        policy = _make_policy(hook_runner=runner)
        turn = _make_turn(
            execute_result=TurnOutput(output="x", metadata={}, next_action=None)
        )

        @contextmanager
        def _conflict(session_dir, owner):
            raise OwnershipError("busy", current_owner="lark")
            yield  # pragma: no cover

        with patch(
            "siada.session.ownership.SessionOwnershipManager.owned_turn", _conflict
        ), _ignored_monitor_and_hooks() as set_active:
            out = policy.execute(turn, "hello", _make_session())

        assert out is None
        # turn.execute never ran; Stop/PostTurn/OnError hooks must not run.
        assert not any(e[0] in ("Stop", "PostTurn", "OnError") for e in runner.events)
        set_active.assert_called_with(None)


class TestSessionLifecycle:
    def test_start_session_fires_session_start_hook(self):
        runner = _FakeHookRunner()
        policy = _make_policy(hook_runner=runner)
        session = _make_session(session_id="sess-start", workspace="/ws")

        policy.start_session(session)

        starts = [e for e in runner.events if e[0] == "SessionStart"]
        assert len(starts) == 1
        assert starts[0][1] == "run"
        assert starts[0][2]["session_id"] == "sess-start"
        assert starts[0][2]["workspace"] == "/ws"
        assert "exit_reason" not in starts[0][2]

    def test_end_session_fires_hook_exactly_once(self):
        runner = _FakeHookRunner()
        policy = _make_policy(hook_runner=runner)
        session = _make_session(session_id="sess-end-once")

        policy.end_session(session, "normal")
        policy.end_session(session, "error")

        ends = [e for e in runner.events if e[0] == "SessionEnd"]
        assert len(ends) == 1
        assert ends[0][1] == "run"
        assert ends[0][2]["exit_reason"] == "normal"
        assert ends[0][2]["session_id"] == "sess-end-once"

    def test_end_session_shuts_down_background_subtasks_on_dedicated_loop(self):
        """end_session must dispatch the background sub-agent shutdown onto
        ConversationTurn's dedicated loop (run_coroutine_threadsafe) -- the
        same cleanup the controller's _fire_session_end used to do."""
        runner = _FakeHookRunner()
        policy = _make_policy(hook_runner=runner)
        session = _make_session(session_id="sess-cleanup")

        class _FakeLoop:
            def is_closed(self):
                return False

        fake_loop = _FakeLoop()
        future = concurrent.futures.Future()
        future.set_result(None)

        with patch(
            "siada.tools.agent.subagent_async.has_pending_background_subtasks",
            return_value=True,
        ), patch.object(ConversationTurn, "_dedicated_loop", fake_loop), patch(
            "asyncio.run_coroutine_threadsafe", return_value=future
        ) as run_coro, patch(
            "siada.tools.agent.subagent_async.shutdown_session_background_subtasks",
            Mock(return_value="shutdown-coro"),
        ) as shutdown:
            policy.end_session(session, "normal")

        shutdown.assert_called_once_with("sess-cleanup")
        run_coro.assert_called_once_with("shutdown-coro", fake_loop)

        ends = [e for e in runner.events if e[0] == "SessionEnd"]
        assert len(ends) == 1
        assert ends[0][2]["exit_reason"] == "normal"

    def test_end_session_hook_error_does_not_crash(self):
        class _BoomRunner(_FakeHookRunner):
            def run(self, event, context=None):
                if event == "SessionEnd":
                    raise RuntimeError("hook failed")
                super().run(event, context)

        policy = _make_policy(hook_runner=_BoomRunner())
        policy.end_session(_make_session(), "normal")  # must not raise
        assert policy._session_end_fired is True

def test_hook_context_is_still_displayed_to_user():
    runner = _FakeHookRunner([SimpleNamespace(additional_context="hook warning")])
    policy = _make_policy(hook_runner=runner)
    turn = _make_turn(execute_result=TurnOutput(output="ok", metadata={}, next_action=None))
    with _ignored_monitor_and_hooks(), patch.object(
        policy, "_maybe_run_goal_verifier", side_effect=lambda t, s, d, r: r,
    ):
        policy.execute(turn, "hello", _make_session())
    assert policy.config.io.print_error.call_args_list == [
        call("hook warning"), call("hook warning"),
    ]


def test_hook_setup_error_clears_running_flag():
    runner = _FakeHookRunner()
    runner.set_workspace = Mock(side_effect=ValueError("bad workspace"))
    policy = _make_policy(hook_runner=runner)
    with patch("siada.io.stdin_interrupt_monitor.is_monitor_active", return_value=True), patch(
        "siada.io.stdin_interrupt_monitor.set_agent_running",
    ) as running, patch("siada.services.plugins.hook_runner.set_active") as active:
        with pytest.raises(ValueError, match="bad workspace"):
            policy.execute(_make_turn(), "hello", _make_session())
    assert running.call_args_list == [call(True), call(False)]
    active.assert_called_with(None)

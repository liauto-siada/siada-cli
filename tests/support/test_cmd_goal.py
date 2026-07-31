"""
Tests for cmd_goal in SlashCommands.

/goal only supports two subcommands by design: setting a new objective and
`/goal clear`. There is deliberately no pause/resume/status subcommand —
"complete" goals are dropped and "blocked" goals are auto-reactivated by
Controller._maybe_reset_goal_on_new_turn as soon as the user sends their next
conversational message.

A goal may be overwritten by /goal <new objective> at ANY time regardless of
its current status (active, blocked, or complete) — no /goal clear needed
first. Every overwrite/clear archives the outgoing goal to
goal_history.jsonl first (see goal_storage.append_goal_history), so nothing
is silently lost even though goal.json itself only ever holds the current
goal.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Pre-import to break circular-import chain:
# slash_commands -> checkpoint_tracker -> session.task_message_state
import siada.session  # noqa: F401
import siada.support.checkpoint_tracker  # noqa: F401

from siada.support.slash_commands import SlashCommands, SwitchEvent
from siada.services.goal import goal_storage
from siada.services.goal.models import Goal


def _make_slash_commands() -> SlashCommands:
    io = MagicMock()
    io.acp_adapter = None
    return SlashCommands(io=io)


def _make_session(session_dir: Path, workspace: str = "/tmp/ws") -> MagicMock:
    session = MagicMock()
    session.siada_config.workspace = workspace
    session.state.openai_session.session_folder = session_dir
    return session


class TestCmdGoalLifecycle:
    def test_set_new_goal_persists_and_prints(self):
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session(session_dir)
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
                out = sc.cmd_goal(session, "ship the feature")

            sc.io.print_info.assert_called_with("Goal set: ship the feature")
            loaded = goal_storage.load_goal(session_dir)
            assert loaded is not None
            assert loaded.objective == "ship the feature"
            assert loaded.status == "active"

    def test_set_new_goal_immediately_hands_objective_to_agent(self):
        """/goal must not be a silent no-op background flag flip -- it hands
        the objective straight to the agent as the first real turn via the
        same SwitchEvent(ai_analysis_prompt=...) channel /init and
        /issue_fix use, so Controller.run() actually executes it."""
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session = _make_session(Path(d))
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
                out = sc.cmd_goal(session, "analyze the cost calculation")

            assert isinstance(out, SwitchEvent)
            assert out.kwargs["ai_analysis_prompt"] == "analyze the cost calculation"


    def test_empty_args_shows_usage_error(self):
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session = _make_session(Path(d))
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
                sc.cmd_goal(session, "")
            sc.io.print_error.assert_called_with("Usage: /goal <objective>  |  /goal clear")

    def test_can_overwrite_an_active_goal_directly(self):
        """A goal may be overwritten at any time, including while active —
        no /goal clear required first."""
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            goal_storage.save_goal(session_dir, Goal.create("first goal"))
            session = _make_session(session_dir)
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
                sc.cmd_goal(session, "second goal")
            sc.io.print_error.assert_not_called()
            sc.io.print_info.assert_called_with("Goal set: second goal")
            loaded = goal_storage.load_goal(session_dir)
            assert loaded.objective == "second goal"
            assert loaded.status == "active"
            assert loaded.consecutive_failures == 0

    def test_overwriting_an_active_goal_archives_it_to_history(self):
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            goal_storage.save_goal(session_dir, Goal.create("first goal"))
            session = _make_session(session_dir)
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
                sc.cmd_goal(session, "second goal")

            history = goal_storage.load_goal_history(session_dir)
            assert len(history) == 1
            assert history[0]["objective"] == "first goal"
            assert "archived_at" in history[0]

    def test_can_set_new_goal_over_a_blocked_one(self):
        """A blocked goal (auto-tripped after repeated verifier failures) may
        be overwritten directly, same as any other status."""
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            goal = Goal.create("stuck goal")
            goal.status = "blocked"
            goal_storage.save_goal(session_dir, goal)
            session = _make_session(session_dir)
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
                sc.cmd_goal(session, "fresh goal")
            sc.io.print_info.assert_called_with("Goal set: fresh goal")
            loaded = goal_storage.load_goal(session_dir)
            assert loaded.objective == "fresh goal"
            assert loaded.status == "active"

    def test_can_set_new_goal_over_a_complete_one(self):
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            goal = Goal.create("done goal")
            goal.status = "complete"
            goal_storage.save_goal(session_dir, goal)
            session = _make_session(session_dir)
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
                sc.cmd_goal(session, "next goal")
            loaded = goal_storage.load_goal(session_dir)
            assert loaded.objective == "next goal"
            assert loaded.status == "active"

    def test_clear_removes_goal_file(self):
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            goal_storage.save_goal(session_dir, Goal.create("to be cleared"))
            session = _make_session(session_dir)
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
                sc.cmd_goal(session, "clear")
            assert goal_storage.load_goal(session_dir) is None

    def test_clear_archives_goal_to_history(self):
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            goal_storage.save_goal(session_dir, Goal.create("to be cleared"))
            session = _make_session(session_dir)
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
                sc.cmd_goal(session, "clear")

            history = goal_storage.load_goal_history(session_dir)
            assert len(history) == 1
            assert history[0]["objective"] == "to be cleared"

    def test_clear_updates_live_context(self):
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            goal_storage.save_goal(session_dir, Goal.create("to be cleared"))
            session = _make_session(session_dir)
            context = MagicMock()
            context.goal = Goal.create("to be cleared")
            fake_cache = {("agent", "/tmp/ws"): context}
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
                sc.cmd_goal(session, "clear")
            assert context.goal is None

    def test_set_goal_updates_live_context(self):
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session(session_dir)
            context = MagicMock()
            context.goal = None
            fake_cache = {("agent", "/tmp/ws"): context}
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
                sc.cmd_goal(session, "new objective")
            assert context.goal is not None
            assert context.goal.objective == "new objective"

    def test_overwriting_an_active_goal_resets_reminder_injected_flag(self):
        """Overwriting an active goal (already reminded once) with a new
        objective must reset reminder_injected -- Goal.create() always
        defaults it to False regardless of the outgoing goal's flag, so
        the new goal gets its own fresh hidden reminder on the next turn
        (see SiadaRunner._maybe_merge_goal_reminder)."""
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session(session_dir)
            old_goal = Goal.create("first goal")
            old_goal.reminder_injected = True  # simulate: already reminded once
            context = MagicMock()
            context.goal = old_goal
            fake_cache = {("agent", "/tmp/ws"): context}
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
                sc.cmd_goal(session, "second goal")

            assert context.goal.objective == "second goal"
            assert context.goal.reminder_injected is False
            loaded = goal_storage.load_goal(session_dir)
            assert loaded.objective == "second goal"
            assert loaded.reminder_injected is False

    def test_clear_discards_reminder_state_along_with_goal(self):
        """After /goal clear, context.goal is None and goal.json is gone --
        _maybe_merge_goal_reminder must become a pure no-op for this
        context (nothing left to gate on)."""
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session(session_dir)
            goal = Goal.create("to be cleared")
            goal.reminder_injected = True
            context = MagicMock()
            context.goal = goal
            fake_cache = {("agent", "/tmp/ws"): context}
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", fake_cache):
                sc.cmd_goal(session, "clear")

            assert context.goal is None
            assert goal_storage.load_goal(session_dir) is None

            from siada.services.siada_runner import SiadaRunner
            result = SiadaRunner._maybe_merge_goal_reminder(context, "next message")
            assert result == "next message"

    def test_multiple_overwrites_accumulate_history_in_order(self):

        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            session = _make_session(session_dir)
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
                sc.cmd_goal(session, "goal one")
                sc.cmd_goal(session, "goal two")
                sc.cmd_goal(session, "goal three")

            history = goal_storage.load_goal_history(session_dir)
            assert [h["objective"] for h in history] == ["goal one", "goal two"]
            # The third goal is still live, not yet archived.
            loaded = goal_storage.load_goal(session_dir)
            assert loaded.objective == "goal three"


class TestCmdGoalNoLiveContextYet:
    """BUGFIX regression coverage: /goal as the very first command in a
    fresh session.

    Before this fix, when /goal ran before any conversation turn had ever
    built a CodeAgentContext for this workspace (SiadaRunner._context_cache
    empty for this workspace), the new goal was written to goal.json on disk
    but NEVER attached to any context object. The SwitchEvent-triggered
    conversation turn that immediately followed then built a brand new
    context with context.goal defaulting to None, so
    turn_hooks.maybe_run_goal_verifier's `if goal is None: return result`
    guard silently no-op'd forever -- the verifier never ran and the goal
    status bar never advanced past "active", no matter how many real turns
    the agent took. See the BUGFIX comment in SlashCommands.cmd_goal.

    The fix stages the goal into session.state.pending_goal (the same
    stage-then-consume mechanism ResumeService already uses for a goal
    recovered from disk on session resume) so SiadaRunner._prepare_context_
    for_run() consumes it into context.goal as soon as the very next turn
    builds/prepares its context.
    """

    def test_set_new_goal_stages_pending_goal_when_no_context_exists(self):
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session = _make_session(Path(d))
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
                sc.cmd_goal(session, "analyze tool invocation")

            staged = session.state.pending_goal
            assert staged is not None
            assert staged.objective == "analyze tool invocation"
            assert staged.status == "active"

    def test_clear_drops_any_staged_pending_goal_when_no_context_exists(self):
        sc = _make_slash_commands()
        with tempfile.TemporaryDirectory() as d:
            session_dir = Path(d)
            goal_storage.save_goal(session_dir, Goal.create("to be cleared"))
            session = _make_session(session_dir)
            # Simulate a goal that was staged but never consumed yet.
            session.state.pending_goal = Goal.create("to be cleared")
            with patch("siada.services.siada_runner.SiadaRunner._context_cache", {}):
                sc.cmd_goal(session, "clear")

            assert session.state.pending_goal is None


"""
Integration regression tests for the refactored Controller (ACP input loop).

Covers the actual ``Controller.run()`` main loop plus its SwitchEvent /
keyboard-interrupt / /btw handling after the controller refactor extracted
``ControllerUI`` and ``TurnPolicy`` into separate modules.

Nothing here touches a real model, stdin, terminal or network:

* ``ControllerUI`` and ``TurnPolicy`` are mocked/faked at construction
  (``Controller.__init__`` instantiates them directly);
* the agent preload thread is stubbed and marked complete;
* the input stream is simulated through a fake ``InputOutput``;
* ``TurnFactory`` and the siadahub ``_ensure_*_ready`` joiners are replaced
  via ``sys.modules`` so the heavyweight turn/agents-SDK modules are never
  imported by the run loop.
"""

import signal
import sys
from contextlib import contextmanager
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest

# Import turn_policy first: it pulls in siada.session before turn.models /
# slash_commands, avoiding a circular import (checkpoint_tracker <->
# session_manager) that importing Controller first used to mask.
from siada.entrypoint.interaction.turn_policy import TurnPolicy  # noqa: F401
from siada.entrypoint.interaction.controller import Controller
from siada.io.io import BACKGROUND_WAKEUP_SENTINEL
from siada.support.slash_commands import SwitchEvent


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
class _SimulatedExit(SystemExit):
    """Raised by test doubles to end ``Controller.run()`` deterministically.

    Deriving from ``SystemExit`` means the loop's ``except Exception`` never
    swallows it, yet the ``finally`` block still runs exactly like a real
    process exit - leaving ``exit_reason == "normal"`` untouched.
    """


class _FakeIO:
    """Simulated InputOutput: a queue of canned inputs plus call recording."""

    def __init__(self, inputs=()):
        self.inputs = list(inputs)
        self.get_input_calls = []  # (display_rule, wakeup_event)
        self.info_lines = []
        self.error_lines = []
        self.acp_adapter = None

    def get_input(self, display_rule=False, wakeup_event=None):
        self.get_input_calls.append((display_rule, wakeup_event))
        if self.inputs:
            return self.inputs.pop(0)
        raise _SimulatedExit("simulated input stream exhausted")

    def print_info(self, message):
        self.info_lines.append(message)

    def print_error(self, exc):
        self.error_lines.append(exc)


class _FakeTurnPolicy:
    """Minimal TurnPolicy stand-in used by the run-loop tests.

    Mirrors the two Controller-facing behaviors of the real TurnPolicy:

    * ``start_session`` / ``end_session`` lifecycle recording, and
    * the once-only SessionEnd guard (real ``_session_end_fired`` flag), so a
      double ``end_session`` (interrupt path + run-loop finally) fires once.
    """

    def __init__(self):
        self.started_sessions = []
        self.ended = []  # list of (session, exit_reason)
        self._session_end_fired = False
        self.notes = []  # staged background sub-agent notes
        self.executed = []  # user_inputs fed to execute()
        self.user_initiated = []
        self.results = iter(())  # queued TurnOutput-like results

    def start_session(self, session):
        self.started_sessions.append(session)

    def end_session(self, session, exit_reason):
        if self._session_end_fired:
            return
        self._session_end_fired = True
        self.ended.append((session, exit_reason))

    def execute(self, turn, user_input, session, *, user_initiated=True):
        self.executed.append(user_input)
        self.user_initiated.append(user_initiated)
        try:
            return next(self.results)
        except StopIteration:
            raise _SimulatedExit(
                f"no more queued results after {len(self.executed)} turns"
            )

    def _drain_background_subtask_notes(self, session):
        notes = list(self.notes)
        self.notes = []
        return notes

    @staticmethod
    def _build_background_subtask_feedback(notes):
        return "BACKGROUND_FEEDBACK::" + "||".join(notes)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def _make_config(acp_mode=True, inputs=()):
    io = _FakeIO(inputs)
    config = SimpleNamespace(
        acp_mode=acp_mode,
        io=io,
        agent_name="test-agent",
        workspace="/workspace",
        model="initial-model",
        llm_config=SimpleNamespace(provider="test-provider", model_name="initial-model"),
        completer=None,
        enable_notification=False,
    )
    return config, io


def _make_session(session_id):
    return SimpleNamespace(session_id=session_id)


def _make_controller(
    config, slash_commands, session=None, shell_mode=False, active_monitor=False
):
    """Build a Controller with mocked ControllerUI / TurnPolicy / preload.

    Returns ``(controller, ui_mock, policy, monitor)``. ``monitor`` is a fake
    StdinInterruptMonitor when ``active_monitor`` is set (used by the /btw
    wiring test), otherwise None.
    """
    from contextlib import ExitStack

    ui = Mock()
    policy = _FakeTurnPolicy()
    monitor = None

    with ExitStack() as stack:
        stack.enter_context(
            patch("siada.entrypoint.interaction.controller.ControllerUI", return_value=ui)
        )
        stack.enter_context(
            patch("siada.entrypoint.interaction.controller.TurnPolicy", return_value=policy)
        )
        stack.enter_context(patch.object(Controller, "_start_preload_agent"))
        # __init__ registers self._release_cli_ownership with atexit; the
        # patched no-op keeps interpreter exit quiet (no logging to a closed
        # stream once pytest tears the capture handlers down).
        stack.enter_context(patch.object(Controller, "_release_cli_ownership"))
        if active_monitor:
            monitor = SimpleNamespace(handlers=[])
            monitor.set_btw_handler = monitor.handlers.append
            stack.enter_context(
                patch(
                    "siada.io.stdin_interrupt_monitor.is_monitor_active",
                    return_value=True,
                )
            )
            stack.enter_context(
                patch(
                    "siada.io.stdin_interrupt_monitor.get_stdin_monitor",
                    return_value=monitor,
                )
            )
        controller = Controller(
            config, slash_commands, shell_mode=shell_mode, session=session
        )

    # The preload thread was stubbed; mark preload complete so
    # wait_for_preload() returns immediately during the run loop.
    controller._preload_complete.set()
    controller._preload_success = True
    return controller, ui, policy, monitor


def _fake_turn_factory_module():
    mod = ModuleType("siada.entrypoint.interaction.turn.turn_factory")
    mod.TurnFactory = SimpleNamespace(
        create_turn=Mock(return_value=SimpleNamespace(kind="fake-turn"))
    )
    return mod


def _fake_siadahub_module():
    mod = ModuleType("siada.entrypoint.siadahub")
    mod._ensure_litellm_ready = Mock()
    mod._ensure_agents_ready = Mock()
    return mod


@contextmanager
def _run_loop_patches():
    """Mock every async/IO dependency Controller.run() imports lazily."""
    with patch.dict(
        sys.modules,
        {
            "siada.entrypoint.interaction.turn.turn_factory": _fake_turn_factory_module(),
            "siada.entrypoint.siadahub": _fake_siadahub_module(),
        },
    ), patch(
        "siada.tools.agent.subagent_async.register_session_wakeup"
    ), patch(
        "siada.tools.agent.subagent_async.unregister_session_wakeup"
    ):
        yield


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #
class TestConstructor:
    def test_rejects_non_acp_without_preload(self):
        """The refactored constructor refuses non-ACP configs up front."""
        config, _ = _make_config(acp_mode=False)
        with pytest.raises(ValueError, match="ACP terminal UI"):
            Controller(config, SimpleNamespace())


# --------------------------------------------------------------------------- #
# run() main loop
# --------------------------------------------------------------------------- #
class TestRunLifecycle:
    def test_run_invokes_policy_lifecycle_and_ui_close(self):
        """A single user turn drives start_session -> execute -> end_session
        and closes the UI in the finally block."""
        config, io = _make_config(inputs=["hello there"])
        session = _make_session("sess-lifecycle")
        ctrl, ui, policy, _ = _make_controller(
            config, SimpleNamespace(), session=session
        )
        policy.results = iter(
            [SimpleNamespace(output="plain reply", metadata={}, next_action=None)]
        )

        with _run_loop_patches():
            with pytest.raises(_SimulatedExit):
                ctrl.run()

        assert policy.started_sessions == [session]
        assert policy.ended == [(session, "normal")]
        assert policy.executed == ["hello there"]
        assert policy.user_initiated == [True]
        # Both input polls carried the controller's real wakeup event; the
        # second one exhausted the simulated stream and ended the loop.
        assert len(io.get_input_calls) == 2
        assert io.get_input_calls == [(False, ctrl._bg_wakeup_event)] * 2
        ui.register_notification_handler.assert_called_once()
        ui.set_processing.assert_any_call(True)
        ui.close.assert_called_once()


class TestRunLoopPriorityAndWakeup:
    def test_pending_retry_not_overwritten_by_concurrent_background_event(self):
        """A queued retry/goal continuation takes precedence: a background
        sub-agent wakeup that fires while the retry is pending must NOT
        overwrite it - the note is injected only after the retry turn."""
        config, io = _make_config(inputs=["first user message"])
        session = _make_session("sess-retry-priority")
        ctrl, ui, policy, _ = _make_controller(
            config, SimpleNamespace(), session=session
        )
        executed = []

        origins = []

        def fake_execute(turn, user_input, session, *, user_initiated=True):
            executed.append(user_input)
            origins.append(user_initiated)
            if len(executed) == 1:
                # A background sub-agent completes right as turn 1 ends.
                ctrl._on_background_subtask_wakeup()
                return SimpleNamespace(
                    output=SwitchEvent(ai_analysis_prompt="AUTO-RETRY-PROMPT"),
                    metadata={},
                    next_action=None,
                )
            if len(executed) == 2:
                return SimpleNamespace(
                    output="retry finished", metadata={}, next_action=None
                )
            raise _SimulatedExit()

        policy.execute = fake_execute
        policy.notes = ["bg-result-note"]

        with _run_loop_patches():
            with pytest.raises(_SimulatedExit):
                ctrl.run()

        # The queued retry continuation ran BEFORE the background note; the
        # concurrent wakeup must never displace `pending_input`.
        assert executed == [
            "first user message",
            "AUTO-RETRY-PROMPT",
            "BACKGROUND_FEEDBACK::bg-result-note",
        ]
        assert "bg-result-note" in executed[2]
        assert origins == [True, False, False]
        # Only the first turn came from the user; the rest were loop-internal.
        assert len(io.get_input_calls) == 1

    def test_wakeup_sentinel_triggers_background_result_injection(self):
        """When the input poll is woken up (sentinel returned), the staged
        background sub-agent results are injected as the next turn."""
        config, io = _make_config()
        session = _make_session("sess-sentinel")
        ctrl, ui, policy, _ = _make_controller(
            config, SimpleNamespace(), session=session
        )
        policy.notes = ["bg-sentinel-note"]

        seen_wakeup_events = []

        def fake_get_input(display_rule=False, wakeup_event=None):
            seen_wakeup_events.append(wakeup_event)
            # Background task completes while the input poll is blocked.
            ctrl._on_background_subtask_wakeup()
            return BACKGROUND_WAKEUP_SENTINEL

        io.get_input = fake_get_input

        executed = []

        def fake_execute(turn, user_input, session, *, user_initiated=True):
            executed.append(user_input)
            assert user_initiated is False
            raise _SimulatedExit()

        policy.execute = fake_execute

        with _run_loop_patches():
            with pytest.raises(_SimulatedExit):
                ctrl.run()

        assert seen_wakeup_events == [ctrl._bg_wakeup_event]
        assert executed == ["BACKGROUND_FEEDBACK::bg-sentinel-note"]
        assert "bg-sentinel-note" in executed[0]

    def test_actual_user_input_after_internal_turn_restores_user_origin(self):
        config, _ = _make_config(inputs=["first message", "human follow-up"])
        ctrl, _, policy, _ = _make_controller(
            config, SimpleNamespace(), session=_make_session("sess-origin"),
        )
        policy.results = iter([
            SimpleNamespace(output=SwitchEvent(ai_analysis_prompt="auto feedback")),
            SimpleNamespace(output="auto reply"),
            SimpleNamespace(output="human reply"),
        ])

        with _run_loop_patches(), pytest.raises(_SimulatedExit):
            ctrl.run()

        assert policy.executed == ["first message", "auto feedback", "human follow-up"]
        assert policy.user_initiated == [True, False, True]


# --------------------------------------------------------------------------- #
# SwitchEvent handling
# --------------------------------------------------------------------------- #
class TestSwitchEvent:
    def test_model_swaps_config_and_rebuilds_llm_config(self):
        config, _ = _make_config()
        ctrl, ui, _, _ = _make_controller(
            config, SimpleNamespace(), session=_make_session("sess-model")
        )
        with patch.object(Controller, "_update_llm_config_for_model") as update:
            result = ctrl._handle_switch_event(SwitchEvent(model="gpt-5.2"))
        assert result is None
        assert ctrl.config.model == "gpt-5.2"
        update.assert_called_once_with("gpt-5.2")
        ui.show_announcements.assert_called_once()

    def test_goal_builds_pending_input(self):
        """ai_analysis_prompt events become the next-loop pending input; the
        /goal variant keeps its "goal_command" flag for the wrapped payload."""
        config, _ = _make_config()
        ctrl, ui, _, _ = _make_controller(
            config, SimpleNamespace(), session=_make_session("sess-goal")
        )

        pending = ctrl._handle_switch_event(
            SwitchEvent(ai_analysis_prompt="analyze the flaky test")
        )
        assert pending == "analyze the flaky test"

        goal_pending = ctrl._handle_switch_event(
            SwitchEvent(
                ai_analysis_prompt="add controller regression tests",
                goal_command=True,
            )
        )
        assert isinstance(goal_pending, list) and len(goal_pending) == 1
        text = goal_pending[0]["content"][0]["text"]
        assert text == "<user_input>/goal add controller regression tests</user_input>"
        # The ai_analysis_prompt branch returns early: no announcements.
        ui.show_announcements.assert_not_called()

    def test_shell_enables_shell_mode(self):
        config, _ = _make_config()
        ctrl, ui, _, _ = _make_controller(
            config, SimpleNamespace(), session=_make_session("sess-shell")
        )
        assert ctrl.shell_mode is False
        result = ctrl._handle_switch_event(SwitchEvent(shell=True))
        assert result is None
        assert ctrl.shell_mode is True
        ui.show_announcements.assert_called_once()

    def test_clear_swaps_session_and_replaces_wakeup_registration(self):
        """/clear creates a fresh session and moves the background-subtask
        wakeup registration from the old session to the new one."""
        old_session = _make_session("sess-old")
        new_session = _make_session("sess-new")
        config, io = _make_config()
        ctrl, ui, _, _ = _make_controller(
            config, SimpleNamespace(), session=old_session
        )

        registered, unregistered = [], []
        fake_sm = ModuleType("siada.session.session_manager")
        fake_sm.RunningSessionManager = SimpleNamespace(
            create_session=Mock(return_value=new_session)
        )
        with patch.dict(sys.modules, {"siada.session.session_manager": fake_sm}), patch(
            "siada.tools.agent.subagent_async.register_session_wakeup",
            side_effect=lambda session_id, callback: registered.append(session_id),
        ), patch(
            "siada.tools.agent.subagent_async.unregister_session_wakeup",
            side_effect=lambda session_id: unregistered.append(session_id),
        ):
            ctrl._register_background_wakeup(old_session)
            result = ctrl._handle_switch_event(SwitchEvent(clear=True))

        assert result is None
        assert ctrl.session is new_session
        assert unregistered == ["sess-old"]
        assert registered == ["sess-old", "sess-new"]
        assert ctrl._bg_wakeup_registered_ids == {"sess-new"}
        assert ctrl._bg_wakeup_event.is_set() is False
        assert io.info_lines[-1] == "New task session created"
        ui.reset_history_state.assert_called_once()


# --------------------------------------------------------------------------- #
# Interrupt + /btw interception
# --------------------------------------------------------------------------- #
class TestInterruptAndBtw:
    def test_keyboard_interrupt_double_press_ends_once_without_stdout_noise(
        self, capsys
    ):
        """Two Ctrl+C in a row take the force-exit path: no ANSI/raw text on
        stdout, SessionEnd fires exactly once (once-only guard), and the MCP
        shutdown is skipped when the service is not initialized."""
        config, io = _make_config()
        session = _make_session("sess-interrupt")
        ctrl, ui, policy, _ = _make_controller(
            config, SimpleNamespace(), session=session
        )
        io.get_input = Mock(side_effect=KeyboardInterrupt())

        fake_mcp = ModuleType("siada.services.mcp.manager_service")
        fake_mcp._mcp_manager_service = SimpleNamespace(
            is_initialized=False, shutdown=Mock()
        )

        def fake_exit(code):
            raise SystemExit(code)

        with patch.dict(
            sys.modules, {"siada.services.mcp.manager_service": fake_mcp}
        ), patch("signal.signal") as set_sigint, patch(
            "sys.exit", side_effect=fake_exit
        ):
            with pytest.raises(SystemExit):
                ctrl.run()

        # First Ctrl+C was recorded; the second triggered the force-exit path.
        assert policy.ended == [(session, "interrupt")]
        ui.send_cancelled.assert_called_once_with(
            "Execution interrupted by user (Ctrl+C)"
        )
        ui.close.assert_called()
        set_sigint.assert_called_once_with(signal.SIGINT, signal.SIG_IGN)
        fake_mcp._mcp_manager_service.shutdown.assert_not_called()

        out = capsys.readouterr().out
        assert "\x1b" not in out  # no ANSI escape sequences
        assert "KeyboardInterrupt" not in out

    def test_btw_intercept_dispatches_side_question_without_touching_main_turn(
        self,
    ):
        """The /btw handler registered with the stdin monitor runs cmd_btw on
        the side fork and never engages the main input/turn machinery."""
        slash_commands = SimpleNamespace(cmd_btw=Mock())
        config, io = _make_config()
        session = _make_session("sess-btw")
        ctrl, ui, policy, monitor = _make_controller(
            config, slash_commands, session=session, active_monitor=True
        )
        assert monitor is not None
        assert len(monitor.handlers) == 1
        handler = monitor.handlers[0]
        assert handler == ctrl._handle_btw_intercept

        handler("what is this function doing?")
        slash_commands.cmd_btw.assert_called_once_with(
            session, "what is this function doing?"
        )

        # The main loop / session machinery was never engaged.
        ui.register_notification_handler.assert_not_called()
        ui.set_processing.assert_not_called()
        assert policy.started_sessions == []
        assert policy.executed == []
        assert io.get_input_calls == []

def test_interactive_entrypoint_rejects_legacy_ui_before_constructing_controller():
    from siada.entrypoint import siadahub

    io = Mock()
    with patch.object(siadahub, "Controller") as constructor:
        assert siadahub._run_interactive(
            SimpleNamespace(), None, SimpleNamespace(acp_mode=False), Mock(), io, None,
        ) == 1
    constructor.assert_not_called()
    assert "--prompt" in io.print_error.call_args.args[0]


@pytest.mark.parametrize("login_error, run_result", [(1, None), (None, 1), (None, 0)])
def test_interactive_entrypoint_cleans_failed_login_and_preserves_exit_code(
    login_error, run_result,
):
    from siada.entrypoint import siadahub

    controller = Mock()
    controller.run.return_value = run_result
    with patch.object(siadahub, "Controller", return_value=controller), patch.object(
        siadahub, "_has_stored_credentials", return_value=False,
    ), patch.object(siadahub, "_apply_login", return_value=login_error), patch.object(
        siadahub, "_try_restore_session", return_value=None,
    ), patch.object(siadahub, "_ensure_login_ready", return_value=None), patch.object(
        siadahub, "_ensure_agents_ready",
    ):
        result = siadahub._run_interactive(
            SimpleNamespace(acp=True), Mock(), SimpleNamespace(acp_mode=True),
            Mock(), Mock(), None,
        )
    assert result == (login_error if login_error is not None else run_result)
    if login_error is not None:
        controller.ui.close.assert_called_once()
        controller.run.assert_not_called()
    else:
        controller.run.assert_called_once()


def test_interactive_cold_resume_announces_only_the_restored_session():
    """--resume must not paint a banner for the disposable startup session."""
    from siada.entrypoint import siadahub

    events = []
    session = SimpleNamespace(session_id="startup-session")
    history = SimpleNamespace(items=["saved-message"])
    controller = Mock()
    controller.run.return_value = 0
    controller.show_announcements.side_effect = lambda: events.append(
        ("banner", session.session_id)
    )
    commands = Mock()
    commands._send_history_to_ui.side_effect = lambda items: events.append(
        ("history", session.session_id, items)
    )

    def restore(args, current_session, io):
        assert args.resume == "saved-session"
        assert current_session is session
        events.append(("restore", session.session_id))
        session.session_id = "saved-session"
        return True, history

    with patch.object(siadahub, "Controller", return_value=controller), patch.object(
        siadahub, "_has_stored_credentials", return_value=False,
    ), patch.object(siadahub, "_apply_login", return_value=None), patch.object(
        siadahub, "_try_restore_session", side_effect=restore,
    ), patch.object(siadahub, "_ensure_login_ready", return_value=None), patch.object(
        siadahub, "_ensure_agents_ready",
    ):
        result = siadahub._run_interactive(
            SimpleNamespace(acp=True, resume="saved-session"),
            session, SimpleNamespace(acp_mode=True), commands, Mock(), None,
        )

    assert result == 0
    assert events == [
        ("restore", "startup-session"),
        ("banner", "saved-session"),
        ("history", "saved-session", history.items),
    ]
    controller.show_announcements.assert_called_once_with()
    commands._push_resumed_goal_state_to_ui.assert_called_once_with(session)


def test_startup_error_still_closes_ui_and_ends_session():
    config, _ = _make_config()
    session = _make_session("startup-failure")
    ctrl, ui, policy, _ = _make_controller(config, SimpleNamespace(), session=session)
    ui.register_notification_handler.side_effect = RuntimeError("registration failed")
    with _run_loop_patches(), pytest.raises(RuntimeError, match="registration failed"):
        ctrl.run()
    ui.close.assert_called_once()
    assert policy.ended == [(session, "error")]


def test_sdk_initialization_precedes_preload_and_title_generation():
    config, _ = _make_config(inputs=["hello"])
    ctrl, ui, _, _ = _make_controller(config, SimpleNamespace(), session=_make_session("order"))
    order = Mock()
    with _run_loop_patches():
        hub = sys.modules["siada.entrypoint.siadahub"]
        order.attach_mock(hub._ensure_litellm_ready, "litellm")
        order.attach_mock(hub._ensure_agents_ready, "agents")
        order.attach_mock(ui.send_session_title_async, "title")
        with patch.object(ctrl, "wait_for_preload") as preload:
            order.attach_mock(preload, "preload")
            with pytest.raises(_SimulatedExit):
                ctrl.run()
    assert [entry[0] for entry in order.mock_calls] == ["litellm", "agents", "preload", "title"]


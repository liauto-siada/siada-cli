"""Headless execution consumes the shared streamed turn and continuation policy."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agents import RawResponsesStreamEvent, ReasoningItem
from openai.types.responses import (
    ResponseCreatedEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseTextDeltaEvent,
)

from siada.entrypoint import siadahub
from siada.entrypoint.interaction.console_progress import ConsoleProgressPresenter
from siada.entrypoint.interaction.nointeractive_controller import NoInteractiveController
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.entrypoint.interaction.turn.models import (
    RETRY_NOTICES, RETRY_REASON_REPETITIVE_STREAM, RETRY_REASON_TRUNCATED_REASONING_ONLY,
)
from siada.entrypoint.interaction.turn_policy import TurnPolicy
from siada.services.file_session import FileSession
from siada.services.siada_runner import SiadaRunner
from siada.session.session_models import RunningSession


class SyntheticStream:
    """Expose final output only after all synthetic events have been consumed."""

    def __init__(self, output="finished", *, reasoning_only=False, repetitive=False, error=None):
        self.output = output
        self.reasoning_only = reasoning_only
        self.repetitive = repetitive
        self.error = error
        self.final_output = None
        self.new_items = []
        self.is_complete = False
        self.cancel = Mock(side_effect=self._cancel)
        self.closed = False
        self.run_loop_task = None

    def _cancel(self):
        self.is_complete = True

    async def stream_events(self):
        try:
            yield RawResponsesStreamEvent(data=ResponseCreatedEvent.model_construct(
                type="response.created", response=None,
            ))
            if self.reasoning_only or self.repetitive:
                delta = "Synthetic reasoning. " * 12 if self.repetitive else "thinking"
                yield RawResponsesStreamEvent(data=ResponseReasoningSummaryTextDeltaEvent.model_construct(
                    type="response.reasoning_summary_text.delta", delta=delta,
                ))
            else:
                yield RawResponsesStreamEvent(data=ResponseTextDeltaEvent.model_construct(
                    type="response.output_text.delta", delta="intermediate text, not the final answer",
                ))
            if self.error is not None:
                raise self.error
            if self.reasoning_only:
                self.new_items = [ReasoningItem(agent=Mock(), raw_item={})]
            self.final_output = self.output
            self.is_complete = True
        finally:
            self.closed = True


@pytest.fixture
def headless(tmp_path, monkeypatch):
    monkeypatch.setattr(siadahub, "_ensure_litellm_ready", lambda: None)
    monkeypatch.setattr(siadahub, "_ensure_agents_ready", lambda: None)
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda session: None)
    io = SimpleNamespace(
        print=Mock(), print_error=Mock(), print_warning=Mock(),
        acp_enabled=False, _pending_image_paths=[],
        get_input=Mock(side_effect=AssertionError("Headless execution must not read user input")),
    )
    config = RunningConfig(
        llm_config=SimpleNamespace(model_name="synthetic"), io=io,
        workspace=str(tmp_path), agent_name="coder", interactive=False,
        memory_enabled=False,
    )
    session = RunningSession(config, session_id="synthetic-headless")
    session.state.openai_session = FileSession(session.session_id, tmp_path)
    yield config, session


@pytest.fixture
def headless_goal_console(headless, monkeypatch):
    from siada.entrypoint.interaction import console_progress
    from siada.services.goal import turn_hooks

    config, session = headless
    config.console_output = True
    messages = []
    presenter = console_progress.ConsoleProgressPresenter
    monkeypatch.setattr(console_progress, "ConsoleProgressPresenter", lambda: presenter(messages.append))
    monkeypatch.setattr(turn_hooks, "_maybe_show_completion_notification", lambda *args: None)
    config.io.print = messages.append
    config.io.print_error = messages.append
    return config, session, messages


@pytest.fixture
def headless_goal_prompt(headless_goal_console, monkeypatch):
    from siada.support.slash_commands import SlashCommands

    config, session, messages = headless_goal_console
    config.io.print_info = messages.append
    config.io.acp_adapter = None
    commands = SlashCommands.__new__(SlashCommands)
    commands.io = config.io
    commands.hook_runner = None
    commands.cmd_goal = Mock(wraps=commands.cmd_goal)

    def run_command(session, text):
        parts = text.strip().split(maxsplit=1)
        assert parts[0] == "/goal"
        return commands.cmd_goal(session, parts[1] if len(parts) > 1 else "")

    commands.run = Mock(side_effect=run_command)
    current = {"context": None}
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: current["context"])
    return config, session, messages, commands, current


@pytest.mark.parametrize("interrupt", [False, True])
def test_explicit_goal_prompt_activates_and_prints_before_first_conversation(
    headless_goal_prompt, monkeypatch, interrupt,
):
    import threading

    from siada.entrypoint.interaction import console_progress
    from siada.entrypoint.interaction.turn.models import TurnOutput
    from siada.entrypoint.interaction.turn_input import build_terminal_pending_input
    from siada.services.goal import goal_storage, verifier
    from siada.services.goal.models import GoalVerdict

    config, session, messages, commands, current = headless_goal_prompt
    started = threading.Event()

    def write(message):
        messages.append(message)
        if message.startswith("[Goal started]"):
            started.set()

    monkeypatch.setattr(console_progress, "ConsoleProgressPresenter", lambda: ConsoleProgressPresenter(write))
    prompt = "/goal 完成合成测试目标"

    async def execute(self, turn_input):
        goal = session.state.pending_goal
        assert goal is not None, "The explicit /goal prompt was not dispatched"
        assert goal.objective == "完成合成测试目标"
        assert await asyncio.to_thread(started.wait, 2), "Goal start was not visible before work"
        assert turn_input.use_input == build_terminal_pending_input(goal.objective, True)
        current["context"] = SimpleNamespace(goal=goal)
        session.state.pending_goal = None
        if interrupt:
            raise asyncio.CancelledError()
        return TurnOutput(output="goal answer", metadata={}, next_action=None)

    run = AsyncMock(side_effect=execute)
    monkeypatch.setattr(ConversationTurn, "execute", lambda self, data: run(self, data))
    check = AsyncMock(return_value=GoalVerdict(passed=True, reason="Synthetic goal passed"))
    monkeypatch.setattr(verifier, "run_goal_verification", check)
    monkeypatch.setattr(siadahub, "_try_restore_session", lambda *args: None)
    monkeypatch.setattr(siadahub, "_apply_login", lambda *args: None)
    monkeypatch.setattr("siada.services.quota_service.get_quota_usage", lambda: None)
    from siada.entrypoint.args_parser.args import get_parser
    args = get_parser(default_config_files=[], git_root=None).parse_args(["--prompt", prompt])

    assert siadahub._run_noninteractive(
        args, session, config, config.io, config.llm_config, commands,
    ) == (130 if interrupt else 0)

    commands.cmd_goal.assert_called_once_with(session, "完成合成测试目标")
    run.assert_awaited_once()
    saved = goal_storage.load_goal(session.openai_session.session_folder)
    assert saved.status == ("paused" if interrupt else "complete")
    goal_messages = [message for message in messages if message.startswith("[Goal ")]
    assert goal_messages[0].startswith("[Goal started]")
    assert goal_messages[-1].startswith("[Goal paused]" if interrupt else "[Goal achieved]")
    if interrupt:
        check.assert_not_awaited()
    else:
        check.assert_awaited_once()
    config.io.get_input.assert_not_called()


def test_explicit_goal_prompt_continues_without_recreating_goal(headless_goal_prompt, monkeypatch):
    from siada.entrypoint.interaction.turn.models import TurnOutput
    from siada.services.goal import goal_storage, verifier
    from siada.services.goal.models import GoalVerdict

    config, session, messages, commands, current = headless_goal_prompt

    async def execute(self, turn_input):
        if current["context"] is None:
            assert session.state.pending_goal is not None
            current["context"] = SimpleNamespace(goal=session.state.pending_goal)
            session.state.pending_goal = None
        return TurnOutput(output="finished goal", metadata={}, next_action=None)

    run = AsyncMock(side_effect=execute)
    monkeypatch.setattr(ConversationTurn, "execute", lambda self, data: run(self, data))
    check = AsyncMock(side_effect=[
        GoalVerdict(passed=False, reason="One check is missing", nextAction="Run the missing check"),
        GoalVerdict(passed=True, reason="All checks passed"),
    ])
    monkeypatch.setattr(verifier, "run_goal_verification", check)

    assert NoInteractiveController(config, session, commands).run(" /goal /goal is literal objective text ") == 0

    commands.cmd_goal.assert_called_once_with(session, "/goal is literal objective text")
    assert run.await_count == check.await_count == 2
    goal = goal_storage.load_goal(session.openai_session.session_folder)
    assert goal.objective == "/goal is literal objective text"
    assert goal.turns == len(goal.verification_results) == 2
    assert messages[-1] == "finished goal"


@pytest.mark.parametrize("prompt, exit_code", [("/goal", 1), ("/goal   ", 1), ("/goal clear", 0), (" /goal CLEAR ", 0)])
def test_goal_control_prompt_does_not_call_the_model(headless_goal_prompt, monkeypatch, prompt, exit_code):
    config, session, messages, commands, current = headless_goal_prompt
    run = AsyncMock(side_effect=AssertionError("Goal control commands must not call the model"))
    monkeypatch.setattr(ConversationTurn, "execute", run)

    assert NoInteractiveController(config, session, commands).run(prompt) == exit_code

    commands.run.assert_called_once()
    run.assert_not_called()
    config.io.get_input.assert_not_called()


def test_goal_prompt_without_prebuilt_commands_uses_real_dispatcher(headless_goal_console, monkeypatch):
    from siada.entrypoint.interaction.turn.models import TurnOutput
    from siada.services.goal import goal_storage, verifier
    from siada.services.goal.models import GoalVerdict
    from siada.services.plugins.plugin_loader import PluginLoader
    from siada.support.slash_commands import SlashCommands

    config, session, messages = headless_goal_console
    config.io.print_info = messages.append
    config.io.acp_adapter = None
    monkeypatch.setattr(PluginLoader, "load_all", lambda self: [])
    monkeypatch.setattr(SlashCommands, "get_commands", lambda self, session=None: ["/goal"])
    current = {"context": None}
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: current["context"])

    async def execute(self, turn_input):
        assert session.state.pending_goal.objective == "Create the first synthetic goal"
        current["context"] = SimpleNamespace(goal=session.state.pending_goal)
        session.state.pending_goal = None
        return TurnOutput(output="fresh goal answer", metadata={}, next_action=None)

    monkeypatch.setattr(ConversationTurn, "execute", execute)
    monkeypatch.setattr(verifier, "run_goal_verification", AsyncMock(return_value=GoalVerdict(passed=True, reason="Verified")))

    assert NoInteractiveController(config, session).run("/goal Create the first synthetic goal") == 0

    assert goal_storage.load_goal(session.openai_session.session_folder).status == "complete"
    assert any(message.startswith("[Goal started]") for message in messages)
    assert messages[-1] == "fresh goal answer"


def test_goal_creation_failure_does_not_start_model_or_report_success(headless_goal_console, monkeypatch):
    from siada.services.goal import goal_storage
    from siada.services.plugins.plugin_loader import PluginLoader
    from siada.support.slash_commands import SlashCommands

    config, session, messages = headless_goal_console
    config.io.print_info = messages.append
    config.io.acp_adapter = None
    monkeypatch.setattr(PluginLoader, "load_all", lambda self: [])
    monkeypatch.setattr(SlashCommands, "get_commands", lambda self, session=None: ["/goal"])
    monkeypatch.setattr(goal_storage, "save_goal", Mock(side_effect=OSError("Synthetic storage failure")))
    run = AsyncMock(side_effect=AssertionError("A failed goal must not start work"))
    monkeypatch.setattr(ConversationTurn, "execute", run)

    assert NoInteractiveController(config, session).run("/goal Create a goal") == 1

    assert any("Synthetic storage failure" in message for message in messages)
    run.assert_not_called()


def test_default_execution_drains_stream_and_prints_only_final_output(headless, monkeypatch):
    config, session = headless
    result = SyntheticStream()
    run = AsyncMock(return_value=result)
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    render = Mock(side_effect=AssertionError("Headless execution must not render deltas"))
    monkeypatch.setattr(ConversationTurn, "_live_incremental_response", render)
    assert NoInteractiveController(config, session).run("original task") == 0
    assert run.await_args.kwargs["stream"] is True
    assert run.await_args.kwargs["session"] is session
    assert "original task" in run.await_args.kwargs["user_input"]
    assert result.is_complete and result.closed
    config.io.print.assert_called_once_with("finished")
    config.io.get_input.assert_not_called()
    render.assert_not_called()
    assert not hasattr(ConversationTurn, "_dedicated_loop")


@pytest.mark.parametrize("reason", [RETRY_REASON_TRUNCATED_REASONING_ONLY, RETRY_REASON_REPETITIVE_STREAM])
def test_shared_policy_continues_incomplete_responses_without_user_input(headless, monkeypatch, reason):
    config, session = headless
    repetitive = reason == RETRY_REASON_REPETITIVE_STREAM
    if repetitive:
        config.llm_config.model_name = "synthetic-deepseek-v4-flash"
    interrupted = SyntheticStream("", reasoning_only=not repetitive, repetitive=repetitive)
    final = SyntheticStream("recovered answer")
    run = AsyncMock(side_effect=[interrupted, final])
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    assert NoInteractiveController(config, session).run("original task") == 0
    assert run.await_count == 2
    assert all(item.kwargs["stream"] is True for item in run.await_args_list)
    assert RETRY_NOTICES[reason] in run.await_args.kwargs["user_input"]
    assert interrupted.closed and final.closed
    if repetitive:
        interrupted.cancel.assert_called_once()
    config.io.print.assert_called_once_with("recovered answer")
    config.io.get_input.assert_not_called()


def test_retry_exhaustion_is_failure_not_an_empty_success(headless, monkeypatch):
    config, session = headless
    results = [SyntheticStream("", reasoning_only=True) for _ in range(TurnPolicy._MAX_AUTO_RETRIES + 1)]
    run = AsyncMock(side_effect=results)
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    assert NoInteractiveController(config, session).run("task") == 1
    assert run.await_count == len(results)
    assert all(result.closed for result in results)
    config.io.print.assert_not_called()
    assert "after automatic retries" in config.io.print_error.call_args.args[0]


@pytest.mark.parametrize("failure", ["no_next_action", "exhausted", "system_error", "crashed"])
def test_blocked_goal_reports_failure_and_nonzero_exit(headless, monkeypatch, failure):
    from siada.entrypoint.interaction import console_progress
    from siada.entrypoint.interaction.turn.models import TurnOutput
    from siada.foundation.execution_progress import publish_execution_progress
    from siada.services.goal.models import Goal, GoalVerdict, GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS
    from siada.services.goal import goal_storage, verifier

    config, session = headless
    goal = Goal.create("Finish the synthetic goal")
    goal.consecutive_system_errors = GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS - 1
    context = SimpleNamespace(goal=goal, goal_max_turns=1)
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: context)
    check = AsyncMock(return_value=GoalVerdict(
        passed=False, reason="Synthetic checks did not pass",
        nextAction="" if failure == "no_next_action" else "Fix the synthetic checks",
        systemError=failure == "system_error",
    ))
    if failure == "crashed":
        check.side_effect = RuntimeError("Synthetic verifier crashed")
    monkeypatch.setattr(verifier, "run_goal_verification", check)
    messages = []
    presenter = console_progress.ConsoleProgressPresenter
    monkeypatch.setattr(console_progress, "ConsoleProgressPresenter", lambda: presenter(messages.append))
    config.io.print = messages.append
    config.io.print_error = messages.append
    config.console_output = True
    ended = AsyncMock()
    monkeypatch.setattr(TurnPolicy, "end_session", ended)

    async def execute(*args, **kwargs):
        publish_execution_progress("progress before verification")
        return TurnOutput(output="partial model answer", metadata={"original": True}, next_action=None)

    monkeypatch.setattr(ConversationTurn, "execute", execute)
    assert NoInteractiveController(config, session).run("Continue the goal") == 1
    assert goal.status == "blocked"
    assert goal_storage.load_goal(session.openai_session.session_folder).status == "blocked"
    assert messages[0].startswith("[Goal started]")
    verifying_index = next(i for i, message in enumerate(messages) if message.startswith("[Goal verifying]"))
    blocked_index = next(i for i, message in enumerate(messages) if message.startswith("[Goal blocked]"))
    assert messages.index("progress before verification") < verifying_index < blocked_index
    assert messages[-2] == "partial model answer"
    assert any("Goal not achieved" in message and "Finish the synthetic goal" in message for message in messages)
    assert "completed" not in [call.args[-1] for call in ended.call_args_list]
    check.assert_awaited_once()


def test_forced_goal_verifier_error_retries_real_controller_without_more_user_input(headless, monkeypatch):
    from siada.entrypoint.interaction.turn.models import TurnOutput
    from siada.services.goal import goal_storage, verifier
    from siada.services.goal.models import Goal, GoalVerdict, GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS

    config, session = headless
    config.enable_notification = False
    goal = Goal.create("Complete the synthetic failure-injection goal")
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: SimpleNamespace(goal=goal))
    monkeypatch.setenv("SIADA_GOAL_VERIFIER_FORCE_ERROR", "1")
    judge = AsyncMock(return_value=GoalVerdict(passed=True, reason="Synthetic normal verdict"))
    monkeypatch.setattr(verifier, "verify_goal_with_context", judge)
    execute = AsyncMock(return_value=TurnOutput(output="Synthetic completed work", metadata={}, next_action=None))
    monkeypatch.setattr(ConversationTurn, "execute", execute)

    assert NoInteractiveController(config, session).run("Pursue the synthetic goal") == 1
    assert execute.call_count == GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS
    assert execute.call_args_list[0].args[0].use_input == "Pursue the synthetic goal"
    assert "SIADA_GOAL_VERIFIER_FORCE_ERROR=1" in execute.call_args_list[1].args[0].use_input
    assert goal.status == "blocked"
    assert goal.turns == GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS
    assert goal.consecutive_failures == 0
    records = goal_storage.load_goal(session.openai_session.session_folder).verification_results
    assert [record["continuing"] for record in records] == [True, False]
    assert all(record["outcome"] == "system_error" for record in records)
    assert all("SIADA_GOAL_VERIFIER_FORCE_ERROR=1" in record["reason"] for record in records)
    config.io.get_input.assert_not_called()
    judge.assert_not_awaited()


@pytest.mark.parametrize("status", ["complete", None])
def test_unverified_goal_state_does_not_fail_ordinary_prompt(headless, monkeypatch, status):
    from siada.entrypoint.interaction.turn.models import TurnOutput
    from siada.services.goal.models import Goal

    config, session = headless
    goal = Goal.create("Previous synthetic goal") if status is not None else None
    if goal is not None:
        goal.status = status
    context = SimpleNamespace(goal=goal)
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: context)
    monkeypatch.setattr(
        ConversationTurn, "execute",
        AsyncMock(return_value=TurnOutput(output="ordinary answer", metadata={}, next_action=None)),
    )
    assert NoInteractiveController(config, session).run("A new task") == 0
    config.io.print.assert_called_once_with("ordinary answer")
    config.io.print_error.assert_not_called()


def test_paused_goal_resumes_and_is_verified_on_ordinary_prompt(headless, monkeypatch):
    """A goal paused by an interruption reacts to the next user prompt.

    Pausing must not silently disable goal mode: the user's new message
    resumes the accumulated goal and ordinary verification runs again.
    """
    from siada.entrypoint.interaction.turn.models import TurnOutput
    from siada.services.goal import verifier
    from siada.services.goal.models import Goal, GoalVerdict

    config, session = headless
    goal = Goal.create("Synthetic interrupted goal")
    goal.set_status("paused")
    context = SimpleNamespace(goal=goal)
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: context)
    judge = AsyncMock(return_value=GoalVerdict(passed=True, reason="Verified after resume"))
    monkeypatch.setattr(verifier, "run_goal_verification", judge)
    monkeypatch.setattr(
        ConversationTurn, "execute",
        AsyncMock(return_value=TurnOutput(output="ordinary answer", metadata={}, next_action=None)),
    )

    assert NoInteractiveController(config, session).run("A new task") == 0
    assert goal.status == "complete"
    judge.assert_awaited_once()


def test_verified_goal_completion_exits_successfully(headless, monkeypatch):
    from siada.entrypoint.interaction.turn.models import TurnOutput
    from siada.services.goal import verifier
    from siada.services.goal.models import Goal, GoalVerdict

    config, session = headless
    goal = Goal.create("Finish the synthetic goal")
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: SimpleNamespace(goal=goal))
    monkeypatch.setattr(verifier, "run_goal_verification", AsyncMock(return_value=GoalVerdict(passed=True, reason="Verified")))
    monkeypatch.setattr(
        ConversationTurn, "execute",
        AsyncMock(return_value=TurnOutput(output="complete answer", metadata={}, next_action=None)),
    )
    assert NoInteractiveController(config, session).run("Continue the goal") == 0
    assert goal.status == "complete"
    config.io.print.assert_called_once_with("complete answer")
    config.io.print_error.assert_not_called()


@pytest.mark.parametrize("system_error", [False, True])
def test_goal_lifecycle_is_visible_during_verification_and_continuation(
    headless_goal_console, monkeypatch, system_error,
):
    import threading

    from siada.entrypoint.interaction import console_progress
    from siada.entrypoint.interaction.turn.models import TurnOutput
    from siada.services.goal import goal_storage, verifier
    from siada.services.goal.models import Goal, GoalVerdict

    config, session, messages = headless_goal_console
    goal = Goal.create("Finish the synthetic console goal")
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: SimpleNamespace(goal=goal))
    verifying_visible = threading.Event()
    presenter = ConsoleProgressPresenter

    def write(message):
        messages.append(message)
        if message.startswith("[Goal verifying]"):
            verifying_visible.set()

    monkeypatch.setattr(console_progress, "ConsoleProgressPresenter", lambda: presenter(write))
    verdicts = iter([
        GoalVerdict(
            passed=False, reason="Synthetic verification needs another round",
            nextAction="Run the remaining synthetic checks", systemError=system_error,
        ),
        GoalVerdict(passed=True, reason="All synthetic checks passed"),
    ])

    async def verify(*args):
        assert await asyncio.to_thread(verifying_visible.wait, 2), "Goal verification progress was buffered"
        verifying_visible.clear()
        return next(verdicts)

    check = AsyncMock(side_effect=verify)
    monkeypatch.setattr(verifier, "run_goal_verification", check)
    execute = AsyncMock(return_value=TurnOutput(output="final goal answer", metadata={}, next_action=None))
    monkeypatch.setattr(ConversationTurn, "execute", execute)

    assert NoInteractiveController(config, session).run("Pursue the goal") == 0

    labels = [message.split("]", 1)[0] + "]" for message in messages[:-1]]
    assert labels == [
        "[Goal started]", "[Goal verifying]",
        "[Goal verification error]" if system_error else "[Goal not achieved]",
        "[Goal verifying]", "[Goal achieved]",
    ]
    assert "rounds: 1" in messages[1]
    assert "rounds: 2" in messages[3]
    assert "Reason: Synthetic verification needs another round" in messages[2]
    assert "Next action: Run the remaining synthetic checks" in messages[2]
    assert "Reason: All synthetic checks passed" in messages[4]
    assert messages[-1] == "final goal answer"
    assert execute.await_count == check.await_count == 2
    records = goal_storage.load_goal(session.openai_session.session_folder).verification_results
    assert len(records) == 2
    config.io.get_input.assert_not_called()


@pytest.mark.parametrize("status", ["active", "paused", "blocked"])
def test_resumed_goal_console_snapshot_does_not_replay_old_verdicts(
    headless_goal_console, monkeypatch, status,
):
    from siada.entrypoint.interaction.turn.models import TurnOutput
    from siada.services.goal import verifier
    from siada.services.goal.models import Goal, GoalVerdict

    config, session, messages = headless_goal_console
    goal = Goal.create("Resume the synthetic console goal")
    goal.turns = 2
    goal.set_status(status)
    goal.verification_results.append({"reason": "Old verification feedback", "achieved": False})
    session.state.pending_goal = goal
    session.state.pending_goal_loaded = True
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: SimpleNamespace(goal=goal))
    monkeypatch.setattr(verifier, "run_goal_verification", AsyncMock(return_value=GoalVerdict(passed=True, reason="Verified after resume")))
    monkeypatch.setattr(ConversationTurn, "execute", AsyncMock(return_value=TurnOutput(output="resumed answer", metadata={}, next_action=None)))

    assert NoInteractiveController(config, session).run("Continue the saved goal") == 0

    assert messages[0].startswith("[Goal continuing]")
    assert "rounds: 2" in messages[0]
    if status != "active":
        assert "Goal resumed" in messages[0]
    assert messages[1].startswith("[Goal verifying]")
    assert "rounds: 3" in messages[1]
    assert messages[2].startswith("[Goal achieved]")
    assert messages[-1] == "resumed answer"
    assert all("Old verification feedback" not in message for message in messages)


def test_goal_interrupt_prints_pause_before_presenter_closes(headless_goal_console, monkeypatch):
    from siada.services.goal.models import Goal

    config, session, messages = headless_goal_console
    goal = Goal.create("Interrupt the synthetic console goal")
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: SimpleNamespace(goal=goal))
    monkeypatch.setattr(ConversationTurn, "execute", AsyncMock(side_effect=asyncio.CancelledError()))

    assert NoInteractiveController(config, session).run("Pursue the goal") == 130

    assert goal.status == "paused"
    assert len(messages) == 2
    assert messages[0].startswith("[Goal started]")
    assert messages[1].startswith("[Goal paused]")
    assert "Goal paused" in messages[1]


@pytest.mark.parametrize("console_output, acp_mode", [(False, False), (True, True)])
def test_goal_events_do_not_print_without_a_console_presenter(
    headless, monkeypatch, capsys, console_output, acp_mode,
):
    from siada.entrypoint.interaction.turn.models import TurnOutput
    from siada.services.goal import turn_hooks, verifier
    from siada.services.goal.models import Goal, GoalVerdict

    config, session = headless
    config.console_output = console_output
    config.acp_mode = acp_mode
    goal = Goal.create("Synthetic quiet goal")
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: SimpleNamespace(goal=goal))
    monkeypatch.setattr(turn_hooks, "_maybe_show_completion_notification", lambda *args: None)
    monkeypatch.setattr(verifier, "run_goal_verification", AsyncMock(return_value=GoalVerdict(passed=True, reason="Verified quietly")))
    monkeypatch.setattr(ConversationTurn, "execute", AsyncMock(return_value=TurnOutput(output="quiet answer", metadata={}, next_action=None)))

    assert NoInteractiveController(config, session).run("Pursue the goal") == 0

    assert capsys.readouterr().out == ""
    config.io.print.assert_called_once_with("quiet answer")


@pytest.mark.parametrize("error", [ValueError("synthetic failure"), asyncio.CancelledError()])
def test_stream_failures_are_not_reported_as_success(headless, monkeypatch, error):
    config, session = headless
    result = SyntheticStream(error=error)
    run = AsyncMock(return_value=result)
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    assert NoInteractiveController(config, session).run("task") == (
        130 if isinstance(error, asyncio.CancelledError) else 1
    )
    assert run.await_count == 1
    assert result.closed
    config.io.print.assert_not_called()
    if isinstance(error, asyncio.CancelledError):
        config.io.print_error.assert_not_called()
    else:
        config.io.print_error.assert_called_once()


def test_plugin_turn_hooks_use_shared_order_and_runtime(headless, monkeypatch):
    from siada.services.plugins.hook_runner import get_active

    config, session = headless
    hooks = Mock()
    hooks.run_with_result = AsyncMock(return_value=[])

    async def run(**kwargs):
        assert get_active() is hooks
        return SyntheticStream()

    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    commands = SimpleNamespace(hook_runner=hooks)
    assert NoInteractiveController(config, session, commands).run("task") == 0
    events = [item.args[0] for item in hooks.mock_calls if item[0] != "set_workspace"]
    assert events == ["SessionStart", "PreTurn", "UserPromptSubmit", "Stop", "PostTurn", "SessionEnd"]
    hooks.set_workspace.assert_called_once_with(config.workspace)
    assert hooks.run_with_result.call_args.args[1]["exit_reason"] == "completed"
    assert get_active() is None


def test_headless_memory_save_finishes_before_runtime_shutdown(headless, monkeypatch):
    config, session = headless
    config.memory_enabled = True
    saved = AsyncMock()
    monkeypatch.setattr(ConversationTurn, "_save_session_memory_if_needed", saved)
    monkeypatch.setattr(SiadaRunner, "run_agent", AsyncMock(return_value=SyntheticStream()))
    assert NoInteractiveController(config, session).run("task") == 0
    saved.assert_awaited_once()


def test_interrupt_returns_130_and_fires_session_end(headless, monkeypatch):
    config, session = headless
    hooks = Mock()
    hooks.run_with_result = AsyncMock(return_value=[])
    monkeypatch.setattr(ConversationTurn, "execute", AsyncMock(side_effect=asyncio.CancelledError()))
    assert NoInteractiveController(config, session, SimpleNamespace(hook_runner=hooks)).run("task") == 130
    assert hooks.run_with_result.call_args.args[0] == "SessionEnd"
    assert hooks.run_with_result.call_args.args[1]["exit_reason"] == "interrupt"
    config.io.print.assert_not_called()


def test_owned_session_prevents_noninteractive_model_execution(headless, monkeypatch):
    from siada.session.ownership import SessionOwner, SessionOwnershipManager

    config, session = headless
    SessionOwnershipManager.set_active_owner(session.openai_session.session_folder, SessionOwner.LARK)
    monkeypatch.setattr(SessionOwnershipManager, "_is_ownership_stale", lambda *args: False)
    run = AsyncMock(return_value=SyntheticStream())
    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    assert NoInteractiveController(config, session).run("task") == 1
    run.assert_not_called()
    config.io.print_warning.assert_called_once()
    config.io.print.assert_not_called()
    assert SessionOwnershipManager.get_active_owner(session.openai_session.session_folder) == SessionOwner.LARK


def test_headless_presents_progress_before_final_answer(headless, monkeypatch):
    from siada.agent_hub.coder.tracing.logger_tracing_processor import LoggerTracingProcessor
    from siada.entrypoint.interaction import console_progress

    config, session = headless
    config.console_output = True
    messages = []
    original_presenter = console_progress.ConsoleProgressPresenter
    monkeypatch.setattr(console_progress, "ConsoleProgressPresenter", lambda: original_presenter(messages.append))
    config.io.print = messages.append
    processor = LoggerTracingProcessor(console_output=True, use_colors=False)

    async def run(**kwargs):
        processor._print("model started")
        await asyncio.sleep(0)
        processor._print("tool completed")
        return SyntheticStream("final answer")

    monkeypatch.setattr(SiadaRunner, "run_agent", run)
    assert NoInteractiveController(config, session).run("task") == 0
    assert messages == ["model started", "tool completed", "final answer"]


@pytest.mark.parametrize("exit_code", [1, 130])
def test_headless_error_and_interrupt_flush_progress(headless, monkeypatch, exit_code):
    from siada.entrypoint.interaction import console_progress
    from siada.foundation.execution_progress import publish_execution_progress

    config, session = headless
    config.console_output = True
    messages = []
    original_presenter = console_progress.ConsoleProgressPresenter
    monkeypatch.setattr(console_progress, "ConsoleProgressPresenter", lambda: original_presenter(messages.append))
    config.io.print_error = messages.append
    async def execute(*args, **kwargs):
        publish_execution_progress("before failure")
        raise KeyboardInterrupt() if exit_code == 130 else RuntimeError("failed")
    monkeypatch.setattr(ConversationTurn, "execute", execute)
    assert NoInteractiveController(config, session).run("task") == exit_code
    assert messages == (
        ["before failure"] if exit_code == 130
        else ["before failure", "Error running agent: failed"]
    )


def test_protocol_mode_does_not_create_console_presenter(headless, monkeypatch, capsys):
    from siada.entrypoint.interaction import console_progress
    from siada.foundation.execution_progress import publish_execution_progress

    config, session = headless
    config.console_output = True
    config.acp_mode = True
    monkeypatch.setattr(console_progress, "ConsoleProgressPresenter", Mock(side_effect=AssertionError("ACP stdout must remain protocol-only")))
    async def execute(*args, **kwargs):
        publish_execution_progress("not protocol traffic")
        return SimpleNamespace(output="done", metadata={})
    monkeypatch.setattr(ConversationTurn, "execute", execute)
    assert NoInteractiveController(config, session).run("task") == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("exit_code", [0, 1, 130])
def test_cli_preserves_noninteractive_exit_code(headless, monkeypatch, exit_code):
    config, session = headless
    config.io.print_info = Mock()
    session.state.openai_session = None
    controller = Mock()
    controller.run.return_value = exit_code
    constructor = Mock(return_value=controller)
    monkeypatch.setattr(siadahub, "NoInteractiveController", constructor)
    monkeypatch.setattr(siadahub, "_try_restore_session", lambda *args: None)
    monkeypatch.setattr(siadahub, "_apply_login", lambda *args: None)
    commands = SimpleNamespace(hook_runner=None)
    assert siadahub._run_noninteractive(
        SimpleNamespace(prompt="task"), session, config, config.io, config.llm_config, commands,
    ) == exit_code
    constructor.assert_called_once_with(config=config, session=session, slash_commands=commands)
    controller.run.assert_called_once_with("task")


@pytest.mark.parametrize("enabled", [None, False, True])
def test_interactive_checkpoint_configuration_preserves_cli_priority(enabled):
    args = SimpleNamespace(checkpointing=enabled, max_checkpoint_files=7)
    conf = SimpleNamespace(checkpoint_config=SimpleNamespace(enable=True, max_checkpoint_files=50))
    interactive = siadahub.get_checkpointing_config(args, conf, interactive_mode=True)
    assert interactive.enable is (True if enabled is None else enabled)
    assert interactive.max_checkpoint_files == 7


@pytest.mark.parametrize("enabled", [None, False, True])
@pytest.mark.parametrize("configured_enabled", [None, False, True])
def test_noninteractive_always_disables_checkpoints(enabled, configured_enabled):
    args = SimpleNamespace(checkpointing=enabled, max_checkpoint_files=7)
    conf = (
        SimpleNamespace(checkpoint_config=SimpleNamespace(enable=configured_enabled, max_checkpoint_files=10))
        if configured_enabled is not None else None
    )
    noninteractive = siadahub.get_checkpointing_config(args, conf, interactive_mode=False)
    assert noninteractive.enable is False
    assert noninteractive.max_checkpoint_files == 50

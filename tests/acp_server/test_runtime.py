import asyncio

from agents import RawResponsesStreamEvent, RunItemStreamEvent, ToolCallOutputItem
from openai.types.responses import (
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionToolCall,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseTextDeltaEvent,
)

from siada.acp_server.runtime import SiadaTurnRunner


class _DummyAgent:
    """Minimal weakref-able stand-in for a real agents.Agent instance."""


def test_runtime_creates_isolated_session_and_uses_streaming_runner(monkeypatch, tmp_path):
    runner = SiadaTurnRunner(agent_name="test-agent")
    calls = []

    class EmptyStreamResult:
        async def stream_events(self):
            if False:
                yield None

    async def fake_run_agent(**kwargs):
        calls.append(kwargs)
        return EmptyStreamResult()

    monkeypatch.setattr("siada.services.siada_runner.SiadaRunner.run_agent", fake_run_agent)

    runner.create_session("acp-1", str(tmp_path))
    async def collect():
        return [chunk async for chunk in runner("acp-1", "hello")]

    result = asyncio.run(collect())

    assert result == []
    assert calls[0]["agent_name"] == "test-agent"
    # Raw ACP client text is wrapped in <user_input> tags at the runtime
    # entry point, mirroring the TUI entry points (see marker.wrap_user_input).
    assert calls[0]["user_input"] == "<user_input>hello</user_input>"
    assert calls[0]["workspace"] == str(tmp_path)
    assert calls[0]["stream"] is True


def _install_fake_slash_commands(runner, session_id, switch_event):
    """Bind a fake SlashCommands whose run() always returns switch_event."""

    class FakeSlashCommands:
        def run(self, session, text):
            return switch_event

    runner._slash_commands[session_id] = FakeSlashCommands()


def _collect_slash_updates(runner, session_id, text):
    # NOTE: a different async ``_collect`` (for runner __call__) already
    # exists further down this module — this helper must keep its own name
    # or the later definition shadows it.
    async def _run():
        return [update async for update in runner.run_slash_command(session_id, text)]

    return asyncio.run(_run())


def test_goal_command_handoff_replays_full_goal_text_wrapped(monkeypatch, tmp_path):
    """ACP /goal kickoff must persist the full "/goal <objective>" text wrapped
    in <user_input> tags — mirroring the CLI loop's
    Controller._build_pending_input_for_ai_analysis, so resumed/replayed
    history shows exactly what the human invoked instead of a bare objective."""
    from siada.support.slash_commands import SwitchEvent

    runner = SiadaTurnRunner(agent_name="test-agent")
    calls = []

    class EmptyStreamResult:
        async def stream_events(self):
            if False:
                yield None

    async def fake_run_agent(**kwargs):
        calls.append(kwargs)
        return EmptyStreamResult()

    monkeypatch.setattr("siada.services.siada_runner.SiadaRunner.run_agent", fake_run_agent)

    runner.create_session("acp-goal", str(tmp_path))
    _install_fake_slash_commands(
        runner, "acp-goal",
        SwitchEvent(ai_analysis_prompt="使用worktree 增加功能", goal_command=True),
    )

    updates = _collect_slash_updates(runner, "acp-goal", "/goal 使用worktree 增加功能")

    assert updates == []
    assert calls[0]["user_input"] == "<user_input>/goal 使用worktree 增加功能</user_input>"


def test_non_goal_ai_analysis_handoff_stays_a_bare_wrapped_prompt(monkeypatch, tmp_path):
    """/init-style SwitchEvent handoffs (no goal_command marker) must keep the
    bare prompt unchanged — only the standard <user_input> wrap from
    __call__ applies, matching the CLI loop's goal_command=False branch."""
    from siada.support.slash_commands import SwitchEvent

    runner = SiadaTurnRunner(agent_name="test-agent")
    calls = []

    class EmptyStreamResult:
        async def stream_events(self):
            if False:
                yield None

    async def fake_run_agent(**kwargs):
        calls.append(kwargs)
        return EmptyStreamResult()

    monkeypatch.setattr("siada.services.siada_runner.SiadaRunner.run_agent", fake_run_agent)

    runner.create_session("acp-init", str(tmp_path))
    _install_fake_slash_commands(
        runner, "acp-init",
        SwitchEvent(ai_analysis_prompt="analyze this codebase"),
    )

    updates = _collect_slash_updates(runner, "acp-init", "/init")

    assert updates == []
    assert calls[0]["user_input"] == "<user_input>analyze this codebase</user_input>"


def _make_stream_result(monkeypatch, events):
    class FakeStreamResult:
        async def stream_events(self):
            for event in events:
                yield event

    async def fake_run_agent(**_kwargs):
        return FakeStreamResult()

    monkeypatch.setattr("siada.services.siada_runner.SiadaRunner.run_agent", fake_run_agent)


def test_runtime_maps_text_delta_to_agent_message_chunk(monkeypatch, tmp_path):
    runner = SiadaTurnRunner(agent_name="test-agent")
    _make_stream_result(
        monkeypatch,
        [
            RawResponsesStreamEvent(
                data=ResponseTextDeltaEvent(
                    content_index=0,
                    delta="Hello",
                    item_id="item-1",
                    logprobs=[],
                    output_index=0,
                    sequence_number=0,
                    type="response.output_text.delta",
                )
            )
        ],
    )
    runner.create_session("acp-1", str(tmp_path))

    updates = asyncio.run(_collect(runner, "acp-1", "hi"))

    assert len(updates) == 1
    assert updates[0].session_update == "agent_message_chunk"
    assert updates[0].content.text == "Hello"


def test_runtime_maps_reasoning_delta_to_agent_thought_chunk(monkeypatch, tmp_path):
    runner = SiadaTurnRunner(agent_name="test-agent")
    _make_stream_result(
        monkeypatch,
        [
            RawResponsesStreamEvent(
                data=ResponseReasoningSummaryTextDeltaEvent(
                    delta="thinking...",
                    item_id="item-1",
                    output_index=0,
                    sequence_number=0,
                    summary_index=0,
                    type="response.reasoning_summary_text.delta",
                )
            )
        ],
    )
    runner.create_session("acp-1", str(tmp_path))

    updates = asyncio.run(_collect(runner, "acp-1", "hi"))

    assert len(updates) == 1
    assert updates[0].session_update == "agent_thought_chunk"
    assert updates[0].content.text == "thinking..."


def test_runtime_maps_tool_call_lifecycle(monkeypatch, tmp_path):
    tool_call = ResponseFunctionToolCall(
        arguments="",
        call_id="call-1",
        name="read_file",
        type="function_call",
        status="in_progress",
    )
    completed_call = tool_call.model_copy(update={"arguments": '{"path":"a.py"}'})

    runner = SiadaTurnRunner(agent_name="test-agent")
    _make_stream_result(
        monkeypatch,
        [
            RawResponsesStreamEvent(
                data=ResponseOutputItemAddedEvent(
                    item=tool_call, output_index=0, sequence_number=0, type="response.output_item.added"
                )
            ),
            RawResponsesStreamEvent(
                data=ResponseFunctionCallArgumentsDeltaEvent(
                    delta='{"path":"a.py"}',
                    item_id="item-1",
                    output_index=0,
                    sequence_number=1,
                    type="response.function_call_arguments.delta",
                )
            ),
            RawResponsesStreamEvent(
                data=ResponseOutputItemDoneEvent(
                    item=completed_call, output_index=0, sequence_number=2, type="response.output_item.done"
                )
            ),
            RunItemStreamEvent(
                name="tool_output",
                item=ToolCallOutputItem(
                    agent=_DummyAgent(),
                    raw_item={"call_id": "call-1"},
                    output="file contents",
                ),
            ),
        ],
    )
    runner.create_session("acp-1", str(tmp_path))

    updates = asyncio.run(_collect(runner, "acp-1", "hi"))

    assert [u.session_update for u in updates] == ["tool_call", "tool_call_update", "tool_call_update"]
    start, in_progress, completed = updates
    assert start.tool_call_id == "call-1"
    assert start.title == "read_file"
    assert start.status == "pending"
    assert in_progress.tool_call_id == "call-1"
    assert in_progress.status == "in_progress"
    assert in_progress.raw_input == {"path": "a.py"}
    assert completed.tool_call_id == "call-1"
    assert completed.status == "completed"
    assert completed.raw_output == "file contents"
    assert completed.content[0].content.text == "file contents"


async def _collect(runner, session_id, prompt):
    return [chunk async for chunk in runner(session_id, prompt)]


def test_list_available_models_returns_known_model_names():
    runner = SiadaTurnRunner()

    models = runner.list_available_models()

    assert "claude-sonnet-4-6" in models


def test_set_model_switches_the_session_llm_config(tmp_path):
    runner = SiadaTurnRunner()
    runner.create_session("acp-1", str(tmp_path))
    original_model = runner.get_model("acp-1")

    other_model = next(m for m in runner.list_available_models() if m != original_model)
    runner.set_model("acp-1", other_model)

    assert runner.get_model("acp-1") == other_model


def test_set_model_preserves_the_configured_provider(tmp_path):
    """Regression test: switching models must not wipe out `provider`
    (e.g. "li"), otherwise `get_provider(None)` blows up on the next prompt.
    """
    runner = SiadaTurnRunner()
    runner.create_session("acp-1", str(tmp_path))
    session = runner._sessions["acp-1"].session
    original_provider = session.siada_config.llm_config.provider
    assert original_provider

    other_model = next(
        m for m in runner.list_available_models()
        if m != runner.get_model("acp-1")
    )
    runner.set_model("acp-1", other_model)

    assert session.siada_config.llm_config.provider == original_provider

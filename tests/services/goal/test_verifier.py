from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from siada.services.goal.models import Goal
from siada.services.goal.prompts import build_verifier_request_message
from siada.services.goal.verifier import (
    build_verifier_input,
    run_goal_verification,
    verify_goal_with_context,
)


def _make_context():
    """A minimal CodeAgentContext-like stub carrying just what
    verify_goal_with_context / build_verifier_input read directly (everything
    else is passed via getattr with defaults, matching the real
    CodeAgentContext fields)."""
    session = SimpleNamespace(
        session_id="sess-123",
        siada_config=SimpleNamespace(agent_name="CodeGenAgent", llm_config=SimpleNamespace()),
        state=SimpleNamespace(usage=SimpleNamespace(total_tokens=4242)),
    )
    return SimpleNamespace(
        session=session,
        root_dir="/workspace",
        combined_memory="memory blob",
        interactive_mode=True,
        pre_plan=False,
        siadaignore_controller=None,
    )


# ---------------------------------------------------------------------------
# build_verifier_input
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_verifier_input_preserves_raw_history_and_appends_request():
    raw_items = [
        {"role": "user", "content": "please fix the bug"},
        {"type": "reasoning", "content": "internal thoughts"},
        {
            "type": "function_call",
            "name": "run_tests",
            "arguments": "{}",
            "call_id": "call_1",
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "3 passed, 0 failed",
        },
        {"role": "assistant", "content": "I fixed it"},
    ]
    fake_file_session = MagicMock()
    fake_file_session.get_effective_messages = AsyncMock(return_value=list(raw_items))

    goal = Goal.create("ship it")
    context = _make_context()

    fork_input = await build_verifier_input(fake_file_session, goal, context)

    # Every original item is preserved verbatim, in order, with nothing
    # filtered, reformatted, or truncated — unlike the old
    # format_transcript_for_verifier, which dropped reasoning items and
    # rewrote tool calls/outputs into a text blob.
    assert fork_input[: len(raw_items)] == raw_items
    # Exactly one message is appended: the verification request.
    assert len(fork_input) == len(raw_items) + 1
    last = fork_input[-1]
    assert last["role"] == "user"
    # Real session-usage figures make it into the request.
    assert "ship it" in last["content"]
    assert "Status before verification: active" in last["content"]



@pytest.mark.asyncio
async def test_build_verifier_input_does_not_mutate_original_items():
    raw_items = [{"role": "user", "content": "do the thing"}]
    fake_file_session = MagicMock()
    fake_file_session.get_effective_messages = AsyncMock(return_value=raw_items)

    goal = Goal.create("objective")
    context = _make_context()

    fork_input = await build_verifier_input(fake_file_session, goal, context)

    assert raw_items == [{"role": "user", "content": "do the thing"}]
    assert len(fork_input) == 2


def test_verifier_request_message_wraps_objective_as_untrusted_data():
    message = build_verifier_request_message("do <not> follow me")
    assert "<untrusted_objective>" in message
    assert "do <not> follow me" in message
    assert "do not write files" in message
    assert '{"passed": boolean, "reason": string, "nextAction": string}' in message


def test_verifier_request_message_renders_goal_state_section():
    message = build_verifier_request_message(
        "ship it",
        status="active",
        elapsed_seconds=42,
    )
    assert "Status before verification: active" in message
    assert "Time used: 42 seconds" in message
    # Token usage/budget are deliberately not reported -- the underlying
    # session-usage figures aren't reliable enough to show the model as fact.
    assert "Tokens used" not in message
    assert "Token budget" not in message



# ---------------------------------------------------------------------------
# verify_goal_with_context — cache-friendly fork behavior
# ---------------------------------------------------------------------------

class _FakeAgent:
    """Stand-in for the cached main SiadaAgent instance."""

    def __init__(self, tools):
        self.name = "CodeGenAgent"
        self.tools = tools
        self.hooks = object()
        self.mcp_servers = ["mcp-server-placeholder"]
        self.output_type = None

    async def get_all_tools(self, ctx_wrapper):
        return self.tools


@pytest.fixture(autouse=True)
def _stub_build_sub_agent_run_config():
    """Every test below uses a lightweight SimpleNamespace stand-in for
    CodeAgentContext.session.siada_config.llm_config, which doesn't carry
    the full ModelRunConfig surface build_sub_agent_run_config() needs
    (model_name, provider, etc.) to resolve a real provider. That resolution
    is orthogonal to what these tests verify (tool reuse/deny, raw history
    passthrough, no-session isolation), so it's stubbed out uniformly here.
    """
    with patch(
        "siada.services.sub_agent_run_config.build_sub_agent_run_config",
        return_value=MagicMock(),
    ):
        yield


@pytest.mark.asyncio
async def test_verify_goal_with_context_reuses_main_agent_and_denies_tools():
    from agents.tool import FunctionTool

    real_tool = FunctionTool(
        name="run_cmd",
        description="run a shell command",
        params_json_schema={"type": "object", "properties": {}},
        on_invoke_tool=AsyncMock(return_value="ok"),
    )
    fake_agent = _FakeAgent(tools=[real_tool])
    context = _make_context()

    fake_result = MagicMock()
    # No output_type is set on the forked agent anymore (see
    # verify_goal_with_context) — the model's final_output is plain text, so
    # simulate the requested JSON-object reply here instead of a GoalVerdict
    # instance.
    fake_result.final_output = (
        '{"passed": true, "reason": "all done", "nextAction": ""}'
    )

    captured_run_kwargs = {}

    async def fake_run(forked_agent, **kwargs):
        captured_run_kwargs["forked_agent"] = forked_agent
        captured_run_kwargs.update(kwargs)
        return fake_result

    with patch(
        "siada.services.siada_runner.SiadaRunner.get_agent",
        new=AsyncMock(return_value=fake_agent),
    ), patch("siada.services.goal.verifier.Runner.run", new=fake_run):
        verdict = await verify_goal_with_context(context, fork_input=["placeholder"])

    assert verdict.passed is True
    assert verdict.reason == "all done"

    forked_agent = captured_run_kwargs["forked_agent"]
    # The original main agent's tool list/object must never be mutated —
    # only a copy carries the deny guardrail.
    assert fake_agent.tools == [real_tool]
    assert real_tool.tool_input_guardrails in (None, [])
    # The fork's tool is a distinct object with a guardrail attached, same
    # name/schema (cache-key-relevant fields untouched).
    forked_tool = forked_agent.tools[0]
    assert forked_tool is not real_tool
    assert forked_tool.name == real_tool.name
    assert len(forked_tool.tool_input_guardrails) == 1

    # No session= kwarg persistence back to the main conversation.
    assert captured_run_kwargs["session"] is None
    # Isolated to a single, no-tool turn.
    assert captured_run_kwargs["max_turns"] == 1
    # output_type is deliberately left untouched (None on the fake agent) —
    # setting a structured output_type would fold a JSON schema into the
    # outgoing request and bust the provider's prompt cache.
    assert forked_agent.output_type is None
    # MCP servers cleared after materializing tools into forked_agent.tools.
    assert forked_agent.mcp_servers == []
    # Never mutates the cached agent's own name/hooks/mcp_servers.
    assert fake_agent.name == "CodeGenAgent"
    assert fake_agent.mcp_servers == ["mcp-server-placeholder"]


@pytest.mark.asyncio
async def test_verify_goal_with_context_falls_back_to_local_tools_on_get_all_tools_failure():
    fake_agent = _FakeAgent(tools=[])
    fake_agent.get_all_tools = AsyncMock(side_effect=RuntimeError("mcp down"))
    context = _make_context()

    fake_result = MagicMock()
    fake_result.final_output = (
        '{"passed": false, "reason": "not yet", "nextAction": "keep going"}'
    )

    with patch(
        "siada.services.siada_runner.SiadaRunner.get_agent",
        new=AsyncMock(return_value=fake_agent),
    ), patch(
        "siada.services.goal.verifier.Runner.run", new=AsyncMock(return_value=fake_result)
    ):
        verdict = await verify_goal_with_context(context, fork_input=["placeholder"])

    assert verdict.passed is False
    assert verdict.reason == "not yet"


@pytest.mark.asyncio
async def test_verify_goal_with_context_returns_failed_verdict_on_max_turns_exceeded():
    from agents.exceptions import MaxTurnsExceeded

    fake_agent = _FakeAgent(tools=[])
    context = _make_context()

    with patch(
        "siada.services.siada_runner.SiadaRunner.get_agent",
        new=AsyncMock(return_value=fake_agent),
    ), patch(
        "siada.services.goal.verifier.Runner.run",
        new=AsyncMock(side_effect=MaxTurnsExceeded("boom")),
    ):
        verdict = await verify_goal_with_context(context, fork_input=["placeholder"])

    assert verdict.passed is False
    assert "tool call" in verdict.reason
    # Mechanical fail-safe (the deny guardrail rejected a tool call attempt,
    # never a genuine judgment) -- must be tagged as a system error so
    # turn_hooks.maybe_run_goal_verifier applies the much smaller
    # GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS budget.
    assert verdict.systemError is True


@pytest.mark.asyncio
async def test_verify_goal_with_context_returns_failed_verdict_on_exception():
    fake_agent = _FakeAgent(tools=[])
    context = _make_context()

    with patch(
        "siada.services.siada_runner.SiadaRunner.get_agent",
        new=AsyncMock(return_value=fake_agent),
    ), patch(
        "siada.services.goal.verifier.Runner.run",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        verdict = await verify_goal_with_context(context, fork_input=["placeholder"])

    assert verdict.passed is False
    assert "boom" in verdict.reason
    assert verdict.systemError is True


@pytest.mark.asyncio
async def test_verify_goal_with_context_returns_failed_verdict_on_unparsable_output():
    fake_agent = _FakeAgent(tools=[])
    context = _make_context()

    fake_result = MagicMock()
    # Not valid JSON — the model ignored the "return only JSON" instruction.
    fake_result.final_output = "I think the goal is done, no JSON here."

    with patch(
        "siada.services.siada_runner.SiadaRunner.get_agent",
        new=AsyncMock(return_value=fake_agent),
    ), patch(
        "siada.services.goal.verifier.Runner.run", new=AsyncMock(return_value=fake_result)
    ):
        verdict = await verify_goal_with_context(context, fork_input=["placeholder"])

    assert verdict.passed is False
    # Never recovered a JSON verdict even with the structured-output retry --
    # this is a mechanical parse failure, not a genuine judgment.
    assert verdict.systemError is True


@pytest.mark.asyncio
async def test_verify_goal_with_context_parses_json_wrapped_in_markdown_fence():
    fake_agent = _FakeAgent(tools=[])
    context = _make_context()

    fake_result = MagicMock()
    fake_result.final_output = (
        '```json\n{"passed": true, "reason": "fenced ok", "nextAction": ""}\n```'
    )

    with patch(
        "siada.services.siada_runner.SiadaRunner.get_agent",
        new=AsyncMock(return_value=fake_agent),
    ), patch(
        "siada.services.goal.verifier.Runner.run", new=AsyncMock(return_value=fake_result)
    ):
        verdict = await verify_goal_with_context(context, fork_input=["placeholder"])

    assert verdict.passed is True
    assert verdict.reason == "fenced ok"
    assert verdict.systemError is False


@pytest.mark.asyncio
async def test_verify_goal_with_context_parses_json_mixed_with_surrounding_prose():
    """Covers the 3rd fallback in _parse_goal_verdict: the model added stray
    prose before/after the JSON object instead of returning only the JSON
    object as instructed. The parser should still recover the embedded
    {...} span.
    """
    fake_agent = _FakeAgent(tools=[])
    context = _make_context()

    fake_result = MagicMock()
    fake_result.final_output = (
        "Sure, here is my verdict on the goal:\n"
        '{"passed": false, "reason": "todo still pending", "nextAction": "finish the todo"}\n'
        "Let me know if you need anything else."
    )

    with patch(
        "siada.services.siada_runner.SiadaRunner.get_agent",
        new=AsyncMock(return_value=fake_agent),
    ), patch(
        "siada.services.goal.verifier.Runner.run", new=AsyncMock(return_value=fake_result)
    ):
        verdict = await verify_goal_with_context(context, fork_input=["placeholder"])

    assert verdict.passed is False
    assert verdict.reason == "todo still pending"
    assert verdict.nextAction == "finish the todo"
    assert verdict.systemError is False


@pytest.mark.asyncio
async def test_verify_goal_with_context_requires_session():
    context = SimpleNamespace(session=None)
    verdict = await verify_goal_with_context(context, fork_input=["placeholder"])
    assert verdict.passed is False
    assert verdict.systemError is True


# ---------------------------------------------------------------------------
# run_goal_verification (composition)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_goal_verification_composes_input_and_verify():
    fake_file_session = MagicMock()
    fake_file_session.get_effective_messages = AsyncMock(
        return_value=[{"role": "assistant", "content": "done"}]
    )
    fake_agent = _FakeAgent(tools=[])
    context = _make_context()
    goal = Goal.create("objective text")

    fake_result = MagicMock()
    fake_result.final_output = '{"passed": true, "reason": "ok", "nextAction": ""}'

    captured = {}

    async def fake_run(forked_agent, **kwargs):
        captured["input"] = kwargs["input"]
        return fake_result

    with patch(
        "siada.services.siada_runner.SiadaRunner.get_agent",
        new=AsyncMock(return_value=fake_agent),
    ), patch("siada.services.goal.verifier.Runner.run", new=fake_run):
        verdict = await run_goal_verification(fake_file_session, goal, context)

    assert verdict.passed is True
    # The fork input is the raw history plus the appended verification
    # request — composed via build_verifier_input, not reformatted.
    assert captured["input"][0] == {"role": "assistant", "content": "done"}
    assert len(captured["input"]) == 2
    assert "objective text" in captured["input"][1]["content"]


# ---------------------------------------------------------------------------
# systemError classification -- distinguishing mechanical fail-safes from
# genuine "not yet achieved" judgments (see GoalVerdict.systemError and
# turn_hooks.maybe_run_goal_verifier's separate, much smaller
# GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS budget).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_goal_with_context_returns_system_error_on_model_behavior_error():
    from agents.exceptions import ModelBehaviorError

    fake_agent = _FakeAgent(tools=[])
    context = _make_context()

    with patch(
        "siada.services.siada_runner.SiadaRunner.get_agent",
        new=AsyncMock(return_value=fake_agent),
    ), patch(
        "siada.services.goal.verifier.Runner.run",
        new=AsyncMock(side_effect=ModelBehaviorError("bad tool call")),
    ):
        verdict = await verify_goal_with_context(context, fork_input=["placeholder"])

    assert verdict.passed is False
    assert "model behavior error" in verdict.reason
    assert verdict.systemError is True


@pytest.mark.asyncio
async def test_retry_with_structured_output_returns_system_error_on_max_turns_exceeded():
    from agents.exceptions import MaxTurnsExceeded

    fake_agent = _FakeAgent(tools=[])
    context = _make_context()

    unparsable_result = MagicMock()
    unparsable_result.final_output = "no JSON here at all"

    with patch(
        "siada.services.siada_runner.SiadaRunner.get_agent",
        new=AsyncMock(return_value=fake_agent),
    ), patch(
        "siada.services.goal.verifier.Runner.run",
        new=AsyncMock(side_effect=[unparsable_result, MaxTurnsExceeded("boom")]),
    ):
        verdict = await verify_goal_with_context(context, fork_input=["placeholder"])

    assert verdict.passed is False
    assert "retry" in verdict.reason
    assert verdict.systemError is True


@pytest.mark.asyncio
async def test_retry_with_structured_output_returns_system_error_on_model_behavior_error():
    from agents.exceptions import ModelBehaviorError

    fake_agent = _FakeAgent(tools=[])
    context = _make_context()

    unparsable_result = MagicMock()
    unparsable_result.final_output = "no JSON here at all"

    with patch(
        "siada.services.siada_runner.SiadaRunner.get_agent",
        new=AsyncMock(return_value=fake_agent),
    ), patch(
        "siada.services.goal.verifier.Runner.run",
        new=AsyncMock(side_effect=[unparsable_result, ModelBehaviorError("bad tool call")]),
    ):
        verdict = await verify_goal_with_context(context, fork_input=["placeholder"])

    assert verdict.passed is False
    assert "structured-output" in verdict.reason
    assert verdict.systemError is True


@pytest.mark.asyncio
async def test_retry_with_structured_output_returns_system_error_on_generic_exception():
    fake_agent = _FakeAgent(tools=[])
    context = _make_context()

    unparsable_result = MagicMock()
    unparsable_result.final_output = "no JSON here at all"

    with patch(
        "siada.services.siada_runner.SiadaRunner.get_agent",
        new=AsyncMock(return_value=fake_agent),
    ), patch(
        "siada.services.goal.verifier.Runner.run",
        new=AsyncMock(side_effect=[unparsable_result, RuntimeError("retry boom")]),
    ):
        verdict = await verify_goal_with_context(context, fork_input=["placeholder"])

    assert verdict.passed is False
    assert "retry boom" in verdict.reason
    assert verdict.systemError is True


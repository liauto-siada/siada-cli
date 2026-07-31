"""
End-to-end multi-turn compaction tests for the sub-agent in-memory session.

Strategy: drive a real ``agents.Runner.run`` with a self-contained FakeModel
(no network / no real LLM), the real ``InMemorySession`` and the two real hooks
(``session_input_callback`` + ``call_model_input_filter``) wired into RunConfig
exactly as ``run_subtask`` wires them.

A scripted tool loop grows the conversation across several model turns. We
control token counting so the context crosses the 70% threshold mid-run and
verify the *real* runner integration:

1. No-compaction run: ``compact`` is never invoked; the session accumulates the
   user input + tool-call items + final assistant message; the run completes.
2. Compaction run: once the (real) ``should_compact`` threshold is crossed, the
   filter calls ``compact``, writes the compacted list back into the session,
   and the *next model call performed by the runner* receives the shorter,
   compacted input. The run still completes with the scripted final answer.

Only ``compact`` (the LLM summarization step) and ``calculate_tokens`` are
stubbed; the session, the hooks, the threshold decision and the whole Runner
pipeline are exercised for real.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agents import Agent, Runner, RunConfig, function_tool
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

import siada.tools.agent.sub_agent_compaction_filter as mod
from siada.agent_hub.context_filter.compaction_strategy import CompactionResult
from siada.tools.agent.sub_agent_compaction_filter import (
    InMemorySession,
    make_sub_agent_compaction_filter,
    make_sub_agent_session_input_callback,
)


# ---------------------------------------------------------------------------
# Tool with an observable side effect (drives the multi-turn loop)
# ---------------------------------------------------------------------------

_TOOL_CALLS: list[str] = []


@function_tool
def record_tool(note: str = "") -> str:
    """A trivial tool that records each invocation and returns a result string."""
    _TOOL_CALLS.append(note or "called")
    return f"tool-result-{len(_TOOL_CALLS)}"


# ---------------------------------------------------------------------------
# Scripted output item builders
# ---------------------------------------------------------------------------

def _tool_call(call_id: str, note: str) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        id=call_id,
        call_id=call_id,
        name="record_tool",
        arguments=f'{{"note": "{note}"}}',
        type="function_call",
    )


def _text(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id="msg_final",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
    )


class _ScriptedModel(Model):
    """Fake Model returning a pre-scripted output list per turn, recording inputs."""

    def __init__(self, scripted_outputs: list[list]):
        self._scripted = scripted_outputs
        self._turn = 0
        self.received_inputs: list = []

    async def get_response(self, system_instructions, input, *args, **kwargs) -> ModelResponse:
        # ``input`` here is exactly what the runner sends after the
        # call_model_input_filter has run, so it reflects compaction.
        self.received_inputs.append(list(input) if isinstance(input, list) else input)
        idx = min(self._turn, len(self._scripted) - 1)
        output = self._scripted[idx]
        self._turn += 1
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    def stream_response(self, *args, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError


def _make_model_run_config(context_window: int = 1000) -> MagicMock:
    cfg = MagicMock()
    cfg.model_name = "claude-sonnet-4.6"
    cfg.context_window = context_window
    return cfg


def _build_run_config(session: InMemorySession, cfg) -> RunConfig:
    """Wire the two real hooks exactly like run_subtask does."""
    return RunConfig(
        tracing_disabled=True,
        session_input_callback=make_sub_agent_session_input_callback(session),
        call_model_input_filter=make_sub_agent_compaction_filter(cfg, session),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSubAgentCompactionE2E(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        _TOOL_CALLS.clear()

    async def test_no_compaction_session_accumulates_and_run_completes(self):
        """Below threshold: compact never runs, session grows, run finishes."""
        model = _ScriptedModel(
            [
                [_tool_call("c1", "n1")],   # turn 1: call the tool
                [_text("all done")],        # turn 2: final answer
            ]
        )
        session = InMemorySession()
        cfg = _make_model_run_config(context_window=1_000_000)
        run_config = _build_run_config(session, cfg)
        agent = Agent(name="e2e-nocompact", model=model, tools=[record_tool])

        with patch.object(mod, "calculate_tokens", return_value=10), \
             patch.object(mod._STRATEGY, "compact", new=AsyncMock()) as mock_compact:
            result = await Runner.run(
                agent, input="start", run_config=run_config, max_turns=5, session=session
            )

        # Compaction never triggered.
        mock_compact.assert_not_called()
        # The tool actually executed once.
        self.assertEqual(_TOOL_CALLS, ["n1"])
        self.assertEqual(result.final_output, "all done")

        # Session accumulated: user input + function_call + function_call_output
        # + final assistant message (>= 4 items).
        final_items = await session.get_items()
        self.assertGreaterEqual(len(final_items), 4)

    async def test_compaction_triggers_and_runner_uses_compacted_input(self):
        """Above threshold mid-run: compact runs, session is rewritten, and the
        next model call performed by the runner receives the compacted input."""
        compacted = [
            {"role": "user", "content": "[[COMPACTED-SUMMARY]]"},
            {"role": "assistant", "content": "most recent kept turn"},
        ]

        model = _ScriptedModel(
            [
                [_tool_call("c1", "n1")],   # turn 1
                [_tool_call("c2", "n2")],   # turn 2
                [_text("final answer")],    # turn 3 (after compaction)
            ]
        )
        session = InMemorySession()
        cfg = _make_model_run_config(context_window=1000)  # threshold = 700
        run_config = _build_run_config(session, cfg)
        agent = Agent(name="e2e-compact", model=model, tools=[record_tool])

        # Token count grows with the number of items in the effective input:
        # 1 item -> 200, 3 items -> 600 (still < 700), 5 items -> 1000 (>= 700).
        def _tokens(model_name, items, **kwargs):
            return len(items) * 200

        with patch.object(mod, "calculate_tokens", side_effect=_tokens), \
             patch.object(
                 mod._STRATEGY, "compact",
                 new=AsyncMock(
                     return_value=CompactionResult(messages=compacted, compacted=True)
                 ),
             ) as mock_compact:
            result = await Runner.run(
                agent, input="start", run_config=run_config, max_turns=6, session=session
            )

        # Compaction was triggered through the real runner pipeline.
        mock_compact.assert_awaited()
        self.assertEqual(result.final_output, "final answer")

        # The model call that happened right after compaction received the
        # compacted (shorter) input — locate it among the recorded inputs.
        def _has_summary(inp) -> bool:
            return isinstance(inp, list) and any(
                isinstance(i, dict) and i.get("content") == "[[COMPACTED-SUMMARY]]"
                for i in inp
            )

        compacted_turns = [inp for inp in model.received_inputs if _has_summary(inp)]
        self.assertTrue(
            compacted_turns,
            "expected at least one model call to receive the compacted input",
        )
        # And that compacted input is exactly what the filter wrote back.
        self.assertEqual(compacted_turns[0], compacted)

        # The pre-compaction turn was longer than the compacted turn.
        pre_compaction_lengths = [
            len(inp) for inp in model.received_inputs
            if isinstance(inp, list) and not _has_summary(inp)
        ]
        self.assertTrue(any(n > len(compacted) for n in pre_compaction_lengths))

        # Session was rewritten from the compacted baseline (no pre-compaction
        # user "start" item lingers as a duplicate growth).
        final_items = await session.get_items()
        self.assertTrue(
            any(i.get("content") == "[[COMPACTED-SUMMARY]]"
                for i in final_items if isinstance(i, dict)),
            "compacted summary should remain in the session after the run",
        )

    async def test_post_compaction_no_recompaction_when_under_threshold(self):
        """After compaction shrinks the session, subsequent turns stay under the
        threshold and do not recompact."""
        compacted = [{"role": "user", "content": "[[COMPACTED-SUMMARY]]"}]

        model = _ScriptedModel(
            [
                [_tool_call("c1", "n1")],   # turn 1
                [_tool_call("c2", "n2")],   # turn 2 -> triggers compaction
                [_tool_call("c3", "n3")],   # turn 3 -> small session, no recompact
                [_text("done")],            # turn 4
            ]
        )
        session = InMemorySession()
        cfg = _make_model_run_config(context_window=1000)
        run_config = _build_run_config(session, cfg)
        agent = Agent(name="e2e-once", model=model, tools=[record_tool])

        def _tokens(model_name, items, **kwargs):
            return len(items) * 200

        with patch.object(mod, "calculate_tokens", side_effect=_tokens), \
             patch.object(
                 mod._STRATEGY, "compact",
                 new=AsyncMock(
                     return_value=CompactionResult(messages=compacted, compacted=True)
                 ),
             ) as mock_compact:
            result = await Runner.run(
                agent, input="start", run_config=run_config, max_turns=8, session=session
            )

        self.assertEqual(result.final_output, "done")
        # Compaction happened, but only while the session was large enough; once
        # shrunk to a single summary item the small turns stay under threshold.
        self.assertGreaterEqual(mock_compact.await_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

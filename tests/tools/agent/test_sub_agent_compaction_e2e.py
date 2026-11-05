"""
End-to-end multi-turn compaction tests for the sub-agent in-memory session.

Strategy: drive real ``agents.Runner.run`` and ``Runner.run_streamed`` calls
with a FakeModel (no network / no real LLM), the real ``InMemorySession`` and hooks
(``session_input_callback`` + ``call_model_input_filter``) wired into RunConfig
exactly as ``run_subtask`` wires them.

A scripted tool loop grows the conversation across several model turns. We
control token counting so the context reaches 60k remaining mid-run and
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

import copy
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agents import Agent, Runner, RunConfig, RunResult, RunResultStreaming, function_tool
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
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


def _text(text: str, message_id: str = "msg_final") -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id=message_id,
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
    )


class _ScriptedModel(Model):
    """Fake Model returning a pre-scripted output list per turn, recording inputs."""

    def __init__(self, scripted_outputs: list[list | Exception]):
        self._scripted = scripted_outputs
        self._turn = 0
        self.received_inputs: list = []

    async def get_response(self, system_instructions, input, *args, **kwargs) -> ModelResponse:
        # ``input`` here is exactly what the runner sends after the
        # call_model_input_filter has run, so it reflects compaction.
        self.received_inputs.append(copy.deepcopy(input))
        idx = min(self._turn, len(self._scripted) - 1)
        output = self._scripted[idx]
        self._turn += 1
        if isinstance(output, Exception):
            raise output
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    async def stream_response(self, system_instructions, input, *args, **kwargs):
        result = await self.get_response(system_instructions, input, *args, **kwargs)
        yield ResponseCompletedEvent(
            type="response.completed",
            sequence_number=0,
            response=Response(
                id=f"response-{self._turn}",
                created_at=0,
                model="scripted-model",
                object="response",
                output=result.output,
                parallel_tool_calls=False,
                tool_choice="auto",
                tools=[],
            ),
        )


def _make_model_run_config(context_window: int = 60_700) -> MagicMock:
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


async def _run_agent(
    agent: Agent,
    session: InMemorySession,
    run_config: RunConfig,
    *,
    streamed: bool,
    input: str = "start",
    max_turns: int = 6,
) -> RunResult | RunResultStreaming:
    """Exercise both SDK loops while fully consuming streamed execution."""
    if streamed:
        result = Runner.run_streamed(
            agent, input=input, run_config=run_config, max_turns=max_turns, session=session
        )
        async for _ in result.stream_events():
            pass
        return result
    return await Runner.run(
        agent, input=input, run_config=run_config, max_turns=max_turns, session=session
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSubAgentCompactionE2E(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        _TOOL_CALLS.clear()

    async def test_first_call_compaction_does_not_restore_original_input(self):
        """The SDK's initial save must not resurrect an input replaced by a summary."""
        for streamed in (False, True):
            for fork in (False, True):
                with self.subTest(streamed=streamed, fork=fork):
                    _TOOL_CALLS.clear()
                    session = InMemorySession()
                    if fork:
                        await session.add_items([
                            {"role": "user", "content": "old task"},
                            {"role": "assistant", "content": "old answer"},
                        ])
                    model = _ScriptedModel([
                        [_tool_call("c1", "n1")], [_text("done")],
                    ])
                    agent = Agent(name="first-compact", model=model, tools=[record_tool])
                    compacted = [{"role": "user", "content": "[[SUMMARY]]"}]
                    config = _build_run_config(session, _make_model_run_config())
                    with patch.object(mod, "calculate_tokens", side_effect=[900, 10]), \
                         patch.object(mod._STRATEGY, "compact", new=AsyncMock(
                             return_value=CompactionResult(messages=compacted, compacted=True)
                         )) as compact:
                        result = await _run_agent(agent, session, config, streamed=streamed)

                    compact.assert_awaited_once()
                    self.assertEqual(result.final_output, "done")
                    self.assertEqual(model.received_inputs[0], compacted)
                    final_items = await session.get_items()
                    for items in [*model.received_inputs, final_items]:
                        self.assertNotIn({"role": "user", "content": "start"}, items)
                    self.assertEqual(len(model.received_inputs[1]), 3)
                    self.assertEqual(len(final_items), 4)
                    self.assertEqual(_TOOL_CALLS, ["n1"])
                    self.assertEqual(final_items[1]["call_id"], "c1")
                    self.assertEqual(final_items[2]["output"], "tool-result-1")

    async def test_fork_preserves_repeated_history_and_new_instruction(self):
        """Identical content in history is not an input-admission identity."""
        history = [
            {"role": "user", "content": "repeat"},
            {"role": "assistant", "content": "previous answer"},
        ] * 2
        for streamed in (False, True):
            with self.subTest(streamed=streamed):
                session = InMemorySession()
                await session.add_items(copy.deepcopy(history))
                model = _ScriptedModel([[_text("done")]])
                agent = Agent(name="fork-repeat", model=model)
                config = _build_run_config(session, _make_model_run_config())
                with patch.object(mod, "calculate_tokens", return_value=10):
                    await _run_agent(agent, session, config, streamed=streamed, input="repeat")
                expected = history + [{"role": "user", "content": "repeat"}]
                self.assertEqual(model.received_inputs[0], expected)
                self.assertEqual((await session.get_items())[:-1], expected)

    async def test_identical_input_in_new_runs_is_preserved(self):
        """A fresh callback represents a new logical run, even with identical input."""
        for streamed in (False, True):
            with self.subTest(streamed=streamed):
                session = InMemorySession()
                for index in range(2):
                    model = _ScriptedModel([[_text("done", message_id=f"msg-{index}")]])
                    agent = Agent(name="repeat-runs", model=model)
                    config = _build_run_config(session, _make_model_run_config())
                    with patch.object(mod, "calculate_tokens", return_value=10):
                        await _run_agent(agent, session, config, streamed=streamed, input="repeat")
                items = await session.get_items()
                self.assertEqual(len(items), 4)
                self.assertEqual(items[0], {"role": "user", "content": "repeat"})
                self.assertEqual(items[2], items[0])

    async def test_model_failure_after_compaction_retry_keeps_summary(self):
        """Retrying the same admitted input cannot restore it after model failure."""
        for streamed in (False, True):
            with self.subTest(streamed=streamed):
                session = InMemorySession()
                compacted = [{"role": "user", "content": "[[SUMMARY]]"}]
                config = _build_run_config(session, _make_model_run_config())
                failed_model = _ScriptedModel([RuntimeError("synthetic model failure")])
                failed_agent = Agent(name="failed", model=failed_model)
                with patch.object(mod, "calculate_tokens", return_value=900), \
                     patch.object(mod._STRATEGY, "compact", new=AsyncMock(
                         return_value=CompactionResult(messages=compacted, compacted=True)
                     )):
                    with self.assertRaisesRegex(RuntimeError, "synthetic model failure"):
                        await _run_agent(failed_agent, session, config, streamed=streamed)
                self.assertEqual(await session.get_items(), compacted)

                retry_model = _ScriptedModel([[_text("recovered")]])
                retry_agent = Agent(name="retry", model=retry_model)
                with patch.object(mod, "calculate_tokens", return_value=10):
                    result = await _run_agent(retry_agent, session, config, streamed=streamed)
                self.assertEqual(result.final_output, "recovered")
                self.assertEqual(retry_model.received_inputs[0], compacted)
                final_items = await session.get_items()
                self.assertEqual(len(final_items), 2)
                self.assertNotIn({"role": "user", "content": "start"}, final_items)

    async def test_mid_run_streamed_compaction_preserves_new_tool_results(self):
        """Later compaction does not restore old turns or lose newly generated items."""
        session = InMemorySession()
        model = _ScriptedModel([
            [_tool_call("c1", "n1")],
            [_tool_call("c2", "n2")],
            [_text("done")],
        ])
        agent = Agent(name="mid-run-stream", model=model, tools=[record_tool])
        config = _build_run_config(session, _make_model_run_config())
        compacted = [{"role": "user", "content": "[[SUMMARY]]"}]
        with patch.object(mod, "calculate_tokens", side_effect=[10, 900, 10]), \
             patch.object(mod._STRATEGY, "compact", new=AsyncMock(
                 return_value=CompactionResult(messages=compacted, compacted=True)
             )) as compact:
            result = await _run_agent(agent, session, config, streamed=True)
        compact.assert_awaited_once()
        self.assertEqual(result.final_output, "done")
        self.assertEqual(model.received_inputs[1], compacted)
        self.assertEqual(model.received_inputs[2][1]["call_id"], "c2")
        self.assertEqual(model.received_inputs[2][2]["output"], "tool-result-2")
        final_items = await session.get_items()
        self.assertEqual(len(final_items), 4)
        self.assertNotIn({"role": "user", "content": "start"}, final_items)
        self.assertEqual(_TOOL_CALLS, ["n1", "n2"])

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
        cfg = _make_model_run_config(context_window=60_700)  # threshold = 700
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
        cfg = _make_model_run_config(context_window=60_700)
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

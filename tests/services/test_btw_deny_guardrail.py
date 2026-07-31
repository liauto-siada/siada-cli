"""Agent-level tests for the /btw tool deny guardrail.

These tests verify that ``_wrap_tools_with_deny`` (siada/services/side_question.py)
actually blocks tool *execution* at runtime — not just in theory.

Strategy: drive a real ``agents.Runner.run`` with a self-contained FakeModel
(no network / no real LLM needed). The fake model emits a tool call on its first
turn; we assert:

1. Control case (tool WITHOUT the deny guardrail): the tool body runs and its
   side effect is recorded — proves the fake-model harness genuinely triggers
   tool execution.
2. Guarded case (tool wrapped with ``_wrap_tools_with_deny``): the tool body is
   NEVER executed (zero side effects), the deny message is fed back to the model
   as the tool result, and the model then produces a normal text answer.
3. The deny guardrail is attached without mutating the original tool object
   (the cached main agent shares it).

If a real LLM round-trip is ever needed, point the model at the proxy path
``/llmproxy/test/callLLMStreamClaude/v1/messages`` on the usual domain — but the
FakeModel approach below is deterministic and preferred for unit tests.
"""

import unittest

from agents import Agent, Runner, RunConfig, function_tool
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from siada.services.side_question import (
    _wrap_tools_with_deny,
    _BTW_TOOL_DENY_MESSAGE,
    _btw_answer_from_failed_run,
)



# --------------------------------------------------------------------------- #
# Test helpers
# --------------------------------------------------------------------------- #

# Records every real execution of the dangerous tool. Reset in setUp.
_SIDE_EFFECTS: list[str] = []


@function_tool
def dangerous_tool(payload: str = "") -> str:
    """A tool with an observable side effect (used to detect execution)."""
    _SIDE_EFFECTS.append(payload or "executed")
    return "DANGER: tool actually ran"


def _tool_call_item(call_id: str = "call_1", payload: str = "boom") -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        id=call_id,
        call_id=call_id,
        name="dangerous_tool",
        arguments=f'{{"payload": "{payload}"}}',
        type="function_call",
    )


def _text_item(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id="msg_1",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
    )


class _ScriptedModel(Model):
    """A fake Model that returns a pre-scripted output list per turn."""

    def __init__(self, scripted_outputs: list[list]):
        # Each element is the ``output`` list for one get_response call.
        self._scripted = scripted_outputs
        self._turn = 0
        self.received_inputs: list = []

    async def get_response(self, system_instructions, input, *args, **kwargs) -> ModelResponse:
        self.received_inputs.append(input)
        idx = min(self._turn, len(self._scripted) - 1)
        output = self._scripted[idx]
        self._turn += 1
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    def stream_response(self, *args, **kwargs):  # pragma: no cover - not used here
        raise NotImplementedError("streaming not needed for these tests")


_RUN_CONFIG = RunConfig(tracing_disabled=True)


class TestBtwDenyGuardrail(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _SIDE_EFFECTS.clear()

    # --- control: without the guardrail the tool really runs --------------- #
    async def test_control_tool_executes_without_guardrail(self):
        model = _ScriptedModel(
            [
                [_tool_call_item()],          # turn 1: call the tool
                [_text_item("done")],         # turn 2: answer after tool result
            ]
        )
        agent = Agent(name="ctrl", model=model, tools=[dangerous_tool])

        result = await Runner.run(agent, input="use the tool", run_config=_RUN_CONFIG, max_turns=4)

        # The tool body executed → side effect recorded.
        self.assertEqual(_SIDE_EFFECTS, ["boom"])
        self.assertEqual(result.final_output, "done")

    # --- guarded: the deny guardrail blocks execution --------------------- #
    async def test_guarded_tool_is_blocked_and_model_recovers(self):
        model = _ScriptedModel(
            [
                [_tool_call_item()],                         # turn 1: tries the tool
                [_text_item("answered without the tool")],   # turn 2: recovers with text
            ]
        )
        guarded_tools = _wrap_tools_with_deny([dangerous_tool])
        agent = Agent(name="guarded", model=model, tools=guarded_tools)

        result = await Runner.run(agent, input="use the tool", run_config=_RUN_CONFIG, max_turns=4)

        # The tool body NEVER ran.
        self.assertEqual(_SIDE_EFFECTS, [])
        # The model recovered into a normal text answer.
        self.assertEqual(result.final_output, "answered without the tool")

        # The deny message was handed back to the model as the tool result:
        # it must appear somewhere in the input fed to the 2nd model turn.
        second_turn_input = model.received_inputs[1]
        serialized = repr(second_turn_input)
        self.assertIn(_BTW_TOOL_DENY_MESSAGE, serialized)

    # --- guarded: never recovering still produces zero side effects -------- #
    async def test_guarded_tool_blocked_even_if_model_keeps_calling(self):
        # Model stubbornly calls the tool on every turn; guardrail must block
        # all of them. Runner stops at max_turns with no side effects.
        from agents.exceptions import MaxTurnsExceeded

        model = _ScriptedModel([[_tool_call_item(call_id="c1")]])  # always a tool call
        guarded_tools = _wrap_tools_with_deny([dangerous_tool])
        agent = Agent(name="stubborn", model=model, tools=guarded_tools)

        with self.assertRaises(MaxTurnsExceeded):
            await Runner.run(agent, input="use it", run_config=_RUN_CONFIG, max_turns=2)

        self.assertEqual(_SIDE_EFFECTS, [])

    # --- the original tool object is not mutated --------------------------- #
    async def test_wrap_does_not_mutate_original_tool(self):
        from agents.tool import FunctionTool

        original_guardrails = list(dangerous_tool.tool_input_guardrails or [])
        wrapped = _wrap_tools_with_deny([dangerous_tool])

        self.assertEqual(len(wrapped), 1)
        self.assertIsInstance(wrapped[0], FunctionTool)
        # Original tool's guardrails are untouched.
        self.assertEqual(list(dangerous_tool.tool_input_guardrails or []), original_guardrails)
        # Wrapped tool carries exactly one extra (deny) guardrail.
        self.assertEqual(
            len(wrapped[0].tool_input_guardrails), len(original_guardrails) + 1
        )
        self.assertEqual(wrapped[0].tool_input_guardrails[-1].get_name(), "btw_deny_tools")

    # --- non-FunctionTool entries pass through unchanged ------------------- #
    async def test_non_function_tool_passes_through(self):
        sentinel = object()  # not a FunctionTool
        wrapped = _wrap_tools_with_deny([sentinel])
        self.assertEqual(wrapped, [sentinel])


class TestBtwAnswerFromFailedRun(unittest.IsolatedAsyncioTestCase):
    """End-to-end tests for ``_btw_answer_from_failed_run``.

    These reproduce the real /btw runtime path: a forked agent runs with
    ``max_turns=1`` and the deny guardrail attached. When the model spends its
    single turn on a tool call (instead of answering directly), the deny
    guardrail rejects the tool (no execution) but the run still hits the turn
    limit and raises ``MaxTurnsExceeded``. We then feed the real
    ``exc.run_data`` into ``_btw_answer_from_failed_run`` exactly like
    ``_run_async`` does, and assert the salvaged answer is correct.
    """

    def setUp(self):
        _SIDE_EFFECTS.clear()

    async def _run_until_max_turns(self, model) -> "object":
        """Run a guarded agent with max_turns=1 and return the MaxTurnsExceeded."""
        from agents.exceptions import MaxTurnsExceeded

        guarded_tools = _wrap_tools_with_deny([dangerous_tool])
        agent = Agent(name="btw-fork", model=model, tools=guarded_tools)
        try:
            await Runner.run(agent, input="q", run_config=_RUN_CONFIG, max_turns=1)
        except MaxTurnsExceeded as exc:
            return exc
        self.fail("expected MaxTurnsExceeded to be raised")

    # --- situation B: tool call only → hint naming the tool ---------------- #
    async def test_tool_call_only_returns_hint_with_tool_name(self):
        # Model only ever emits a tool call (no text). Deny blocks execution,
        # run hits max_turns=1 → MaxTurnsExceeded.
        model = _ScriptedModel([[_tool_call_item()]])
        exc = await self._run_until_max_turns(model)

        # Sanity: the run carried partial output AND the tool never executed.
        self.assertIsNotNone(getattr(exc, "run_data", None))
        self.assertEqual(_SIDE_EFFECTS, [])

        answer = _btw_answer_from_failed_run(exc.run_data)
        self.assertIn("dangerous_tool", answer)
        self.assertIn("instead of answering directly", answer)

    # --- situation A: text + tool call → prefer the emitted text ----------- #
    async def test_text_plus_tool_call_returns_text(self):
        # Model emits BOTH a text message and a tool call in the same turn.
        model = _ScriptedModel([[_text_item("here is my partial answer"), _tool_call_item()]])
        exc = await self._run_until_max_turns(model)

        self.assertEqual(_SIDE_EFFECTS, [])
        answer = _btw_answer_from_failed_run(exc.run_data)
        self.assertEqual(answer, "here is my partial answer")

    # --- defensive: run_data=None falls back to generic 'a tool' ----------- #
    async def test_none_run_data_returns_generic_hint(self):
        answer = _btw_answer_from_failed_run(None)
        self.assertIn("a tool", answer)
        self.assertIn("instead of answering directly", answer)


if __name__ == "__main__":
    unittest.main()


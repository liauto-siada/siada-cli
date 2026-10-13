"""
Tests for the reasoning-only retry loop in ``siada.tools.agent.run_subtask``.

``run_subtask_impl`` does not call ``Runner.run_streamed`` once and read the
result directly: it drives ``_run_subtask_attempts``, an async generator that
yields one streamed result per attempt.  The caller consumes
``result.stream_events()`` for the yielded result and then resumes the
generator, and that resume is where the retry decision is made:

* retry when the finished result carries no usable output (``final_output`` is
  ``None`` or blank) *and* its last generated item is a bare
  ``agents.items.ReasoningItem`` — a possible incomplete completion, without
  establishing why the response ended;
* at most two retries (three attempts in total); once the budget is exhausted
  the generator raises ``RuntimeError("Sub-agent returned an empty
  reasoning-only result after 3 attempts.")``;
* every attempt reuses the same session / context / starting agent, and a retry
  submits a continuation directive instead of the original instruction, so the
  work already persisted in the session is not replayed;
* everything else ends the loop without a retry — normal text, a trailing
  ``MessageOutputItem`` with empty text, and an exception raised while consuming
  the stream (``CancelledError`` included), which must propagate unchanged.

``Runner.run_streamed`` is monkeypatched in every test, so no model call is
made.  The integration tests at the end drive ``run_subtask_impl`` itself with
its remaining dependencies mocked, mirroring ``test_run_subtask_display.py``.
"""

import asyncio
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agents.items import MessageOutputItem, ReasoningItem

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.agent.run_subtask import _run_subtask_attempts, run_subtask_impl
from siada.tools.agent.sub_agent_compaction_filter import InMemorySession


INSTRUCTION = "Find the root cause of the failing test and report it."

EXHAUSTED_ERROR_MESSAGE = (
    "Sub-agent returned an empty reasoning-only result after 3 attempts."
)


# ---------------------------------------------------------------------------
# Fakes and drivers
# ---------------------------------------------------------------------------

async def _empty_stream_events():
    """Stand-in for a stream that yields no events (an exhausted completion)."""
    return
    yield  # pragma: no cover - unreachable, keeps this an async generator


def _stream_that_raises(error):
    """Return an async-generator function whose consumption raises *error*."""
    async def _stream():
        raise error
        yield  # pragma: no cover - unreachable, keeps this an async generator

    return _stream


def _reasoning_only_result(final_output=None):
    """Streamed result whose last (and only) generated item is reasoning."""
    return SimpleNamespace(
        final_output=final_output,
        new_items=[MagicMock(spec=ReasoningItem)],
        stream_events=_empty_stream_events,
    )


def _text_result(text="Sub-agent finished the task."):
    """Streamed result that ends with a normal, non-empty output message."""
    return SimpleNamespace(
        final_output=text,
        new_items=[MagicMock(spec=MessageOutputItem)],
        stream_events=_empty_stream_events,
    )


def _empty_message_result(final_output=""):
    """Streamed result whose last item is an output message with no text."""
    message = MagicMock(spec=MessageOutputItem)
    message.raw_item = SimpleNamespace(content=[])
    return SimpleNamespace(
        final_output=final_output,
        new_items=[message],
        stream_events=_empty_stream_events,
    )


def _streamed_kwargs(mock_run_streamed):
    """Keyword arguments of every ``Runner.run_streamed`` call, in order."""
    return [call.kwargs for call in mock_run_streamed.call_args_list]


async def _consume_attempts(attempts, attempts_sink):
    """Drive an ``_run_subtask_attempts`` generator the way its caller does.

    Each yielded result's event stream is consumed before the generator is
    resumed for the next attempt; the generator is closed on the way out so a
    failed stream never leaves a live attempt behind.
    """
    try:
        async for result in attempts:
            attempts_sink.append(result)
            async for _event in result.stream_events():
                pass
    finally:
        await attempts.aclose()


class _AttemptTestBase(unittest.IsolatedAsyncioTestCase):
    """Shared run kwargs plus a ``Runner.run_streamed`` patch for one attempt run."""

    def setUp(self):
        self.session = InMemorySession()
        self.starting_agent = MagicMock(name="starting_agent")
        self.context = MagicMock(name="sub_agent_context")
        self.run_config = MagicMock(name="run_config")

    def _run_kwargs(self):
        return dict(
            starting_agent=self.starting_agent,
            input=INSTRUCTION,
            context=self.context,
            run_config=self.run_config,
            max_turns=7,
            session=self.session,
        )

    def _patched_runner(self, results):
        """Patch ``Runner.run_streamed`` to return *results* in order."""
        return patch(
            "siada.tools.agent.run_subtask.Runner.run_streamed",
            side_effect=list(results),
        )


# ---------------------------------------------------------------------------
# 1. Retry decision: only an empty, reasoning-only result is retried
# ---------------------------------------------------------------------------

class TestAttemptRetryDecision(_AttemptTestBase):
    async def test_normal_text_result_is_not_retried(self):
        result = _text_result("Root cause: the fixture is missing.")
        attempts = []

        with self._patched_runner([result, _text_result("unexpected retry")]) as mock_run:
            await _consume_attempts(
                _run_subtask_attempts(**self._run_kwargs()), attempts
            )

        self.assertEqual(attempts, [result])
        self.assertEqual(mock_run.call_count, 1)

    async def test_empty_message_result_is_not_retried(self):
        for final_output in ("", None):
            with self.subTest(final_output=final_output):
                result = _empty_message_result(final_output)
                attempts = []

                with self._patched_runner(
                    [result, _text_result("unexpected retry")]
                ) as mock_run:
                    await _consume_attempts(
                        _run_subtask_attempts(**self._run_kwargs()), attempts
                    )

                self.assertEqual(attempts, [result])
                self.assertEqual(mock_run.call_count, 1)

    async def test_reasoning_item_with_non_empty_output_is_not_retried(self):
        result = _reasoning_only_result(final_output="Here is the answer.")
        attempts = []

        with self._patched_runner([result, _text_result("unexpected retry")]) as mock_run:
            await _consume_attempts(
                _run_subtask_attempts(**self._run_kwargs()), attempts
            )

        self.assertEqual(attempts, [result])
        self.assertEqual(mock_run.call_count, 1)

    async def test_result_without_new_items_is_not_retried(self):
        result = SimpleNamespace(
            final_output=None,
            new_items=[],
            stream_events=_empty_stream_events,
        )
        attempts = []

        with self._patched_runner([result, _text_result("unexpected retry")]) as mock_run:
            await _consume_attempts(
                _run_subtask_attempts(**self._run_kwargs()), attempts
            )

        self.assertEqual(attempts, [result])
        self.assertEqual(mock_run.call_count, 1)

    async def test_empty_reasoning_only_result_is_retried_then_exhausted(self):
        for final_output in (None, "", "   \n"):
            with self.subTest(final_output=final_output):
                results = [_reasoning_only_result(final_output) for _ in range(3)]
                attempts = []

                with self._patched_runner(results) as mock_run:
                    with self.assertRaises(RuntimeError) as raised:
                        await _consume_attempts(
                            _run_subtask_attempts(**self._run_kwargs()), attempts
                        )

                self.assertEqual(str(raised.exception), EXHAUSTED_ERROR_MESSAGE)
                self.assertEqual(mock_run.call_count, 3)
                for attempt, result in zip(attempts, results):
                    self.assertIs(attempt, result)

    async def test_retry_reuses_session_context_and_agent(self):
        results = [
            _reasoning_only_result(),
            _reasoning_only_result(),
            _text_result("Recovered summary."),
        ]
        attempts = []

        with self._patched_runner(results) as mock_run:
            await _consume_attempts(
                _run_subtask_attempts(**self._run_kwargs()), attempts
            )

        self.assertEqual(attempts, results)

        calls = _streamed_kwargs(mock_run)
        self.assertEqual(len(calls), 3)
        for call in calls:
            # Same objects on every attempt: the work already persisted in the
            # session is continued instead of restarting the run.
            self.assertIs(call["session"], self.session)
            self.assertIs(call["context"], self.context)
            self.assertIs(call["starting_agent"], self.starting_agent)
            self.assertIs(call["run_config"], self.run_config)
            self.assertEqual(call["max_turns"], 7)

        inputs = [call["input"] for call in calls]
        # The original instruction is submitted exactly once; every retry sends
        # a continuation directive instead of re-submitting it.
        self.assertEqual(inputs[0], INSTRUCTION)
        for retry_input in inputs[1:]:
            self.assertIsInstance(retry_input, str)
            self.assertTrue(
                retry_input.strip(), "a retry must send a non-empty continuation directive"
            )
            self.assertNotEqual(retry_input, INSTRUCTION)

    async def test_stream_exception_propagates_without_retry(self):
        error = RuntimeError("stream exploded")
        result = _text_result()
        result.stream_events = _stream_that_raises(error)
        attempts = []

        with self._patched_runner([result, _text_result("unexpected retry")]) as mock_run:
            with self.assertRaises(RuntimeError) as raised:
                await _consume_attempts(
                    _run_subtask_attempts(**self._run_kwargs()), attempts
                )

        self.assertIs(raised.exception, error)
        self.assertEqual(attempts, [result])
        self.assertEqual(mock_run.call_count, 1)

    async def test_cancelled_error_propagates_without_retry(self):
        error = asyncio.CancelledError("consumer cancelled")
        result = _text_result()
        result.stream_events = _stream_that_raises(error)
        attempts = []

        with self._patched_runner([result, _text_result("unexpected retry")]) as mock_run:
            with self.assertRaises(asyncio.CancelledError) as raised:
                await _consume_attempts(
                    _run_subtask_attempts(**self._run_kwargs()), attempts
                )

        self.assertIs(raised.exception, error)
        self.assertEqual(attempts, [result])
        self.assertEqual(mock_run.call_count, 1)


# ---------------------------------------------------------------------------
# 2. run_subtask_impl integration: failure reporting and MCP cleanup
# ---------------------------------------------------------------------------

def _make_agent_context():
    """Minimal ``CodeAgentContext`` stand-in for ``run_subtask_impl``."""
    agent_context = MagicMock(spec=CodeAgentContext)
    agent_context.root_dir = "/tmp"
    agent_context.session = MagicMock(name="parent_session")
    agent_context.provider = "default"
    agent_context.web_tools_enabled = None
    agent_context.sub_agent_items = []
    agent_context.allow_recursive_subagents = False
    agent_context.root_session_id = None
    agent_context.subagent_self_id = None
    return agent_context


def _make_agent_definition():
    """User-defined agent stand-in; its MCP servers must be opened and closed."""
    definition = MagicMock(name="agent_definition")
    definition.name = "demo-agent"
    definition.prompt = "Answer the task using the demo MCP server."
    definition.mcp_servers = ("demo-mcp-server",)
    return definition


class _RecordingMcpServers:
    """Async context manager recording what ``open_agent_mcp_servers`` returns."""

    def __init__(self):
        self.enter_count = 0
        self.exit_count = 0

    async def __aenter__(self):
        self.enter_count += 1
        return ["demo-mcp-server"]

    async def __aexit__(self, exc_type, exc, tb):
        self.exit_count += 1
        return False


class _MockedSubtaskRun:
    """Patch every ``run_subtask_impl`` dependency and record what it did."""

    def __init__(self, results, *, with_definition=False):
        self.results = list(results)
        self.agent_context = _make_agent_context()
        self.agent_definition = _make_agent_definition() if with_definition else None
        self.mcp_servers = _RecordingMcpServers()
        self.finishes = []  # (status, summary) pairs, in call order
        self.pushes = []  # sub-agent detail-view entry kinds, in call order
        self._stack = ExitStack()

    def __enter__(self):
        self._stack.__enter__()
        try:
            self.run_streamed = self._stack.enter_context(
                patch(
                    "siada.tools.agent.run_subtask.Runner.run_streamed",
                    side_effect=list(self.results),
                )
            )
            self.subtask_agent = self._stack.enter_context(
                patch("siada.tools.agent.run_subtask.SubTaskAgent")
            )
            self._stack.enter_context(
                patch(
                    "siada.tools.agent.run_subtask.start_sub_agent",
                    return_value=MagicMock(id="sa_retry"),
                )
            )
            self._stack.enter_context(
                patch(
                    "siada.tools.agent.run_subtask.finish_sub_agent",
                    side_effect=lambda _ctx, _id, status, summary: self.finishes.append(
                        (status, summary)
                    ),
                )
            )
            self._stack.enter_context(
                patch(
                    "siada.tools.agent.run_subtask.push_sub_agent_message",
                    side_effect=lambda _id, kind, _content, **_kwargs: self.pushes.append(
                        kind
                    ),
                )
            )
            self._stack.enter_context(
                patch(
                    "siada.tools.agent.run_subtask.load_preloaded_skills",
                    return_value=[],
                )
            )
            self._stack.enter_context(
                patch("siada.tools.agent.run_subtask._build_default_tools", return_value=[])
            )
            self._stack.enter_context(
                patch("siada.tools.agent.run_subtask.filter_tools_for_agent", return_value=[])
            )
            self._stack.enter_context(
                patch(
                    "siada.tools.agent.run_subtask.open_agent_mcp_servers",
                    return_value=self.mcp_servers,
                )
            )
        except BaseException:
            self._stack.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._stack.__exit__(exc_type, exc, tb)

    async def run(self, instruction=INSTRUCTION):
        """Invoke the implementation under test with the mocked dependencies."""
        return await run_subtask_impl(
            instruction=instruction,
            agent_context=self.agent_context,
            run_config=MagicMock(name="run_config"),
            agent_definition=self.agent_definition,
        )

    @property
    def streamed_kwargs(self):
        """Keyword arguments of every ``Runner.run_streamed`` call, in order."""
        return _streamed_kwargs(self.run_streamed)

    @property
    def finish_statuses(self):
        return [status for status, _summary in self.finishes]


class TestRunSubtaskImplRetryIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_normal_text_completes_once_without_retry(self):
        result = _text_result("The task is done.")

        with _MockedSubtaskRun([result, _text_result("unexpected retry")]) as run:
            summary = await run.run()

        self.assertEqual(summary, "The task is done.")
        self.assertEqual(run.run_streamed.call_count, 1)
        self.assertEqual(run.subtask_agent.call_count, 1)
        self.assertEqual(run.finish_statuses, ["completed"])
        self.assertEqual(run.finishes[0][1], "The task is done.")
        self.assertIn("message", run.pushes)

    async def test_retry_after_reasoning_only_result_completes_with_retry_summary(self):
        results = [_reasoning_only_result(), _text_result("Recovered summary.")]

        with _MockedSubtaskRun(results) as run:
            summary = await run.run()

        self.assertEqual(summary, "Recovered summary.")
        self.assertEqual(run.run_streamed.call_count, 2)
        # One SubTaskAgent (and one session/context) is built for the whole
        # retry loop, not rebuilt per attempt.
        self.assertEqual(run.subtask_agent.call_count, 1)

        calls = run.streamed_kwargs
        self.assertIsInstance(calls[0]["session"], InMemorySession)
        self.assertEqual(calls[0]["input"], INSTRUCTION)
        self.assertNotEqual(calls[1]["input"], INSTRUCTION)
        self.assertIs(calls[1]["session"], calls[0]["session"])
        self.assertIs(calls[1]["context"], calls[0]["context"])
        self.assertIs(calls[1]["starting_agent"], calls[0]["starting_agent"])

        self.assertEqual(run.finish_statuses, ["completed"])
        self.assertEqual(run.finishes[0][1], "Recovered summary.")

    async def test_exhausted_retries_fail_sub_agent_and_close_mcp_servers(self):
        results = [_reasoning_only_result() for _ in range(3)]

        with _MockedSubtaskRun(results, with_definition=True) as run:
            with self.assertRaises(RuntimeError) as raised:
                await run.run()

        self.assertEqual(str(raised.exception), EXHAUSTED_ERROR_MESSAGE)
        self.assertEqual(run.run_streamed.call_count, 3)

        calls = run.streamed_kwargs
        self.assertIsInstance(calls[0]["session"], InMemorySession)
        # The original instruction is submitted once; both retries continue the
        # existing session with a continuation directive.
        self.assertEqual(calls[0]["input"], INSTRUCTION)
        for call in calls[1:]:
            self.assertNotEqual(call["input"], INSTRUCTION)
            self.assertIs(call["session"], calls[0]["session"])
            self.assertIs(call["context"], calls[0]["context"])
            self.assertIs(call["starting_agent"], calls[0]["starting_agent"])

        # Exactly one terminal notification, and it is the failure path: no
        # "completed" status (and no summary) is ever reported for this run.
        self.assertEqual(run.finish_statuses, ["failed"])
        self.assertEqual(run.finishes[0][1], EXHAUSTED_ERROR_MESSAGE)
        self.assertNotIn("message", run.pushes)

        # The definition's MCP servers were connected for the run and must be
        # closed even though the retry budget was exhausted.
        self.assertEqual(run.mcp_servers.enter_count, 1)
        self.assertEqual(run.mcp_servers.exit_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

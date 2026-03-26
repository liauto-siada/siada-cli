"""
Tests for run_subtask display behaviour.

Verifies that:
1. RunSubtaskFormatter correctly extracts the task summary from the instruction.
2. The run_subtask stream handler calls the same IO methods that
   conversation_turn.output_stream_content uses, specifically:
     - ToolCallItem  → io.advance_tool_call_stage() + io.print_tool_call_all_stages(content, final=True)
                       (NOT io.print_tool_call which has no lifecycle-event path)
     - ToolCallOutputItem → render_tool_call_output (type-aware dispatch, not bare str())
     - MessageOutputItem  → io.acp_thinking() (thinking-style, NOT io.print_info which
                            sends a tool_use lifecycle event the frontend renders as a box)
"""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call

from agents import RunItemStreamEvent
from agents.items import ToolCallItem, ToolCallOutputItem, MessageOutputItem, ResponseFunctionToolCall
from agents import ToolOutputText, ToolOutputImage

from siada.tools.tool_call_format.formatters import RunSubtaskFormatter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool_call_event(tool_name: str, arguments: str, call_id: str = "call_1") -> RunItemStreamEvent:
    """Build a RunItemStreamEvent wrapping a ToolCallItem."""
    raw = MagicMock(spec=ResponseFunctionToolCall)
    raw.name = tool_name
    raw.call_id = call_id
    raw.arguments = arguments

    item = MagicMock(spec=ToolCallItem)
    item.raw_item = raw

    event = MagicMock(spec=RunItemStreamEvent)
    event.item = item
    return event


def _make_tool_output_event(output) -> RunItemStreamEvent:
    """Build a RunItemStreamEvent wrapping a ToolCallOutputItem."""
    item = MagicMock(spec=ToolCallOutputItem)
    item.output = output

    event = MagicMock(spec=RunItemStreamEvent)
    event.item = item
    return event


def _make_message_event(text: str) -> RunItemStreamEvent:
    """Build a RunItemStreamEvent wrapping a MessageOutputItem."""
    part = MagicMock()
    part.type = "output_text"
    part.text = text

    raw_item = MagicMock()
    raw_item.content = [part]

    item = MagicMock(spec=MessageOutputItem)
    item.raw_item = raw_item

    event = MagicMock(spec=RunItemStreamEvent)
    event.item = item
    return event


def _make_mock_io(acp_enabled: bool = True):
    """Return a mock IO object that records method calls."""
    io = MagicMock()
    io.acp_enabled = acp_enabled
    return io


async def _run_events(events, io):
    """Drive run_subtask_impl with a fixed set of stream events and a mock IO."""
    from siada.agent_hub.coder.sub_task_agent import SubTaskResult

    fake_result = MagicMock()

    async def _stream():
        for e in events:
            yield e

    fake_result.stream_events = _stream
    fake_result.final_output = SubTaskResult(status="completed", summary="done")

    agent_ctx = MagicMock()
    agent_ctx.root_dir = "/tmp"
    agent_ctx.session.siada_config.io = io

    with patch("siada.tools.agent.run_subtask.Runner.run_streamed", return_value=fake_result), \
         patch("siada.tools.agent.run_subtask.build_sub_agent_run_config", return_value=MagicMock()), \
         patch("siada.tools.agent.run_subtask.SubTaskAgent", return_value=MagicMock()):
        from siada.tools.agent.run_subtask import run_subtask_impl
        return await run_subtask_impl(
            instruction="test",
            agent_context=agent_ctx,
            run_config=MagicMock(),
        )


# ---------------------------------------------------------------------------
# Part 1 – RunSubtaskFormatter
# ---------------------------------------------------------------------------

class TestRunSubtaskFormatter(unittest.TestCase):
    """RunSubtaskFormatter must extract the task line that follows 'Your task:'."""

    def setUp(self):
        self.fmt = RunSubtaskFormatter()

    def _instruction(self, task_line: str) -> str:
        return (
            "Design document: /tmp/design.md\n\n"
            "Previous step result:\nN/A\n\n"
            f"Your task:\n{task_line}\n\n"
            "---\nSome context here."
        )

    def test_task_on_next_line(self):
        """Standard format: 'Your task:' on its own line, task on the next."""
        args = json.dumps({"instruction": self._instruction("Implement step 1: 新建微信公众号发布工具")})
        content, complete = self.fmt.format_input("c1", "run_subtask", args)
        self.assertEqual(content, "Sub-agent task: Implement step 1: 新建微信公众号发布工具")
        self.assertTrue(complete)

    def test_task_inline_after_colon(self):
        """Less common: task description on the same line as 'Your task:'."""
        args = json.dumps({"instruction": "Design doc: x\n\nYour task: Create the module\n"})
        content, complete = self.fmt.format_input("c1", "run_subtask", args)
        self.assertEqual(content, "Sub-agent task: Create the module")
        self.assertTrue(complete)

    def test_fallback_to_first_line_when_no_your_task(self):
        """If no 'Your task:' header, fall back to the first non-empty line."""
        args = json.dumps({"instruction": "Do something important\nwith details below."})
        content, complete = self.fmt.format_input("c1", "run_subtask", args)
        self.assertTrue(content.startswith("Sub-agent task:"))
        self.assertIn("Do something important", content)

    def test_invalid_json_returns_generic_label(self):
        """Malformed JSON must not raise; return a generic label."""
        content, complete = self.fmt.format_input("c1", "run_subtask", "{bad json")
        self.assertEqual(content, "Sub-agent task")
        self.assertTrue(complete)

    def test_empty_instruction(self):
        args = json.dumps({"instruction": ""})
        content, complete = self.fmt.format_input("c1", "run_subtask", args)
        self.assertEqual(content, "Sub-agent task")
        self.assertTrue(complete)

    def test_supported_function(self):
        self.assertEqual(self.fmt.supported_function, "run_subtask")


# ---------------------------------------------------------------------------
# Part 2 – Stream event handling (mirrors conversation_turn behaviour)
# ---------------------------------------------------------------------------

class TestRunSubtaskStreamDisplay(unittest.TestCase):
    """
    Verify run_subtask_impl routes each RunItemStreamEvent to the correct IO method.

    Reference: conversation_turn.output_stream_content uses:
      - ResponseOutputItemDoneEvent  → io.advance_tool_call_stage()
                                     + io.print_tool_call_all_stages(content, final=True)
      - RunItemStreamEvent/ToolCallOutputItem → render_tool_call_output (type dispatch)
      - (no MessageOutputItem in parent turn; sub-agent text → thinking style)
    """

    def _run(self, events, io):
        return asyncio.run(_run_events(events, io))

    # -- ToolCallItem ---------------------------------------------------------

    def test_tool_call_uses_all_stages_not_print_tool_call(self):
        """
        ToolCallItem must call advance_tool_call_stage + print_tool_call_all_stages(final=True).
        io.print_tool_call must NOT be called (it has no lifecycle-event path to the frontend).
        """
        io = _make_mock_io()
        args = json.dumps({"command": "view", "path": "/tmp/foo.py"})
        events = [_make_tool_call_event("edit_file", args)]

        self._run(events, io)

        io.advance_tool_call_stage.assert_called_once()
        # print_tool_call_all_stages must be called with final=True
        calls = io.print_tool_call_all_stages.call_args_list
        self.assertTrue(len(calls) >= 1, "print_tool_call_all_stages not called")
        _, kwargs = calls[-1]
        self.assertTrue(kwargs.get("final", False), "print_tool_call_all_stages not called with final=True")
        # The old, lifecycle-event-less method must NOT be used
        io.print_tool_call.assert_not_called()

    def test_tool_call_content_goes_through_formatter(self):
        """
        The content passed to print_tool_call_all_stages must come from the formatter,
        not be a raw JSON dump or just the tool name.
        """
        io = _make_mock_io()
        args = json.dumps({"command": "view", "path": "/tmp/important.py"})
        events = [_make_tool_call_event("edit_file", args)]

        self._run(events, io)

        call_args = io.print_tool_call_all_stages.call_args_list[-1]
        content = call_args[0][0] if call_args[0] else call_args[1].get("message", "")
        # The formatter for edit_file should produce something nicer than raw JSON
        self.assertNotEqual(content, args, "Content should be formatted, not raw JSON")

    # -- ToolCallOutputItem ---------------------------------------------------

    def test_tool_output_str_uses_print_tool_result(self):
        """Plain string output calls io.print_tool_result with that string."""
        io = _make_mock_io()
        events = [_make_tool_output_event("file content here")]

        self._run(events, io)

        io.print_tool_result.assert_called_once_with("file content here")

    def test_tool_output_tool_output_text_unwraps_text(self):
        """ToolOutputText output calls io.print_tool_result with .text, not str(obj)."""
        io = _make_mock_io()
        output = MagicMock(spec=ToolOutputText)
        output.text = "unwrapped text content"
        events = [_make_tool_output_event(output)]

        self._run(events, io)

        io.print_tool_result.assert_called_once_with("unwrapped text content")

    def test_tool_output_tool_output_image_shows_placeholder(self):
        """ToolOutputImage calls io.print_tool_result with a human-readable placeholder."""
        io = _make_mock_io()
        output = MagicMock(spec=ToolOutputImage)
        events = [_make_tool_output_event(output)]

        self._run(events, io)

        io.print_tool_result.assert_called_once_with("✓ Image loaded successfully")

    def test_tool_output_format_for_display_called_when_available(self):
        """Outputs that have format_for_display() (e.g. FunctionCallResult) use it."""
        io = _make_mock_io()
        output = MagicMock()
        output.format_for_display.return_value = "nicely formatted result"
        # Remove ToolOutputText/ToolOutputImage from spec so only duck-type check applies
        del output.text
        events = [_make_tool_output_event(output)]

        self._run(events, io)

        output.format_for_display.assert_called_once()
        io.print_tool_result.assert_called_once_with("nicely formatted result")

    # -- MessageOutputItem ----------------------------------------------------

    def test_message_output_uses_acp_thinking_not_print_info(self):
        """
        Sub-agent planning text (MessageOutputItem) must go to acp_thinking,
        which the frontend renders as collapsible thinking — not print_info
        which sends a tool_use lifecycle event and renders as a box.
        """
        io = _make_mock_io(acp_enabled=True)
        events = [_make_message_event("Now let me look at the existing tools...")]

        self._run(events, io)

        io.acp_thinking.assert_called_once_with("Now let me look at the existing tools...")
        io.print_info.assert_not_called()

    def test_message_output_non_acp_uses_dim_console_print(self):
        """In non-ACP (terminal) mode, sub-agent text is printed dim, not via print_info."""
        io = _make_mock_io(acp_enabled=False)
        events = [_make_message_event("Planning step...")]

        self._run(events, io)

        # acp_thinking is still called (it's a no-op when acp_enabled=False)
        io.acp_thinking.assert_called_once()
        # Console dim print must happen
        io.console.print.assert_called_once_with("Planning step...", style="dim")
        io.print_info.assert_not_called()

    # -- Order sanity ---------------------------------------------------------

    def test_mixed_events_processed_in_order(self):
        """All three event types in sequence all produce output."""
        io = _make_mock_io()
        events = [
            _make_tool_call_event("edit_file", json.dumps({"command": "view", "path": "/x"})),
            _make_tool_output_event("result text"),
            _make_message_event("I have finished."),
        ]

        self._run(events, io)

        io.advance_tool_call_stage.assert_called_once()
        io.print_tool_call_all_stages.assert_called()
        io.print_tool_result.assert_called_once_with("result text")
        io.acp_thinking.assert_called_once_with("I have finished.")


if __name__ == "__main__":
    unittest.main(verbosity=2)

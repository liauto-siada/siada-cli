"""
Tests for run_subtask display behaviour.

Verifies that:
1. RunSubtaskFormatter correctly extracts the task summary from the instruction.
2. Sub-agent stream events are NOT rendered to the main message flow (no
   tool-call boxes, tool results, or thinking text) — content is pushed only
   to the sub-agent detail view via ACP (sub_agent_notifier).
3. The notifier wiring: start → per-event content entries → completed/failed.
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
    fake_result = MagicMock()

    async def _stream():
        for e in events:
            yield e

    fake_result.stream_events = _stream
    fake_result.final_output = "done"

    agent_ctx = MagicMock()
    agent_ctx.root_dir = "/tmp"
    agent_ctx.session.siada_config.io = io
    agent_ctx.sub_agent_items = []
    # A bare MagicMock() attribute is truthy by default, which would make
    # run_subtask_impl's `agent_context.allow_recursive_subagents` check
    # spuriously True and attempt on-disk persistence against mock paths.
    agent_ctx.allow_recursive_subagents = False
    agent_ctx.root_session_id = None

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
# Part 2 – Stream events never reach the main-flow IO (hidden by design)
# ---------------------------------------------------------------------------

class TestRunSubtaskStreamHidden(unittest.TestCase):
    """
    Sub-agent stream events must NOT reach the main-flow IO at all.

    The main conversation stays clean while a sub agent runs: no tool-call
    boxes, no tool results, no thinking text. Everything is available via the
    Sub Agents panel → Enter detail view (fed by sub_agent_notifier pushes,
    covered in TestSubAgentNotifications).
    """

    def _run(self, events, io):
        return asyncio.run(_run_events(events, io))

    def _assert_no_main_flow_rendering(self, io):
        io.advance_tool_call_stage.assert_not_called()
        io.print_tool_call_all_stages.assert_not_called()
        io.print_tool_call.assert_not_called()
        io.print_tool_result.assert_not_called()
        io.acp_thinking.assert_not_called()
        io.console.print.assert_not_called()
        io.print_info.assert_not_called()

    def test_tool_call_not_rendered(self):
        io = _make_mock_io()
        events = [_make_tool_call_event("edit_file", json.dumps({"command": "view", "path": "/tmp/foo.py"}))]

        self._run(events, io)

        self._assert_no_main_flow_rendering(io)

    def test_tool_output_not_rendered(self):
        io = _make_mock_io()
        events = [_make_tool_output_event("file content here")]

        self._run(events, io)

        self._assert_no_main_flow_rendering(io)

    def test_message_output_not_rendered_acp_and_terminal(self):
        for acp_enabled in (True, False):
            with self.subTest(acp_enabled=acp_enabled):
                io = _make_mock_io(acp_enabled=acp_enabled)
                events = [_make_message_event("planning text")]

                self._run(events, io)

                self._assert_no_main_flow_rendering(io)

    def test_mixed_events_nothing_rendered(self):
        io = _make_mock_io()
        events = [
            _make_tool_call_event("edit_file", json.dumps({"command": "view", "path": "/x"})),
            _make_tool_output_event("result text"),
            _make_message_event("I have finished."),
        ]

        self._run(events, io)

        self._assert_no_main_flow_rendering(io)


# ---------------------------------------------------------------------------
# Part 3 – Sub-agent ACP notifications (sub_agent_notifier wiring)
# ---------------------------------------------------------------------------

class TestSubAgentNotifications(unittest.TestCase):
    def _run_with_events(self, events):
        io = _make_mock_io()
        agent_ctx = MagicMock()
        agent_ctx.root_dir = "/tmp"
        agent_ctx.session.siada_config.io = io
        agent_ctx.sub_agent_items = []
        agent_ctx.allow_recursive_subagents = False
        agent_ctx.root_session_id = None

        fake_result = MagicMock()

        async def _stream():
            for e in events:
                yield e

        fake_result.stream_events = _stream
        fake_result.final_output = "final summary"

        with patch("siada.tools.agent.run_subtask.Runner.run_streamed", return_value=fake_result), \
             patch("siada.tools.agent.run_subtask.build_sub_agent_run_config", return_value=MagicMock()), \
             patch("siada.tools.agent.run_subtask.SubTaskAgent", return_value=MagicMock()), \
             patch("siada.tools.agent.run_subtask.start_sub_agent") as mock_start, \
             patch("siada.tools.agent.run_subtask.push_sub_agent_message") as mock_push, \
             patch("siada.tools.agent.run_subtask.finish_sub_agent") as mock_finish:
            mock_start.return_value = MagicMock(id="sa_test1234")
            from siada.tools.agent.run_subtask import run_subtask_impl
            result = asyncio.run(run_subtask_impl(
                instruction="test",
                agent_context=agent_ctx,
                run_config=MagicMock(),
            ))
        return result, mock_start, mock_push, mock_finish

    def test_start_called_before_run(self):
        _, mock_start, _, _ = self._run_with_events([])
        mock_start.assert_called_once()
        self.assertEqual(mock_start.call_args[0][1], "test")

    def test_events_push_entries_and_finish_completed(self):
        events = [
            _make_tool_call_event("run_cmd", '{"command": "ls"}'),
            _make_tool_output_event("ok"),
            _make_message_event("thinking…"),
        ]
        _, mock_start, mock_push, mock_finish = self._run_with_events(events)
        kinds = [c.args[1] for c in mock_push.call_args_list]
        self.assertEqual(kinds, ["tool_call", "tool_output", "thinking", "message"])
        self.assertTrue(all(c.args[0] == "sa_test1234" for c in mock_push.call_args_list))
        mock_finish.assert_called_once()
        self.assertEqual(mock_finish.call_args[0][2], "completed")
        self.assertEqual(mock_finish.call_args[0][3], "final summary")

    def test_exception_pushes_failed_and_reraises(self):
        io = _make_mock_io()
        agent_ctx = MagicMock()
        agent_ctx.root_dir = "/tmp"
        agent_ctx.session.siada_config.io = io
        agent_ctx.sub_agent_items = []
        agent_ctx.allow_recursive_subagents = False
        agent_ctx.root_session_id = None

        with patch("siada.tools.agent.run_subtask.Runner.run_streamed", side_effect=RuntimeError("boom")), \
             patch("siada.tools.agent.run_subtask.build_sub_agent_run_config", return_value=MagicMock()), \
             patch("siada.tools.agent.run_subtask.SubTaskAgent", return_value=MagicMock()), \
             patch("siada.tools.agent.run_subtask.start_sub_agent") as mock_start, \
             patch("siada.tools.agent.run_subtask.push_sub_agent_message"), \
             patch("siada.tools.agent.run_subtask.finish_sub_agent") as mock_finish:
            mock_start.return_value = MagicMock(id="sa_test1234")
            from siada.tools.agent.run_subtask import run_subtask_impl
            with self.assertRaises(RuntimeError):
                asyncio.run(run_subtask_impl(
                    instruction="test",
                    agent_context=agent_ctx,
                    run_config=MagicMock(),
                ))
        mock_finish.assert_called_once()
        self.assertEqual(mock_finish.call_args[0][2], "failed")
        self.assertIn("boom", mock_finish.call_args[0][3])

    def test_tool_output_push_uses_extracted_text(self):
        output = MagicMock(spec=ToolOutputText)
        output.text = "unwrapped text content"
        _, _, mock_push, _ = self._run_with_events([_make_tool_output_event(output)])
        first = mock_push.call_args_list[0]
        self.assertEqual(first.args[1], "tool_output")
        self.assertEqual(first.args[2], "unwrapped text content")

    def test_tool_output_to_text_variants(self):
        from siada.tools.agent.run_subtask import _tool_output_to_text
        self.assertEqual(_tool_output_to_text(None), "")
        self.assertEqual(_tool_output_to_text("plain"), "plain")
        text_out = MagicMock(spec=ToolOutputText)
        text_out.text = "inner"
        self.assertEqual(_tool_output_to_text(text_out), "inner")
        img_out = MagicMock(spec=ToolOutputImage)
        self.assertEqual(_tool_output_to_text(img_out), "✓ Image loaded successfully")
        fmt = MagicMock()
        fmt.format_for_display.return_value = "formatted"
        self.assertEqual(_tool_output_to_text(fmt), "formatted")


if __name__ == "__main__":
    unittest.main(verbosity=2)

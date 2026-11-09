"""Freeze legacy trace messages while moving console writes to presentation."""

import threading
from datetime import datetime
from types import SimpleNamespace

import pytest
from agents import Agent, RunConfig, function_tool
from agents.testing import ScriptedModel, assistant_message, function_call
from agents.tracing import generation_span
from agents.tracing.provider import DefaultTraceProvider

from siada.foundation.agent_logging import LoggingRunner

from siada.agent_hub.coder.tracing import logger_tracing_processor as tracing
from siada.entrypoint.interaction.console_progress import ConsoleProgressPresenter
from siada.foundation.execution_progress import execution_progress_scope


# Captured from the legacy processor with only synthetic data and a fixed clock.
LEGACY_LINES = [
    "", "🚀 === TRACE STARTED ===", "Workflow: Synthetic Workflow",
    "Trace ID: trace_synthetic", "Group ID: synthetic-session", "Started: ",
    "=========================", "", "", "🤖 === MODEL CALL 1 ===",
    "Model: synthetic-model", "📥 New Input Messages:", "  [user]: hello",
    "📤 Model Output:", "  💭 [reasoning]: think",
    '  🔧 Tool Call: lookup({"path":"sample"})',
    "📊 Usage: Input=11, Output=3, Total=14", "===================",
    "", "🔧 === TOOL CALL 1 ===", "Function: lookup",
    '📥 Input: {"path":"sample"}', "📤 Output: tool result",
    '🔗 MCP Data: {', '  "server": "synthetic"', "}", "===============",
    "", "🤖 === MODEL CALL 2 ===", "Model: synthetic-model",
    "📥 New Input Messages:", "  [tool]: tool result", "📤 Model Output:",
    "  [assistant]: done", "📊 Usage: Input=15, Output=2, Total=17",
    "===================", "==================", "", "🏁 === TRACE ENDED ===",
    "Workflow: Synthetic Workflow", "Duration: 0.0s", "Model Calls: 2",
    "Tool Calls: 1", "Handoffs: 1", "Tokens: Input=26, Output=5, Total=31",
    "======================", "",
]
LEGACY_TRANSCRIPT = "\n".join(LEGACY_LINES) + "\n"


class FixedClock(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 1, 2, 3, 4, 5)


@pytest.fixture
def processor(tmp_path, monkeypatch):
    monkeypatch.setattr(tracing, "datetime", FixedClock)
    return tracing.LoggerTracingProcessor(
        use_colors=False, show_timestamps=False, output_file=str(tmp_path / "trace.log"),
    )


def replay(processor):
    trace = SimpleNamespace(trace_id="trace_synthetic", name="Synthetic Workflow", group_id="synthetic-session")
    def span(kind, **data):
        return SimpleNamespace(trace_id=trace.trace_id, span_data=SimpleNamespace(type=kind, **data))
    model = span(
        "generation", model="synthetic-model",
        input=[{"role": "system", "content": "hidden"}, {"role": "user", "content": "hello"}],
        output=[{"type": "reasoning", "content": "think"}, {"type": "function_call", "name": "lookup", "arguments": '{"path":"sample"}'}],
        usage={"total_input_tokens": 11, "output_tokens": 3, "total_tokens": 14},
    )
    tool = span("function", name="lookup", input='{"path":"sample"}', output="tool result", mcp_data={"server": "synthetic"})
    final = span(
        "generation", model="synthetic-model",
        input=model.span_data.input + [{"role": "tool", "content": "tool result"}],
        output=[{"type": "message", "role": "assistant", "content": "done"}],
        usage={"total_input_tokens": 15, "output_tokens": 2, "total_tokens": 17},
    )
    processor.on_trace_start(trace)
    for item in [model, tool, final]:
        processor.on_span_start(item)
        processor.on_span_end(item)
    processor.on_span_end(span("handoff", to_agent="Verifier"))
    processor.on_trace_end(trace)


def test_trace_alone_only_writes_the_same_log(processor, capsys):
    replay(processor)
    assert capsys.readouterr().out == ""
    with open(processor.output_file, encoding="utf-8") as file:
        assert file.read() == LEGACY_TRANSCRIPT


def test_presenter_prints_byte_identical_legacy_transcript(processor, capsys):
    with ConsoleProgressPresenter() as presenter:
        with execution_progress_scope(presenter.channel):
            replay(processor)
    assert capsys.readouterr().out == LEGACY_TRANSCRIPT


def test_trace_never_calls_console_writer_on_its_callback_thread(processor):
    callers = []
    with ConsoleProgressPresenter(lambda message: callers.append(threading.current_thread().name)) as presenter:
        with execution_progress_scope(presenter.channel):
            replay(processor)
    assert callers
    assert set(callers) == {"siada-console-progress"}


def test_file_only_trace_does_not_publish_messages(processor):
    processor.console_output = False
    messages = []
    with ConsoleProgressPresenter(messages.append) as presenter:
        with execution_progress_scope(presenter.channel):
            replay(processor)
    assert messages == []
    with open(processor.output_file, encoding="utf-8") as file:
        assert file.read() == LEGACY_TRANSCRIPT


def test_colors_timestamps_and_indentation_stay_in_console_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tracing, "datetime", FixedClock)
    processor = tracing.LoggerTracingProcessor(output_file=str(tmp_path / "trace.log"), indent_level=1)
    with ConsoleProgressPresenter() as presenter:
        with execution_progress_scope(presenter.channel):
            replay(processor)
    output = capsys.readouterr().out
    assert output.startswith("  \n\033[95m\033[1m🚀 === TRACE STARTED ===\033[0m\n")
    assert "🕐 03:04:05 " in output
    expected_log = output
    for color in processor.colors.values():
        expected_log = expected_log.replace(color, "")
    with open(processor.output_file, encoding="utf-8") as file:
        assert file.read() == expected_log


def test_routed_subtask_logs_and_console_sequence_are_preserved(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tracing, "datetime", FixedClock)
    processor = tracing.LoggerTracingProcessor(
        output_file=str(tmp_path / "main.log"), use_colors=False, show_timestamps=False,
        file_router=lambda name: str(tmp_path / "subtask.log") if name == "SubTaskAgent" else None,
    )
    child = SimpleNamespace(trace_id="child", name="SubTaskAgent", group_id=None)
    with ConsoleProgressPresenter() as presenter:
        with execution_progress_scope(presenter.channel):
            processor.on_trace_start(child)
            replay(processor)
            processor.on_trace_end(child)
    output = capsys.readouterr().out
    assert output.count("TRACE STARTED") == output.count("TRACE ENDED") == 2
    assert output.index("Workflow: SubTaskAgent") < output.index("Workflow: Synthetic Workflow")
    assert (tmp_path / "main.log").read_text() == LEGACY_TRANSCRIPT
    assert "Workflow: SubTaskAgent" in (tmp_path / "subtask.log").read_text()


def test_file_write_failure_is_presented_with_the_original_warning(tmp_path, capsys):
    processor = tracing.LoggerTracingProcessor(output_file=str(tmp_path), use_colors=False)
    with ConsoleProgressPresenter() as presenter:
        with execution_progress_scope(presenter.channel):
            processor._print("message")
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "message"
    assert lines[1].startswith(f"Warning: Failed to write to file {tmp_path}:")


class TracedScriptedModel(ScriptedModel):
    """Populate deterministic provider-like spans without any model transport."""

    @staticmethod
    def fill(span, output):
        span.span_data.output = [item.model_dump() for item in output]
        span.span_data.usage = {"total_input_tokens": 7, "output_tokens": 2, "total_tokens": 9}

    async def get_response(self, *args, **kwargs):
        input_items = kwargs["input"] if "input" in kwargs else args[1]
        with generation_span(model="synthetic-model", input=input_items) as span:
            response = await super().get_response(*args, **kwargs)
            self.fill(span, response.output)
            return response

    async def stream_response(self, *args, **kwargs):
        input_items = kwargs["input"] if "input" in kwargs else args[1]
        with generation_span(model="synthetic-model", input=input_items) as span:
            async for event in super().stream_response(*args, **kwargs):
                if event.type == "response.completed":
                    self.fill(span, event.response.output)
                yield event


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_real_sdk_run_keeps_progress_and_file_transcript_identical(processor, monkeypatch, capsys, stream):
    from agents.tracing import setup

    provider = DefaultTraceProvider()
    provider.set_processors([processor])
    monkeypatch.setattr(setup, "GLOBAL_TRACE_PROVIDER", provider)
    actions = []

    @function_tool
    def lookup(path: str) -> str:
        """Return a deterministic local tool result."""
        actions.append(path)
        return "tool result"

    model = TracedScriptedModel([
        [function_call("lookup", {"path": "sample"}, call_id="synthetic-call")],
        [assistant_message("done")],
    ], emit_traces=False)
    agent = Agent(name="synthetic-agent", model=model, tools=[lookup])
    config = RunConfig(workflow_name="Synthetic Workflow", trace_id="trace_synthetic", group_id="synthetic-session")
    with ConsoleProgressPresenter() as presenter:
        with execution_progress_scope(presenter.channel):
            if stream:
                result = LoggingRunner.run_streamed(agent, input="hello", run_config=config)
                async for _ in result.stream_events():
                    pass
            else:
                result = await LoggingRunner.run(agent, input="hello", run_config=config)
            presenter.flush()
    output = capsys.readouterr().out
    assert result.final_output == "done"
    assert actions == ["sample"]
    assert output.count("MODEL CALL") == 2
    assert output.count("=== TOOL CALL") == 1
    assert "📥 Input: " in output and "📤 Output: tool result" in output
    assert "Tokens: Input=14, Output=4, Total=18" in output
    with open(processor.output_file, encoding="utf-8") as file:
        assert output == file.read()
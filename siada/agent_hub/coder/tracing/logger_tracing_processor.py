import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agents.tracing import TracingProcessor

# Module-level set to track which log-file glob patterns have already been
# cleaned up in this process (so cleanup runs at most once per pattern per run).
_cleaned_log_patterns: set = set()


def _ensure_log_cleanup(file_path: str) -> None:
    """Run 30-day log cleanup for a file's pattern, once per process per pattern.

    Derives the glob pattern from the file name, e.g.
    ``subtask_trace-20260610.log`` → ``subtask_trace-*.log``.
    """
    p = Path(file_path)
    # Strip the trailing 8-digit date segment to build the glob pattern
    stem = p.stem  # e.g. "subtask_trace-20260610"
    prefix = re.sub(r"-\d{8}$", "", stem)  # e.g. "subtask_trace"
    pattern = f"{prefix}-*.log"

    if pattern not in _cleaned_log_patterns:
        _cleaned_log_patterns.add(pattern)
        try:
            from siada.foundation.logging import cleanup_old_logs
            cleanup_old_logs(pattern, keep_days=30, log_directory=str(p.parent))
        except Exception:
            pass


@dataclass
class TraceState:
    """Track state information for a single Trace"""
    trace_id: str
    message_count: int = 0  # Number of printed messages
    agent_history: List[str] = field(default_factory=list)  # Agent switching history
    start_time: datetime = field(default_factory=datetime.now)
    handoff_count: int = 0  # Number of handoffs
    model_call_count: int = 0  # Number of model calls
    tool_call_count: int = 0  # Number of tool calls
    total_input_tokens: int = 0  # Total input tokens
    total_output_tokens: int = 0  # Total output tokens
    total_tokens: int = 0
    # Per-trace output file (overrides processor-level output_file when set)
    output_file: Optional[str] = None


class LoggerTracingProcessor(TracingProcessor):
    """
    Detailed reasoning process logger

    This TracingProcessor provides detailed visualization of the reasoning process, including:
        - Incremental input and complete output of model calls
        - Input/output details of tool calls
        - Complete record of Agent handoffs
        - Lifecycle tracking of the entire reasoning process

    Usage:
        from agents.tracing import add_trace_processor
        from examples.tracing.logger_tracing_processor import LoggerTracingProcessor

        # Register the processor
        add_trace_processor(LoggerTracingProcessor())

        # Then run the Agent normally
        result = await Runner.run(agent=your_agent, input="your input")
    """

    def __init__(
        self,
        show_model_calls: bool = True,
        show_tool_calls: bool = True,
        show_handoffs: bool = True,
        show_trace_lifecycle: bool = True,
        show_timestamps: bool = True,
        show_system_messages: bool = False,
        use_colors: bool = True,
        console_output: bool = True,
        output_file: Optional[str] = None,
        indent_level: int = 0,
        file_router: Optional[Callable[[str], str]] = None,
    ):
        """
        Initialize the logger

        Args:
            show_model_calls: Whether to show model calls
            show_tool_calls: Whether to show tool calls
            show_handoffs: Whether to show Agent handoffs
            show_trace_lifecycle: Whether to show Trace lifecycle
            show_timestamps: Whether to show timestamps
            show_system_messages: Whether to show system messages (default: False)
            use_colors: Whether to use colored output
            console_output: Whether to output to console (default: True)
            output_file: Default output file path (used when file_router is None or
                returns None)
            indent_level: Indentation level
            file_router: Optional callable ``(trace_name: str) -> str`` that returns
                the output file path for a given trace name.  When provided, each
                trace is written to the file path returned by this function,
                enabling per-trace log file routing (e.g. sub-agent traces to a
                separate file).
        """
        self.show_model_calls = show_model_calls
        self.show_tool_calls = show_tool_calls
        self.show_handoffs = show_handoffs
        self.show_trace_lifecycle = show_trace_lifecycle
        self.show_timestamps = show_timestamps
        self.show_system_messages = show_system_messages
        self.use_colors = use_colors
        self.console_output = console_output
        self.output_file = output_file
        self.indent_level = indent_level
        self.file_router = file_router

        # State tracking
        self.trace_states: Dict[str, TraceState] = {}

        # Color definitions
        self.colors = {
            'trace': '\033[95m',      # Purple
            'model': '\033[94m',      # Blue
            'tool': '\033[92m',       # Green
            'handoff': '\033[93m',    # Yellow
            'input': '\033[96m',      # Cyan
            'output': '\033[91m',     # Red
            'reset': '\033[0m',       # Reset
            'bold': '\033[1m',        # Bold
        } if use_colors else {k: '' for k in ['trace', 'model', 'tool', 'handoff', 'input', 'output', 'reset', 'bold']}

    def _print(self, message: str, output_file: Optional[str] = None) -> None:
        """Print message with file output support.

        Args:
            message: The message to print.
            output_file: Per-trace output file override.  When provided, takes
                precedence over ``self.output_file``.
        """
        indent = "  " * self.indent_level
        full_message = f"{indent}{message}"

        # Print to console only if console_output is enabled
        if self.console_output:
            print(full_message)

        # Determine which file to write to (per-trace override > processor default)
        effective_file = output_file or self.output_file
        if effective_file:
            try:
                with open(effective_file, 'a', encoding='utf-8') as f:
                    # Remove color codes for file output
                    clean_message = full_message
                    for color in self.colors.values():
                        clean_message = clean_message.replace(color, '')
                    f.write(clean_message + '\n')
            except Exception as e:
                # Only print warning to console if console output is enabled
                if self.console_output:
                    print(f"Warning: Failed to write to file {effective_file}: {e}")

    def _truncate_content(self, content: str, max_length: int = 8000) -> str:
        """Truncate overly long content"""
        if len(content) <= max_length:
            return content
        # return content[:max_length] + "..."
        return content

    def _format_timestamp(self) -> str:
        """Format timestamp"""
        if not self.show_timestamps:
            return ""
        return f"🕐 {datetime.now().strftime('%H:%M:%S')} "

    def _format_json(self, data: Any) -> str:
        """Format JSON data"""
        try:
            if isinstance(data, str):
                return data
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            return data

    def _print_incremental_messages(self, trace_id: str, messages: List[Dict[str, Any]]) -> None:
        """Print message list incrementally"""
        if not messages:
            return

        state = self.trace_states.get(trace_id)
        if not state:
            return

        output_file = state.output_file

        # Only print new messages
        new_messages = messages[state.message_count:]
        if not new_messages:
            return

        # Pre-filter messages to check if we have any to display
        messages_to_display = []
        for msg in new_messages:
            role = msg.get('role', 'unknown')
            # Skip system messages if show_system_messages is False
            if role == 'system' and not self.show_system_messages:
                continue
            messages_to_display.append(msg)

        # Only print header if we have messages to display
        if not messages_to_display:
            # Update the count even if no messages are displayed
            state.message_count = len(messages)
            return

        self._print(f"{self.colors['input']}📥 New Input Messages:{self.colors['reset']}", output_file)

        for msg in messages_to_display:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')

            # Handle different types of content
            if isinstance(content, list):
                # Multimodal content
                content_summary = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get('type') == 'text':
                            text_content = item.get('text', '')
                            content_summary.append(f"text: {self._truncate_content(str(text_content))}")

                        elif item.get('type') == 'image_url':
                            content_summary.append("image: [image data]")
                        else:
                            content_summary.append(f"{item.get('type', 'unknown')}: [data]")
                content_str = " | ".join(content_summary)
            else:
                content_str = self._truncate_content(str(content))

            self._print(f"  [{role}]: {re.sub(r'(data:image/jpeg;base64,)[^\"]*', r'\\1...', content_str)}", output_file)

        # Update the count of printed messages
        state.message_count = len(messages)

    def _format_model_output(self, output: List[Dict[str, Any]], output_file: Optional[str] = None) -> None:
        """Format model output"""
        self._print(f"{self.colors['output']}📤 Model Output:{self.colors['reset']}", output_file)

        for item in output:
            if isinstance(item, dict):
                # First check if there's a role field, which usually indicates a message
                if 'role' in item:
                    role = item.get('role', 'assistant')
                    content = item.get('content', '')
                    truncated_content = self._truncate_content(str(content))
                    self._print(f"  [{role}]: {truncated_content}", output_file)
                    continue

                # Check if there's a type field
                item_type = item.get('type')
                if item_type == 'reasoning':
                    # Reasoning / thinking output (e.g., Claude extended thinking)
                    content = item.get('content', '')
                    truncated_content = self._truncate_content(str(content))
                    self._print(f"  💭 [reasoning]: {truncated_content}", output_file)

                elif item_type == 'message':
                    # Message output
                    role = item.get('role', 'assistant')
                    content = item.get('content', '')
                    truncated_content = self._truncate_content(str(content))
                    self._print(f"  [{role}]: {truncated_content}", output_file)

                elif item_type == 'function_call':
                    # Tool call
                    name = item.get('name', 'unknown')
                    args = item.get('arguments', {})
                    formatted_args = self._format_json(args)
                    truncated_args = self._truncate_content(str(formatted_args))
                    self._print(f"  🔧 Tool Call: {name}({truncated_args})", output_file)

                elif item_type:
                    # Other types with explicit type
                    formatted_item = self._format_json(item)
                    truncated_item = self._truncate_content(str(formatted_item))
                    self._print(f"  [{item_type}]: {truncated_item}", output_file)

                else:
                    # No type field, try to identify intelligently
                    if 'content' in item:
                        # Looks like a message
                        role = item.get('role', 'assistant')
                        content = item.get('content', '')
                        truncated_content = self._truncate_content(str(content))
                        self._print(f"  [{role}]: {truncated_content}", output_file)
                    elif 'name' in item and 'arguments' in item:
                        # Looks like a function call
                        name = item.get('name', 'unknown')
                        args = item.get('arguments', {})
                        formatted_args = self._format_json(args)
                        truncated_args = self._truncate_content(str(formatted_args))
                        self._print(f"  🔧 Tool Call: {name}({truncated_args})", output_file)
                    else:
                        # Unrecognized structure, display as data
                        formatted_item = self._format_json(item)
                        truncated_item = self._truncate_content(str(formatted_item))
                        self._print(f"  [data]: {truncated_item}", output_file)
            else:
                formatted_item = self._format_json(item)
                truncated_item = self._truncate_content(str(formatted_item))
                self._print(f"  {truncated_item}", output_file)

    def on_trace_start(self, trace) -> None:
        """Callback when Trace starts"""
        # Always create TraceState so span callbacks can track counts correctly,
        # regardless of whether show_trace_lifecycle is enabled.
        state = TraceState(trace_id=trace.trace_id, start_time=datetime.now())

        # Apply file router: determine per-trace output file if configured
        if self.file_router:
            routed_file = self.file_router(trace.name)
            if routed_file:
                state.output_file = routed_file
                # Ensure old logs for this file's pattern are cleaned up
                _ensure_log_cleanup(routed_file)

        self.trace_states[trace.trace_id] = state

        if not self.show_trace_lifecycle:
            return

        output_file = state.output_file
        self._print(f"\n{self.colors['trace']}{self.colors['bold']}🚀 === TRACE STARTED ==={self.colors['reset']}", output_file)
        self._print(f"{self.colors['trace']}Workflow: {trace.name}{self.colors['reset']}", output_file)
        self._print(f"{self.colors['trace']}Trace ID: {trace.trace_id}{self.colors['reset']}", output_file)
        if trace.group_id:
            self._print(f"{self.colors['trace']}Group ID: {trace.group_id}{self.colors['reset']}", output_file)
        self._print(f"{self.colors['trace']}Started: {self._format_timestamp()}{self.colors['reset']}", output_file)
        self._print(f"{self.colors['trace']}========================={self.colors['reset']}\n", output_file)

    def on_trace_end(self, trace) -> None:
        """Callback when Trace ends"""
        if not self.show_trace_lifecycle:
            return

        state = self.trace_states.get(trace.trace_id)
        if state:
            output_file = state.output_file
            duration = datetime.now() - state.start_time

            self._print(f"\n{self.colors['trace']}{self.colors['bold']}🏁 === TRACE ENDED ==={self.colors['reset']}", output_file)
            self._print(f"{self.colors['trace']}Workflow: {trace.name}{self.colors['reset']}", output_file)
            self._print(f"{self.colors['trace']}Duration: {duration.total_seconds():.1f}s{self.colors['reset']}", output_file)
            self._print(f"{self.colors['trace']}Model Calls: {state.model_call_count}{self.colors['reset']}", output_file)
            self._print(f"{self.colors['trace']}Tool Calls: {state.tool_call_count}{self.colors['reset']}", output_file)
            self._print(f"{self.colors['trace']}Handoffs: {state.handoff_count}{self.colors['reset']}", output_file)
            self._print(f"{self.colors['trace']}Tokens: Input={state.total_input_tokens}, Output={state.total_output_tokens}, Total={state.total_tokens}{self.colors['reset']}", output_file)
            self._print(f"{self.colors['trace']}======================{self.colors['reset']}\n", output_file)

            # Clean up state
            del self.trace_states[trace.trace_id]

    def on_span_start(self, span) -> None:
        """Span 开始时的回调"""
        span_type = span.span_data.type
        trace_id = span.trace_id
        state = self.trace_states.get(trace_id)
        output_file = state.output_file if state else None

        if span_type == "generation" and self.show_model_calls:
            # Update count when span starts
            if state:
                state.model_call_count += 1

            # Handle the start of model generation Span
            data = span.span_data
            call_num = state.model_call_count if state else "?"

            self._print(f"\n{self.colors['model']}{self.colors['bold']}🤖 === MODEL CALL {call_num} ==={self.colors['reset']}", output_file)
            self._print(f"{self.colors['model']}{self._format_timestamp()}Model: {data.model or 'unknown'}{self.colors['reset']}", output_file)

            # Print incremental input messages
            if data.input and state:
                self._print_incremental_messages(span.trace_id, data.input)

    def on_span_end(self, span) -> None:
        """Span 结束时的回调"""
        span_type = span.span_data.type
        trace_id = span.trace_id

        # Update status count
        state = self.trace_states.get(trace_id)
        if state:
            if span_type == "generation":
                # generation count has been updated in on_span_start
                pass
            elif span_type == "function":
                state.tool_call_count += 1
            elif span_type == "handoff":
                state.handoff_count += 1

        if span_type == "generation" and self.show_model_calls:
            self._handle_generation_span(span, state)
        elif span_type == "function" and self.show_tool_calls:
            self._handle_function_span(span, state)
        elif span_type == "handoff" and self.show_handoffs:
            self._handle_handoff_span(span, state)

    def _handle_generation_span(self, span, state: Optional[TraceState]) -> None:
        """Handle output when model generation Span ends"""
        data = span.span_data
        output_file = state.output_file if state else None

        # Print model output
        if data.output:
            self._format_model_output(data.output, output_file)

        # Print usage statistics
        if data.usage:
            usage = data.usage
            input_tokens = usage.get('total_input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            total_tokens = usage.get('total_tokens', 0)
            self._print(f"{self.colors['model']}📊 Usage: Input={usage.get('total_input_tokens', 0)}, Output={usage.get('output_tokens', 0)}, Total={usage.get('total_tokens', 0)}{self.colors['reset']}", output_file)
            if state:
                state.total_input_tokens += input_tokens
                state.total_output_tokens += output_tokens
                state.total_tokens += total_tokens
        self._print(f"{self.colors['model']}==================={self.colors['reset']}", output_file)

    def _handle_function_span(self, span, state: Optional[TraceState]) -> None:
        """处理函数调用 Span"""
        data = span.span_data
        output_file = state.output_file if state else None

        call_num = state.tool_call_count if state else "?"
        self._print(f"\n{self.colors['tool']}{self.colors['bold']}🔧 === TOOL CALL {call_num} ==={self.colors['reset']}", output_file)
        self._print(f"{self.colors['tool']}{self._format_timestamp()}Function: {data.name}{self.colors['reset']}", output_file)

        # Print input
        if data.input:
            formatted_input = self._format_json(data.input)
            truncated_input = self._truncate_content(str(formatted_input))
            self._print(f"{self.colors['input']}📥 Input: {truncated_input}{self.colors['reset']}", output_file)

        # Print output
        if data.output is not None:
            formatted_output = self._format_json(data.output)
            truncated_output = self._truncate_content(str(formatted_output))
            self._print(f"{self.colors['output']}📤 Output: {re.sub(r'(data:image/jpeg;base64,)[^\"]*', r'\\1...', truncated_output)}{self.colors['reset']}", output_file)

        # Print MCP data (if any)
        if data.mcp_data:
            formatted_mcp = self._format_json(data.mcp_data)
            truncated_mcp = self._truncate_content(str(formatted_mcp))
            self._print(f"{self.colors['tool']}🔗 MCP Data: {truncated_mcp}{self.colors['reset']}", output_file)

        self._print(f"{self.colors['tool']}==============={self.colors['reset']}", output_file)

    def _handle_handoff_span(self, span, state: Optional[TraceState]) -> None:
        """Handle Handoff Span end"""
        data = span.span_data
        output_file = state.output_file if state else None

        # Update Agent history
        if state and data.to_agent:
            if data.to_agent not in state.agent_history:
                state.agent_history.append(data.to_agent)

        self._print(f"{self.colors['handoff']}=================={self.colors['reset']}", output_file)

    def shutdown(self) -> None:
        """Shutdown the processor"""
        if self.trace_states:
            self._print("Warning: Some traces were not properly ended")
        self.trace_states.clear()

    def force_flush(self) -> None:
        """Force flush the buffer"""
        # For console output, usually no special handling is needed
        pass


# Convenient factory functions
def create_simple_logger(console_output: bool = True) -> LoggerTracingProcessor:
    """Create a simple logger"""
    return LoggerTracingProcessor(
        show_model_calls=True,
        show_tool_calls=True,
        show_handoffs=True,
        show_trace_lifecycle=True,
        use_colors=True,
        console_output=console_output
    )


def create_detailed_logger(
    output_file: Optional[str] = None,
    console_output: bool = True,
    file_router: Optional[Callable[[str], str]] = None,
) -> LoggerTracingProcessor:
    """Create a detailed logger with built-in sub-agent log routing.

    Sub-agent traces (workflow_name="SubTaskAgent") are automatically written
    to a separate ``subtask_trace-YYYYMMDD.log`` file so they can be reviewed
    independently from the main agent log.

    Args:
        output_file: Default log file path for the main agent trace.  When not
            provided, defaults to the daily-rotated ``agent_trace-YYYYMMDD.log``
            file in ``~/.siada-cli/logs/``.
        console_output: Whether to echo output to the console.
        file_router: Optional custom callable ``(trace_name: str) -> str`` that
            maps a trace name to an output file path.  Providing this overrides
            the built-in SubTaskAgent routing described above.
    """
    from siada.foundation.constants import SIADA_HOME
    log_dir = SIADA_HOME / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")

    if output_file is None:
        output_file = str(log_dir / f"agent_trace-{date_str}.log")

    # Built-in routing: route SubTaskAgent traces to a dedicated daily log file.
    # Callers can pass a custom file_router to override this behaviour.
    if file_router is None:
        subtask_log = str(log_dir / f"subtask_trace-{date_str}.log")
        file_router = lambda name: subtask_log if name == "SubTaskAgent" else None

    return LoggerTracingProcessor(
        show_model_calls=True,
        show_tool_calls=True,
        show_handoffs=True,
        show_trace_lifecycle=True,
        show_timestamps=True,
        use_colors=True,
        console_output=console_output,
        output_file=output_file,
        file_router=file_router,
    )


def create_file_only_logger(output_file: Optional[str] = None) -> LoggerTracingProcessor:
    """Create a logger that only writes to file (no console output)"""
    return create_detailed_logger(output_file=output_file, console_output=False)


def create_minimal_logger(console_output: bool = True) -> LoggerTracingProcessor:
    """Create a minimal logger"""
    return LoggerTracingProcessor(
        show_model_calls=True,
        show_tool_calls=False,
        show_handoffs=True,
        show_trace_lifecycle=False,
        use_colors=False,
        console_output=console_output
    )

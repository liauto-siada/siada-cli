from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from agents.tracing import TracingProcessor, Trace, Span
from openai.types.responses import ResponseFunctionToolCall

@dataclass
class ModelCall:
    """模型调用记录"""
    call_id: int
    model: str
    input_messages: List[Dict[str, Any]]
    output_messages: List[Dict[str, Any]]
    usage: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: Optional[float] = None


@dataclass
class ToolCall:
    """工具调用记录"""
    call_id: int
    tool_name: str
    input_args: Any
    output_result: Any
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None


@dataclass
class ExecutionTrace:
    trace_id: str
    workflow_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    model_calls: List[ModelCall] = field(default_factory=list)
    tool_calls: List[ToolCall] = field(default_factory=list)
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    
    @property
    def duration_seconds(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "workflow_name": self.workflow_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "model_calls": [
                {
                    "call_id": call.call_id,
                    "model": call.model,
                    "input_messages": call.input_messages,
                    "output_messages": call.output_messages,
                    "usage": call.usage,
                    "timestamp": call.timestamp.isoformat(),
                    "duration_ms": call.duration_ms
                }
                for call in self.model_calls
            ],
            "tool_calls": [
                {
                    "call_id": call.call_id,
                    "tool_name": call.tool_name,
                    "input_args": call.input_args,
                    "output_result": call.output_result,
                    "timestamp": call.timestamp.isoformat(),
                    "duration_ms": call.duration_ms,
                    "success": call.success,
                    "error_message": call.error_message
                }
                for call in self.tool_calls
            ],
            "statistics": {
                "total_model_calls": len(self.model_calls),
                "total_tool_calls": len(self.tool_calls),
                "total_tokens": self.total_tokens,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens
            }
        }


class ExecutionTraceCollector(TracingProcessor):
    """
    Collect the execution traces of Agents (MODEL CALL and TOOL CALL).
    """
    
    def __init__(self):
        self.traces: Dict[str, ExecutionTrace] = {}
        self.active_spans: Dict[str, Dict[str, Any]] = {}  # span_id -> span_info
    
    def get_trace(self, trace_id: str) -> Optional[ExecutionTrace]:
        return self.traces.get(trace_id)
    
    def get_latest_trace(self) -> Optional[ExecutionTrace]:
        if not self.traces:
            return None
        return max(self.traces.values(), key=lambda t: t.start_time)
    
    def clear_traces(self) -> None:
        self.traces.clear()
        self.active_spans.clear()
    
    def on_trace_start(self, trace: Trace) -> None:
        execution_trace = ExecutionTrace(
            trace_id=trace.trace_id,
            workflow_name=trace.name or "unknown",
            start_time=datetime.now()
        )
        self.traces[trace.trace_id] = execution_trace
    
    def on_trace_end(self, trace: Trace) -> None:
        if trace.trace_id in self.traces:
            self.traces[trace.trace_id].end_time = datetime.now()
    
    def on_span_start(self, span: Span) -> None:
        span_info = {
            "span_id": span.span_id,
            "trace_id": span.trace_id,
            "type": span.span_data.type,
            "start_time": datetime.now()
        }
        self.active_spans[span.span_id] = span_info
    
    def on_span_end(self, span: Span) -> None:
        span_info = self.active_spans.get(span.span_id)
        if not span_info:
            return
        
        trace = self.traces.get(span.trace_id)
        if not trace:
            return
        
        duration_ms = None
        if span_info.get("start_time"):
            duration = datetime.now() - span_info["start_time"]
            duration_ms = duration.total_seconds() * 1000
        
        span_type = span.span_data.type
        
        if span_type == "generation":
            self._handle_model_call(span, trace, duration_ms)
        elif span_type == "function":
            self._handle_tool_call(span, trace, duration_ms)
        
        self.active_spans.pop(span.span_id, None)
    
    def _handle_model_call(self, span: Span, trace: ExecutionTrace, duration_ms: Optional[float]) -> None:
        data = span.span_data
        
        model_call = ModelCall(
            call_id=len(trace.model_calls) + 1,
            model=data.model or "unknown",
            input_messages=data.input or [],
            output_messages=data.output or [],
            usage=data.usage,
            duration_ms=duration_ms
        )
        
        trace.model_calls.append(model_call)
        
        if data.usage:
            trace.total_input_tokens += data.usage.get('input_tokens', 0)
            trace.total_output_tokens += data.usage.get('output_tokens', 0)
            trace.total_tokens += data.usage.get('total_tokens', 0)
    
    def _handle_tool_call(self, span: Span, trace: ExecutionTrace, duration_ms: Optional[float]) -> None:
        data = span.span_data
        
        success = True
        error_message = None
        
        if data.output and isinstance(data.output, str):
            if "error" in data.output.lower() or "exception" in data.output.lower():
                success = False
                error_message = data.output
        
        tool_call = ToolCall(
            call_id=len(trace.tool_calls) + 1,
            tool_name=data.name or "unknown",
            input_args=data.input,
            output_result=data.output,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message
        )
        
        trace.tool_calls.append(tool_call)
    
    def shutdown(self) -> None:
        pass
    
    def force_flush(self) -> None:
        pass

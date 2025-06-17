
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from agents.tracing import TracingProcessor


@dataclass
class TraceState:
    """跟踪单个 Trace 的状态信息"""
    trace_id: str
    message_count: int = 0  # 已打印的消息数量
    agent_history: List[str] = field(default_factory=list)  # Agent 切换历史
    start_time: datetime = field(default_factory=datetime.now)
    handoff_count: int = 0  # Handoff 次数
    model_call_count: int = 0  # 模型调用次数
    tool_call_count: int = 0  # 工具调用次数


class LoggerTracingProcessor(TracingProcessor):
    """
    详细的推理过程日志记录器

    这个 TracingProcessor 提供了详细的推理过程可视化，包括：
        - 模型调用的增量输入和完整输出
        - 工具调用的输入输出详情
        - Agent 切换（handoff）的完整记录
        - 整个推理过程的生命周期跟踪

    使用方法：
        from agents.tracing import add_trace_processor
        from examples.tracing.logger_tracing_processor import LoggerTracingProcessor

        # 注册处理器
        add_trace_processor(LoggerTracingProcessor())

        # 然后正常运行 Agent
        result = await Runner.run(agent=your_agent, input="your input")
    """
    
    def __init__(
        self,
        show_model_calls: bool = True,
        show_tool_calls: bool = True,
        show_handoffs: bool = True,
        show_trace_lifecycle: bool = True,
        max_content_length: int = 500,
        show_timestamps: bool = True,
        use_colors: bool = True,
        output_file: Optional[str] = None,
        indent_level: int = 0
    ):
        """
        初始化日志记录器
        
        Args:
            show_model_calls: 是否显示模型调用
            show_tool_calls: 是否显示工具调用
            show_handoffs: 是否显示 Agent 切换
            show_trace_lifecycle: 是否显示 Trace 生命周期
            max_content_length: 内容最大显示长度
            show_timestamps: 是否显示时间戳
            use_colors: 是否使用颜色输出
            output_file: 可选的输出文件路径
            indent_level: 缩进级别
        """
        self.show_model_calls = show_model_calls
        self.show_tool_calls = show_tool_calls
        self.show_handoffs = show_handoffs
        self.show_trace_lifecycle = show_trace_lifecycle
        self.max_content_length = max_content_length
        self.show_timestamps = show_timestamps
        self.use_colors = use_colors
        self.output_file = output_file
        self.indent_level = indent_level
        
        # 状态跟踪
        self.trace_states: Dict[str, TraceState] = {}
        
        # 颜色定义
        self.colors = {
            'trace': '\033[95m',      # 紫色
            'model': '\033[94m',      # 蓝色
            'tool': '\033[92m',       # 绿色
            'handoff': '\033[93m',    # 黄色
            'input': '\033[96m',      # 青色
            'output': '\033[91m',     # 红色
            'reset': '\033[0m',       # 重置
            'bold': '\033[1m',        # 粗体
        } if use_colors else {k: '' for k in ['trace', 'model', 'tool', 'handoff', 'input', 'output', 'reset', 'bold']}
    
    def _print(self, message: str) -> None:
        """打印消息，支持文件输出"""
        indent = "  " * self.indent_level
        full_message = f"{indent}{message}"
        
        print(full_message)
        
        if self.output_file:
            try:
                with open(self.output_file, 'a', encoding='utf-8') as f:
                    # 移除颜色代码用于文件输出
                    clean_message = full_message
                    for color in self.colors.values():
                        clean_message = clean_message.replace(color, '')
                    f.write(clean_message + '\n')
            except Exception as e:
                print(f"Warning: Failed to write to file {self.output_file}: {e}")
    
    def _format_timestamp(self) -> str:
        """格式化时间戳"""
        if not self.show_timestamps:
            return ""
        return f"🕐 {datetime.now().strftime('%H:%M:%S')} "
    
    def _truncate_content(self, content: str) -> str:
        """截断过长的内容"""
        if len(content) <= self.max_content_length:
            return content
        return content[:self.max_content_length] + "..."
    
    def _format_json(self, data: Any) -> str:
        """格式化 JSON 数据"""
        try:
            if isinstance(data, str):
                return self._truncate_content(data)
            return self._truncate_content(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            return self._truncate_content(str(data))
    
    def _print_incremental_messages(self, trace_id: str, messages: List[Dict[str, Any]]) -> None:
        """增量打印消息列表"""
        if not messages:
            return
            
        state = self.trace_states.get(trace_id)
        if not state:
            return
        
        # 只打印新增的消息
        new_messages = messages[state.message_count:]
        if not new_messages:
            return
        
        self._print(f"{self.colors['input']}📥 New Input Messages:{self.colors['reset']}")
        
        for i, msg in enumerate(new_messages, start=state.message_count + 1):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            # 处理不同类型的内容
            if isinstance(content, list):
                # 多模态内容
                content_summary = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get('type') == 'text':
                            content_summary.append(f"text: {self._truncate_content(item.get('text', ''))}")
                        elif item.get('type') == 'image_url':
                            content_summary.append("image: [image data]")
                        else:
                            content_summary.append(f"{item.get('type', 'unknown')}: [data]")
                content_str = " | ".join(content_summary)
            else:
                content_str = self._truncate_content(str(content))
            
            self._print(f"  [{role}]: {content_str}")
        
        # 更新已打印的消息数量
        state.message_count = len(messages)
    
    def _format_model_output(self, output: List[Dict[str, Any]]) -> None:
        """格式化模型输出"""
        self._print(f"{self.colors['output']}📤 Model Output:{self.colors['reset']}")
        
        for item in output:
            if isinstance(item, dict):
                item_type = item.get('type', 'unknown')
                
                if item_type == 'message':
                    # 消息输出
                    role = item.get('role', 'assistant')
                    content = item.get('content', '')
                    self._print(f"  [{role}]: {self._truncate_content(str(content))}")
                
                elif item_type == 'function_call':
                    # 工具调用
                    name = item.get('name', 'unknown')
                    args = item.get('arguments', {})
                    self._print(f"  🔧 Tool Call: {name}({self._format_json(args)})")
                
                else:
                    # 其他类型
                    self._print(f"  [{item_type}]: {self._format_json(item)}")
            else:
                self._print(f"  {self._format_json(item)}")
    
    def on_trace_start(self, trace) -> None:
        """Trace 开始时的回调"""
        if not self.show_trace_lifecycle:
            return
        
        # 记录 Trace 状态
        self.trace_states[trace.trace_id] = TraceState(
            trace_id=trace.trace_id,
            start_time=datetime.now()
        )
        
        self._print(f"\n{self.colors['trace']}{self.colors['bold']}🚀 === TRACE STARTED ==={self.colors['reset']}")
        self._print(f"{self.colors['trace']}Workflow: {trace.name}{self.colors['reset']}")
        self._print(f"{self.colors['trace']}Trace ID: {trace.trace_id}{self.colors['reset']}")
        if trace.group_id:
            self._print(f"{self.colors['trace']}Group ID: {trace.group_id}{self.colors['reset']}")
        self._print(f"{self.colors['trace']}Started: {self._format_timestamp()}{self.colors['reset']}")
        self._print(f"{self.colors['trace']}========================={self.colors['reset']}\n")
    
    def on_trace_end(self, trace) -> None:
        """Trace 结束时的回调"""
        if not self.show_trace_lifecycle:
            return
        
        state = self.trace_states.get(trace.trace_id)
        if state:
            duration = datetime.now() - state.start_time
            
            self._print(f"\n{self.colors['trace']}{self.colors['bold']}🏁 === TRACE ENDED ==={self.colors['reset']}")
            self._print(f"{self.colors['trace']}Workflow: {trace.name}{self.colors['reset']}")
            self._print(f"{self.colors['trace']}Duration: {duration.total_seconds():.1f}s{self.colors['reset']}")
            self._print(f"{self.colors['trace']}Model Calls: {state.model_call_count}{self.colors['reset']}")
            self._print(f"{self.colors['trace']}Tool Calls: {state.tool_call_count}{self.colors['reset']}")
            self._print(f"{self.colors['trace']}Handoffs: {state.handoff_count}{self.colors['reset']}")
            self._print(f"{self.colors['trace']}======================{self.colors['reset']}\n")
            
            # 清理状态
            del self.trace_states[trace.trace_id]
    
    def on_span_start(self, span) -> None:
        """Span 开始时的回调"""
        # 这里可以记录 Span 开始的信息，如果需要的话
        pass
    
    def on_span_end(self, span) -> None:
        """Span 结束时的回调"""
        span_type = span.span_data.type
        trace_id = span.trace_id
        
        # 更新状态计数
        state = self.trace_states.get(trace_id)
        if state:
            if span_type == "generation":
                state.model_call_count += 1
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
        """处理模型生成 Span"""
        data = span.span_data
        
        call_num = state.model_call_count if state else "?"
        self._print(f"\n{self.colors['model']}{self.colors['bold']}🤖 === MODEL CALL {call_num} ==={self.colors['reset']}")
        self._print(f"{self.colors['model']}{self._format_timestamp()}Model: {data.model or 'unknown'}{self.colors['reset']}")
        
        # 打印增量输入消息
        if data.input and state:
            self._print_incremental_messages(span.trace_id, data.input)
        
        # 打印模型输出
        if data.output:
            self._format_model_output(data.output)
        
        # 打印使用统计
        if data.usage:
            usage = data.usage
            self._print(f"{self.colors['model']}📊 Usage: Input={usage.get('input_tokens', 0)}, Output={usage.get('output_tokens', 0)}, Total={usage.get('total_tokens', 0)}{self.colors['reset']}")
        
        self._print(f"{self.colors['model']}==================={self.colors['reset']}")
    
    def _handle_function_span(self, span, state: Optional[TraceState]) -> None:
        """处理函数调用 Span"""
        data = span.span_data
        
        call_num = state.tool_call_count if state else "?"
        self._print(f"\n{self.colors['tool']}{self.colors['bold']}🔧 === TOOL CALL {call_num} ==={self.colors['reset']}")
        self._print(f"{self.colors['tool']}{self._format_timestamp()}Function: {data.name}{self.colors['reset']}")
        
        # 打印输入
        if data.input:
            self._print(f"{self.colors['input']}📥 Input: {self._format_json(data.input)}{self.colors['reset']}")
        
        # 打印输出
        if data.output is not None:
            self._print(f"{self.colors['output']}📤 Output: {self._format_json(data.output)}{self.colors['reset']}")
        
        # 打印 MCP 数据（如果有）
        if data.mcp_data:
            self._print(f"{self.colors['tool']}🔗 MCP Data: {self._format_json(data.mcp_data)}{self.colors['reset']}")
        
        self._print(f"{self.colors['tool']}==============={self.colors['reset']}")
    
    def _handle_handoff_span(self, span, state: Optional[TraceState]) -> None:
        """处理 Handoff Span"""
        data = span.span_data
        
        handoff_num = state.handoff_count if state else "?"
        self._print(f"\n{self.colors['handoff']}{self.colors['bold']}🔄 === HANDOFF {handoff_num} ==={self.colors['reset']}")
        self._print(f"{self.colors['handoff']}{self._format_timestamp()}{self.colors['reset']}")
        
        if data.from_agent:
            self._print(f"{self.colors['handoff']}📤 From Agent: {data.from_agent}{self.colors['reset']}")
        
        if data.to_agent:
            self._print(f"{self.colors['handoff']}📥 To Agent: {data.to_agent}{self.colors['reset']}")
            
            # 更新 Agent 历史
            if state:
                if data.to_agent not in state.agent_history:
                    state.agent_history.append(data.to_agent)
        
        self._print(f"{self.colors['handoff']}=================={self.colors['reset']}")
    
    def shutdown(self) -> None:
        """关闭处理器"""
        if self.trace_states:
            self._print("Warning: Some traces were not properly ended")
        self.trace_states.clear()
    
    def force_flush(self) -> None:
        """强制刷新缓冲区"""
        # 对于控制台输出，通常不需要特殊处理
        pass


# 便捷的工厂函数
def create_simple_logger() -> LoggerTracingProcessor:
    """创建一个简单的日志记录器"""
    return LoggerTracingProcessor(
        show_model_calls=True,
        show_tool_calls=True,
        show_handoffs=True,
        show_trace_lifecycle=True,
        max_content_length=300,
        use_colors=True
    )


def create_detailed_logger(output_file: Optional[str] = None) -> LoggerTracingProcessor:
    """创建一个详细的日志记录器"""
    return LoggerTracingProcessor(
        show_model_calls=True,
        show_tool_calls=True,
        show_handoffs=True,
        show_trace_lifecycle=True,
        max_content_length=1000,
        show_timestamps=True,
        use_colors=True,
        output_file=output_file
    )


def create_minimal_logger() -> LoggerTracingProcessor:
    """创建一个最小化的日志记录器"""
    return LoggerTracingProcessor(
        show_model_calls=True,
        show_tool_calls=False,
        show_handoffs=True,
        show_trace_lifecycle=False,
        max_content_length=200,
        use_colors=False
    )

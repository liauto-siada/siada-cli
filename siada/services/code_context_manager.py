"""
混合上下文管理器
结合TracingProcessor和AgentHooks来确保完整的消息历史维护
"""
from __future__ import annotations

from typing import Any

from agents import Agent, RunContextWrapper
from agents.lifecycle import AgentHooks
from agents.tool import Tool
from agents.tracing import TracingProcessor, Trace, Span
from agents.tracing.span_data import GenerationSpanData, FunctionSpanData
from agents.items import TResponseInputItem

from siada.foundation.code_agent_context import CodeAgentContext


class ContextHooks(AgentHooks[CodeAgentContext]):
    """混合上下文管理器

    使用AgentHooks来捕获Agent级别的事件，
    确保用户输入和助手输出都被正确记录
    """

    def __init__(self):
        super().__init__()
        print("🔧 HybridContextManager 初始化完成")

    async def on_start(
            self,
            context: RunContextWrapper[CodeAgentContext],
            agent: Agent[CodeAgentContext]
    ) -> None:
        """Agent开始执行前的处理"""
        if context.context:
            print(f"🚀 Agent '{agent.name}' 开始执行")
            print(f"📊 当前消息历史: {context.context.get_history_summary()}")

            # 检查是否有待处理的压缩
            if context.context.compression_pending:
                print(f"🔄 检测到待处理的压缩操作")
                if context.context.compression_summary and context.context.messages_to_remove_count > 0:
                    context.context.apply_compression(
                        context.context.compression_summary,
                        context.context.messages_to_remove_count
                    )
                    print(f"✅ 压缩已应用，当前历史: {context.context.get_history_summary()}")

    async def on_end(
            self,
            context: RunContextWrapper[CodeAgentContext],
            agent: Agent[CodeAgentContext],
            output: Any
    ) -> None:
        """Agent执行完成后的处理 - 更新消息历史"""
        if not context.context:
            return

        print(f"🏁 Agent '{agent.name}' 执行完成")
        print(f"📤 输出内容: {str(output)[:100]}...")

        # 将助手的回复添加到历史
        if isinstance(output, str):
            assistant_message: TResponseInputItem = {
                "role": "assistant",
                "content": output
            }
            context.context.add_message(assistant_message)
            print(f"📝 已添加助手回复到历史")
            print(f"📊 更新后历史: {context.context.get_history_summary()}")

    async def on_tool_start(
            self,
            context: RunContextWrapper[CodeAgentContext],
            agent: Agent[CodeAgentContext],
            tool: Tool
    ) -> None:
        """工具开始执行前的处理"""
        if tool.name == "compress_context_tool":
            print(f"🛠️ 开始执行上下文压缩工具")
            if context.context:
                print(f"📊 压缩前历史: {context.context.get_history_summary()}")

    async def on_tool_end(
            self,
            context: RunContextWrapper[CodeAgentContext],
            agent: Agent[CodeAgentContext],
            tool: Tool,
            result: str
    ) -> None:
        """工具执行完成后的处理"""
        if tool.name == "compress_context_tool" and context.context:
            print(f"🎯 上下文压缩工具执行完成")

            # 检查压缩是否已标记
            if context.context.compression_pending:
                print(f"✅ 压缩已标记，将在下次Agent开始时应用")
                print(f"📝 待删除消息数: {context.context.messages_to_remove_count}")
            else:
                print(f"ℹ️ 无需压缩或压缩条件不满足")


class ContextTracingProcessor(TracingProcessor):
    """混合TracingProcessor

    主要用于捕获工具调用和其他tracing事件
    """

    def __init__(self, context: CodeAgentContext):
        self.context = context
        print("🔧 HybridTracingProcessor 初始化完成")

    def on_trace_start(self, trace: "Trace") -> None:
        pass

    def on_span_start(self, span: "Span[Any]") -> None:

        span_type = span.span_data.type
        if span_type == "generation" or span_type == "function" or span_type == "handoff":
            self.context.message_history = span.span_data.input

    def on_span_end(self, span: "Span[Any]") -> None:

        if span_type == "generation" or span_type == "function" or span_type == "handoff":
            self.context.message_history = span.span_data.output

    def on_trace_end(self, trace: "Trace") -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self) -> None:
        """强制刷新所有队列的spans/traces"""
        pass


def create_context_with_user_message(user_input: str) -> CodeAgentContext:
    """创建包含用户消息的上下文"""
    context = CodeAgentContext()

    # 添加用户消息到历史
    user_message: TResponseInputItem = {
        "role": "user",
        "content": user_input
    }
    context.add_message(user_message)

    print(f"🆕 创建新的上下文，用户输入: {user_input}")
    print(f"📊 初始历史: {context.get_history_summary()}")
    return context

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
        pass
        

    async def on_end(
            self,
            context: RunContextWrapper[CodeAgentContext],
            agent: Agent[CodeAgentContext],
            output: Any
    ) -> None:
        pass

    async def on_tool_start(
            self,
            context: RunContextWrapper[CodeAgentContext],
            agent: Agent[CodeAgentContext],
            tool: Tool
    ) -> None:
       pass

    async def on_tool_end(
            self,
            context: RunContextWrapper[CodeAgentContext],
            agent: Agent[CodeAgentContext],
            tool: Tool,
            result: str
    ) -> None:
        if tool.name == "compress_context_tool" and context.context:
            try:
                # 解析工具返回的结果
                import json
                compression_result = json.loads(result)
                
                # 检查压缩是否成功
                if compression_result.get("status") == 1:
                    start_index = compression_result.get("start_index")
                    end_index = compression_result.get("end_index")
                    summary = compression_result.get("summary")
                    
                    # 验证索引有效性
                    if (start_index is not None and end_index is not None and 
                        0 <= start_index < end_index <= len(context.context.message_history)):
                        
                        # 删除被压缩的消息范围
                        del context.context.message_history[start_index:end_index]
                        
                        # 在删除位置插入压缩摘要作为新消息
                        summary_message = {
                            "role": "system",
                            "content": summary
                        }
                        context.context.message_history.insert(start_index, summary_message)
                        
                        print(f"✅ 成功压缩消息 [{start_index}:{end_index}]，替换为摘要")
                    else:
                        print(f"❌ 压缩索引无效: start_index={start_index}, end_index={end_index}")
                else:
                    print(f"❌ 压缩失败: {compression_result.get('summary', '未知错误')}")
                    
            except json.JSONDecodeError as e:
                print(f"❌ 解析压缩工具结果失败: {e}")
            except Exception as e:
                print(f"❌ 处理压缩结果时发生错误: {e}")


class ContextTracingProcessor(TracingProcessor):


    def __init__(self, context: CodeAgentContext):
        self.context = context

    def on_trace_start(self, trace: "Trace") -> None:
        pass

    def on_span_start(self, span: "Span[Any]") -> None:


        if hasattr(span.span_data, "input") and span.span_data.input:
            if isinstance(span.span_data.input, list):
                self.context.message_history = span.span_data.input
            else:
                self.context.add_message(span.span_data.input)


    def on_span_end(self, span: "Span[Any]") -> None:

        if hasattr(span.span_data, "output"):
            output = span.span_data.output
            if output:
                if isinstance(output, list):
                    self.context.add_messages(output)
                else:
                    self.context.add_message(output)


    def on_trace_end(self, trace: "Trace") -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self) -> None:
        pass

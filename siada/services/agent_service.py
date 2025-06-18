"""
Agent服务模块

提供创建和运行OpenAI Agent的功能
"""
import os
from typing import Any, Dict, List, Optional, AsyncGenerator

from agents import Agent, ItemHelpers, RunResultStreaming, Runner, function_tool, RunResult
from agents.run import RunConfig

from siada.core.config import settings
from siada.core.logging import logger
from siada.memory.memory_service import MemoryService
from siada.agent_hub.coder.code_context import CodeAgentContext
from siada.utils import JsonUtils, AgentLogger


class AgentService:
    """
    Agent服务类
    
    封装OpenAI Agents SDK的功能，提供创建和运行Agent的方法
    """

    @staticmethod
    async def stream_agent_events(
        agent: Agent,
        input_text: str,
        max_turns: Optional[int] = None,
        run_config: Optional[RunConfig] = None,
        context: Optional[Any] = None,
    ) -> tuple[RunResultStreaming, AsyncGenerator[Dict[str, Any], None]]:
        """
        以SSE方式流式输出Agent运行事件

        Args:
            agent: 要运行的Agent对象
            input_text: 输入文本
            max_turns: 最大运行轮数
            run_config: 运行配置
            context: 可选的上下文对象，用于传递给Runner.run

        Returns:
            返回一个元组 (StreamResult对象, 事件异步生成器)
        """
        # 使用提供的run_config或默认配置
        effective_run_config = run_config or settings.DEFAULT_RUN_CONFIG

        # 根据是否提供了context参数，调用不同的Runner.run方法
        result_stream = Runner.run_streamed(
            starting_agent=agent,
            input=input_text,
            max_turns=max_turns or settings.MAX_TURNS,
            run_config=effective_run_config,
            context=context
        )

        # 记录启动日志
        start_message = AgentLogger.format_start(agent.name)
        logger.info(start_message)

        # 记录用户输入
        AgentLogger.log_user_input(input_text)

        async def generate_events():
            # 发送用户输入
            yield {
                "event": "start",
                "data": {
                    "message": input_text
                }
            }

            # 处理流式事件
            current_msg = ''
            current_tool_call = ''
            last_message = None  # 用于存储可能的最后一个消息
            last_tool_call_output = None  # 用于存储可能的最后一个输出
            
            async for event in result_stream.stream_events():
                if last_tool_call_output:
                    output_message = AgentLogger.format_tool_output(last_tool_call_output)
                    AgentLogger.log_tool_output(output_message)
                    yield {
                        "event": "message",
                        "data": {
                            "output": last_tool_call_output
                        }
                    }
                    last_tool_call_output = None
                if event.type == "raw_response_event":
                    continue
                elif event.type == "agent_updated_stream_event":
                    continue
                elif event.type == "run_item_stream_event":
                    if event.item.type == "tool_call_item":
                        # 收到工具调用，表示这是一个动作
                        tool_name = event.item.raw_item.name
                        tool_args = event.item.raw_item.arguments
                        current_tool_call += AgentLogger.format_tool_call(tool_name, tool_args)
                        
                        # 如果有之前保存的输出，先打印它，因为现在已经确定不是最后一个输出
                        

                    elif event.item.type == "tool_call_output_item":
                        # 保存工具输出，但不立即处理，因为它可能是最后一个事件
                        last_tool_call_output = event.item.output

                    elif event.item.type == "message_output_item":
                        # 这可能是下一个动作的思考，也可能是最终输出
                        
                        # 如果之前存储了未处理的最后消息，说明它不是最终消息，应当处理它
                        if last_message:
                            log_message = AgentLogger.format_msg_action(last_message)
                            AgentLogger.log_observation(log_message)
                            
                            yield {
                                "event": "message",
                                "data": {
                                    "message": last_message
                                }
                            }
                        
                        # 保存当前消息为新的可能最终消息
                        current_msg = ItemHelpers.text_message_output(event.item)
                        last_message = current_msg  # 存储可能的最后消息

                    else:
                        logger.info(f"other_item_type: {event.item.type}")
                        yield {
                            "event": "message",
                            "data": {
                                "type": event.item.type
                            }
                        }

                # 如果累积了动作，处理当前的思考和动作对
                if current_tool_call:
                    log_message = AgentLogger.format_action(current_msg, current_tool_call)
                    AgentLogger.log_action(log_message)

                    yield {
                        "event": "message",
                        "data": {
                            "thought": current_msg,
                            "action": current_tool_call.strip()
                        }
                    }

                    current_tool_call = ''
                    current_msg = ''
                    last_message = None  # 重置最后消息

            # 记录最终输出
            final_output = AgentLogger.format_final_output(str(result_stream.final_output))
            AgentLogger.log_final_output(final_output)

            # 发送最终结果
            yield {
                "event": "finish",
                "data": {
                    "output": final_output,
                    "turns": result_stream.current_turn,
                    "completed": result_stream.is_complete
                }
            }

            # 记录完成日志
            finished_message = AgentLogger.format_finished(agent.name)
            logger.info(finished_message)

        # 返回StreamResult对象和事件生成器
        return result_stream, generate_events()


    @staticmethod
    async def run_agent(
            agent: Agent,
            input_text: str,
            max_turns: Optional[int] = None,
            run_config: Optional[RunConfig] = None,
    ) -> RunResult:
        """
        运行Agent

        Args:
            agent: 要运行的Agent对象
            input_text: 输入文本
            max_turns: 最大运行轮数
            run_config: 运行配置

        Returns:
            包含运行结果的字典
        """
        # 使用提供的run_config或默认配置
        effective_run_config = run_config or settings.DEFAULT_RUN_CONFIG
        current_working_dir = os.getcwd()
        context = CodeAgentContext(root_dir=current_working_dir)

        result = await Runner.run(
            starting_agent=agent,
            input=input_text,
            max_turns=max_turns or settings.MAX_TURNS,
            run_config=effective_run_config,
            context=context
        )

        # # 构建响应
        # response = {
        #     "final_output": result.final_output
        # }

        print(f"Final Output: {result.final_output}")

        return result

    @staticmethod
    async def _run_agent(
        agent: Agent,
        input_text: str,
        max_turns: Optional[int] = None,
        run_config: Optional[RunConfig] = None,
        context: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        运行Agent
        
        Args:
            agent: 要运行的Agent对象
            input_text: 输入文本
            max_turns: 最大运行轮数
            run_config: 运行配置
            context: 可选的上下文对象，用于传递给Runner.run

        Returns:
            包含运行结果的字典
        """
        # 使用提供的run_config或默认配置
        effective_run_config = run_config or settings.DEFAULT_RUN_CONFIG
        
        # 获取StreamResult对象和事件生成器
        result_stream, events_generator = await AgentService.stream_agent_events(
            agent=agent,
            input_text=input_text,
            max_turns=max_turns,
            run_config=effective_run_config,
            context=context
        )
        
        # 消费事件流
        async for _ in events_generator:
            # 仅消费事件流，不做额外处理
            pass
        
        # 构建响应
        response = {
            "final_output": result_stream.final_output,
            "turns": result_stream.current_turn,
            "completed": result_stream.is_complete
        }
        
        # 后处理agent结果，更新Memory缓存
        await AgentService.post_process_agent_result(result_stream)
        
        return response

    @staticmethod
    def create_function_tool(func: Any) -> Any:
        """
        创建一个函数工具
        
        Args:
            func: 要转换为工具的函数
            
        Returns:
            转换后的函数工具
        """
        return function_tool(func)

    @staticmethod
    async def post_process_agent_result(result_stream: RunResultStreaming):
        """
        将agent执行结果后的当前agent更新到Memory缓存
        
        Args:
            result_stream: Agent执行结果流
        """
        # 从上下文中获取session_id
        from siada.core.context import get_session_id
        session_id = get_session_id()
        
        if session_id:
            # 获取Memory实例
            memory = await MemoryService.get_memory(session_id)
            
            # 更新current_agent
            memory.system_context.current_agent = result_stream.current_agent
            
            # 保存更新后的Memory实例
            await MemoryService.set_memory(memory)

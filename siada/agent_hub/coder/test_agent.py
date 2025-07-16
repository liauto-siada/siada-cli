"""
Bug修复Agent模块

提供专门用于代码bug修复的Agent实现
"""
import os
from dataclasses import dataclass

from agents import RunContextWrapper, RunResult, Runner, RunConfig, add_trace_processor, TContext, AgentOutputSchema

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.siada_agent import SiadaAgent
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.foundation.config import settings
from siada.models.provider import SiadaProvider
from siada.agent_hub.coder.prompt import test_prompt
from siada.agent_hub.coder.tracing import create_detailed_logger
import logging

logging.getLogger().setLevel(logging.INFO)


@dataclass
class CCAOutput:
    type_of_card: str
    topic_of_card: str
    content_of_card: list[str]


class TestAgent(SiadaAgent[CodeAgentContext]):
    """
    代码生成Agent

    专门用于代码生成的Agent实现
    """

    def __init__(self, *args, **kwargs):

        def __init__(self, *args, **kwargs):
            super().__init__(
                name="TestAgent",
                tools=[edit, regex_search_files, run_cmd, fix_attempt_completion],
                tool_use_behavior=StopAtTools(stop_at_tool_names=['fix_attempt_completion']),
                *args,
                **kwargs
            )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        system_prompt = test_prompt.get_system_prompt(root_dir)
        return system_prompt

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        context = CodeAgentContext(root_dir=current_working_dir)
        return context

    async def run(self, user_input: str, context: CodeAgentContext) -> RunResult:
        """
        执行Bug修复任务

        Args:
            user_input: 用户描述的Bug问题，包括错误信息、相关文件路径等
            context: 用于提供上下文信息的上下文对象
        Returns:
            修复结果，包含最终输出、执行轮数等信息
        """

        config = RunConfig(tracing_disabled=False)
        add_trace_processor(create_detailed_logger())

        result = await Runner.run(
            starting_agent=self,
            input=user_input,
            max_turns=settings.MAX_TURNS,
            run_config=config,
            context=context
        )

        return result

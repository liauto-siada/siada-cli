import os

from agents import RunContextWrapper, RunResultStreaming, Runner, RunConfig, add_trace_processor
from agents.agent import StopAtTools

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import bug_reproduce_prompt
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.config import settings
from siada.provider.li.li_provider import SiadaProvider
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.reproduce_completion import reproduce_completion
from siada.tools.coder.run_cmd import run_cmd
from siada.agent_hub.coder.tracing import create_detailed_logger


class BugReproduceAgent(CodeGenAgent):

    def __init__(self, *args, **kwargs):
        provider = SiadaProvider()

        super().__init__(
            name="BugReproduceAgent",
            tools=[edit, regex_search_files, run_cmd, reproduce_completion],
            tool_use_behavior=StopAtTools(stop_at_tool_names=['reproduce_completion']),
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        system_prompt = bug_reproduce_prompt.get_system_prompt(root_dir)
        return system_prompt

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        context = CodeAgentContext(root_dir=current_working_dir)
        return context

    def run_streamed(self, user_input: str, context: CodeAgentContext) -> RunResultStreaming:
        """
        执行Bug复现任务

        Args:
            user_input: 用户描述的Bug问题，包括错误信息、相关文件路径等
            context: 用于提供上下文信息的上下文对象
        Returns:
            复现结果，包含最终输出、执行轮数等信息
        """
        pass

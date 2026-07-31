"""
Bug修复Agent模块

提供专门用于代码bug修复的Agent实现
"""
import os

from agents import RunContextWrapper, RunResult, add_trace_processor, RunResultStreaming
from agents.agent import StopAtTools

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.siada_agent import SiadaAgent
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.run_powershell import get_run_powershell_tool_if_available
from siada.tools.coder.test_completion import test_completion
from siada.agent_hub.coder.prompt import test_prompt
from siada.agent_hub.coder.prompt.base.tool_use import should_enable_parallel_tool_calls_in_prompt
from siada.agent_hub.coder.tracing import create_detailed_logger
import logging
from siada.foundation.setting import settings

logging.getLogger().setLevel(logging.INFO)


class TestAgent(SiadaAgent[CodeAgentContext]):
    """
    Test Execution Agent: an agent dedicated to running test cases.
    """

    def __init__(self, *args, **kwargs):
        _tools = [edit, regex_search_files, run_cmd, test_completion]
        _pwsh = get_run_powershell_tool_if_available()
        if _pwsh is not None:
            _tools.append(_pwsh)
        super().__init__(
            name="TestAgent",
            tools=_tools,
            tool_use_behavior=StopAtTools(stop_at_tool_names=['test_completion']),
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        enable_parallel = should_enable_parallel_tool_calls_in_prompt(run_context)
        system_prompt = test_prompt.get_system_prompt(root_dir, enable_parallel_tool_calls=enable_parallel)
        return system_prompt

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        context = CodeAgentContext(root_dir=current_working_dir)
        return context

    async def run(self, user_input: str, context: CodeAgentContext, run_config=None, openai_session=None) -> RunResult:
        """
        Execute test agent task.
        
        Args:
            user_input: User input for test execution
            context: Code agent context
            run_config: Run configuration (provided by SiadaRunner)
            openai_session: OpenAI session (provided by SiadaRunner)
            
        Returns:
            RunResult: The result of execution
        """
        add_trace_processor(create_detailed_logger())

        result = await self.run_impl(
                    starting_agent=self,
                    input=user_input,
                    max_turns=settings.MAX_TURNS,
                    context=context,
                    run_config=run_config,
                    openai_session=openai_session,
        )

        return result

    async def run_streamed(self, user_input: str, context: CodeAgentContext, run_config=None, openai_session=None) -> RunResultStreaming:
        """
        Run the agent in streaming mode
        
        Args:
            user_input: User input for test execution
            context: Code agent context
            run_config: Run configuration (provided by SiadaRunner)
            openai_session: OpenAI session (provided by SiadaRunner)
            
        Returns:
            RunResultStreaming: The streaming result of execution
        """
        add_trace_processor(create_detailed_logger())

        result = await self.run_streamed_impl(
                    starting_agent=self,
                    input=user_input,
                    max_turns=settings.MAX_TURNS,
                    context=context,
                    run_config=run_config,
                    openai_session=openai_session,
        )

        return result

"""
Bug修复Agent模块

提供专门用于代码bug修复的Agent实现
"""
import os
from dataclasses import dataclass

from agents import RunContextWrapper, RunResult, Runner, RunConfig, add_trace_processor, TContext, AgentOutputSchema, \
    RunResultStreaming
from agents.agent import StopAtTools

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.siada_agent import SiadaAgent
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.test_completion import test_completion
from siada.foundation.config import settings
from siada.agent_hub.coder.prompt import test_prompt
from siada.agent_hub.coder.tracing import create_detailed_logger
import logging

logging.getLogger().setLevel(logging.INFO)


class TestAgent(SiadaAgent[CodeAgentContext]):
    """
    Test Execution Agent: an agent dedicated to running test cases.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(
            name="TestAgent",
            handoff_description="A helpful agent that can test whether a bug has been fixed.",
            tools=[edit, regex_search_files, run_cmd, test_completion],
            tool_use_behavior=StopAtTools(stop_at_tool_names=['test_completion']),
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

    def run_streamed(self, user_input: str, context: CodeAgentContext) -> RunResultStreaming:

        pass

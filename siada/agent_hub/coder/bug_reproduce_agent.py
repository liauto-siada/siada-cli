import os

from agents import RunContextWrapper
from agents.agent import StopAtTools

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import bug_reproduce_prompt
from siada.agent_hub.coder.prompt.base.tool_use import should_enable_parallel_tool_calls_in_prompt
from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.reproduce_completion import reproduce_completion
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.run_powershell import get_run_powershell_tool_if_available


class BugReproduceAgent(CodeGenAgent):

    def __init__(self, *args, **kwargs):

        _tools = [edit, regex_search_files, run_cmd, reproduce_completion]
        _pwsh = get_run_powershell_tool_if_available()
        if _pwsh is not None:
            _tools.append(_pwsh)

        super().__init__(
            name="BugReproduceAgent",
            tools=_tools,
            tool_use_behavior=StopAtTools(stop_at_tool_names=['reproduce_completion']),
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        enable_parallel = should_enable_parallel_tool_calls_in_prompt(run_context)
        system_prompt = bug_reproduce_prompt.get_system_prompt(root_dir, enable_parallel_tool_calls=enable_parallel)
        return system_prompt

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        context = CodeAgentContext(root_dir=current_working_dir)
        return context

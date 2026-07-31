import os

from agents import  RunContextWrapper, RunResult,  set_trace_processors

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import issue_review_prompt
from siada.agent_hub.coder.prompt.base.tool_use import should_enable_parallel_tool_calls_in_prompt
from siada.agent_hub.coder.tracing.logger_tracing_processor import create_detailed_logger
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.setting import settings
from siada.foundation.tools.get_git_diff import GitDiffUtil
from siada.tools.ast.ast_tool import list_code_definition_names
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.patch_selection_completion import patch_selection_completion
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.run_powershell import get_run_powershell_tool_if_available

class IssueReviewAgent(CodeGenAgent):
    """
    Agent to review issues in a repository.
    """

    def __init__(self, *args, **kwargs):
        _tools = [edit, regex_search_files, run_cmd, list_code_definition_names, patch_selection_completion]
        _pwsh = get_run_powershell_tool_if_available()
        if _pwsh is not None:
            _tools.append(_pwsh)
        super().__init__(
            name="IssueReviewAgent",
            tools=_tools,
            tool_use_behavior={
                "stop_at_tool_names": ["patch_selection_completion"],
            },
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        enable_parallel = should_enable_parallel_tool_calls_in_prompt(run_context)
        system_prompt = issue_review_prompt.get_system_prompt(root_dir, enable_parallel_tool_calls=enable_parallel)
        return system_prompt

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        context = CodeAgentContext(root_dir=current_working_dir)

        if hasattr(self, 'model') and hasattr(self.model, 'context'):
            self.model.context = context

        return context

    async def run(self, user_input: str, context: CodeAgentContext) -> RunResult:
        patch = GitDiffUtil.get_git_diff_exclude_test_files(context.root_dir)

        input = f"""
Here is the issue description and the code patch that fixes the problem.
**Issue Description:**
{user_input}

**Code Change:**
{patch}
"""

        # set_trace_processors([create_detailed_logger(output_file="agent_trace.log")]), 

        result = await self.run_impl(
            starting_agent=self,
            input=input,
            max_turns=settings.MAX_TURNS,
            context=context,
        )

        return result
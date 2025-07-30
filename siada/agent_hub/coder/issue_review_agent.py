import os

from agents import RunConfig, RunContextWrapper, RunResult, Runner, set_trace_processors

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import issue_review_prompt
from siada.agent_hub.coder.tracing.logger_tracing_processor import create_detailed_logger
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.config import settings
from siada.foundation.tools.get_git_diff import GitDiffUtil
from siada.provider.li.li_provider import SiadaProvider
from siada.tools.ast.ast_tool import list_code_definition_names
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.issue_review_completion import issue_review_completion
from siada.tools.coder.run_cmd import run_cmd

class IssueReviewAgent(CodeGenAgent):
    """
    Agent to review issues in a repository.
    """

    def __init__(self, *args, **kwargs):
        provider = SiadaProvider()
        model = provider.get_model(settings.Claude_4_0_SONNET)

        super().__init__(
            name="IssueReviewAgent",
            tools=[edit, regex_search_files, run_cmd, list_code_definition_names, issue_review_completion],
            model=model,
            tool_use_behavior={
                "stop_at_tool_names": ["issue_review_completion"],
            },
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        system_prompt = issue_review_prompt.get_system_prompt(root_dir)
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

        config = RunConfig(tracing_disabled=False)

        set_trace_processors([create_detailed_logger(output_file="agent_trace.log")]), 

        result = await Runner.run(
            starting_agent=self,
            input=input,
            max_turns=settings.MAX_TURNS,
            run_config=config,
            context=context
        )

        return result
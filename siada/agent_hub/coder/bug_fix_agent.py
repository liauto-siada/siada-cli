import os

from agents import RunContextWrapper

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import bug_fix_prompt
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.config import settings
from siada.models.provider import SiadaProvider
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.fix_attempt_completion import fix_attempt_completion


class  BugFixAgent(CodeGenAgent):

    def __init__(self, *args, **kwargs):
        provider = SiadaProvider()
        model = provider.get_model(settings.Claude_4_0_SONNET)

        super().__init__(
            name="BugFixAgent",
            tools=[edit, regex_search_files, run_cmd,fix_attempt_completion],
            model=model,
            tool_use_behavior={
                "stop_at_tool_names": ["fix_attempt_completion"],
            },
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        system_prompt = bug_fix_prompt.get_system_prompt(root_dir)
        return system_prompt


    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        context = CodeAgentContext(root_dir=current_working_dir)
        return context

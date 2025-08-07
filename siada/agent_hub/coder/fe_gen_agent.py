from agents import RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import fe_gen_prompt
from siada.tools.browser.browser_action_tool import browser_operate
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd


class FeGenAgent(CodeGenAgent):

    def __init__(self, *args, **kwargs):

        super().__init__(
            name="FeGenAgent",
            tools=[edit, regex_search_files, run_cmd, browser_operate],
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        system_prompt = fe_gen_prompt.get_system_prompt(root_dir)
        return system_prompt

        # instructions=f"""
        #     You are an Browser Operate Agent.
        #     Your task is to perform browser operations according to the user's instructions,
        #     and you can use the browser_operate tool.
        #     """,
        # return instructions

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = "/Users/yunan/code/test/fe_gen"
        context = CodeAgentContext(root_dir=current_working_dir)
        return context

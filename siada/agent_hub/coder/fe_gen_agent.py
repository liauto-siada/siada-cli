from agents import RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import fe_gen_prompt
from siada.agent_hub.coder.prompt.base.tool_use import should_enable_parallel_tool_calls_in_prompt
from siada.tools.ast.ast_tool import list_code_definition_names
from siada.tools.browser import browser_operate_by_gym
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd


class FeGenAgent(CodeGenAgent):

    def __init__(self, *args, **kwargs):

        super().__init__(
            name="FeGenAgent",
            tools=[edit, regex_search_files, run_cmd, list_code_definition_names, browser_operate_by_gym],
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        enable_parallel = should_enable_parallel_tool_calls_in_prompt(run_context)
        system_prompt = fe_gen_prompt.get_system_prompt(root_dir, enable_parallel_tool_calls=enable_parallel)
        return system_prompt

        # instructions=f"""
        #     You are an Browser Operate Agent.
        #     Your task is to perform browser operations according to the user's instructions,
        #     and you can use the browser_operate tool.
        #     """,
        # return instructions

    # async def get_context(self) -> CodeAgentContext:
    #     current_working_dir = "/Users/yunan/code/test/fe_gen"
    #     context = CodeAgentContext(root_dir=current_working_dir)
    #     return context

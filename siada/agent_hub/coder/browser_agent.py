from agents import RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import browser_system_prompt
from siada.agent_hub.coder.prompt.base.tool_use import should_enable_parallel_tool_calls_in_prompt
from siada.tools.browser.browsergym_action_tool import browser_operate_by_gym
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.run_powershell import get_run_powershell_tool_if_available


class BrowserAgent(CodeGenAgent):

    def __init__(self, *args, **kwargs):

        _tools = [edit, regex_search_files, run_cmd, browser_operate_by_gym]
        _pwsh = get_run_powershell_tool_if_available()
        if _pwsh is not None:
            _tools.append(_pwsh)

        super().__init__(
            name="BrowserAgent",
            tools=_tools,
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        
        # Get combined memory from context (prepared by SiadaRunner)
        combined_memory = run_context.context.combined_memory
        
        # Get preferred language and agent name from session config
        preferred_language = run_context.context.preferred_language
        agent_name = run_context.context.session.siada_config.agent_name
        # Get pre_plan setting from context
        pre_plan = run_context.context.pre_plan

        enable_parallel = should_enable_parallel_tool_calls_in_prompt(run_context)
        system_prompt = browser_system_prompt.get_system_prompt(
            root_dir, run_context.context.interactive_mode,
            combined_memory, preferred_language, agent_name, pre_plan,
            enable_parallel_tool_calls=enable_parallel
        )
        return system_prompt

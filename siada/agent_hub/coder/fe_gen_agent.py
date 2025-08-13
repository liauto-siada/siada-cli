from agents import RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import fe_gen_prompt
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd


class FeGenAgent(CodeGenAgent):

    def __init__(self, *args, **kwargs):

        super().__init__(
            name="FeGenAgent",
            tools=[edit, regex_search_files, run_cmd],
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        interactive_mode = run_context.context.interactive_mode
        system_prompt = fe_gen_prompt.get_system_prompt(root_dir, interactive_mode)
        return system_prompt


    async def get_context(self) -> CodeAgentContext:
        current_working_dir = "/Users/yunan/code/test/fe_gen"
        interactive_mode = self.get_interactive_mode()
            
        context = CodeAgentContext(
            root_dir=current_working_dir,
            interactive_mode=interactive_mode
        )
        return context

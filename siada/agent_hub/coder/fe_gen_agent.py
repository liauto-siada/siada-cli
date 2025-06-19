from agents import RunContextWrapper

from siada.agent_hub.coder import BugFixAgent
from siada.agent_hub.coder.code_context import CodeAgentContext
from siada.agent_hub.coder.prompt import fe_gen_prompt
from siada.foundation.config import settings
from siada.models.provider import SiadaProvider
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd


class FeGenAgent(BugFixAgent):

    def __init__(self, *args, **kwargs):
        provider = SiadaProvider()
        model = provider.get_model(settings.Claude_4_0_SONNET)

        # 设置Bug修复相关的指令和工具
        super().__init__(
            name="FeGenAgent",
            tools=[edit, regex_search_files, run_cmd],
            model=model,
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        system_prompt = fe_gen_prompt.get_system_prompt(root_dir)
        return system_prompt


    async def get_context(self) -> CodeAgentContext:
        current_working_dir = "/Users/yunan/code/test/fe_gen"
        context = CodeAgentContext(root_dir=current_working_dir)
        return context

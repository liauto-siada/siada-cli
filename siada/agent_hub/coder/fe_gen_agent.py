from agents import RunContextWrapper, RunResultStreaming, Runner, RunConfig, add_trace_processor

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import fe_gen_prompt
from siada.foundation.config import settings
from siada.provider.li.li_provider import SiadaProvider
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.agent_hub.coder.tracing import create_detailed_logger


class FeGenAgent(CodeGenAgent):

    def __init__(self, *args, **kwargs):
        provider = SiadaProvider()
        model = provider.get_model(settings.Claude_4_0_SONNET)

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

    def run_streamed(self, user_input: str, context: CodeAgentContext) -> RunResultStreaming:
        """
        执行前端代码生成任务

        Args:
            user_input: 用户的前端代码生成请求，包含需求和规格说明
            context: 用于提供上下文信息的上下文对象
        Returns:
            生成结果，包含最终输出、执行轮数等信息
        """
        pass

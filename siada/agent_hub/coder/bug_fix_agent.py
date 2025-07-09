import os

from agents import RunContextWrapper, RunConfig, RunResult, Runner

from siada.agent_hub.coder.bug_reproduce_agent import BugReproduceAgent
from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import bug_fix_prompt
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.config import settings
from siada.models.provider import SiadaProvider
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd


class  BugFixAgent(CodeGenAgent):

    def __init__(self, *args, **kwargs):
        provider = SiadaProvider()
        model = provider.get_model(settings.Claude_4_0_SONNET)

        # reproduce_tool = reproduce_agent.as_tool(
        #             tool_name="reproduce_bug_tool",
        #             tool_description="According to the issue description, generate executable test cases to reproduce the issue.",
        #         )
        super().__init__(
            name="BugFixAgent",
            tools=[edit, regex_search_files, run_cmd],
            model=model,
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

    async def run(self, user_input: str, context: CodeAgentContext) -> RunResult:
        """
        执行Bug修复任务
        使用reproduce_agent 复现任务， 然后使用当前Agent进行修复。

        Args:
            user_input: 用户描述的Bug问题，包括错误信息、相关文件路径等
            context: 用于提供上下文信息的上下文对象
        Returns:
            修复结果，包含最终输出、执行轮数等信息
        """
        config = RunConfig(tracing_disabled=False)
        input_with_env = self.assemble_user_input(user_input, context)

        reproduce_agent = BugReproduceAgent()
        reproduce_result = await Runner.run(
            starting_agent=reproduce_agent,
            input=input_with_env,
            max_turns=settings.MAX_TURNS,
            run_config=config,
            context=context
        )

        reproduce_message = {"content": reproduce_result.final_output, "role": "user"}
        user_message = {"content": input_with_env, "role": "user"}

        input_list = [user_message, reproduce_message]

        result = await Runner.run(
            starting_agent=self,
            input=input_list,
            max_turns=settings.MAX_TURNS,
            run_config=config,
            context=context
        )

        return result
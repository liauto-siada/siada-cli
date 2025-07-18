import os

from agents import RunContextWrapper, RunConfig, RunResult, RunResultStreaming, Runner, add_trace_processor

from siada.agent_hub.coder.bug_reproduce_agent import BugReproduceAgent
from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt.bug_prompt import bug_fix_prompt
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.config import settings
from siada.provider.li.li_provider import SiadaProvider
from siada.tools.ast.ast_tool import list_code_definition_names
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.fix_attempt_completion import fix_attempt_completion
from agents import set_trace_processors
from siada.agent_hub.coder.tracing import create_detailed_logger




class  BugFixAgent(CodeGenAgent):

    def __init__(self, *args, **kwargs):
        provider = SiadaProvider()
        model = provider.get_model(settings.Claude_4_0_SONNET)

        super().__init__(
            name="BugFixAgent",
            tools=[edit, regex_search_files, run_cmd, fix_attempt_completion, list_code_definition_names],
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

    async def run(self, user_input: str, context: CodeAgentContext) -> RunResult:
        """
        Execute bug fixing task.
        Use reproduce_agent to reproduce the issue, then use current Agent to fix it.

        Args:
            user_input: User-described bug problem, including error messages, related file paths, etc.
            context: Context object for providing contextual information
        Returns:
            Fix result, including final output, execution rounds, and other information
        """
        config = RunConfig(tracing_disabled=False)
        set_trace_processors([create_detailed_logger()])
        input_with_env = self.assemble_user_input(user_input, context)

        # reproduce_agent = BugReproduceAgent()
        # reproduce_result = await Runner.run(
        #     starting_agent=reproduce_agent,
        #     input=input_with_env,
        #     max_turns=settings.MAX_TURNS,
        #     run_config=config,
        #     context=context
        # )
        # reproduce_message = {"content": reproduce_result.final_output, "role": "user"}
        # user_message = {"content": input_with_env, "role": "user"}
        #input_list = [user_message, reproduce_message]

        result = await Runner.run(
            starting_agent=self,
            input=input_with_env,
            max_turns=settings.MAX_TURNS,
            run_config=config,
            context=context
        )

        return result

    def run_streamed(self, user_input: str, context: CodeAgentContext) -> RunResultStreaming:
        """
        执行Bug修复任务

        Args:
            user_input: 用户描述的Bug问题，包括错误信息、相关文件路径等
            context: 用于提供上下文信息的上下文对象
        Returns:
            修复结果，包含最终输出、执行轮数等信息
        """
        pass

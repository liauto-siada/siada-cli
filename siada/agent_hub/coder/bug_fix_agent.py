"""
Bug修复Agent模块

提供专门用于代码bug修复的Agent实现
"""
from typing import Any

from agents import Agent, RunContextWrapper, Runner, RunConfig, add_trace_processor

from siada.tools.coder.file_operator import read, edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.core.config import settings
from siada.models.provider import SiadaProvider
from siada.agent_hub.coder.code_context import CodeAgentContext
from siada.agent_hub.coder.prompt import bug_fix_prompt
from siada.agent_hub.coder.tracing import create_detailed_logger


class BugFixAgent(Agent[CodeAgentContext]):
    """
    Bug修复Agent

    专门用于代码bug修复的Agent实现
    """

    def __init__(self, *args, **kwargs):
        """
        初始化Bug修复Agent
        
        设置专门用于bug修复的指令、工具和模型配置
        """
        # 使用SiadaProvider提供的默认模型
        provider = SiadaProvider()
        model = provider.get_model(settings.Claude_4_0_SONNET)
        
        # 设置Bug修复相关的指令和工具
        super().__init__(
            name="BugFixAgent",
            tools=[edit, regex_search_files, run_cmd],
            model=model,
            *args,
            **kwargs
        )


    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        system_prompt = bug_fix_prompt.get_system_prompt(self, root_dir)
        return system_prompt



    async def run(self, user_input: str, context: CodeAgentContext) -> Any:
        """
        执行Bug修复任务
        
        Args:
            user_input: 用户描述的Bug问题，包括错误信息、相关文件路径等
            
        Returns:
            修复结果，包含最终输出、执行轮数等信息
        """

        config = RunConfig(tracing_disabled=False)
        add_trace_processor(create_detailed_logger(output_file="agent_trace.log"))

        result = await Runner.run(
            starting_agent=self,
            input=user_input,
            max_turns=settings.MAX_TURNS,
            run_config=config,
            context=context
        )
        
        return result

"""
Bug修复Agent模块

提供专门用于代码bug修复的Agent实现
"""
from typing import Any

from agents import Agent

from siada.tools.coder.file_operator import read, edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.services.agent_service import AgentService
from siada.foundation.config import settings
from siada.models.provider import SiadaProvider


class BugFixAgent(Agent[]):
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
            instructions="""
            你是一个专业的Bug修复助手，专门帮助用户定位和修复代码中的问题。
            
            你的主要职责包括：
            1. 分析代码中的错误和异常
            2. 定位问题的根本原因
            3. 提供修复建议和解决方案
            4. 验证修复后的代码是否正常工作
            5. 使用适当的工具进行代码搜索、读取和编辑
            
            工作流程：
            1. 首先理解用户描述的问题
            2. 使用搜索工具定位相关代码文件
            3. 读取和分析问题代码
            4. 识别bug的根本原因
            5. 提供具体的修复方案
            6. 如果需要，直接修改代码文件
            7. 建议测试方法验证修复效果
            
            请以系统化、专业的方式处理每个Bug修复任务。
            """,
            tools=[read, edit, regex_search_files, run_cmd],
            model=model,
            *args,
            **kwargs
        )
    
    async def run(self, user_input: str) -> Any:
        """
        执行Bug修复任务
        
        Args:
            user_input: 用户描述的Bug问题，包括错误信息、相关文件路径等
            
        Returns:
            修复结果，包含最终输出、执行轮数等信息
        """
        # 使用AgentService来运行Agent
        result = await AgentService.run_agent(
            agent=self,
            input_text=user_input
        )
        
        return result

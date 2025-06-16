"""
软件开发Agent模块

提供软件开发功能的Agent实现，可以执行命令行命令
"""

from agents import Agent, RunConfig, MessageOutputItem, ItemHelpers, HandoffOutputItem, ToolCallItem, \
    ToolCallOutputItem, add_trace_processor
from pydantic import BaseModel

from src.core.config import settings
from src.services.agent_service import AgentService
from src.tools.coder.file_operator import read, edit
from src.tools.coder.file_search import regex_search_files
from src.user_agents import agent_map
from src.tools.coder.run_cmd import run_cmd
import asyncio
from src.models.provider import SiadaProvider

import logging

from src.user_agents.coder.tracing import create_detailed_logger

#logging.getLogger("openai.agents").setLevel(logging.INFO)  # 或者 logging.WARNING
logging.getLogger().setLevel(logging.INFO)

def init_coder_agent():
    """
    初始化软件开发Agent
    
    创建一个专门用于软件开发的Agent并添加到agent_map中
    """
    # 使用SiadaProvider提供的默认模型
    provider = SiadaProvider()
    model = provider.get_model(settings.Claude_4_0_SONNET)

    # 创建软件开发Agent
    coder_agent = Agent(
        name="CoderAgent",
        instructions="""
        你是一个专业的软件开发助手，可以帮助用户完成各种开发任务。
        
        你可以使用run_cmd工具执行命令行命令，帮助用户：
        1. 编写、编译和运行代码
        2. 管理项目和依赖
        3. 执行构建和部署操作
        4. 进行版本控制操作
        5. 执行其他开发相关的命令行任务
        
        在执行命令前，请确保：
        - 理解用户的需求和上下文
        - 选择最合适的命令和参数
        - 考虑命令执行的安全性和影响
        - 清晰地解释你将要执行的命令及其目的
        
        执行命令后，请：
        - 解释命令的输出结果
        - 提供下一步的建议（如果适用）
        - 回答用户可能的疑问
        
        请以专业、清晰的方式与用户交流，并提供有价值的技术建议。
        """,
        tools=[run_cmd, edit, regex_search_files],
        #tools=[run_cmd],
        model=model,
    )
    
    # 将Agent添加到map中
    agent_map["coder"] = coder_agent
    
    print(f"已初始化软件开发Agent: CoderAgent")


async def main():
    """主函数，用于测试CoderAgent"""
    init_coder_agent()
    agent = agent_map["coder"]

    # task = """
    #     请帮我查看当前目录都有哪些文件，
    #     如果有python文件，请打印 I love python
    #     """

    task = """
           在/Users/yunan/code/copilot/siada-api/tests/tools 目录下创建一个文件， test_code.py
           实现一个冒泡排序算法
            """
    
    # task = """
    #        阅读/Users/yunan/code/copilot/siada-api/tests/tools/test_edit内容
    #         """
    config = RunConfig(tracing_disabled=False)
    add_trace_processor(create_detailed_logger(output_file="agent_trace.log"))

    result = await AgentService.run_agent(
        agent=agent,
        input_text=task,
        run_config=config
    )


if __name__ == '__main__':
    asyncio.run(main())

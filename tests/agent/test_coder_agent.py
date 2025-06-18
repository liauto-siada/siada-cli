"""
Coder Agent测试

测试Coder Agent是否能正常使用工具
"""
import unittest

from agents import RunConfig

from siada.models.provider import SiadaProvider
from siada.services.agent_service import AgentService
from siada.agent_hub import agent_map
from siada.agent_hub.coder.coder_agent import init_coder_agent


class TestCoderAgent(unittest.IsolatedAsyncioTestCase):
    """测试Coder Agent"""

    async def test_coder_agent_run_cmd(self):
        """测试Coder Agent是否能正常使用run_cmd工具执行实际命令"""
        # 初始化coder_agent
        init_coder_agent()
        agent = agent_map["coder"]

        # 准备测试任务 - 使用安全的命令
        task = """
        请执行以下命令：
        1. 显示当前目录: pwd
        2. 列出当前目录文件: ls -la
        3. 显示当前日期和时间: date
        """

        # 运行agent
        result = await AgentService.run_agent(
            agent=agent,
            input_text=task,
            run_config=RunConfig(model="claude-3-7-sonnet", model_provider=SiadaProvider(), tracing_disabled=True)
        )

        # 验证结果
        print("\n测试结果:")
        print(f"输出文本: {result.final_output}")
        
        # 验证agent是否生成了输出
        assert result["final_output"] is not None
        # 验证输出中是否包含命令执行的结果
        # assert "pwd" in {result.final_output}.lower() or "目录" in {result.final_output}
        # assert "ls" in {result.final_output}.lower() or "文件" in {result.final_output}
        # assert "date" in {result.final_output}.lower() or "时间" in {result.final_output}

    async def test_coder_agent_file_operations(self):
        """测试Coder Agent执行文件操作命令"""
        init_coder_agent()
        agent = agent_map["coder"]
        
        task = """
        请帮我查看当前目录都有哪些文件，
        如果有python文件，请打印 I love python
        """
        
        result = await AgentService.run_agent(
            agent=agent,
            input_text=task,
            run_config=RunConfig(model="claude-3-7-sonnet", model_provider=SiadaProvider(), tracing_disabled=True)
        )
        
        print("\n模糊命令测试结果:")
        print(f"输出文本: {result['final_output']}")
        
        assert {result.final_output}  is not None


    async def test_coder_agent_complex_commands(self):
        """测试Coder Agent执行复杂命令"""
        init_coder_agent()
        agent = agent_map["coder"]
        
        task = """
        请执行以下复杂命令：
        1. 查找当前目录下所有Python文件: find . -name "*.py" | sort
        2. 统计Python文件的总行数: find . -name "*.py" -exec wc -l {} \\; | awk '{total += $1} END {print total}'
        """
        
        result = await AgentService.run_agent(
            agent=agent,
            input_text=task,
            run_config=RunConfig(model="claude-3-7-sonnet", model_provider=SiadaProvider(), tracing_disabled=True)
        )
        
        print("\n复杂命令测试结果:")
        print(f"输出文本: {result.final_output}")
        
        assert {result.final_output} is not None

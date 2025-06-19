"""
SiadaRunner.run_agent 方法测试

测试基于配置文件的Agent运行功能
"""
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from siada.services.siada_runner import SiadaRunner
from siada.agent_hub.coder.fe_gen_agent import FeGenAgent
from siada.agent_hub.coder.code_context import CodeAgentContext


class TestSiadaRunnerRunAgent(unittest.IsolatedAsyncioTestCase):
    """测试 SiadaRunner.run_agent 方法"""


    async def test_fegen_agent(self):
        user_input = """ 
                     实现一个冒泡排序算法
                     """
        agent_name = "fegen"
        result = await SiadaRunner.run_agent(agent_name, user_input)
        print(result)



if __name__ == '__main__':
    unittest.main()

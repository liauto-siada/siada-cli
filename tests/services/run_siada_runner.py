"""
SiadaRunner.run_agent 方法测试

测试基于配置文件的Agent运行功能
"""
import unittest

from siada.services.siada_runner import SiadaRunner



class TestSiadaRunnerRunAgent(unittest.IsolatedAsyncioTestCase):
    """测试 SiadaRunner.run_agent 方法"""


    async def test_fegen_agent(self):
        user_input = """ 
                     帮我创建一个显示公历、藏历、农历对应的网页卡片，必须是真实数据，包含：周的数据，农历节气，藏历中的各种吉日、凶日，以及吉日凶日的具体原因单次显示一个完整的月份，并可以前后查看每个月的数据。
                     """
        agent_name = "fegen"
        result = await SiadaRunner.run_agent(agent_name, user_input)
        print(result)



if __name__ == '__main__':
    unittest.main()

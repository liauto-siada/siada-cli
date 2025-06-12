import unittest

from agents import Agent, Runner, RunConfig

from src.models.provider import SiadaProvider
from src.tools.weather_tool import fetch_weather


class TestSiadaClient(unittest.IsolatedAsyncioTestCase):

    async def test_tool_call(self):
        agent = Agent(name="Test Agent", tools=[fetch_weather], model="claude-3-5-sonnet")

        result = await Runner.run(agent, input="what is the weather in lat:39.90 ,long:116.40 ?",
                                  run_config=RunConfig(model_provider=SiadaProvider()))

        print("\n测试结果:")
        print(f"输出文本: {result}")

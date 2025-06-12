import unittest
import json

from agents import ItemHelpers
from agents.run import RunConfig, Runner

from src.models.provider import SiadaProvider
from src.services.agent_service import AgentService
import src.trace
from src.tools.weather_tool import fetch_weather


class TestAgentService(unittest.IsolatedAsyncioTestCase):        
    


    async def test_chat_complete(self):
        agent = await AgentService.create_agent("TB", "你是一个律师", [])

        result = await AgentService.run_agent(agent=agent,
                               input_text="介绍下你自己",
                               run_config=RunConfig(model_provider=SiadaProvider()))
                               
        # 打印结果
        print("\n测试结果:")
        print(f"输出文本: {result['final_output']}")


    async def test_run_agent_stream(self):
        agent = await (AgentService
                       .create_agent(name="Agent", instructions='', tools=[fetch_weather]))

        # 获取流式运行结果
        stream_result = Runner.run_streamed(
            starting_agent=agent,
            input="北京的天气怎么样",
            max_turns=10,
            run_config=RunConfig(model_provider=SiadaProvider())
        )

        # 处理流式事件
        print("\n开始处理流式事件...")
        async for event in stream_result.stream_events():
            if event.type == "raw_response_event":
                continue
            # 当Agent更新时，打印相关信息
            elif event.type == "agent_updated_stream_event":
                print(f"Agent更新: {event.new_agent.name}")
            # 当生成项目时，打印相关信息
            elif event.type == "run_item_stream_event":
                if event.item.type == "tool_call_item":
                    print("工具调用")
                elif event.item.type == "tool_call_output_item":
                    print(f"工具输出: {event.item.output}")
                elif event.item.type == "message_output_item":
                    print(f"消息输出:{ItemHelpers.text_message_output(event.item)}")
                else:
                    print(f"其他项目类型: {event.item.type}")
            else:
                print(f"其他事件类型: {event.type}")
                
        print("流式事件处理完成")

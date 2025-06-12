import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import json
import uuid

from src.models.llm_connection import SiadaClient
from src.models.chat_complete import ChatCompletionChunk, Choice, ChoiceDelta
from openai import AsyncStream
from openai.types.chat import ChatCompletion


class TestSiadaClient(unittest.TestCase):
    """测试SiadaClient类"""

    def setUp(self):
        """测试前的设置"""
        self.client = SiadaClient()
        self.test_messages = [
            {"role": "system", "content": "你的名字叫小A，是一名律师"},
            {"role": "user", "content": [{"type": "text", "text": "请介绍一下你自己"}]}
        ]
        
    def test_get_header(self):
        """测试get_header方法"""
        headers = SiadaClient.get_header()
        self.assertEqual(headers, {'Content-Type': 'application/json'})

    async def _run_chat_complete_stream_test(self):
        """测试chat_complete_stream方法的异步执行部分 - 使用真实API调用"""
        # 准备工具数据
        tools = []

        # 调用待测试方法 - 使用真实API
        stream_response = await self.client.chat_complete_stream(
            model="claude-3-5-sonnet",
            messages=self.test_messages,
            temperature=0.7,
            max_tokens=1000,
            tools=tools
        )
        
        # 读取流式响应
        full_response = ""
        print("\n开始接收流式响应:")
        
        async for chunk in stream_response:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                # 打印每个响应块，方便观察
                print(content, end="", flush=True)
        
        print("\n\n完整响应:")
        print(full_response)
        
        # 验证响应不为空
        self.assertTrue(len(full_response) > 0, "响应不应为空")
        return full_response

    def test_chat_complete_stream(self):
        """测试chat_complete_stream方法 - 使用真实API调用"""
        # 运行异步测试
        full_response = asyncio.run(self._run_chat_complete_stream_test())
        print(f"\n获取到的完整响应长度: {len(full_response)}")

    @patch('uuid.uuid4')
    # @patch('requests.post')
    def test_chat_complete(self, mock_uuid):
        """测试chat_complete方法"""
        # 模拟UUID
        mock_uuid_value = "12345678-1234-5678-1234-567812345678"
        mock_uuid.return_value = uuid.UUID(mock_uuid_value)
        
        # # 模拟API响应
        # mock_response = MagicMock()
        # mock_response.status_code = 200
        # mock_response.text = json.dumps({
        #     "id": "chatcmpl-123456789",
        #     "object": "chat.completion",
        #     "created": 1677858242,
        #     "model": "gpt-3.5-turbo-0301",
        #     "choices": [
        #         {
        #             "message": {
        #                 "role": "assistant",
        #                 "content": "我是小A，一名律师。我专注于提供法律咨询和服务。"
        #             },
        #             "finish_reason": "stop"
        #         }
        #     ],
        #     "usage": {
        #         "prompt_tokens": 10,
        #         "completion_tokens": 20,
        #         "total_tokens": 30
        #     }
        # })
        # mock_post.return_value = mock_response
        
        # 调用待测试方法并获取结果
        result = asyncio.run(self.client.chat_complete(
            model="claude-3-5-sonnet",
            messages=self.test_messages,
            temperature=0.7,
            max_tokens=1000
        ))
        
        # 打印结果
        print("result:", result)
        
        # 验证结果不为None
        self.assertIsNotNone(result)

    @patch('uuid.uuid4')
    @patch('requests.post')
    def test_chat_complete_with_claude_model(self, mock_post, mock_uuid):
        """测试使用Claude模型的chat_complete方法"""
        # 模拟UUID
        mock_uuid_value = "12345678-1234-5678-1234-567812345678"
        mock_uuid.return_value = uuid.UUID(mock_uuid_value)
        
        # 模拟API响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "id": "chatcmpl-123456789",
            "object": "chat.completion",
            "created": 1677858242,
            "model": "claude-3-opus-20240229",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "我是小A，一名律师。我专注于提供法律咨询和服务。"
                    },
                    "index": 0,
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        })
        mock_post.return_value = mock_response
        
        # 准备工具数据
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "获取天气信息"
                }
            }
        ]
        
        # 调用待测试方法
        result = self.client.chat_complete(
            model_name="claude-3-opus-20240229",
            messages=self.test_messages,
            temperature=0.7,
            max_tokens=100,
            stop=["END"],
            tools=tools
        )

        print("result:", result)
        # 验证结果
        self.assertIsInstance(result, ChatCompletion)
        
        # 验证请求参数
        request_body = mock_post.call_args[1]['json']
        self.assertEqual(request_body['model_name'], "claude-3-opus-20240229")
        # 验证Claude特定处理
        self.assertEqual(request_body['stop_sequences'], ["END"])  # stop 被转换为 stop_sequences
        self.assertIn('parameters', request_body['tools'][0]['function'])  # 确认添加了parameters字段
        
    @patch('requests.post')
    def test_chat_complete_error(self, mock_post):
        """测试API调用失败的情况"""
        # 模拟API错误响应
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        # 验证异常抛出
        with self.assertRaises(Exception) as context:
            self.client.chat_complete(
                model_name="gpt-3.5-turbo",
                messages=self.test_messages
            )
        
        self.assertIn('Error calling LLM', str(context.exception))


if __name__ == '__main__':
    unittest.main()

from copy import deepcopy
import json
import uuid
from typing import Any, Optional

import httpx
from siada.foundation.constants import LLM_API_CONNECT_TIMEOUT, LLM_API_READ_TIMEOUT
from litellm.types.utils import ModelResponse as LitellmModelResponse
from siada.foundation.logging import logger
from siada.provider.li.domian.li_chat_complete_chunk import LiChatCompletionChunk
from siada.provider.li.stream.__stream import AsyncStream

class SiadaClient:
    """连接Siada LLM服务的客户端类"""

    # 单例客户端实例
    _client: Optional[httpx.Client] = None

    _async_client: Optional[httpx.AsyncClient] = None

    def __init__(self):
        self.llm_url = "http://li-mate-codegen.lixiang.com/llmproxy/callLLMV2"
        self.llm_stream_url = "http://li-mate-codegen.lixiang.com/llmproxy/callLLMStream"

    @classmethod
    def get_client(cls) -> httpx.Client:
        """
        获取或创建HTTP客户端实例

        Returns:
            httpx.Client: HTTP客户端实例
        """
        if cls._client is None:
            cls._client = httpx.Client(
                timeout=httpx.Timeout(
                    connect=LLM_API_CONNECT_TIMEOUT,
                    read=LLM_API_READ_TIMEOUT,
                    write=LLM_API_READ_TIMEOUT,
                    pool=LLM_API_CONNECT_TIMEOUT
                ),
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=30  # 连接保持活跃的秒数
                )
            )
        return cls._client

    @classmethod
    def get_async_client(cls) -> httpx.AsyncClient:
        if cls._async_client is None:
            cls._async_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=LLM_API_CONNECT_TIMEOUT,
                    read=LLM_API_READ_TIMEOUT,
                    write=LLM_API_READ_TIMEOUT,
                    pool=LLM_API_CONNECT_TIMEOUT
                ),
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=30  # 连接保持活跃的秒数
                )
            )

        return cls._async_client

    @staticmethod
    def get_header():
        return {
            'Content-Type': 'application/json',
        }

    @staticmethod
    def _clean_not_given(obj: Any) -> Any:
        """
        递归清理对象中的NotGiven类型值

        Args:
            obj: 需要清理的对象

        Returns:
            清理后的对象
        """
        if obj.__class__.__name__ == 'NotGiven':
            return None
        elif isinstance(obj, dict):
            return {k: SiadaClient._clean_not_given(v) for k, v in obj.items() if v.__class__.__name__ != 'NotGiven'}
        elif isinstance(obj, list):
            return [SiadaClient._clean_not_given(item) for item in obj if item.__class__.__name__ != 'NotGiven']
        else:
            return obj

    @staticmethod
    def _clean_gemini_tools_default(tools: list) -> list:
        """
        为Gemini模型tools中有default但缺少type的参数补充type属性

        Args:
            tools: tools列表

        Returns:
            处理后的tools列表
        """
        if not isinstance(tools, list):
            return tools
            
        # 使用深拷贝避免修改原始数据
        cleaned_tools = deepcopy(tools)
        
        for tool in cleaned_tools:
            if not isinstance(tool, dict):
                continue
                
            # 只处理function类型的tool
            if (tool.get('type') == 'function' and 
                'function' in tool and 
                isinstance(tool['function'], dict)):
                
                function = tool['function']
                
                # 处理parameters.properties中的default属性
                if ('parameters' in function and 
                    isinstance(function['parameters'], dict) and
                    'properties' in function['parameters'] and
                    isinstance(function['parameters']['properties'], dict)):
                    
                    properties = function['parameters']['properties']
                    
                    # 为有default但缺少type的属性补充type
                    for prop_name, prop_value in properties.items():
                        if (isinstance(prop_value, dict) and 
                            'default' in prop_value and 
                            'type' not in prop_value):
                            # 根据default的类型推断type
                            default_value = prop_value['default']
                            inferred_type = SiadaClient._infer_type_from_default(default_value)
                            if inferred_type:
                                prop_value['type'] = inferred_type
        
        return cleaned_tools

    @staticmethod
    def _infer_type_from_default(default_value: Any) -> str:
        """
        根据default值推断JSON Schema type

        Args:
            default_value: 默认值

        Returns:
            str: JSON Schema类型字符串
        """
        if isinstance(default_value, bool):
            return "boolean"
        elif isinstance(default_value, int):
            return "integer"
        elif isinstance(default_value, float):
            return "number"
        elif isinstance(default_value, str):
            return "string"
        elif isinstance(default_value, list):
            return "array"
        elif isinstance(default_value, dict):
            return "object"
        elif default_value is None:
            return "null"
        else:
            # 对于其他类型，默认为string
            return "string"

    @staticmethod
    def _is_gemini_model(model: str) -> bool:
        """
        判断是否为Gemini模型

        Args:
            model: 模型名称

        Returns:
            bool: 是否为Gemini模型
        """
        if not model:
            return False
        return model.lower().startswith('gemini')

    @staticmethod
    def _process_request_body(llm_request_body: dict) -> dict:
        """
        处理请求体，包括清理NotGiven值和Gemini模型特殊处理

        Args:
            llm_request_body: 原始请求体

        Returns:
            dict: 处理后的请求体
        """
        # 清理NotGiven类型的值
        llm_request_body = SiadaClient._clean_not_given(llm_request_body)
        
        # 如果是Gemini模型，清理tools中的default属性
        model_key = 'model' if 'model' in llm_request_body else 'model_name'
        if SiadaClient._is_gemini_model(llm_request_body.get(model_key, '')):
            if 'tools' in llm_request_body:
                llm_request_body['tools'] = SiadaClient._clean_gemini_tools_default(llm_request_body['tools'])
        
        return llm_request_body

    async def chat_complete_stream(self, **kwargs) -> AsyncStream[LiChatCompletionChunk]:
        """
                调用LLM API获取聊天完成结果

        Args:
            **kwargs: LLM参数

        Returns:
            AsyncStream[ChatCompletionChunk]: 流式聊天完成结果
        """
        uid = str(uuid.uuid4())

        llm_request_body = deepcopy(kwargs)

        # 添加UUID
        llm_request_body['uuid'] = uid

        # 处理请求体：清理NotGiven值和Gemini模型特殊处理
        llm_request_body = self._process_request_body(llm_request_body)

        # 记录请求信息，方便调试
        logger.debug(f"request: uuid={uid}, model={llm_request_body.get('model')}")

        # 使用httpx直接发送请求，避免OpenAI客户端的封装可能造成的问题
        async_client = self.get_async_client()

        # 发送请求
        response = await async_client.post(
            "http://li-mate-codegen.lixiang.com/llmproxy/callLLMStream",
            headers=self.get_header(),
            json=llm_request_body,
            timeout=None  # 使用客户端默认超时
        )

        # 检查状态码
        if response.status_code != httpx.codes.OK:
            error_msg = f"request failed: HTTP {response.status_code} - {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        # 创建AsyncStream处理响应
        return AsyncStream[LiChatCompletionChunk](
            response=response,
            cast_to=LiChatCompletionChunk,
        )

    async def chat_complete(self, **kwargs) -> LitellmModelResponse:
        """
        调用LLM API获取聊天完成结果

        Args:
            **kwargs: LLM参数

        Returns:
            LitellmModelResponse: OpenAI格式的聊天完成结果
        """
        uid = str(uuid.uuid4())

        llm_request_body = deepcopy(kwargs)

        llm_request_body['model_name'] = llm_request_body.pop('model', "")

        llm_request_body['uuid'] = uid

        # 处理请求体：清理NotGiven值和Gemini模型特殊处理
        llm_request_body = self._process_request_body(llm_request_body)

        client = self.get_client()
        response = client.post(
            self.llm_url,
            headers=self.get_header(),
            json=llm_request_body,
        )

        if response.status_code != httpx.codes.OK:
            logger.error(f"LLM sync request failed: {response.status_code} - {response.text}")
            raise Exception(f'Error calling LLM, LLM Response: {response.text}')

        # 先将响应文本转换为JSON
        response_json = json.loads(response.text)

        self.pre_process_raw_response(response_json)

        # 构建LitellmModelResponse对象
        chat_completion = LitellmModelResponse.model_validate(response_json)

        return chat_completion

    @staticmethod
    def pre_process_raw_response(response_json: dict):
        """
        预处理原始响应

        Args:
            response_json: 原始响应JSON

        Returns:
            dict: 处理后的响应JSON
        """
        # 处理response_json中的choices中的message中的reasoning_content
        for choice in response_json.get('choices', []):
            if 'message' in choice and 'reasoning_content' in choice['message']:
                reasoning_content = choice['message']['reasoning_content']
                
                if reasoning_content is not None and isinstance(reasoning_content, list):
                    # 添加thinking_blocks字段，赋值为原始list
                    choice['message']['thinking_blocks'] = reasoning_content
                    
                    # 提取thinking类型的内容作为reasoning_content
                    thinking_content = ""
                    for item in reasoning_content:
                        if isinstance(item, dict) and item.get('type') == 'thinking':
                            thinking_content += item.get('thinking', '')
                    
                    # 设置处理后的reasoning_content
                    choice['message']['reasoning_content'] = thinking_content if thinking_content else ""

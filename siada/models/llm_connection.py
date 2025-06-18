from copy import deepcopy
import json
import uuid
from typing import Any, Optional

import httpx
from siada.foundation.constants import LLM_API_CONNECT_TIMEOUT, LLM_API_READ_TIMEOUT
from litellm.types.utils import ModelResponse as LitellmModelResponse
from siada.foundation.logging import logger
from siada.stream.__stream import AsyncStream
from siada.models.chat_complete import ChatCompletionChunk


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

    async def chat_complete_stream(self, **kwargs) -> AsyncStream[ChatCompletionChunk]:
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

        # 清理NotGiven类型的值
        llm_request_body = self._clean_not_given(llm_request_body)

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
        return AsyncStream[ChatCompletionChunk](
            response=response,
            cast_to=ChatCompletionChunk,
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

        # 清理NotGiven类型的值
        llm_request_body = self._clean_not_given(llm_request_body)

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
        # 将response_json中的choices中的message中的reasoning_content, 如果不是str类型，转换为空字符串
        for choice in response_json.get('choices', []):
            if 'message' in choice and 'reasoning_content' in choice['message']:
                if (choice['message']['reasoning_content'] is not None
                        and isinstance(choice['message']['reasoning_content'], list)):
                    choice['message']['reasoning_content'] = ""

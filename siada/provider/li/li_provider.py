from siada.provider.li.domian.li_chat_complete_chunk import LiChatCompletionChunk
import time
import asyncio
from typing import Any, AsyncIterator, Literal, cast, overload

import litellm
from agents import GenerationSpanData, ModelProvider, Model, ModelResponse, Span, TResponseInputItem, \
    AgentOutputSchemaBase, Tool, \
    Handoff, ModelTracing, Usage
from agents.model_settings import  ModelSettings
from agents.extensions.models.litellm_model import LitellmConverter
from agents.items import TResponseStreamEvent
from agents.tracing.create import generation_span
from openai.types.responses import Response
from openai import NOT_GIVEN, NotGiven
from agents.models.chatcmpl_converter import Converter
from agents.models.fake_id import FAKE_RESPONSES_ID

from siada.provider.li.llm_connection import SiadaClient

from litellm.types.utils import ModelResponse as LitellmModelResponse

from siada.foundation.logging import logger
from siada.provider.li.stream.__stream import AsyncStream
from siada.provider.li.stream._stream_handler import ChatCmplStreamHandler as StreamHandler
from agents.models.chatcmpl_helpers import HEADERS



class LiModel(Model):


    def __init__(self, model: str):
        super().__init__()
        self._client = SiadaClient()
        self.model = model
        

    def _non_null_or_not_given(self, value: Any) -> Any:
        return value if value is not None else NOT_GIVEN

    async def get_response(
            self,
            system_instructions: str | None,
            input: str | list[TResponseInputItem],
            model_settings: ModelSettings,
            tools: list[Tool],
            output_schema: AgentOutputSchemaBase | None,
            handoffs: list[Handoff],
            tracing: ModelTracing,
            *,
            previous_response_id: str | None,
            prompt: Any | None
            
    ) -> ModelResponse:
        """Get a response from the model.

        Args:
            system_instructions: The system instructions to use.
            input: The input items to the model, in OpenAI Responses format.
            model_settings: The model settings to use.
            tools: The tools available to the model.
            output_schema: The output schema to use.
            handoffs: The handoffs available to the model.
            tracing: Tracing configuration.
            previous_response_id: the ID of the previous response. Generally not used by the model,
                except for the OpenAI Responses API.
            prompt: The prompt config to use for the model.

        Returns:
            The full model response.
        """
        # 先转换消息格式
        converted_messages = Converter.items_to_messages(input)
        if system_instructions:
            converted_messages.insert(0, {
                "content": system_instructions,
                "role": "system",
            })
        
        with generation_span(
                input=converted_messages if tracing.include_data() else None,  # 使用转换后的消息
                model=str(self.model),
                model_config=model_settings.to_json_dict()
                             | {"model_impl": "siada_llm"},
                disabled=tracing.is_disabled(),
        ) as span_generation:
            response = await self._fetch_response(
                system_instructions,
                input,
                model_settings,
                tools,
                output_schema,
                handoffs,
                span_generation,
                tracing,
                stream=False,
            )

            assert isinstance(response.choices[0], litellm.types.utils.Choices)

            # if _debug.DONT_LOG_MODEL_DATA:
            #     logger.debug("Received model response")
            # else:
            #     logger.debug(
            #         f"LLM resp:\n{json.dumps(response.choices[0].message.model_dump(), indent=2)}\n"
            #     )
            #
            if hasattr(response, "usage"):
                response_usage = response.usage
                usage = (
                    Usage(
                        requests=1,
                        input_tokens=response_usage.prompt_tokens,
                        output_tokens=response_usage.completion_tokens,
                        total_tokens=response_usage.total_tokens,
                    )
                    if response.usage
                    else Usage()
                )
            else:
                usage = Usage()

            if tracing.include_data():
                span_generation.span_data.output = [response.choices[0].message.model_dump()]
            span_generation.span_data.usage = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            }

            items = Converter.message_to_output_items(
                LitellmConverter.convert_message_to_openai(response.choices[0].message)
            )

            return ModelResponse(
                output=items,
                usage=usage,
                response_id=None,
            )

    async def stream_response(
            self,
            system_instructions: str | None,
            input: str | list[TResponseInputItem],
            model_settings: ModelSettings,
            tools: list[Tool],
            output_schema: AgentOutputSchemaBase | None,
            handoffs: list[Handoff],
            tracing: ModelTracing,
            *,
            previous_response_id: str | None,
            prompt: Any | None
    ) -> AsyncIterator[TResponseStreamEvent]:
        """Stream a response from the model.

        Args:
            system_instructions: The system instructions to use.
            input: The input items to the model, in OpenAI Responses format.
            model_settings: The model settings to use.
            tools: The tools available to the model.
            output_schema: The output schema to use.
            handoffs: The handoffs available to the model.
            tracing: Tracing configuration.
            previous_response_id: the ID of the previous response. Generally not used by the model,
                except for the OpenAI Responses API.
            prompt: The prompt config to use for the model.

        Returns:
            An iterator of response stream events, in OpenAI Responses format.
        """
        # 先转换消息格式
        converted_messages = Converter.items_to_messages(input)
        if system_instructions:
            converted_messages.insert(0, {
                "content": system_instructions,
                "role": "system",
            })
        
        with generation_span(
                input=converted_messages if tracing.include_data() else None,  # 使用转换后的消息
                model=str(self.model),
                model_config=model_settings.to_json_dict()
                             | {"model_impl": "siadallm"},
                disabled=tracing.is_disabled(),
        ) as span_generation:
            response, stream = await self._fetch_response(
                system_instructions,
                input,
                model_settings,
                tools,
                output_schema,
                handoffs,
                span_generation,
                tracing,
                stream=True,
            )

            final_response: Response | None = None
            async for chunk in StreamHandler.handle_stream(response, stream):
                yield chunk

                if chunk.type == "response.completed":
                    final_response = chunk.response

            if tracing.include_data() and final_response:
                span_generation.span_data.output = [final_response.model_dump()]

            if final_response and final_response.usage:
                span_generation.span_data.usage = {
                    "input_tokens": final_response.usage.input_tokens,
                    "output_tokens": final_response.usage.output_tokens,
                }

    @overload
    async def _fetch_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        span: Span[GenerationSpanData],
        tracing: ModelTracing,
        stream: Literal[True],
    ) -> tuple[Response, AsyncStream[LiChatCompletionChunk]]: ...

    @overload
    async def _fetch_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        span: Span[GenerationSpanData],
        tracing: ModelTracing,
        stream: Literal[False],
    ) -> LitellmModelResponse: ...


    async def _fetch_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        span: Span[GenerationSpanData],
        tracing: ModelTracing,
        stream: bool = False,
    ) -> LitellmModelResponse | tuple[Response, AsyncStream[LiChatCompletionChunk]]:
        # 检查是否已经在 span 中设置了转换后的消息
        if span.span_data.input:
            converted_messages = span.span_data.input
        else:
            # 如果没有，才进行转换
            converted_messages = Converter.items_to_messages(input)
            if system_instructions:
                converted_messages.insert(
                    0,
                    {
                        "content": system_instructions,
                        "role": "system",
                    },
                )
            if tracing.include_data():
                span.span_data.input = converted_messages

        parallel_tool_calls = (
            True
            if model_settings.parallel_tool_calls and tools and len(tools) > 0
            else False
            if model_settings.parallel_tool_calls is False
            else NOT_GIVEN
        )
        tool_choice = Converter.convert_tool_choice(model_settings.tool_choice)
        response_format = Converter.convert_response_format(output_schema)

        converted_tools = [Converter.tool_to_openai(tool) for tool in tools] if tools else []

        for handoff in handoffs:
            converted_tools.append(Converter.convert_handoff_tool(handoff))


        reasoning_effort = model_settings.reasoning.effort if model_settings.reasoning else None

        stream_options = None
        if stream and model_settings.include_usage is not None:
            stream_options = {"include_usage": model_settings.include_usage}

        extra_kwargs = {}
        if model_settings.extra_query:
            extra_kwargs["extra_query"] = model_settings.extra_query
        if model_settings.metadata:
            extra_kwargs["metadata"] = model_settings.metadata
        if model_settings.extra_body and isinstance(model_settings.extra_body, dict):
            extra_kwargs.update(model_settings.extra_body)

        # Add kwargs from model_settings.extra_args, filtering out None values
        if model_settings.extra_args:
            extra_kwargs.update(model_settings.extra_args)


        complete_kwargs = {
            "model": self.model,
            "messages": converted_messages,
            "tools": converted_tools or None,
            "temperature": model_settings.temperature,
            "top_p": model_settings.top_p,
            "frequency_penalty": model_settings.frequency_penalty,
            "presence_penalty": model_settings.presence_penalty,
            "max_tokens": model_settings.max_tokens,
            "tool_choice": self._remove_not_given(tool_choice),
            "response_format": self._remove_not_given(response_format),
            "parallel_tool_calls": parallel_tool_calls,
            "stream": stream,
            "stream_options": stream_options,
            "reasoning_effort": reasoning_effort,
            "extra_headers": {**HEADERS, **(model_settings.extra_headers or {})},
            "api_key": self.api_key,
            "base_url": self.base_url,
            **extra_kwargs,
        }
        
        if stream:
            ret = await self._client.chat_complete_stream(**complete_kwargs)
        else:
            max_retries = 3
            retry_delay = 30
            
            for attempt in range(max_retries + 1):
                try:
                    ret = await self._client.chat_complete(**complete_kwargs)
                    break
                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(f"chat_complete failed (attempt {attempt + 1}/{max_retries + 1}): {str(e)}")
                        logger.info(f"Waiting {retry_delay} seconds before retry...")
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.error(f"chat_complete failed after maximum retries: {str(e)}")
                        raise
        if isinstance(ret, LitellmModelResponse):
            return ret

        response = Response(
            id=FAKE_RESPONSES_ID,
            created_at=time.time(),
            model=self.model,
            object="response",
            output=[],
            tool_choice=cast(Literal["auto", "required", "none"], tool_choice)
            if tool_choice != NOT_GIVEN
            else "auto",
            top_p=model_settings.top_p,
            temperature=model_settings.temperature,
            tools=[],
            parallel_tool_calls=parallel_tool_calls or False,
            reasoning=model_settings.reasoning,
        )
        return response, ret
    
    def _remove_not_given(self, value: Any) -> Any:
        if isinstance(value, NotGiven):
            return None
        return value




class SiadaProvider(ModelProvider):
    """The base interface for a model provider.

    Model provider is responsible for looking up Models by name.
    """

    def get_model(self, model_name: str | None) -> Model:
        """Get a model by name.

        Args:
            model_name: The name of the model to get.

        Returns:
            The model.
        """
        return LiModel(model=model_name)

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from agents import AgentOutputSchemaBase, Handoff, Model, ModelSettings, ModelTracing, ModelResponse
from agents.exceptions import UserError
from agents.tool import Tool
from agents.tracing import generation_span
from agents.usage import Usage
from google import genai
from openai.types.responses import (
    Response, ResponseCompletedEvent, ResponseContentPartAddedEvent, ResponseContentPartDoneEvent,
    ResponseCreatedEvent, ResponseFunctionCallArgumentsDeltaEvent, ResponseFunctionCallArgumentsDoneEvent,
    ResponseOutputItemAddedEvent, ResponseOutputItemDoneEvent, ResponseReasoningSummaryPartAddedEvent,
    ResponseReasoningSummaryPartDoneEvent, ResponseReasoningSummaryTextDeltaEvent,
    ResponseReasoningSummaryTextDoneEvent, ResponseTextDeltaEvent, ResponseTextDoneEvent,
)
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails, ResponseUsage
from pydantic import ValidationError

from siada.provider.gemini.converter import build_config, items_to_contents
from siada.provider.gemini.routing import wire_model_name
from siada.provider.gemini.stream_handler import GeminiResponseAssembly
from siada.provider.gemini.transport import GeminiTransport
from siada.provider.retry import MissingFinalResponseError


class GeminiModel(Model):
    request_protocol = "gemini"
    supports_native_responses_items = False

    @property
    def replay_domain(self) -> str:
        return f"{self._transport.provider}:{self._transport.backend}"

    def __init__(self, model: str, *, client: genai.Client | None = None, transport: GeminiTransport | None = None):
        if client is not None and transport is not None:
            raise ValueError("Pass either a Gen AI client or a Gemini transport, not both.")
        self.model = wire_model_name(model)
        self._owns_transport = transport is None and client is None
        if transport is None and client is None:
            from siada.provider.default.gemini_transport import DefaultGeminiTransport
            transport = DefaultGeminiTransport()
        self._transport = transport or GeminiTransport(client)

    def _request(self, instructions, input, settings, tools, output_schema, handoffs, previous_response_id, conversation_id, prompt):
        if previous_response_id or conversation_id or prompt:
            raise UserError("Gemini uses client-owned Content history, not server-owned Responses state.")
        failure = None
        try:
            contents, extra_instructions = items_to_contents(input, self._transport.origin(self.model))
            config = build_config(settings, tools, handoffs, output_schema, instructions, extra_instructions, self.model)
            return contents, config
        except (ValidationError, KeyError, IndexError, TypeError, ValueError):
            failure = UserError("Invalid native Gemini input or configuration; no model request was sent.")
        raise failure

    @staticmethod
    def _usage(assembly: GeminiResponseAssembly) -> tuple[Usage, ResponseUsage | None]:
        raw = assembly.usage
        if raw is None:
            return Usage(requests=1), None
        prompt_tokens = raw.prompt_token_count or 0
        cached_tokens = raw.cached_content_token_count or 0
        input_tokens = max(0, prompt_tokens - cached_tokens)
        output_tokens = (raw.candidates_token_count or 0) + (raw.thoughts_token_count or 0)
        total_tokens = raw.total_token_count or prompt_tokens + output_tokens
        response_usage = ResponseUsage(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens,
                                       input_tokens_details=InputTokensDetails(cached_tokens=cached_tokens, cache_write_tokens=0),
                                       output_tokens_details=OutputTokensDetails(reasoning_tokens=raw.thoughts_token_count or 0))
        return Usage(requests=1, input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens,
                     input_tokens_details=response_usage.input_tokens_details, output_tokens_details=response_usage.output_tokens_details), response_usage

    def _response(self, assembly: GeminiResponseAssembly, settings: ModelSettings) -> Response:
        _agents_usage, usage = self._usage(assembly)
        response = Response(id=assembly.response_id, object="response", created_at=time.time(), model=self.model,
                            output=assembly.output, status="completed", error=None, incomplete_details=None,
                            parallel_tool_calls=settings.parallel_tool_calls is not False, tool_choice="auto", tools=[],
                            temperature=settings.temperature, top_p=settings.top_p, usage=usage)
        if settings.preserve_raw_usage and assembly.usage is not None:
            response.raw_usage = assembly.usage.model_dump(mode="json", exclude_none=True)
        return response

    async def get_response(self, system_instructions: str | None, input: Any, model_settings: ModelSettings, tools: list[Tool],
                           output_schema: AgentOutputSchemaBase | None, handoffs: list[Handoff], tracing: ModelTracing,
                           *, previous_response_id: str | None = None, conversation_id: str | None = None, prompt: Any = None) -> ModelResponse:
        with generation_span(model=self.model, model_config={"model_impl": "google_genai"}, disabled=tracing.is_disabled()) as span:
            contents, config = self._request(system_instructions, input, model_settings, tools, output_schema, handoffs, previous_response_id, conversation_id, prompt)
            response = await self._transport.generate(self.model, contents, config)
            assembly = GeminiResponseAssembly(self._transport.origin(self.model))
            assembly.add(response)
            output = assembly.finalize(parallel_tool_calls=model_settings.parallel_tool_calls)
            usage, _response_usage = self._usage(assembly)
            span.span_data.usage = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
            return ModelResponse(output=output, usage=usage, response_id=assembly.response_id,
                                 raw_usage=assembly.usage.model_dump(mode="json", exclude_none=True) if model_settings.preserve_raw_usage and assembly.usage else None)

    async def stream_response(self, system_instructions: str | None, input: Any, model_settings: ModelSettings, tools: list[Tool],
                              output_schema: AgentOutputSchemaBase | None, handoffs: list[Handoff], tracing: ModelTracing,
                              *, previous_response_id: str | None = None, conversation_id: str | None = None, prompt: Any = None) -> AsyncIterator[Any]:
        with generation_span(model=self.model, model_config={"model_impl": "google_genai"}, disabled=tracing.is_disabled()) as span:
            stream = self._stream_response(system_instructions, input, model_settings, tools, output_schema, handoffs,
                                           previous_response_id, conversation_id, prompt)
            try:
                async for event in stream:
                    if event.type == "response.completed" and event.response.usage is not None:
                        usage = event.response.usage
                        span.span_data.usage = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
                    yield event
            finally:
                await stream.aclose()

    async def _stream_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs,
                               previous_response_id, conversation_id, prompt):
        contents, config = self._request(system_instructions, input, model_settings, tools, output_schema, handoffs, previous_response_id, conversation_id, prompt)
        assembly = GeminiResponseAssembly(self._transport.origin(self.model))
        sequence = 0
        initial = self._response(assembly, model_settings)
        initial.status = "in_progress"
        initial.usage = None
        yield ResponseCreatedEvent(response=initial, type="response.created", sequence_number=sequence)
        sequence += 1
        added: set[int] = set()
        exposed = False
        stream = self._transport.stream(self.model, contents, config)
        try:
            async for chunk in stream:
                for index, kind, delta in assembly.add(chunk):
                    item = assembly.output[index]
                    if index not in added:
                        empty = item.model_copy(deep=True)
                        if kind == "message":
                            empty.content = []
                        else:
                            empty.summary = []
                        yield ResponseOutputItemAddedEvent(item=empty, output_index=index, type="response.output_item.added", sequence_number=sequence)
                        sequence += 1
                        added.add(index)
                        if kind == "message":
                            yield ResponseContentPartAddedEvent(item_id=item.id, output_index=index, content_index=0,
                                                                part=item.content[0].model_copy(update={"text": ""}),
                                                                type="response.content_part.added", sequence_number=sequence)
                        else:
                            yield ResponseReasoningSummaryPartAddedEvent(item_id=item.id, output_index=index, summary_index=0,
                                                                         part={"type": "summary_text", "text": ""},
                                                                         type="response.reasoning_summary_part.added", sequence_number=sequence)
                        sequence += 1
                    if delta:
                        if kind == "message":
                            exposed = True
                            yield ResponseTextDeltaEvent(item_id=item.id, output_index=index, content_index=0, delta=delta,
                                                         logprobs=[], type="response.output_text.delta", sequence_number=sequence)
                        else:
                            yield ResponseReasoningSummaryTextDeltaEvent(item_id=item.id, output_index=index, summary_index=0,
                                                                        delta=delta, type="response.reasoning_summary_text.delta", sequence_number=sequence)
                        sequence += 1
            if assembly.finish_reason is None:
                raise MissingFinalResponseError(model=self.model, response_id=assembly.response_id, last_event=None, output_exposed=exposed)
            assembly.finalize(parallel_tool_calls=model_settings.parallel_tool_calls)
            for index, item in sorted(enumerate(assembly.output), key=lambda entry: entry[1].type == "function_call"):
                if index not in added:
                    empty = item.model_copy(deep=True)
                    empty.status = "in_progress"
                    if item.type == "function_call":
                        empty.arguments = ""
                    yield ResponseOutputItemAddedEvent(item=empty, output_index=index, type="response.output_item.added", sequence_number=sequence)
                    sequence += 1
                if item.type == "function_call":
                    yield ResponseFunctionCallArgumentsDeltaEvent(item_id=item.id, output_index=index, delta=item.arguments,
                                                                 type="response.function_call_arguments.delta", sequence_number=sequence)
                    sequence += 1
                    yield ResponseFunctionCallArgumentsDoneEvent(item_id=item.id, output_index=index, name=item.name, arguments=item.arguments,
                                                                type="response.function_call_arguments.done", sequence_number=sequence)
                    sequence += 1
                elif item.type == "message" and item.content:
                    yield ResponseTextDoneEvent(item_id=item.id, output_index=index, content_index=0, text=item.content[0].text, logprobs=[],
                                                type="response.output_text.done", sequence_number=sequence)
                    sequence += 1
                    yield ResponseContentPartDoneEvent(item_id=item.id, output_index=index, content_index=0, part=item.content[0],
                                                       type="response.content_part.done", sequence_number=sequence)
                    sequence += 1
                elif item.type == "reasoning":
                    yield ResponseReasoningSummaryTextDoneEvent(item_id=item.id, output_index=index, summary_index=0, text=item.summary[0].text,
                                                               type="response.reasoning_summary_text.done", sequence_number=sequence)
                    sequence += 1
                    yield ResponseReasoningSummaryPartDoneEvent(item_id=item.id, output_index=index, summary_index=0,
                                                                part={"type": "summary_text", "text": item.summary[0].text},
                                                                type="response.reasoning_summary_part.done", sequence_number=sequence)
                    sequence += 1
                yield ResponseOutputItemDoneEvent(item=item, output_index=index, type="response.output_item.done", sequence_number=sequence)
                sequence += 1
            yield ResponseCompletedEvent(response=self._response(assembly, model_settings), type="response.completed", sequence_number=sequence)
        finally:
            await stream.aclose()

    async def close(self) -> None:
        if self._owns_transport:
            await self._transport.aclose()

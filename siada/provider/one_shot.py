"""Standalone SDK model requests with Siada input compatibility and ownership."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import nullcontext
from dataclasses import fields
from typing import Any

from agents import ModelResponse, ModelSettings, ModelTracing, TResponseInputItem
from agents.exceptions import ModelBehaviorError
from agents.items import ItemHelpers, TResponseOutputItem, TResponseStreamEvent
from agents.usage import Usage, _extract_raw_usage_snapshot, _response_usage_to_usage
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared import Reasoning

from siada.foundation.context import agent_name_scope
from siada.provider.chat_completions import reorder_tool_call_output_items
from siada.provider.provider_factory import get_provider, resolve_provider_by_model
from siada.provider.retry import model_retry_scope
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelProviderWrapper
from siada.support.chat_compat_items import to_chat_compatible_items


def extract_response_text(response: ModelResponse | None) -> str:
    """Extract assistant text only, excluding reasoning, refusals, and tool calls."""
    if response is None:
        return ""
    return "".join(ItemHelpers.extract_text(item) or "" for item in response.output)


def _chat_messages_to_input(
    messages: list[ChatCompletionMessageParam],
) -> list[TResponseInputItem]:
    """Adapt legacy text/image messages and completed tool pairs to SDK inputs."""
    items: list[Any] = []
    for message in messages:
        role = message["role"]
        content = message.get("content")
        if role == "tool":
            items.append({
                "type": "function_call_output",
                "call_id": message["tool_call_id"],
                "output": content or "",
            })
            continue
        if role not in {"system", "developer", "user", "assistant"}:
            raise ValueError(f"Unsupported one-shot message role: {role!r}")
        if isinstance(content, list):
            converted = []
            for part in content:
                if part["type"] == "text":
                    converted.append({"type": "input_text", "text": part["text"]})
                elif part["type"] == "image_url":
                    image = part["image_url"]
                    converted.append({
                        "type": "input_image",
                        "image_url": image["url"],
                        "detail": image.get("detail", "auto"),
                    })
                else:
                    raise ValueError(f"Unsupported one-shot content type: {part['type']!r}")
            content = converted
        if content is not None:
            items.append({"role": role, "content": content})
        for tool_call in message.get("tool_calls", []):
            if tool_call["type"] != "function":
                raise ValueError("Only function tool-call history is supported")
            items.append({
                "type": "function_call",
                "call_id": tool_call["id"],
                "name": tool_call["function"]["name"],
                "arguments": tool_call["function"]["arguments"],
            })
    return items


def _build_model_settings(
    settings: ModelSettings | None, kwargs: dict[str, Any]
) -> ModelSettings:
    """Map completion options to SDK settings without mutating caller values."""
    values = dict(kwargs)
    effort = values.pop("reasoning_effort", None)
    if effort is not None and "reasoning" not in values:
        values["reasoning"] = Reasoning(effort=effort)
    if "max_completion_tokens" in values:
        values.setdefault("max_tokens", values.pop("max_completion_tokens"))
    known_fields = {field.name for field in fields(ModelSettings)}
    overrides = {key: value for key, value in values.items() if key in known_fields}
    extra_args = dict((settings.extra_args if settings else None) or {})
    extra_args.update(overrides.pop("extra_args", None) or {})
    extra_args.update({key: value for key, value in values.items() if key not in known_fields})
    result = (settings or ModelSettings()).resolve(overrides)
    if result.timeout is not None:
        # Direct Model calls do not get Runner's timeout enforcement. Bound both
        # cooperative cancellation and the provider's socket attempt.
        extra_args["timeout"] = result.timeout
    if extra_args:
        reserved = {
            "stream", "tools", "handoffs", "model", "messages", "input",
            "api_base", "base_url", "api_key",
        }
        if invalid := reserved.intersection(extra_args):
            raise ValueError(f"Reserved one-shot request options in extra_args: {sorted(invalid)}")
        result = result.resolve({"extra_args": extra_args})
    return result


async def _collect_final_response(
    stream: AsyncIterator[TResponseStreamEvent], settings: ModelSettings,
) -> ModelResponse:
    """Consume a single SDK stream without exposing deltas or accepting partial output."""
    output_items: dict[int, TResponseOutputItem] = {}
    try:
        async for event in stream:
            if event.type in {"response.failed", "response.incomplete", "error", "response.error"}:
                raise ModelBehaviorError(f"One-shot model stream terminated with {event.type}")
            if event.type == "response.output_item.done":
                output_items[event.output_index] = event.item
            elif event.type == "response.completed":
                response = event.response
                # Chat adapters synthesize a Responses body without a status;
                # the completed event is authoritative unless status contradicts it.
                if response is None or getattr(response, "status", None) not in {None, "completed"}:
                    raise ModelBehaviorError("One-shot model stream has no completed response body")
                # Providers already normalize usage, including cached input tokens.
                # Reuse the SDK conversion rather than subtracting cache tokens again.
                usage = _response_usage_to_usage(response.usage) if response.usage else Usage(requests=1)
                return ModelResponse(
                    output=response.output or [output_items[index] for index in sorted(output_items)],
                    usage=usage,
                    response_id=response.id,
                    request_id=getattr(response, "_request_id", None),
                    raw_usage=(
                        _extract_raw_usage_snapshot(response, fallback=response.usage)
                        if settings.preserve_raw_usage is True else None
                    ),
                )
        raise ModelBehaviorError("One-shot model stream ended without a final response")
    finally:
        # Close only this request's iterator; the runtime still owns the provider.
        close = getattr(stream, "aclose", None)
        if close is not None:
            await close()


async def one_shot_completion(
    input: str | list[TResponseInputItem],
    *,
    model: str | None,
    provider: str | None = None,
    system_instructions: str | None = None,
    messages: list[ChatCompletionMessageParam] | None = None,
    model_settings: ModelSettings | None = None,
    agent_name: str | None = None,
    tracing: ModelTracing = ModelTracing.DISABLED,
    stream: bool = True,
    num_retries: int | None = None,
    **kwargs: Any,
) -> ModelResponse:
    """Make one model call and return its final response, borrowing the provider.

    Streaming transport is used by default, consuming SDK events internally.
    Set stream=False to explicitly use non-streaming transport instead.
    The caller always receives a complete ModelResponse, never an iterator.
    An explicit timeout bounds the whole request, including stream consumption.
    Endpoint overrides require a provider implementing request_scope (the
    default provider). Tools are never offered or executed, and no session
    admission callback is installed. Transport retries remain provider-owned.
    """
    options = dict(kwargs)
    if options.pop("tools", None) or options.pop("handoffs", None):
        raise ValueError("one_shot_completion does not offer tools or handoffs")
    base_url = options.pop("base_url", options.pop("api_base", None))
    api_key = options.pop("api_key", None)
    settings = _build_model_settings(model_settings, options)
    input_items = _chat_messages_to_input(messages) if messages is not None else input

    # The scope starts before model resolution: some providers select endpoints
    # and headers from the agent-name context while constructing their models.
    with model_retry_scope(num_retries), agent_name_scope(agent_name):
        base_provider = get_provider(resolve_provider_by_model(model, provider))
        request_scope = nullcontext()
        if base_url is not None or api_key is not None:
            scope_factory = getattr(base_provider, "request_scope", None)
            if scope_factory is None:
                raise ValueError(
                    "This provider does not support request-local endpoint overrides; "
                    "use provider='default' for an independent custom endpoint"
                )
            request_scope = scope_factory(base_url=base_url, api_key=api_key)
        with request_scope:
            wrapped_provider = ModelProviderWrapper(
                base_provider=base_provider, input_processor=process_input
            )
            selected_model = wrapped_provider.get_model(model)
            if num_retries is not None:
                # LiteLLM has an independent retry layer. Native SDK clients
                # disable it at construction; retained vendor adapters need
                # their own option so the durable learning queue owns retries.
                from agents.extensions.models.litellm_model import LitellmModel

                if isinstance(selected_model.wrapped_model, LitellmModel):
                    extra_args = dict(settings.extra_args or {})
                    extra_args["num_retries"] = 0
                    settings = settings.resolve({"extra_args": extra_args})
            if isinstance(input_items, list) and not selected_model.supports_native_responses_items:
                # Compaction can replay interleaved completed tool pairs into any
                # Chat adapter, not only Kimi. Repair item order before conversion.
                input_items = reorder_tool_call_output_items(to_chat_compatible_items(input_items))
            request_args = {
                "system_instructions": system_instructions,
                "input": input_items,
                "model_settings": settings,
                "tools": [],
                "output_schema": None,
                "handoffs": [],
                "tracing": tracing,
                "previous_response_id": None,
                "conversation_id": None,
                "prompt": None,
            }
            request = (
                _collect_final_response(selected_model.stream_response(**request_args), settings)
                if stream else selected_model.get_response(**request_args)
            )
            if settings.timeout is not None:
                return await asyncio.wait_for(request, timeout=settings.timeout)
            return await request
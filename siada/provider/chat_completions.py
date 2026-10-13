"""Shared compatibility helpers for OpenAI Chat Completions models."""

from __future__ import annotations

from functools import wraps
from inspect import signature
from typing import Any

from agents.models.chatcmpl_converter import Converter
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI


def _install_tool_output_image_adapter() -> None:
    """Preserve tool-result images for every model, installing once across reloads."""
    current_converter = Converter.items_to_messages
    if getattr(current_converter, "_siada_tool_output_image_adapter", False):
        return

    original_converter = current_converter.__func__
    converter_signature = signature(original_converter)

    @wraps(original_converter)
    def items_to_messages(cls: type[Converter], *args: Any, **kwargs: Any) -> list[Any]:
        bound = converter_signature.bind(cls, *args, **kwargs)
        bound.arguments["preserve_tool_output_all_content"] = True
        return original_converter(*bound.args, **bound.kwargs)

    setattr(items_to_messages, "_siada_tool_output_image_adapter", True)
    Converter.items_to_messages = classmethod(items_to_messages)


_install_tool_output_image_adapter()


def _item_field(item: Any, field: str) -> Any:
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


def reorder_tool_call_output_items(items: list) -> list:
    """Re-pair ``function_call_output`` items with their ``function_call`` items.

    Moves each ``function_call_output`` so that it directly follows the
    ``function_call`` item holding the same ``call_id``.  After
    ``Converter.items_to_messages`` runs on the reordered list, every
    ``role: "tool"`` message immediately follows the assistant message that
    declared its ``tool_call_id`` -- the ordering Kimi/Moonshot APIs require.

    Rules:
    - Returns a new list; neither the input list nor its items are mutated.
    - Only outputs that appear *after* their call are moved; outputs that
      precede their call, orphaned outputs (no matching call) and items that
      are not function calls/outputs keep their original relative order.
    - If there is nothing to move, the input list is returned as-is.
    """
    output_indices: dict[Any, int] = {}
    for index, item in enumerate(items):
        if _item_field(item, "type") == "function_call_output":
            call_id = _item_field(item, "call_id")
            if call_id and call_id not in output_indices:
                output_indices[call_id] = index

    if not output_indices:
        return items

    moved: set[int] = set()
    reordered: list = []
    for index, item in enumerate(items):
        if index in moved:
            continue
        reordered.append(item)
        if _item_field(item, "type") != "function_call":
            continue
        output_index = output_indices.get(_item_field(item, "call_id"))
        if output_index is not None and output_index > index and output_index not in moved:
            reordered.append(items[output_index])
            moved.add(output_index)
    return reordered


class KimiToolOrderingMixin:
    """Preserve Kimi/Moonshot's required call/result adjacency before SDK conversion."""

    async def _fetch_response(self, *args: Any, **kwargs: Any) -> Any:
        positional_args = list(args)
        if len(positional_args) > 1:
            input_items = positional_args[1]
            input_in_kwargs = False
        else:
            input_items = kwargs.get("input")
            input_in_kwargs = True

        model_name = str(self.model).lower()
        if (
            isinstance(input_items, list)
            and ("kimi" in model_name or "moonshot" in model_name)
        ):
            reordered = reorder_tool_call_output_items(input_items)
            if input_in_kwargs:
                kwargs["input"] = reordered
            else:
                positional_args[1] = reordered

        return await super()._fetch_response(*positional_args, **kwargs)


class RefreshingOpenAIClientMixin:
    """Refresh a provider-owned OpenAI client before each model call."""

    _client_factory: Any

    def _refresh_openai_client(self) -> AsyncOpenAI:
        client = self._client_factory.get_client()
        self._client = client
        return client

    async def get_response(self, *args: Any, **kwargs: Any) -> Any:
        self._refresh_openai_client()
        return await super().get_response(*args, **kwargs)

    async def stream_response(self, *args: Any, **kwargs: Any) -> Any:
        self._refresh_openai_client()
        stream = super().stream_response(*args, **kwargs)
        try:
            async for event in stream:
                yield event
        finally:
            aclose = getattr(stream, "aclose", None)
            if callable(aclose):
                await aclose()
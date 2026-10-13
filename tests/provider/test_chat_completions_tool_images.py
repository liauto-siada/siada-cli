"""Unconditional tool-image preservation for SDK Chat Completions conversion."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from contextvars import ContextVar
from inspect import signature
from runpy import run_path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio
from agents import ModelSettings, ToolOutputImage
from agents.items import ItemHelpers
from agents.models.chatcmpl_converter import Converter
from agents.models.interface import ModelTracing
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI
from openai.types.responses import ResponseFunctionToolCall

from siada.foundation import context as foundation_context
from siada.foundation.context import LLM_CONFIG, context_var_scope, get_context_var
from siada.provider import chat_completions
from siada.provider.default.chat_completions import DefaultOpenAIChatCompletionsModel
from siada.provider.reasoning_replay import should_replay_reasoning_content


IMAGE_URL = "data:image/png;base64,aW1hZ2U="


def _tool_history(*, image_only: bool = False) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = [{"type": "input_image", "image_url": IMAGE_URL}]
    if not image_only:
        output.insert(0, {"type": "input_text", "text": "image evidence"})
    return [
        {
            "type": "function_call",
            "call_id": "call-image",
            "name": "edit_file",
            "arguments": '{"command":"view","path":"image.png"}',
        },
        {"type": "function_call_output", "call_id": "call-image", "output": output},
        {"role": "user", "content": "describe the image"},
    ]


def _assert_tool_content(body: dict[str, Any]) -> None:
    tool_message = next(
        message for message in body["messages"] if message["role"] == "tool"
    )
    assert tool_message["tool_call_id"] == "call-image"
    expected_content = [
        {"type": "text", "text": "image evidence"},
        {"type": "image_url", "image_url": {"url": IMAGE_URL, "detail": "auto"}},
    ]
    assert tool_message["content"] == expected_content


async def _request(model: Any, items: Any, *, stream: bool = False) -> Any:
    kwargs = {
        "system_instructions": None,
        "input": items,
        "model_settings": ModelSettings(),
        "tools": [],
        "output_schema": None,
        "handoffs": [],
        "tracing": ModelTracing.DISABLED,
    }
    if stream:
        return [event async for event in model.stream_response(**kwargs)]
    return await model.get_response(**kwargs)


@pytest_asyncio.fixture(params=["default", "sdk"])
async def chat_transport(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    captured: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured.append(body)
        await asyncio.sleep(0)
        if body.get("stream"):
            chunks = [
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": body["model"],
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": "ok"},
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": body["model"],
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
            ]
            sse = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=sse + "data: [DONE]\n\n",
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
            request=request,
        )

    client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://gateway.test/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    factory = SimpleNamespace(get_client=lambda *args: client)
    if request.param == "default":

        def make_model(model_name: str):
            return DefaultOpenAIChatCompletionsModel(
                model_name, factory, should_replay_reasoning_content
            )

    else:

        def make_model(model_name: str):
            return OpenAIChatCompletionsModel(model_name, client)

    try:
        yield make_model, captured
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["gpt-4o", "glm-5.2", "kimi-k3", "custom-model"])
@pytest.mark.parametrize("stream", [False, True])
async def test_tool_images_are_preserved_regardless_of_current_config(
    chat_transport, model_name: str, stream: bool
):
    make_model, captured = chat_transport
    with context_var_scope(LLM_CONFIG, SimpleNamespace(supports_images=False)):
        model = make_model(model_name)
    items = _tool_history()
    original_items = deepcopy(items)
    config = SimpleNamespace(supports_images=True)
    with context_var_scope(LLM_CONFIG, config):
        for supports_images in (True, False, True):
            config.supports_images = supports_images
            await _request(model, items, stream=stream)
            _assert_tool_content(captured[-1])
    for missing_config in (SimpleNamespace(), None):
        with context_var_scope(LLM_CONFIG, missing_config):
            await _request(model, items, stream=stream)
            _assert_tool_content(captured[-1])
    assert items == original_items


@pytest.mark.asyncio
async def test_concurrent_requests_preserve_images_regardless_of_config(chat_transport):
    make_model, captured = chat_transport
    model = make_model("glm-5.2")
    original_config = get_context_var(LLM_CONFIG)
    ready = asyncio.Event()
    started = 0

    async def send(supports_images: bool) -> None:
        nonlocal started
        config = SimpleNamespace(supports_images=supports_images)
        with context_var_scope(LLM_CONFIG, config):
            started += 1
            if started == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), timeout=5)
            items = _tool_history()
            items[-1]["content"] = f"supports_images={supports_images}"
            await _request(model, items)

    await asyncio.gather(send(True), send(False))
    assert len(captured) == 2
    assert {body["messages"][-1]["content"] for body in captured} == {
        "supports_images=True",
        "supports_images=False",
    }
    for body in captured:
        _assert_tool_content(body)
    assert get_context_var(LLM_CONFIG) is original_config


@pytest.mark.parametrize("image_only", [False, True])
def test_unavailable_context_does_not_affect_tool_images(
    monkeypatch: pytest.MonkeyPatch, image_only: bool
):
    monkeypatch.setattr(
        foundation_context, "context_dict_var", ContextVar("unavailable_context")
    )
    messages = Converter.items_to_messages(
        _tool_history(image_only=image_only), preserve_tool_output_all_content=False
    )
    assert messages[1]["content"][-1] == {
        "type": "image_url",
        "image_url": {"url": IMAGE_URL, "detail": "auto"},
    }


@pytest.mark.parametrize("preserve_content", [True, False])
def test_adapter_overrides_positional_preservation_flag(preserve_content: bool):
    with context_var_scope(LLM_CONFIG, SimpleNamespace(supports_images=False)):
        messages = Converter.items_to_messages(
            _tool_history(), "glm-5.2", False, preserve_content
        )
    _assert_tool_content({"messages": messages})


@pytest.mark.parametrize("preserve_content", [True, False])
def test_adapter_overrides_keyword_preservation_flag(preserve_content: bool):
    with context_var_scope(LLM_CONFIG, SimpleNamespace(supports_images=False)):
        messages = Converter.items_to_messages(
            _tool_history(), preserve_tool_output_all_content=preserve_content
        )
    _assert_tool_content({"messages": messages})


def test_adapter_does_not_read_image_capability():
    class UnreliableConfig:
        @property
        def supports_images(self) -> bool:
            raise AssertionError("Tool conversion must not read supports_images")

    with context_var_scope(LLM_CONFIG, UnreliableConfig()):
        messages = Converter.items_to_messages(_tool_history())
    _assert_tool_content({"messages": messages})


def test_adapter_installs_once_and_preserves_classmethod_contract():
    converter_function = Converter.items_to_messages.__func__
    converter_signature = signature(Converter.items_to_messages)
    original_signature = signature(converter_function.__wrapped__)
    chat_completions._install_tool_output_image_adapter()
    chat_completions._install_tool_output_image_adapter()
    run_path(chat_completions.__file__)
    assert Converter.items_to_messages.__func__ is converter_function
    assert signature(Converter.items_to_messages) == converter_signature
    assert converter_signature == original_signature.replace(
        parameters=list(original_signature.parameters.values())[1:]
    )

    class CustomConverter(Converter):
        @classmethod
        def extract_all_content(cls, content: Any) -> str:
            return "custom conversion"

    with context_var_scope(LLM_CONFIG, SimpleNamespace(supports_images=True)):
        messages = CustomConverter.items_to_messages(_tool_history())
    assert messages[1]["content"] == "custom conversion"


@pytest.mark.asyncio
async def test_image_only_tool_output_is_preserved_with_capability_disabled(
    chat_transport,
):
    make_model, captured = chat_transport
    with context_var_scope(LLM_CONFIG, SimpleNamespace(supports_images=False)):
        await _request(make_model("glm-5.2"), _tool_history(image_only=True))
    tool_message = captured[0]["messages"][1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call-image"
    assert tool_message["content"] == [
        {"type": "image_url", "image_url": {"url": IMAGE_URL, "detail": "auto"}}
    ]


def test_tui_image_only_input_is_rejected_when_disabled():
    from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
    from siada.entrypoint.interaction.turn.interface import ImageNotSupportedError

    turn = ConversationTurn.__new__(ConversationTurn)
    turn.config = SimpleNamespace(
        llm_config=SimpleNamespace(supports_images=False),
        io=SimpleNamespace(_pending_image_paths=["image.png"]),
    )
    with pytest.raises(ImageNotSupportedError):
        turn._resolve_image_input("[Image #1]", ["image.png"])
    assert turn.config.io._pending_image_paths is None


@pytest.mark.asyncio
@pytest.mark.parametrize("supports_images", [True, False])
async def test_edit_file_and_tui_image_entry_guards_are_unchanged(
    chat_transport, tmp_path, supports_images: bool
):
    from PIL import Image

    from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
    from siada.tools.coder.file_operator import _edit_file
    from siada.tools.coder.observation.error import ErrorObservation

    image_path = tmp_path / "image.png"
    Image.new("RGB", (2, 2), color="white").save(image_path)
    config = SimpleNamespace(supports_images=supports_images)
    turn = ConversationTurn.__new__(ConversationTurn)
    turn.config = SimpleNamespace(
        llm_config=config, io=SimpleNamespace(_pending_image_paths=[str(image_path)])
    )
    user_input = turn._resolve_image_input("describe the image", [str(image_path)])
    assert turn.config.io._pending_image_paths is None
    context = SimpleNamespace(
        context=SimpleNamespace(root_dir=str(tmp_path), model_run_config=config)
    )
    output = _edit_file(context, "view", str(image_path))
    if supports_images:
        assert isinstance(output, ToolOutputImage)
        assert user_input[0]["content"][1]["type"] == "input_image"
    else:
        assert isinstance(output, ErrorObservation)
        assert user_input == "describe the image"

    tool_call = ResponseFunctionToolCall(
        type="function_call",
        call_id="call-image",
        name="edit_file",
        arguments='{"command":"view","path":"image.png"}',
    )
    user_items = (
        user_input
        if isinstance(user_input, list)
        else [{"role": "user", "content": user_input}]
    )
    items = [
        tool_call.model_dump(),
        ItemHelpers.tool_call_output_item(tool_call, output),
        *user_items,
    ]
    make_model, captured = chat_transport
    with context_var_scope(LLM_CONFIG, config):
        await _request(make_model("glm-5.2"), items)
    messages = captured[0]["messages"]
    assert ("image_url" in json.dumps(messages[1])) is supports_images
    assert ("image_url" in json.dumps(messages[-1])) is supports_images


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_transport", ["default"], indirect=True)
@pytest.mark.parametrize("supports_images", [True, False])
async def test_kimi_tool_ordering_is_preserved_with_image_outputs(
    chat_transport, supports_images: bool
):
    make_model, captured = chat_transport
    items = _tool_history()[:1] + [
        {
            "type": "message",
            "id": "message-progress",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "working"}],
        },
        {
            "type": "function_call",
            "call_id": "call-text",
            "name": "tool_text",
            "arguments": "{}",
        },
        _tool_history()[1],
        {"type": "function_call_output", "call_id": "call-text", "output": "text evidence"},
        {"role": "user", "content": "continue"},
    ]
    original_items = deepcopy(items)
    with context_var_scope(LLM_CONFIG, SimpleNamespace(supports_images=supports_images)):
        await _request(make_model("kimi-k3"), items)
    messages = captured[0]["messages"]
    assert [message["role"] for message in messages] == [
        "assistant",
        "tool",
        "assistant",
        "tool",
        "user",
    ]
    for call_index in (0, 2):
        assert (
            messages[call_index]["tool_calls"][0]["id"]
            == messages[call_index + 1]["tool_call_id"]
        )
    _assert_tool_content(captured[0])
    assert items == original_items
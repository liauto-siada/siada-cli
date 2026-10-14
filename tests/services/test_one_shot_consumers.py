"""Offline regression coverage for migrated standalone model consumers."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agents import ModelResponse
from agents.tool_context import ToolContext
from agents.usage import Usage
from openai.types.responses import Response, ResponseCompletedEvent, ResponseOutputMessage

from siada.foundation.context import LLM_CONFIG, context_var_scope
from siada.provider import fast_llm, one_shot
from siada.services import session_title, vision_bridge
from siada.services.browser_skill import llm_utils


def sdk_response(text):
    return ModelResponse(
        output=[ResponseOutputMessage.model_validate({
            "id": "msg-synthetic", "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        })],
        usage=Usage(), response_id="response-synthetic",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [None, False, True])
async def test_fast_completion_keeps_config_and_per_call_precedence(monkeypatch, stream):
    monkeypatch.setattr(fast_llm, "_get_fast_model_and_provider", lambda: (
        "gpt-4o-mini", "default", {"api_base": "https://aux.test/v1", "api_key": "synthetic-config-key"},
    ))
    completion = AsyncMock(return_value=sdk_response("answer"))
    monkeypatch.setattr(one_shot, "one_shot_completion", completion)
    result = await fast_llm.fast_completion(
        "hello", agent_name="synthetic-aux", api_key="synthetic-call-key", max_tokens=55,
        messages=[{"role": "user", "content": "override"}],
        **({"stream": stream} if stream is not None else {}),
    )
    assert one_shot.extract_response_text(result) == "answer"
    completion.assert_awaited_once_with(
        "hello", provider="default", model="gpt-4o-mini", stream=True if stream is None else stream, agent_name="synthetic-aux",
        api_base="https://aux.test/v1", api_key="synthetic-call-key", max_tokens=55,
        messages=[{"role": "user", "content": "override"}],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("consumer", [
    "fast", "simple", "title", "browser", "memory_slug", "memory_summary", "vision",
])
async def test_standalone_consumers_default_to_streaming(monkeypatch, tmp_path, consumer):
    from siada.provider.client_factory import simple_completion
    from siada.services.memory.memory_service import MemoryService
    from siada.tools.memory import memory_tool

    final_text = "Synthetic answer"
    final = sdk_response(final_text)

    async def events(**kwargs):
        response = Response.model_construct(
            id="resp-synthetic", status="completed", output=final.output, usage=None,
        )
        yield ResponseCompletedEvent.model_construct(
            type="response.completed", response=response, sequence_number=1,
        )

    model = SimpleNamespace(
        model="gpt-4o", get_response=AsyncMock(return_value=final), stream_response=Mock(side_effect=events),
    )
    provider = SimpleNamespace(get_model=Mock(return_value=model), aclose=AsyncMock())
    monkeypatch.setattr(one_shot, "get_provider", lambda name: provider)
    monkeypatch.setattr(fast_llm, "_get_fast_model_and_provider", lambda: ("gpt-4o", "default", {}))
    monkeypatch.setattr(vision_bridge, "_get_vision_engine", lambda: ("gpt-4o", "default"))

    with context_var_scope(LLM_CONFIG, SimpleNamespace(model_name="gpt-4o", provider="default")):
        if consumer == "fast":
            result = one_shot.extract_response_text(await fast_llm.fast_completion("synthetic prompt"))
        elif consumer == "simple":
            result = one_shot.extract_response_text(await simple_completion("synthetic prompt"))
        elif consumer == "title":
            result = await session_title.generate_session_title("synthetic prompt")
        elif consumer == "browser":
            result = await llm_utils.call_fast_llm("synthetic prompt", agent_name="synthetic-browser")
        elif consumer == "memory_slug":
            service = MemoryService.__new__(MemoryService)
            result = await service._generate_slug_via_llm("synthetic transcript")
        elif consumer == "memory_summary":
            result = await memory_tool._summarize_session("synthetic transcript", "topic", "2026-01-01.md", "brief")
        else:
            image = tmp_path / "synthetic.png"
            image.write_bytes(b"synthetic-image")
            result = await vision_bridge._transcribe_one("default", "gpt-4o", str(image), "")

    assert result == ("synthetic-answer" if consumer == "memory_slug" else final_text)
    model.stream_response.assert_called_once()
    model.get_response.assert_not_awaited()
    provider.aclose.assert_not_awaited()


@pytest.mark.asyncio
async def test_fast_config_is_independent_of_main_context(monkeypatch):
    config = {
        "model": "gpt-4o-mini", "base_url": "https://aux.test/v1", "api_key": "synthetic-aux-key",
        "extra_headers": {"X-Synthetic": "auxiliary"},
    }
    monkeypatch.setattr(fast_llm, "_get_user_fast_llm_config", lambda: config)
    completion = AsyncMock(return_value=sdk_response("answer"))
    monkeypatch.setattr(one_shot, "one_shot_completion", completion)
    main = SimpleNamespace(model_name="gpt-4o", provider="synthetic-main")
    with context_var_scope(LLM_CONFIG, main):
        await fast_llm.fast_completion("hello")
    sent = completion.await_args.kwargs
    assert sent["model"] == "gpt-4o-mini" and sent["provider"] == "default"
    assert sent["api_base"] == config["base_url"] and sent["api_key"] == config["api_key"]
    assert sent["extra_headers"] == config["extra_headers"]
    assert sent["extra_headers"] is not config["extra_headers"]
    assert main.model_name == "gpt-4o" and main.provider == "synthetic-main"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [None, False, True])
async def test_simple_completion_keeps_active_context_model(monkeypatch, stream):
    from siada.provider.client_factory import simple_completion

    completion = AsyncMock(return_value=sdk_response("answer"))
    monkeypatch.setattr(one_shot, "one_shot_completion", completion)
    with context_var_scope(LLM_CONFIG, SimpleNamespace(model_name="gpt-4o", provider="default")):
        result = await simple_completion(
            "hello", agent_name="synthetic-aux", model="ignored", temperature=0.2,
            **({"stream": stream} if stream is not None else {}),
        )
    assert one_shot.extract_response_text(result) == "answer"
    completion.assert_awaited_once_with(
        "hello", model="gpt-4o", provider="default", agent_name="synthetic-aux", temperature=0.2,
        **({"stream": stream} if stream is not None else {}),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("text, expected", [('"Fix parser."', "Fix parser"), ("", None)])
async def test_session_title_uses_sdk_text(monkeypatch, text, expected):
    completion = AsyncMock(return_value=sdk_response(text))
    monkeypatch.setattr(fast_llm, "fast_completion", completion)
    assert await session_title.generate_session_title("parser is broken") == expected
    assert completion.await_args.kwargs["agent_name"] == "session_title_generator"


@pytest.mark.asyncio
async def test_session_title_failure_keeps_fallback(monkeypatch):
    monkeypatch.setattr(fast_llm, "fast_completion", AsyncMock(side_effect=TimeoutError("synthetic timeout")))
    assert await session_title.generate_session_title("parser is broken") is None
    assert await session_title.generate_session_title("") is None


@pytest.mark.parametrize("text, expected", [("API Design", "api-design"), ("", None)])
def test_memory_slug_extraction_uses_sdk_text(text, expected):
    from siada.services.memory.memory_service import MemoryService

    service = MemoryService.__new__(MemoryService)
    assert service._extract_slug_from_response(sdk_response(text)) == expected


@pytest.mark.asyncio
async def test_browser_skill_keeps_timeout_and_reasoning_settings(monkeypatch):
    completion = AsyncMock(return_value=sdk_response("{\"match\": true}"))
    monkeypatch.setattr(fast_llm, "fast_completion", completion)
    assert await llm_utils.call_fast_llm("classify", agent_name="synthetic-browser") == '{"match": true}'
    completion.assert_awaited_once_with(
        "classify", agent_name="synthetic-browser", timeout=50, extra_body={"reasoning_effort": "low"},
    )


@pytest.mark.asyncio
async def test_browser_skill_failure_keeps_empty_text_fallback(monkeypatch):
    monkeypatch.setattr(fast_llm, "fast_completion", AsyncMock(side_effect=RuntimeError("synthetic failure")))
    assert await llm_utils.call_fast_llm("classify", agent_name="synthetic-browser") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("detail, max_tokens", [("brief", 800), ("detailed", 2000)])
async def test_memory_summary_keeps_system_prompt_and_budget(monkeypatch, detail, max_tokens):
    from siada.tools.memory import memory_tool

    completion = AsyncMock(return_value=sdk_response(" summary "))
    monkeypatch.setattr(fast_llm, "fast_completion", completion)
    assert await memory_tool._summarize_session("transcript", "topic", "2026-01-01.md", detail) == "summary"
    sent = completion.await_args.kwargs
    assert sent["messages"][0]["role"] == "system"
    assert "transcript" in sent["messages"][1]["content"]
    assert sent["max_tokens"] == max_tokens
    assert sent["temperature"] == 0.1


@pytest.mark.asyncio
async def test_memory_summary_empty_response_keeps_original_text_fallback(monkeypatch):
    from siada.tools.memory import memory_tool

    monkeypatch.setattr(fast_llm, "fast_completion", AsyncMock(return_value=sdk_response("")))
    result = await memory_tool._summarize_session("transcript", "topic", "2026-01-01.md", "brief")
    assert result == "transcript\n\n[LLM summary unavailable]"


@pytest.mark.asyncio
async def test_vision_transcription_sends_native_sdk_image_input(monkeypatch, tmp_path):
    image = tmp_path / "synthetic.png"
    image.write_bytes(b"synthetic-image")
    monkeypatch.setattr(vision_bridge, "_get_vision_engine", lambda: ("gpt-4o", "default"))
    completion = AsyncMock(return_value=sdk_response(" image evidence "))
    monkeypatch.setattr(one_shot, "one_shot_completion", completion)
    assert await vision_bridge.transcribe_images([str(image)], "focus on color") == [(str(image), "image evidence")]
    sent = completion.await_args
    assert sent.kwargs == {"model": "gpt-4o", "provider": "default", "max_tokens": 32768}
    content = sent.args[0][0]["content"]
    assert content[0]["type"] == "input_text"
    assert "focus on color" in content[0]["text"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_vision_missing_file_and_model_failure_keep_fallback(monkeypatch, tmp_path):
    completion = AsyncMock(side_effect=RuntimeError("synthetic failure"))
    monkeypatch.setattr(one_shot, "one_shot_completion", completion)
    assert await vision_bridge._transcribe_one("default", "gpt-4o", str(tmp_path / "missing.png"), "") is None
    completion.assert_not_awaited()
    image = tmp_path / "synthetic.png"
    image.write_bytes(b"synthetic-image")
    assert await vision_bridge._transcribe_one("default", "gpt-4o", str(image), "") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name, temperature", [
    ("gpt-4o", 0.2), ("gpt-5.4", None), ("gpt-6-astra", None),
])
async def test_explicit_compression_resolves_configuration_from_run_context(monkeypatch, model_name, temperature):
    from siada.tools import compression_tool

    completion = AsyncMock(return_value=sdk_response(" summary "))
    monkeypatch.setattr(compression_tool, "one_shot_completion", completion)
    context = SimpleNamespace(context=SimpleNamespace(session=SimpleNamespace(siada_config=SimpleNamespace(
        llm_config=SimpleNamespace(model_name=model_name, provider="default"),
    ))))
    result = await compression_tool._compress_messages_with_model(
        [{"role": "user", "content": "original text"}], "synthetic reason", context,
    )
    assert result == "summary"
    sent = completion.await_args.kwargs
    assert sent["model"] == model_name and sent["provider"] == "default"
    assert sent["temperature"] == temperature
    assert sent["stream"] is True
    assert "original text" in sent["system_instructions"]


@pytest.mark.asyncio
async def test_explicit_compression_empty_response_keeps_failure_message(monkeypatch):
    from siada.tools import compression_tool

    monkeypatch.setattr(compression_tool, "one_shot_completion", AsyncMock(return_value=sdk_response("")))
    context = SimpleNamespace(context=SimpleNamespace(session=SimpleNamespace(siada_config=SimpleNamespace(
        llm_config=SimpleNamespace(model_name="gpt-4o", provider="default"),
    ))))
    summary = await compression_tool._compress_messages_with_model(
        [{"role": "user", "content": "original text"}], "synthetic reason", context,
    )
    assert summary.startswith("[Smart Compression Summary]")
    assert "synthetic reason" in summary
    assert "Summary generation failed" in summary


@pytest.mark.asyncio
@pytest.mark.parametrize("start_index", [0, 1])
async def test_explicit_compression_tool_passes_context_and_preserves_history(monkeypatch, start_index):
    from siada.tools import compression_tool

    history = [
        {"role": "user", "content": "original task"},
        {"role": "assistant", "content": "synthetic decision"},
        {"role": "user", "content": "synthetic next step"},
    ]
    original_history = [dict(message) for message in history]
    context = ToolContext(context=SimpleNamespace(
        get_messages=lambda: history,
        session=SimpleNamespace(siada_config=SimpleNamespace(
            llm_config=SimpleNamespace(model_name="gpt-4o", provider="default"),
        )),
    ), tool_name="compress_context_tool", tool_call_id="call-synthetic", tool_arguments="{}")
    completion = AsyncMock(return_value=sdk_response("[Smart Compression Summary] synthetic summary"))
    monkeypatch.setattr(compression_tool, "one_shot_completion", completion)

    result = await compression_tool.compress_context_tool.on_invoke_tool(
        context,
        json.dumps({"reason": "synthetic reason", "start_index": start_index, "end_index": 3}),
    )

    assert result == {
        "status": 1,
        "start_index": 1,
        "end_index": 3,
        "summary": "[Smart Compression Summary] synthetic summary",
    }
    completion.assert_awaited_once()
    sent = completion.await_args.kwargs
    assert sent["model"] == "gpt-4o" and sent["provider"] == "default"
    assert sent["stream"] is True
    assert "original task" not in sent["system_instructions"]
    assert "synthetic decision" in sent["system_instructions"]
    assert "synthetic next step" in sent["system_instructions"]
    assert history == original_history


@pytest.mark.asyncio
async def test_explicit_compression_tool_reports_model_failure(monkeypatch):
    from siada.tools import compression_tool

    history = [{"role": "user", "content": "original task"}, {"role": "assistant", "content": "decision"}]
    context = ToolContext(context=SimpleNamespace(
        get_messages=lambda: history,
        session=SimpleNamespace(siada_config=SimpleNamespace(
            llm_config=SimpleNamespace(model_name="gpt-4o", provider="default"),
        )),
    ), tool_name="compress_context_tool", tool_call_id="call-synthetic", tool_arguments="{}")
    completion = AsyncMock(side_effect=RuntimeError("synthetic model failure"))
    monkeypatch.setattr(compression_tool, "one_shot_completion", completion)

    result = await compression_tool.compress_context_tool.on_invoke_tool(
        context, json.dumps({"reason": "synthetic reason", "start_index": 1, "end_index": 2}),
    )

    assert result["status"] == 0
    assert "synthetic model failure" in result["summary"]
    completion.assert_awaited_once()
    assert len(history) == 2
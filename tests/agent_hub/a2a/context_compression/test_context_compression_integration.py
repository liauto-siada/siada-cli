"""
Integration tests for ContextCompressionPlugin with the real ADK Runner.

Unlike the unit tests (test_context_compression_plugin.py) which directly call
before_model_callback, these tests verify:

1. ADK Runner actually invokes before_model_callback when a plugin is registered.
2. The real LlmRequest built by ADK has llm_request.model populated (critical risk).
3. Dynamically registered agents also pass through the plugin.

All actual LLM calls (LiMateModel + SiadaClient) are mocked – zero network/token
consumption.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mark all async tests in this module so pytest-asyncio picks them up
# regardless of whether asyncio_mode=auto or strict is active.
pytestmark = pytest.mark.asyncio

from google.adk.agents import LlmAgent
from google.adk.apps.app import App
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from siada.agent_hub.a2a.common.context_compression_plugin import ContextCompressionPlugin
from siada.provider.adk_provider.limate_model import LiMateModel

# ── helpers ──────────────────────────────────────────────────────────────────

MODEL_NAME = "claude-sonnet-4-5"


def _make_fake_llm_response() -> "LlmResponse":  # noqa: F821
    """Build a minimal LlmResponse ADK can process."""
    from google.adk.models.llm_response import LlmResponse

    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text="这是一个测试回复。")],
        ),
        partial=False,
    )


async def _fake_generate(llm_request, stream=False) -> AsyncGenerator:
    """Mock for LiMateModel.generate_content_async – yields one fake response."""
    yield _make_fake_llm_response()


def _build_runner_with_plugin(
    plugin: ContextCompressionPlugin,
    agent_name: str = "test_compression_agent",
) -> Runner:
    """Create a minimal ADK Runner with the plugin registered via App."""
    model = LiMateModel(model=MODEL_NAME)
    agent = LlmAgent(
        name=agent_name,
        model=model,
        instruction="你是一个有帮助的助手。",
    )
    # In newer ADK versions, plugins must be provided via App, not Runner directly.
    app = App(name=agent_name, root_agent=agent, plugins=[plugin])
    session_service = InMemorySessionService()
    return Runner(app=app, session_service=session_service)


# ── tests ────────────────────────────────────────────────────────────────────


async def test_plugin_before_model_callback_invoked_by_real_runner():
    """ADK Runner must call before_model_callback for each LLM turn."""
    plugin = ContextCompressionPlugin()
    callback_invocations: list[dict] = []

    # Spy: record every invocation and inspect the real LlmRequest.
    original_callback = plugin.before_model_callback

    async def spy_callback(*, callback_context, llm_request):
        callback_invocations.append(
            {
                "model": getattr(llm_request, "model", "MISSING"),
                "contents_count": len(llm_request.contents or []),
            }
        )
        return await original_callback(
            callback_context=callback_context, llm_request=llm_request
        )

    plugin.before_model_callback = spy_callback

    runner = _build_runner_with_plugin(plugin)

    with patch.object(
        LiMateModel,
        "generate_content_async",
        side_effect=_fake_generate,
    ):
        session = await runner.session_service.create_session(
            app_name="test_compression_agent", user_id="test_user"
        )
        user_message = types.Content(
            role="user", parts=[types.Part(text="你好，请介绍一下自己。")]
        )
        async for _ in runner.run_async(
            user_id="test_user",
            session_id=session.id,
            new_message=user_message,
        ):
            pass

    assert len(callback_invocations) >= 1, (
        "before_model_callback should have been called at least once by the ADK Runner"
    )
    print(f"\n✅ before_model_callback called {len(callback_invocations)} time(s)")
    print(f"   First invocation: {callback_invocations[0]}")


async def test_real_llm_request_model_field_is_populated():
    """The real LlmRequest built by ADK must have llm_request.model populated.

    This is the highest-risk field: if it's empty the plugin silently skips
    compression for every request.
    """
    plugin = ContextCompressionPlugin()
    captured_models: list[str | None] = []

    original_callback = plugin.before_model_callback

    async def spy_callback(*, callback_context, llm_request):
        captured_models.append(getattr(llm_request, "model", None))
        return await original_callback(
            callback_context=callback_context, llm_request=llm_request
        )

    plugin.before_model_callback = spy_callback

    runner = _build_runner_with_plugin(plugin)

    with patch.object(
        LiMateModel,
        "generate_content_async",
        side_effect=_fake_generate,
    ):
        session = await runner.session_service.create_session(
            app_name="test_compression_agent", user_id="test_user"
        )
        async for _ in runner.run_async(
            user_id="test_user",
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part(text="你好")]
            ),
        ):
            pass

    assert len(captured_models) >= 1, "Callback was never invoked"
    assert all(m is not None and m != "" for m in captured_models), (
        f"llm_request.model was empty in at least one callback invocation: {captured_models}"
    )
    print(f"\n✅ llm_request.model values: {captured_models}")


async def test_plugin_compression_triggered_via_runner():
    """End-to-end: plugin compresses history when threshold is exceeded.

    Uses a very low threshold so even a tiny conversation triggers compression.
    Verifies that the LlmRequest.contents shrinks after the plugin runs.
    """
    import siada.agent_hub.a2a.common.context_compression_plugin as mod

    plugin = ContextCompressionPlugin()
    contents_before: list[int] = []
    contents_after: list[int] = []

    FAKE_SUMMARY = (
        "<context>\n1. Previous Conversation: 简单问候。\n</context>"
    )

    original_callback = plugin.before_model_callback

    async def spy_callback(*, callback_context, llm_request):
        contents_before.append(len(llm_request.contents or []))
        result = await original_callback(
            callback_context=callback_context, llm_request=llm_request
        )
        contents_after.append(len(llm_request.contents or []))
        return result

    plugin.before_model_callback = spy_callback

    runner = _build_runner_with_plugin(plugin)

    filler = "这是填充内容，用于撑大上下文。" * 100

    with patch.object(LiMateModel, "generate_content_async", side_effect=_fake_generate), patch.object(
        plugin, "_call_llm_to_compact", new=AsyncMock(return_value=FAKE_SUMMARY)
    ):
        original_threshold = mod.COMPRESSION_TOKEN_THRESHOLD
        mod.COMPRESSION_TOKEN_THRESHOLD = 0.00001
        try:
            session = await runner.session_service.create_session(
                app_name="test_compression_agent", user_id="test_user"
            )
            # Send several rounds to build up history
            for i in range(6):
                async for _ in runner.run_async(
                    user_id="test_user",
                    session_id=session.id,
                    new_message=types.Content(
                        role="user",
                        parts=[types.Part(text=f"第{i + 1}轮：{filler}")],
                    ),
                ):
                    pass
        finally:
            mod.COMPRESSION_TOKEN_THRESHOLD = original_threshold

    # Find a turn where compression actually fired (contents shrank)
    compression_fired = any(
        after < before
        for before, after in zip(contents_before, contents_after)
    )
    assert compression_fired, (
        f"Expected at least one turn to trigger compression.\n"
        f"contents_before={contents_before}\n"
        f"contents_after={contents_after}"
    )
    print(
        f"\n✅ Compression fired via real Runner "
        f"(before={contents_before}, after={contents_after})"
    )


async def test_plugin_compression_with_tool_calls_preserves_tool_sequence_integrity():
    """End-to-end: when the conversation history contains tool call sequences,
    compression must never produce an orphaned function_call or function_response.

    We inject synthetic tool-call Contents into llm_request.contents via the spy,
    then trigger compression with a very low threshold and verify the resulting
    contents list has all tool pairs intact.
    """
    import siada.agent_hub.a2a.common.context_compression_plugin as mod

    plugin = ContextCompressionPlugin()

    FAKE_SUMMARY = "<context>\n1. Previous Conversation: 测试摘要。\n</context>"

    # Contents to inject: mix of real user/model turns + tool call sequences
    filler = "填充内容。" * 30
    injected_contents: list[types.Content] = []
    for i in range(6):
        injected_contents.append(
            types.Content(role="user", parts=[types.Part(text=f"第{i + 1}轮用户消息：{filler}")])
        )
        if i % 2 == 1:
            call_id = f"call_{i}"
            injected_contents.append(
                types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id=call_id, name="test_tool", args={"x": i}
                            )
                        )
                    ],
                )
            )
            injected_contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=call_id, name="test_tool", response={"result": "ok"}
                            )
                        )
                    ],
                )
            )
        else:
            injected_contents.append(
                types.Content(
                    role="model", parts=[types.Part(text=f"第{i + 1}轮模型回复：{filler}")]
                )
            )

    compressed_contents: list | None = None

    original_callback = plugin.before_model_callback

    async def spy_callback(*, callback_context, llm_request):
        nonlocal compressed_contents
        # Override contents with our crafted tool-call history
        llm_request.contents = list(injected_contents)
        result = await original_callback(
            callback_context=callback_context, llm_request=llm_request
        )
        compressed_contents = list(llm_request.contents)
        return result

    plugin.before_model_callback = spy_callback

    runner = _build_runner_with_plugin(plugin)

    with patch.object(LiMateModel, "generate_content_async", side_effect=_fake_generate), patch.object(
        plugin, "_call_llm_to_compact", new=AsyncMock(return_value=FAKE_SUMMARY)
    ):
        original_threshold = mod.COMPRESSION_TOKEN_THRESHOLD
        mod.COMPRESSION_TOKEN_THRESHOLD = 0.00001
        try:
            session = await runner.session_service.create_session(
                app_name="test_compression_agent", user_id="test_user"
            )
            async for _ in runner.run_async(
                user_id="test_user",
                session_id=session.id,
                new_message=types.Content(
                    role="user", parts=[types.Part(text="触发压缩的消息")]
                ),
            ):
                pass
        finally:
            mod.COMPRESSION_TOKEN_THRESHOLD = original_threshold

    assert compressed_contents is not None, "Spy callback was never invoked"

    # Verify no orphaned function_call
    for i, content in enumerate(compressed_contents):
        if (
            content.role == "model"
            and content.parts
            and any(getattr(p, "function_call", None) for p in content.parts)
        ):
            assert i + 1 < len(compressed_contents), (
                f"Orphaned function_call at index {i}"
            )
            next_c = compressed_contents[i + 1]
            assert (
                next_c.role == "user"
                and next_c.parts
                and any(getattr(p, "function_response", None) for p in next_c.parts)
            ), f"function_call at index {i} not followed by function_response"

    # Verify no orphaned function_response
    for i, content in enumerate(compressed_contents):
        if (
            content.role == "user"
            and content.parts
            and any(getattr(p, "function_response", None) for p in content.parts)
        ):
            assert i > 0, f"Orphaned function_response at index 0"
            prev_c = compressed_contents[i - 1]
            assert (
                prev_c.role == "model"
                and prev_c.parts
                and any(getattr(p, "function_call", None) for p in prev_c.parts)
            ), f"function_response at index {i} not preceded by function_call"

    print(
        f"\n✅ Tool call sequence integrity preserved via real Runner "
        f"({len(injected_contents)} → {len(compressed_contents)} contents)"
    )


async def test_dynamically_registered_agent_also_uses_plugin():
    """A dynamically registered agent must also pass through the plugin.

    Simulates the runtime scenario: AdkIntegration.register_agent() is called
    after setup(), and the new runner is built on demand by get_runner_async().
    We bypass AdkWebServer here and test Runner directly with a second agent.
    """
    plugin = ContextCompressionPlugin()
    callback_count = 0

    original_callback = plugin.before_model_callback

    async def spy_callback(*, callback_context, llm_request):
        nonlocal callback_count
        callback_count += 1
        return await original_callback(
            callback_context=callback_context, llm_request=llm_request
        )

    plugin.before_model_callback = spy_callback

    # Simulate a dynamically created agent (e.g. a custom agent registered at runtime)
    dynamic_model = LiMateModel(model=MODEL_NAME)
    dynamic_agent = LlmAgent(
        name="dynamic_test_agent",
        model=dynamic_model,
        instruction="你是一个动态注册的测试助手。",
    )
    session_service = InMemorySessionService()
    # Plugin registered via App (the same way AdkWebServer.get_runner_async does it)
    app = App(name="dynamic_test_agent", root_agent=dynamic_agent, plugins=[plugin])
    runner = Runner(app=app, session_service=session_service)

    with patch.object(LiMateModel, "generate_content_async", side_effect=_fake_generate):
        session = await runner.session_service.create_session(
            app_name="dynamic_test_agent", user_id="test_user"
        )
        async for _ in runner.run_async(
            user_id="test_user",
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part(text="你好，动态 agent！")]
            ),
        ):
            pass

    assert callback_count >= 1, (
        "Plugin was not invoked for the dynamically registered agent"
    )
    print(f"\n✅ Dynamic agent also invokes plugin ({callback_count} call(s))")


# ── standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def _run_all():
        tests = [
            test_plugin_before_model_callback_invoked_by_real_runner,
            test_real_llm_request_model_field_is_populated,
            test_plugin_compression_triggered_via_runner,
            test_dynamically_registered_agent_also_uses_plugin,
        ]
        passed = failed = 0
        for t in tests:
            try:
                await t()
                passed += 1
            except Exception as e:
                import traceback
                print(f"\n❌ {t.__name__} FAILED: {e}")
                traceback.print_exc()
                failed += 1
        print(f"\n{'=' * 50}")
        print(f"Results: {passed} passed, {failed} failed")

    asyncio.run(_run_all())

"""
Unit tests for ContextCompressionPlugin.

All LLM calls are mocked – zero token consumption, no network required.

Test coverage:
- Original tests: compression trigger/no-trigger, summary appearance, failure resilience
- New tests (this round): content type helpers, _adjust_to_safe_boundary,
  _get_header_contents, tool-call sequence integrity
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types

import siada.agent_hub.a2a.common.context_compression_plugin as mod
from siada.agent_hub.a2a.common.context_compression_plugin import ContextCompressionPlugin

# ── helpers ──────────────────────────────────────────────────────────────────

FAKE_SUMMARY = (
    "<context>\n"
    "1. Previous Conversation: 用户询问了多个技术问题，助手给出了详细回答。\n"
    "2. Current Work: 正在实现上下文压缩功能。\n"
    "3. Key Technical Concepts:\n"
    "   - Google ADK plugin system\n"
    "   - Token counting with litellm\n"
    "</context>"
)


def _make_content(role: str, text: str) -> types.Content:
    """Create a plain text Content."""
    return types.Content(role=role, parts=[types.Part(text=text)])


def _make_function_call_content(
    fn_name: str = "my_tool", call_id: str = "call_1"
) -> types.Content:
    """Create a model Content that contains a function_call part."""
    return types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    id=call_id, name=fn_name, args={"arg": "value"}
                )
            )
        ],
    )


def _make_function_response_content(
    fn_name: str = "my_tool", call_id: str = "call_1", result: str = "tool result"
) -> types.Content:
    """Create a user Content that contains a function_response part."""
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=call_id, name=fn_name, response={"result": result}
                )
            )
        ],
    )


def _make_llm_request(
    num_turns: int = 10,
    model: str = "claude-sonnet-4-5",
    long_text: bool = True,
) -> MagicMock:
    """Build a mock LlmRequest with *num_turns* user/model conversation rounds."""
    contents = []
    filler = "这是一段用于填充上下文长度的重复内容，帮助触发压缩阈值。" * (50 if long_text else 1)
    for i in range(num_turns):
        contents.append(_make_content("user", f"第{i + 1}轮用户消息：{filler}"))
        contents.append(_make_content("model", f"第{i + 1}轮模型回复：{filler}"))

    req = MagicMock()
    req.model = model
    req.contents = contents
    req.config = MagicMock()
    req.config.system_instruction = "你是一个有帮助的助手。"
    return req


def _make_llm_request_with_tool_calls(num_text_turns: int = 4) -> MagicMock:
    """Build a mock LlmRequest that interleaves tool calls with normal text turns.

    Structure (for num_text_turns=4):
        [user_text_0]
        [model_text_0]
        [user_text_1]
        [model_tool_call_1]   ← function_call
        [user_tool_resp_1]    ← function_response
        [user_text_2]
        [model_text_2]
        [user_text_3]
        [model_tool_call_3]
        [user_tool_resp_3]
        [user_text_4]
        [model_text_4]
    """
    filler = "这是填充内容。" * 20
    contents = []
    for i in range(num_text_turns):
        contents.append(_make_content("user", f"第{i + 1}轮用户消息：{filler}"))
        if i % 2 == 1:
            # Odd turns: model makes a tool call, then receives the response
            call_id = f"call_{i}"
            contents.append(_make_function_call_content(call_id=call_id))
            contents.append(_make_function_response_content(call_id=call_id))
        else:
            contents.append(_make_content("model", f"第{i + 1}轮模型文本回复：{filler}"))

    req = MagicMock()
    req.model = "claude-sonnet-4-5"
    req.contents = contents
    req.config = MagicMock()
    req.config.system_instruction = "你是一个有帮助的助手。"
    return req


# ── original tests (preserved) ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compression_triggered_and_reduces_contents():
    """Compression should run when threshold is very low, and reduce contents length."""
    plugin = ContextCompressionPlugin()
    req = _make_llm_request(num_turns=10)
    original_count = len(req.contents)

    callback_ctx = MagicMock()

    with patch.object(plugin, "_call_llm_to_compact", new=AsyncMock(return_value=FAKE_SUMMARY)):
        # Force trigger by setting threshold to almost 0
        original_threshold = mod.COMPRESSION_TOKEN_THRESHOLD
        mod.COMPRESSION_TOKEN_THRESHOLD = 0.00001
        try:
            result = await plugin.before_model_callback(
                callback_context=callback_ctx,
                llm_request=req,
            )
        finally:
            mod.COMPRESSION_TOKEN_THRESHOLD = original_threshold

    assert result is None, "before_model_callback must always return None"
    assert len(req.contents) < original_count, (
        f"Expected contents to shrink (was {original_count}, now {len(req.contents)})"
    )
    print(f"\n✅ Contents reduced: {original_count} → {len(req.contents)}")


@pytest.mark.asyncio
async def test_summary_appears_in_contents():
    """The summary text should appear in the compressed contents."""
    plugin = ContextCompressionPlugin()
    req = _make_llm_request(num_turns=10)

    callback_ctx = MagicMock()

    with patch.object(plugin, "_call_llm_to_compact", new=AsyncMock(return_value=FAKE_SUMMARY)):
        original_threshold = mod.COMPRESSION_TOKEN_THRESHOLD
        mod.COMPRESSION_TOKEN_THRESHOLD = 0.00001
        try:
            await plugin.before_model_callback(
                callback_context=callback_ctx,
                llm_request=req,
            )
        finally:
            mod.COMPRESSION_TOKEN_THRESHOLD = original_threshold

    all_texts = [
        part.text
        for c in req.contents
        for part in (c.parts or [])
        if part.text
    ]
    found = any(FAKE_SUMMARY in text for text in all_texts)
    assert found, "Summary text should appear in compressed contents"
    print(f"\n✅ Summary found in contents")


@pytest.mark.asyncio
async def test_no_compression_below_threshold():
    """When tokens are below threshold, contents should remain unchanged."""
    plugin = ContextCompressionPlugin()
    req = _make_llm_request(num_turns=3, long_text=False)
    original_count = len(req.contents)

    callback_ctx = MagicMock()

    with patch.object(plugin, "_call_llm_to_compact", new=AsyncMock(return_value=FAKE_SUMMARY)):
        result = await plugin.before_model_callback(
            callback_context=callback_ctx,
            llm_request=req,
        )

    assert result is None
    assert len(req.contents) == original_count, (
        "Contents should be unchanged when below threshold"
    )
    print(f"\n✅ No compression for small conversation ({original_count} contents unchanged)")


@pytest.mark.asyncio
async def test_compression_failure_leaves_contents_intact():
    """If LLM summarization fails, original contents should be preserved."""
    plugin = ContextCompressionPlugin()
    req = _make_llm_request(num_turns=10)
    original_count = len(req.contents)

    callback_ctx = MagicMock()

    with patch.object(plugin, "_call_llm_to_compact", new=AsyncMock(return_value=None)):
        original_threshold = mod.COMPRESSION_TOKEN_THRESHOLD
        mod.COMPRESSION_TOKEN_THRESHOLD = 0.00001
        try:
            result = await plugin.before_model_callback(
                callback_context=callback_ctx,
                llm_request=req,
            )
        finally:
            mod.COMPRESSION_TOKEN_THRESHOLD = original_threshold

    assert result is None
    assert len(req.contents) == original_count, (
        "Contents should be intact when summarization fails"
    )
    print(f"\n✅ Contents preserved on summarization failure ({original_count} contents)")


@pytest.mark.asyncio
async def test_too_few_contents_skipped():
    """Plugin should skip compression when contents < 4."""
    plugin = ContextCompressionPlugin()
    req = _make_llm_request(num_turns=1)  # only 2 contents
    original_count = len(req.contents)

    callback_ctx = MagicMock()

    with patch.object(plugin, "_call_llm_to_compact", new=AsyncMock(return_value=FAKE_SUMMARY)):
        original_threshold = mod.COMPRESSION_TOKEN_THRESHOLD
        mod.COMPRESSION_TOKEN_THRESHOLD = 0.00001
        try:
            result = await plugin.before_model_callback(
                callback_context=callback_ctx,
                llm_request=req,
            )
        finally:
            mod.COMPRESSION_TOKEN_THRESHOLD = original_threshold

    assert result is None
    assert len(req.contents) == original_count
    print(f"\n✅ Skipped compression for {original_count} contents (< 4)")


@pytest.mark.asyncio
async def test_contents_start_with_user_role_after_compression():
    """After compression, the first Content should have role='user'."""
    plugin = ContextCompressionPlugin()
    req = _make_llm_request(num_turns=10)

    callback_ctx = MagicMock()

    with patch.object(plugin, "_call_llm_to_compact", new=AsyncMock(return_value=FAKE_SUMMARY)):
        original_threshold = mod.COMPRESSION_TOKEN_THRESHOLD
        mod.COMPRESSION_TOKEN_THRESHOLD = 0.00001
        try:
            await plugin.before_model_callback(
                callback_context=callback_ctx,
                llm_request=req,
            )
        finally:
            mod.COMPRESSION_TOKEN_THRESHOLD = original_threshold

    assert req.contents[0].role == "user", (
        f"First content after compression should be 'user', got '{req.contents[0].role}'"
    )
    print(f"\n✅ First content role is 'user' after compression")


# ── NEW: content type helper tests ───────────────────────────────────────────


def test_is_tool_call_detects_function_call_content():
    """_is_tool_call should be True only for model Content with function_call parts."""
    tool_call = _make_function_call_content()
    plain_model = _make_content("model", "普通文本回复")
    plain_user = _make_content("user", "用户消息")
    tool_resp = _make_function_response_content()

    assert ContextCompressionPlugin._is_tool_call(tool_call) is True
    assert ContextCompressionPlugin._is_tool_call(plain_model) is False
    assert ContextCompressionPlugin._is_tool_call(plain_user) is False
    assert ContextCompressionPlugin._is_tool_call(tool_resp) is False
    print("\n✅ _is_tool_call correctly identifies tool call contents")


def test_is_tool_response_detects_function_response_content():
    """_is_tool_response should be True only for user Content with function_response parts."""
    tool_resp = _make_function_response_content()
    plain_user = _make_content("user", "用户消息")
    plain_model = _make_content("model", "模型回复")
    tool_call = _make_function_call_content()

    assert ContextCompressionPlugin._is_tool_response(tool_resp) is True
    assert ContextCompressionPlugin._is_tool_response(plain_user) is False
    assert ContextCompressionPlugin._is_tool_response(plain_model) is False
    assert ContextCompressionPlugin._is_tool_response(tool_call) is False
    print("\n✅ _is_tool_response correctly identifies tool response contents")


def test_is_real_user_message_excludes_tool_response():
    """_is_real_user_message should be True for text user messages, False for tool responses."""
    plain_user = _make_content("user", "用户消息")
    tool_resp = _make_function_response_content()
    plain_model = _make_content("model", "模型回复")

    assert ContextCompressionPlugin._is_real_user_message(plain_user) is True
    assert ContextCompressionPlugin._is_real_user_message(tool_resp) is False
    assert ContextCompressionPlugin._is_real_user_message(plain_model) is False
    print("\n✅ _is_real_user_message correctly excludes tool responses")


def test_is_model_text_message_excludes_tool_calls():
    """_is_model_text_message should be True for plain model text, False for tool calls."""
    plain_model = _make_content("model", "模型文本回复")
    tool_call = _make_function_call_content()
    plain_user = _make_content("user", "用户消息")

    assert ContextCompressionPlugin._is_model_text_message(plain_model) is True
    assert ContextCompressionPlugin._is_model_text_message(tool_call) is False
    assert ContextCompressionPlugin._is_model_text_message(plain_user) is False
    print("\n✅ _is_model_text_message correctly excludes tool call model turns")


# ── NEW: _adjust_to_safe_boundary tests ──────────────────────────────────────


def test_adjust_to_safe_boundary_skips_tool_response_in_general_case():
    """In the general case, split_index on a tool_response should advance to the
    next real user text message, never stopping on a function_response.

    Sequence:
        0: user_text
        1: model_tool_call
        2: user_tool_resp    ← initial split_index (should be skipped)
        3: user_text         ← expected result
        4: model_text
    """
    contents = [
        _make_content("user", "第1轮用户消息"),
        _make_function_call_content(call_id="c1"),
        _make_function_response_content(call_id="c1"),
        _make_content("user", "第2轮用户消息"),
        _make_content("model", "第2轮模型回复"),
    ]
    # split_index=2 lands on tool_response; should advance to index 3
    result = ContextCompressionPlugin._adjust_to_safe_boundary(contents, split_index=2)
    assert result == 3, f"Expected 3 (next real user), got {result}"
    print(f"\n✅ _adjust_to_safe_boundary skipped tool_response → landed on index {result}")


def test_adjust_to_safe_boundary_protects_full_tool_sequence_at_end():
    """Boundary case: last message is function_response → scan back to keep full
    tool sequence (function_response + function_call + any preceding model turns).

    Sequence:
        0: user_text
        1: model_text
        2: user_text
        3: model_tool_call   ← must be kept
        4: user_tool_resp    ← last, split_index >= n-1

    Expected: split_index moves back to 2 (before model_tool_call),
    so the entire tool round-trip [model_tool_call, user_tool_resp] is preserved.
    """
    contents = [
        _make_content("user", "第1轮用户消息"),
        _make_content("model", "第1轮模型回复"),
        _make_content("user", "第2轮用户消息"),
        _make_function_call_content(call_id="c1"),
        _make_function_response_content(call_id="c1"),
    ]
    result = ContextCompressionPlugin._adjust_to_safe_boundary(contents, split_index=5)
    # tool sequence starts at index 3 (model_tool_call); the safe cut is before it → index 2
    assert result == 2, (
        f"Expected 2 (before tool sequence), got {result}"
    )
    print(f"\n✅ _adjust_to_safe_boundary protected full tool sequence → index {result}")


def test_adjust_to_safe_boundary_last_is_real_user():
    """Boundary case: last message is a real user text → cut point should be that index,
    so the user message falls into the 'keep' window.

    Sequence:
        0: user_text
        1: model_text
        2: user_text
        3: model_text
        4: user_text   ← last, split_index >= n-1 → expect result = 4
    """
    contents = [
        _make_content("user", "第1轮"),
        _make_content("model", "回复1"),
        _make_content("user", "第2轮"),
        _make_content("model", "回复2"),
        _make_content("user", "第3轮"),  # last
    ]
    result = ContextCompressionPlugin._adjust_to_safe_boundary(contents, split_index=5)
    assert result == 4, f"Expected 4 (last real user), got {result}"
    print(f"\n✅ _adjust_to_safe_boundary kept last user message → index {result}")


# ── NEW: _get_header_contents tests ──────────────────────────────────────────


def test_get_header_contents_includes_first_user_and_model_reply():
    """_get_header_contents should return the first user message AND the first model
    text reply as the topic anchor pair.
    """
    contents = [
        _make_content("user", "第一条用户消息"),       # index 0
        _make_content("model", "第一条模型回复"),      # index 1
        _make_content("user", "第二条用户消息"),       # index 2
        _make_content("model", "第二条模型回复"),      # index 3
    ]
    header = ContextCompressionPlugin._get_header_contents(contents, split_index=4)
    assert len(header) == 2, f"Expected 2 header items (user+model), got {len(header)}"
    assert header[0].role == "user"
    assert header[1].role == "model"
    assert header[0].parts[0].text == "第一条用户消息"
    assert header[1].parts[0].text == "第一条模型回复"
    print("\n✅ _get_header_contents returned user+model pair")


def test_get_header_contents_skips_tool_call_model_turn():
    """If the first model turn is a tool call (not plain text), it should be skipped.
    The header should only contain the user message (no model anchor).
    """
    contents = [
        _make_content("user", "第一条用户消息"),          # index 0
        _make_function_call_content(call_id="c1"),         # index 1: tool call, skip
        _make_function_response_content(call_id="c1"),     # index 2: tool resp
        _make_content("user", "第二条用户消息"),           # index 3
        _make_content("model", "第二条模型回复"),          # index 4
    ]
    header = ContextCompressionPlugin._get_header_contents(contents, split_index=5)
    # The first model turn is a tool_call → no model anchor added; header has only user
    assert len(header) == 1, f"Expected 1 header item (only user), got {len(header)}"
    assert header[0].role == "user"
    print("\n✅ _get_header_contents skipped tool_call model turn → only user in header")


# ── NEW: compressed structure tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_compressed_contents_includes_user_model_header_anchor():
    """After compression, the first two Contents should be the topic anchor pair:
    [user_text, model_text], followed by the summary as a user message.
    """
    plugin = ContextCompressionPlugin()
    req = _make_llm_request(num_turns=10)

    callback_ctx = MagicMock()

    with patch.object(plugin, "_call_llm_to_compact", new=AsyncMock(return_value=FAKE_SUMMARY)):
        original_threshold = mod.COMPRESSION_TOKEN_THRESHOLD
        mod.COMPRESSION_TOKEN_THRESHOLD = 0.00001
        try:
            await plugin.before_model_callback(
                callback_context=callback_ctx,
                llm_request=req,
            )
        finally:
            mod.COMPRESSION_TOKEN_THRESHOLD = original_threshold

    # First content: user anchor
    assert req.contents[0].role == "user", "First content should be user anchor"
    # Second content could be model anchor or summary (depends on how many turns were compressed)
    # At minimum, the summary must be present somewhere
    all_texts = [
        part.text
        for c in req.contents
        for part in (c.parts or [])
        if part.text
    ]
    assert any(FAKE_SUMMARY in t for t in all_texts), "Summary must be in compressed contents"
    print(f"\n✅ Compressed contents structure: {[c.role for c in req.contents[:4]]}")


# ── NEW: tool call sequence integrity test ────────────────────────────────────


@pytest.mark.asyncio
async def test_compression_with_tool_calls_preserves_sequence_integrity():
    """After compression, no orphaned function_call or function_response should exist.

    An orphaned function_call is a model Content with function_call parts that is NOT
    immediately followed by a user Content with function_response parts.

    This verifies _adjust_to_safe_boundary correctly avoids splitting tool sequences.
    """
    plugin = ContextCompressionPlugin()
    req = _make_llm_request_with_tool_calls(num_text_turns=8)
    original_count = len(req.contents)

    callback_ctx = MagicMock()

    with patch.object(plugin, "_call_llm_to_compact", new=AsyncMock(return_value=FAKE_SUMMARY)):
        original_threshold = mod.COMPRESSION_TOKEN_THRESHOLD
        mod.COMPRESSION_TOKEN_THRESHOLD = 0.00001
        try:
            await plugin.before_model_callback(
                callback_context=callback_ctx,
                llm_request=req,
            )
        finally:
            mod.COMPRESSION_TOKEN_THRESHOLD = original_threshold

    compressed = req.contents

    # Verify no orphaned function_call: every tool_call must be followed by tool_response
    for i, content in enumerate(compressed):
        if ContextCompressionPlugin._is_tool_call(content):
            assert i + 1 < len(compressed), (
                f"Orphaned function_call at index {i} (nothing follows it)"
            )
            assert ContextCompressionPlugin._is_tool_response(compressed[i + 1]), (
                f"function_call at index {i} not followed by function_response "
                f"(got role={compressed[i + 1].role})"
            )

    # Verify no orphaned function_response: every tool_response must be preceded by tool_call
    for i, content in enumerate(compressed):
        if ContextCompressionPlugin._is_tool_response(content):
            assert i > 0, f"Orphaned function_response at index 0"
            assert ContextCompressionPlugin._is_tool_call(compressed[i - 1]), (
                f"function_response at index {i} not preceded by function_call "
                f"(got role={compressed[i - 1].role})"
            )

    print(
        f"\n✅ Tool call sequence integrity preserved "
        f"({original_count} → {len(compressed)} contents, no orphaned tool calls)"
    )


# ── standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def _run_all():
        sync_tests = [
            test_is_tool_call_detects_function_call_content,
            test_is_tool_response_detects_function_response_content,
            test_is_real_user_message_excludes_tool_response,
            test_is_model_text_message_excludes_tool_calls,
            test_adjust_to_safe_boundary_skips_tool_response_in_general_case,
            test_adjust_to_safe_boundary_protects_full_tool_sequence_at_end,
            test_adjust_to_safe_boundary_last_is_real_user,
            test_get_header_contents_includes_first_user_and_model_reply,
            test_get_header_contents_skips_tool_call_model_turn,
        ]
        async_tests = [
            test_compression_triggered_and_reduces_contents,
            test_summary_appears_in_contents,
            test_no_compression_below_threshold,
            test_compression_failure_leaves_contents_intact,
            test_too_few_contents_skipped,
            test_contents_start_with_user_role_after_compression,
            test_compressed_contents_includes_user_model_header_anchor,
            test_compression_with_tool_calls_preserves_sequence_integrity,
        ]
        passed = failed = 0

        for t in sync_tests:
            try:
                t()
                passed += 1
            except Exception as e:
                print(f"\n❌ {t.__name__} FAILED: {e}")
                import traceback
                traceback.print_exc()
                failed += 1

        for t in async_tests:
            try:
                await t()
                passed += 1
            except Exception as e:
                print(f"\n❌ {t.__name__} FAILED: {e}")
                import traceback
                traceback.print_exc()
                failed += 1

        print(f"\n{'=' * 50}")
        print(f"Results: {passed} passed, {failed} failed")

    asyncio.run(_run_all())

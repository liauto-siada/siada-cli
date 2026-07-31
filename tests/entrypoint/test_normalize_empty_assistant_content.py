"""Tests for _normalize_empty_assistant_content in siada.entrypoint.

Covers the fix for: Kimi/Moonshot (and other OpenAI-compatible providers)
rejecting assistant turns that end up with no text AND no tool_calls with
"the message ... must not be empty", even after content is set to None.
"""

from siada.entrypoint import _normalize_empty_assistant_content


def test_empty_string_content_with_tool_calls_becomes_none():
    """Pure tool-call turn: content='' + tool_calls -> content=None, message kept."""
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {}}],
        }
    ]
    _normalize_empty_assistant_content(messages)

    assert len(messages) == 1
    assert messages[0]["content"] is None


def test_empty_string_content_without_tool_calls_is_dropped():
    """Interrupted-stream turn: content='' + no tool_calls -> message is removed
    entirely, instead of being left as an empty/None placeholder that some
    OpenAI-compatible providers (e.g. Kimi/Moonshot) reject outright.
    """
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "   "},
        {"role": "user", "content": "still there?"},
    ]
    _normalize_empty_assistant_content(messages)

    assert len(messages) == 2
    assert messages[0]["content"] == "hi"
    assert messages[1]["content"] == "still there?"


def test_none_content_without_tool_calls_is_dropped():
    """content already None + no tool_calls should also be dropped."""
    messages = [
        {"role": "assistant", "content": None},
    ]
    _normalize_empty_assistant_content(messages)

    assert messages == []


def test_list_content_with_only_empty_text_block_and_tool_calls_becomes_none():
    """Thinking-block turn where the trailing text block is empty, but a
    tool_calls is present -> keep thinking block, drop empty text, keep msg.
    """
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "let me think..."},
                {"type": "text", "text": ""},
            ],
            "tool_calls": [{"id": "call_1", "type": "function", "function": {}}],
        }
    ]
    _normalize_empty_assistant_content(messages)

    assert len(messages) == 1
    assert messages[0]["content"] == [
        {"type": "thinking", "thinking": "let me think..."}
    ]


def test_list_content_all_empty_text_without_tool_calls_is_dropped():
    """List content whose only non-empty-worthy blocks are empty text blocks,
    and no tool_calls -> drop the message.
    """
    messages = [
        {
            "role": "assistant",
            "content": [{"type": "text", "text": ""}],
        }
    ]
    _normalize_empty_assistant_content(messages)

    assert messages == []


def test_list_content_with_remaining_blocks_keeps_message_untouched_shape():
    """List content with a mix of valid + empty text blocks -> empty text
    dropped, message kept regardless of tool_calls.
    """
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": ""},
                {"type": "text", "text": "hello"},
            ],
        }
    ]
    _normalize_empty_assistant_content(messages)

    assert len(messages) == 1
    assert messages[0]["content"] == [{"type": "text", "text": "hello"}]


def test_non_assistant_messages_are_untouched():
    messages = [
        {"role": "user", "content": ""},
        {"role": "system", "content": None},
    ]
    original = [dict(m) for m in messages]
    _normalize_empty_assistant_content(messages)

    assert messages == original


def test_none_and_empty_messages_input_are_noop():
    assert _normalize_empty_assistant_content(None) is None
    assert _normalize_empty_assistant_content([]) is None


def test_multiple_empty_assistant_turns_are_all_dropped_preserving_order():
    messages = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": ""},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": None},
        {"role": "user", "content": "q3"},
    ]
    _normalize_empty_assistant_content(messages)

    assert [m["content"] for m in messages] == ["q1", "q2", "q3"]


def test_orphaned_reasoning_content_without_content_or_tool_calls_is_dropped():
    """This is the exact shape produced by
    ``agents.models.chatcmpl_converter.Converter.items_to_messages()`` for a
    Kimi/GLM/DeepSeek reasoning-replay turn that got interrupted right after
    the reasoning step -- before any text or tool call was emitted: the
    ``content`` key is entirely absent (not even ``None``, since
    ``new_asst["content"]`` is never assigned when there are no text
    segments) and ``tool_calls`` was deleted because it ended up empty.
    Kimi's API does not treat ``reasoning_content`` as satisfying its
    "must not be empty" check, so this message must be dropped entirely,
    exactly like the plain-empty-string case -- this is the root cause of
    the originally reported 400 error.
    """
    messages = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "reasoning_content": "let me think about this..."},
        {"role": "user", "content": "q2"},
    ]
    _normalize_empty_assistant_content(messages)

    assert [m["content"] for m in messages] == ["q1", "q2"]


def test_reasoning_content_preserved_when_tool_calls_present():
    """The common, healthy Kimi/GLM reasoning-replay shape: reasoning_content
    co-occurs with a real tool_calls entry. This message carries real
    information and must be left untouched -- content=None stays None
    (valid, since tool_calls is non-empty) and reasoning_content survives.
    """
    messages = [
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "let me think about this...",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {}}],
        }
    ]
    original = dict(messages[0])
    _normalize_empty_assistant_content(messages)

    assert messages == [original]


def test_reasoning_content_preserved_when_text_content_present():
    """reasoning_content co-occurring with real text content must also
    survive untouched.
    """
    messages = [
        {
            "role": "assistant",
            "content": "here is my answer",
            "reasoning_content": "let me think about this...",
        }
    ]
    original = dict(messages[0])
    _normalize_empty_assistant_content(messages)

    assert messages == [original]

"""Unit tests for the sentinel marker utilities.

Covers two marker families:
- Holographic prefetch (``wrap_prefetch_block`` / ``strip_prefetch_block``).
- Feishu/Lark IM context (``wrap_im_context_block`` / ``strip_im_context_block``).

Plus the unified strip-all helpers used by frontend rendering and memory
review (``strip_all_injection_blocks`` / ``has_any_injection_block``).
"""

from siada.services.memory.holographic.marker import (
    HOLOGRAPHIC_PREFETCH_BEGIN,
    HOLOGRAPHIC_PREFETCH_END,
    IM_CONTEXT_INJECTION_BEGIN,
    IM_CONTEXT_INJECTION_END,
    USER_INPUT_BEGIN,
    USER_INPUT_END,
    has_any_injection_block,
    has_prefetch_block,
    split_prefetch_blocks,
    strip_all_injection_blocks,
    strip_im_context_block,
    strip_prefetch_block,
    strip_user_input,
    wrap_im_context_block,
    wrap_prefetch_block,
    wrap_user_input,
)



def test_wrap_empty_returns_empty_string():
    assert wrap_prefetch_block("") == ""
    assert wrap_prefetch_block(None) == ""  # tolerant of None
    assert wrap_prefetch_block("   \n\t\n") == ""


def test_wrap_produces_begin_end_sentinels():
    out = wrap_prefetch_block("## Holographic Memory\n- fact A\n- fact B")
    assert out.startswith(HOLOGRAPHIC_PREFETCH_BEGIN + "\n")
    assert HOLOGRAPHIC_PREFETCH_END in out
    # Trailing blank line so caller can simply concatenate user input.
    assert out.endswith("\n\n")
    assert "## Holographic Memory" in out


def test_has_prefetch_block_positive_and_negative():
    wrapped = wrap_prefetch_block("- fact A")
    assert has_prefetch_block(wrapped) is True
    assert has_prefetch_block(wrapped + "\nuser turn") is True
    assert has_prefetch_block("plain user text") is False
    assert has_prefetch_block("") is False
    assert has_prefetch_block(None) is False  # type: ignore[arg-type]


def test_strip_returns_input_when_no_marker():
    assert strip_prefetch_block("hello world") == "hello world"
    assert strip_prefetch_block("") == ""


def test_strip_removes_single_block_and_keeps_user_text():
    user_text = "Please review the PR."
    full = wrap_prefetch_block("- fact A") + user_text
    cleaned = strip_prefetch_block(full)
    assert cleaned == user_text
    assert HOLOGRAPHIC_PREFETCH_BEGIN not in cleaned
    assert HOLOGRAPHIC_PREFETCH_END not in cleaned


def test_strip_handles_multiple_blocks_across_turns():
    """Multiple wrapped blocks (e.g. concatenated history) all get stripped."""
    block1 = wrap_prefetch_block("- fact A")
    block2 = wrap_prefetch_block("- fact B")
    full = block1 + "first turn\n\n" + block2 + "second turn"
    cleaned = strip_prefetch_block(full)
    assert HOLOGRAPHIC_PREFETCH_BEGIN not in cleaned
    assert "first turn" in cleaned
    assert "second turn" in cleaned


def test_split_extracts_block_bodies_and_remaining_text():
    user_text = "What changed in main.py?"
    full = wrap_prefetch_block("## Holographic Memory\n- fact A") + user_text
    blocks, remaining = split_prefetch_blocks(full)
    assert len(blocks) == 1
    assert "fact A" in blocks[0]
    # No sentinels leak into either side of the split.
    assert HOLOGRAPHIC_PREFETCH_BEGIN not in blocks[0]
    assert HOLOGRAPHIC_PREFETCH_END not in blocks[0]
    assert remaining == user_text


def test_split_returns_empty_blocks_when_text_is_plain():
    blocks, remaining = split_prefetch_blocks("hello")
    assert blocks == []
    assert remaining == "hello"


def test_split_handles_multiple_blocks():
    block1 = wrap_prefetch_block("- fact A")
    block2 = wrap_prefetch_block("- fact B")
    full = block1 + "user turn 1\n\n" + block2 + "user turn 2"
    blocks, remaining = split_prefetch_blocks(full)
    assert len(blocks) == 2
    assert "fact A" in blocks[0]
    assert "fact B" in blocks[1]
    # Remaining text keeps both user turns interleaved correctly.
    assert "user turn 1" in remaining
    assert "user turn 2" in remaining
    assert HOLOGRAPHIC_PREFETCH_BEGIN not in remaining


# ── IM-context block helpers ─────────────────────────────────────────


def test_im_context_wrap_uses_im_sentinels():
    """IM context wrap must use the IM sentinels, not the holographic ones."""
    out = wrap_im_context_block(
        '// Replied message (untrusted metadata):\n{"sender": "Alice"}'
    )
    assert out.startswith(IM_CONTEXT_INJECTION_BEGIN + "\n")
    assert IM_CONTEXT_INJECTION_END in out
    # Must not collide with holographic markers.
    assert HOLOGRAPHIC_PREFETCH_BEGIN not in out
    assert HOLOGRAPHIC_PREFETCH_END not in out


def test_im_context_strip_removes_only_im_blocks():
    user_text = "Got it, will look into it."
    full = wrap_im_context_block("// Replied message: hi") + user_text
    cleaned = strip_im_context_block(full)
    assert cleaned == user_text


# ── strip-all / has-any covering both families ───────────────────────


def test_has_any_injection_block_detects_either_family():
    holo = wrap_prefetch_block("- fact A")
    im = wrap_im_context_block("// Replied message: hi")
    assert has_any_injection_block(holo + "user") is True
    assert has_any_injection_block(im + "user") is True
    assert has_any_injection_block("plain user text") is False


def test_strip_all_removes_both_holographic_and_im_context():
    """Frontend / memory review path: a user message can carry both kinds.

    Lark inbound message goes through both injectors when holographic memory
    is enabled — quoted reply (head) + holographic facts (also head) +
    msg.content + suffix (tail). After strip_all, only msg.content remains.
    """
    holo = wrap_prefetch_block("## Holographic Memory\n- fact A")
    im_head = wrap_im_context_block(
        '// Replied message (untrusted metadata):\n{"sender": "Alice"}'
    )
    im_tail = wrap_im_context_block(
        '// Conversation info (untrusted metadata):\n{"chat_id": "oc_xxx"}'
    )
    user_text = "Please summarise the discussion."
    full = holo + im_head + user_text + "\n\n" + im_tail.rstrip("\n")
    cleaned = strip_all_injection_blocks(full)
    assert HOLOGRAPHIC_PREFETCH_BEGIN not in cleaned
    assert IM_CONTEXT_INJECTION_BEGIN not in cleaned
    assert "fact A" not in cleaned
    assert "chat_id" not in cleaned
    assert "Replied message" not in cleaned
    assert user_text in cleaned


def test_strip_all_is_noop_for_plain_text():
    """No markers → input is returned untouched (zero-cost)."""
    plain = "Hello, what's the status of the build?"
    assert strip_all_injection_blocks(plain) == plain
    assert strip_all_injection_blocks("") == ""
    assert strip_all_injection_blocks(None) is None  # type: ignore[arg-type]


# ── User-input tag (wrap_user_input / strip_user_input) ────────────────
#
# Unlike the injection-block helpers above (which discard the whole
# wrapped block on strip), this tag wraps the human's own literal text —
# stripping only removes the two literal tag strings and keeps the body
# plus anything sitting outside the tags untouched.


def test_wrap_user_input_basic():
    out = wrap_user_input("hello agent")
    assert out == f"{USER_INPUT_BEGIN}hello agent{USER_INPUT_END}"
    assert out == "<user_input>hello agent</user_input>"


def test_wrap_user_input_noop_on_non_str_or_empty():
    """Non-str / empty input is returned unchanged (no wrapping)."""
    assert wrap_user_input("") == ""
    assert wrap_user_input(None) is None  # type: ignore[arg-type]
    sentinel = ["not", "a", "string"]
    assert wrap_user_input(sentinel) is sentinel  # type: ignore[arg-type]


def test_wrap_user_input_preserves_whitespace_only_text():
    """Whitespace-only text is truthy → still wrapped (unlike empty string)."""
    assert wrap_user_input("   ") == "<user_input>   </user_input>"


def test_wrap_user_input_is_idempotent():
    """Wrapping an already-wrapped string is a no-op, guarding against
    double-wrapping when a value passes through more than one entry point
    (e.g. both ConversationTurn and PendingUserInputInjector)."""
    once = wrap_user_input("hello agent")
    twice = wrap_user_input(once)
    assert twice == once
    assert twice.count(USER_INPUT_BEGIN) == 1
    assert twice.count(USER_INPUT_END) == 1


def test_strip_user_input_roundtrip():
    user_text = "Please review the PR."
    wrapped = wrap_user_input(user_text)
    assert strip_user_input(wrapped) == user_text


def test_strip_user_input_is_noop_when_tag_absent():
    plain = "plain text, never wrapped"
    assert strip_user_input(plain) == plain


def test_strip_user_input_noop_on_non_str_or_empty():
    assert strip_user_input("") == ""
    assert strip_user_input(None) is None  # type: ignore[arg-type]


def test_strip_user_input_preserves_content_outside_tags():
    """Content sitting outside the <user_input> tags (e.g. IM context
    blocks appended before/after by LarkAgentExecutor._build_user_input)
    must survive the strip untouched — only the tag strings are removed."""
    im_head = wrap_im_context_block("// Replied message: hi")
    im_tail = wrap_im_context_block('// Conversation info: {"chat_id": "oc_xxx"}')
    user_text = "Please summarise the discussion."
    full = im_head + wrap_user_input(user_text) + "\n\n" + im_tail.rstrip("\n")
    cleaned = strip_user_input(full)
    assert USER_INPUT_BEGIN not in cleaned
    assert USER_INPUT_END not in cleaned
    # Everything outside the <user_input> tags is preserved as-is.
    assert user_text in cleaned
    assert "Replied message" in cleaned
    assert "chat_id" in cleaned


def test_strip_user_input_handles_multiple_tags():
    """Multiple wrapped segments (e.g. concatenated turn history) all have
    their tags removed, keeping every body intact."""
    full = wrap_user_input("first turn") + " " + wrap_user_input("second turn")
    cleaned = strip_user_input(full)
    assert cleaned == "first turn second turn"
    assert USER_INPUT_BEGIN not in cleaned
    assert USER_INPUT_END not in cleaned

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
    has_any_injection_block,
    has_prefetch_block,
    split_prefetch_blocks,
    strip_all_injection_blocks,
    strip_im_context_block,
    strip_prefetch_block,
    wrap_im_context_block,
    wrap_prefetch_block,
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

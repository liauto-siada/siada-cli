"""
Tests for ``fix_tool_message_ordering`` — the Chat Completions repair applied
to the compaction summarization call.

Regression context
------------------
Session 1786609084879-68bf0bb7 (model bailian-kimi-k3) failed compaction with::

    litellm.BadRequestError: MoonshotException - an assistant message with
    'tool_calls' must be followed by tool messages responding to each
    'tool_call_id'. The following tool_call_ids did not have response
    messages: edit_file_24

The Responses-API item stream contained an interleaved assistant text message
between a function_call and its function_call_output (valid for Responses)::

    fc_edit_file_24, assistant_text, fc_edit_file_25, fco_edit_file_24, fco_edit_file_25

``Converter.items_to_messages`` flushed the pending assistant message at the
interleaved text, stranding ``tool(edit_file_24)`` behind the second
assistant message — which Moonshot strictly rejects. The normal streaming
path already repairs this (li_provider → LitellmModel._fix_tool_message_ordering);
``fix_tool_message_ordering`` brings the same repair to the compaction path.
"""
from __future__ import annotations

from agents.models.chatcmpl_converter import Converter

from siada.agent_hub.context_filter.utils import (
    _OMITTED_TOOL_OUTPUT_PLACEHOLDER,
    fix_tool_message_ordering,
)


# ── helpers ──────────────────────────────────────────────────────────────

def _assert_moonshot_invariant(messages) -> None:
    """Assert the strict Chat Completions invariant Moonshot enforces.

    Every assistant message with tool_calls must be immediately followed by
    tool messages responding to each tool_call_id, in order.
    """
    for i, m in enumerate(messages):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            expected = [tc["id"] for tc in m["tool_calls"]]
            got = []
            j = i + 1
            while j < len(messages) and messages[j].get("role") == "tool":
                got.append(messages[j]["tool_call_id"])
                j += 1
            assert got == expected, (
                f"assistant msg #{i} tool_calls={expected} but immediately "
                f"following tool messages={got}"
            )
        # A tool message must never appear without a preceding assistant
        # message claiming it.
        if m.get("role") == "tool":
            assert i > 0 and messages[i - 1].get("role") == "assistant", (
                f"orphan tool message at #{i}: {m.get('tool_call_id')}"
            )


def _fc(call_id, name="edit_file"):
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": "{}",
    }


def _fco(call_id, output="done"):
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": output,
    }


def _assistant_text(text):
    # Real Responses output messages always carry a server-minted ``id`` -- the
    # SDK's ``maybe_response_output_message`` requires it (``{"id", "content"}``
    # must be present), otherwise the item is parsed as an EasyInputMessage and
    # its ``output_text`` parts are rejected.  Keep the fixture realistic.
    return {
        "id": "msg_fixture_1",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
    }


# ── tests ────────────────────────────────────────────────────────────────


class TestInterleavedResponsesItems:
    """The exact failure shape from session 1786609084879-68bf0bb7."""

    def test_interleaved_text_between_call_and_output(self):
        items = [
            {"role": "user", "content": "do something"},
            _fc("edit_file_24"),
            _assistant_text("单一 spawn 点。开始实施："),
            _fc("edit_file_25"),
            _fco("edit_file_24", "file A written"),
            _fco("edit_file_25", "file B written"),
        ]
        # Sanity: the raw conversion carries both tool calls and both outputs.
        # (How the SDK arranges them differs across versions: <=0.22.2 split
        # the turn into assistant(A) -> assistant(text, B); >=0.22.3 merges
        # the text and both calls into a single assistant message, which the
        # Chat Completions API accepts.  Either way the repair below must
        # yield the Moonshot-valid ordering.)
        raw = Converter.items_to_messages(items)
        assert [m.get("role") for m in raw].count("tool") == 2

        fixed = fix_tool_message_ordering(raw)
        _assert_moonshot_invariant(fixed)

        # Content and pairing are preserved, order follows the call order.
        tool_pairs = [
            (m["tool_calls"][0]["id"], None)
            for m in fixed
            if m.get("role") == "assistant" and m.get("tool_calls")
        ]
        tool_msgs = [m for m in fixed if m.get("role") == "tool"]
        assert [p[0] for p in tool_pairs] == ["edit_file_24", "edit_file_25"]
        assert [m["tool_call_id"] for m in tool_msgs] == [
            "edit_file_24",
            "edit_file_25",
        ]
        assert [m["content"] for m in tool_msgs] == [
            "file A written",
            "file B written",
        ]

        # The interleaved assistant text survives exactly once. Which split
        # carries it depends on how the SDK ordered the raw conversion:
        # <=0.22.2 produced assistant(A) -> assistant(text, B) (text on the
        # second), >=0.22.3 merges text and both calls into one message, which
        # the repair splits with shared content kept on the first split.
        call_carrying_texts = [
            m.get("content")
            for m in fixed
            if m.get("role") == "assistant" and m.get("tool_calls")
        ]
        assert call_carrying_texts.count("单一 spawn 点。开始实施：") == 1


class TestAlreadyValidSequences:
    def test_parallel_calls_same_assistant_message(self):
        """Standard parallel group: fc_A, fc_B, fco_A, fco_B.

        The converter merges both calls into one assistant message; the fix
        splits it into one assistant message per call, each followed by its
        own tool response. Content stays on the first split only.
        """
        items = [
            {"role": "user", "content": "hi"},
            _assistant_text("calling two tools"),
            _fc("call_A"),
            _fc("call_B"),
            _fco("call_A", "out A"),
            _fco("call_B", "out B"),
        ]
        fixed = fix_tool_message_ordering(Converter.items_to_messages(items))
        _assert_moonshot_invariant(fixed)

        assistant_with_calls = [
            m
            for m in fixed
            if m.get("role") == "assistant" and m.get("tool_calls")
        ]
        assert len(assistant_with_calls) == 2
        assert assistant_with_calls[0].get("content") == "calling two tools"
        # Second split must not duplicate the shared text.
        assert "content" not in assistant_with_calls[1]

    def test_simple_pair_unchanged_semantics(self):
        items = [
            {"role": "user", "content": "hi"},
            _fc("call_A"),
            _fco("call_A", "out A"),
            _assistant_text("final answer"),
        ]
        fixed = fix_tool_message_ordering(Converter.items_to_messages(items))
        _assert_moonshot_invariant(fixed)
        assert fixed[-1]["role"] == "assistant"
        assert fixed[-1]["content"] == "final answer"


class TestChatLevelRepairs:
    """Repairs applied directly on Chat Completions-shaped messages."""

    def test_missing_tool_result_gets_placeholder(self):
        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_X",
                        "type": "function",
                        "function": {"name": "edit_file", "arguments": "{}"},
                    }
                ],
            },
            {"role": "assistant", "content": "unrelated text"},
        ]
        fixed = fix_tool_message_ordering(messages)
        _assert_moonshot_invariant(fixed)
        tool_msg = fixed[2]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "call_X"
        assert tool_msg["content"] == _OMITTED_TOOL_OUTPUT_PLACEHOLDER

    def test_orphan_tool_message_dropped(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "tool", "tool_call_id": "ghost", "content": "stale"},
            {"role": "assistant", "content": "answer"},
        ]
        fixed = fix_tool_message_ordering(messages)
        assert [m["role"] for m in fixed] == ["user", "assistant"]

    def test_tool_message_moved_next_to_its_assistant(self):
        """A tool message stranded behind another assistant message is moved."""
        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_A",
                        "type": "function",
                        "function": {"name": "f", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "text in between",
                "tool_calls": [
                    {
                        "id": "call_B",
                        "type": "function",
                        "function": {"name": "f", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_A", "content": "out A"},
            {"role": "tool", "tool_call_id": "call_B", "content": "out B"},
        ]
        fixed = fix_tool_message_ordering(messages)
        _assert_moonshot_invariant(fixed)
        assert [m.get("role") for m in fixed] == [
            "user",
            "assistant",
            "tool",
            "assistant",
            "tool",
        ]
        assert fixed[2]["tool_call_id"] == "call_A"
        assert fixed[4]["tool_call_id"] == "call_B"


class TestEdgeCases:
    def test_empty_list(self):
        assert fix_tool_message_ordering([]) == []

    def test_none_passthrough(self):
        assert fix_tool_message_ordering(None) is None

    def test_no_tool_calls_unchanged(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        assert fix_tool_message_ordering(messages) == messages

    def test_input_not_mutated(self):
        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_A",
                        "type": "function",
                        "function": {"name": "f", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_A", "content": "out A"},
        ]
        snapshot = [dict(m) for m in messages]
        fix_tool_message_ordering(messages)
        assert messages == snapshot

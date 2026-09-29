"""
Tests for ConversationTurn._is_truncated_reasoning_only_completion.

Covers the Chat Completions/LiteLLM "fake completion" detection: a turn that
ends with an empty final_output whose LAST generated item is a bare
ReasoningItem should be treated as a truncated stream, not a genuine empty
response from the model. ConversationTurn.execute() only detects and tags
this on TurnOutput.metadata["truncated_reasoning_only"] -- the retry
decision itself lives at the Controller layer (see
Controller._retry_on_truncated_reasoning).
"""
from types import SimpleNamespace

from agents.items import ReasoningItem, MessageOutputItem, ToolCallItem

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn


class _FakeAgent:
    """Minimal stand-in for a real Agent -- RunItemBase.__post_init__ takes
    a weakref to ``agent``, which fails for ``None``, so tests need *some*
    weakly-referenceable object here instead."""
    pass


def _make_turn():
    return ConversationTurn.__new__(ConversationTurn)


def _reasoning_item():
    return ReasoningItem(agent=_FakeAgent(), raw_item=SimpleNamespace())


def _message_item():
    return MessageOutputItem(agent=_FakeAgent(), raw_item=SimpleNamespace())


def _tool_call_item():
    return ToolCallItem(agent=_FakeAgent(), raw_item=SimpleNamespace())


class _FakeResult:
    def __init__(self, final_output, new_items):
        self.final_output = final_output
        self.new_items = new_items


class TestIsTruncatedReasoningOnlyCompletion:
    def test_true_when_empty_output_and_last_item_is_reasoning(self):
        turn = _make_turn()
        result = _FakeResult("", [_reasoning_item()])
        assert turn._is_truncated_reasoning_only_completion(result) is True

    def test_true_when_none_output_and_last_item_is_reasoning(self):
        turn = _make_turn()
        result = _FakeResult(None, [_reasoning_item()])
        assert turn._is_truncated_reasoning_only_completion(result) is True

    def test_true_when_whitespace_only_output(self):
        turn = _make_turn()
        result = _FakeResult("   \n", [_reasoning_item()])
        assert turn._is_truncated_reasoning_only_completion(result) is True

    def test_false_when_final_output_is_non_empty(self):
        """A genuine reasoning-then-answer turn must not be flagged, even
        though a ReasoningItem is present earlier in new_items."""
        turn = _make_turn()
        result = _FakeResult("here is my answer", [_reasoning_item(), _message_item()])
        assert turn._is_truncated_reasoning_only_completion(result) is False

    def test_false_when_last_item_is_message_output(self):
        """Healthy turn: reasoning followed by a real message -- last item
        is NOT a bare ReasoningItem, so this must never be flagged even if
        final_output were empty for some other legitimate reason."""
        turn = _make_turn()
        result = _FakeResult("", [_reasoning_item(), _message_item()])
        assert turn._is_truncated_reasoning_only_completion(result) is False

    def test_false_when_last_item_is_tool_call(self):
        turn = _make_turn()
        result = _FakeResult("", [_reasoning_item(), _tool_call_item()])
        assert turn._is_truncated_reasoning_only_completion(result) is False

    def test_false_when_no_new_items(self):
        """Empty output with genuinely no generated items at all (e.g. the
        model returned nothing whatsoever) must not be treated as the
        truncated-reasoning case -- there's no ReasoningItem to detect."""
        turn = _make_turn()
        result = _FakeResult("", [])
        assert turn._is_truncated_reasoning_only_completion(result) is False

    def test_false_when_output_non_empty_and_no_reasoning(self):
        turn = _make_turn()
        result = _FakeResult("answer text", [_message_item()])
        assert turn._is_truncated_reasoning_only_completion(result) is False

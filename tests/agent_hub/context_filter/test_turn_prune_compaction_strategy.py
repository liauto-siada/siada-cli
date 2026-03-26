"""Unit tests for TurnPruneSummaryCompaction."""
from __future__ import annotations

from unittest.mock import patch, MagicMock, AsyncMock
import pytest

from siada.agent_hub.context_filter.turn_prune_compaction_strategy import (
    TurnPruneSummaryCompaction,
    CompactionResult,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _user_msg(text="hi"):
    """Create a fake user message recognized by is_user_message."""
    return {"role": "user", "content": text, "_type": "user"}


def _assistant_msg(tool_use_ids=None):
    """Create a fake assistant message (function_call item).

    In the real API, each function_call is a top-level item in the messages
    list with {type: "function_call", call_id: "xxx", ...}.
    For simplicity, if multiple ids are given, we return just the first one
    since each real function_call is a separate message.
    """
    if tool_use_ids:
        return {"type": "function_call", "call_id": tool_use_ids[0],
                "name": "test", "arguments": "{}", "_type": "assistant"}
    return {"type": "function_call", "call_id": None,
            "name": "test", "arguments": "{}", "_type": "assistant"}


def _reasoning_msg():
    """Create a fake reasoning message."""
    return {"type": "reasoning", "id": "__fake_id__", "_type": "assistant"}


def _output_msg(text="some text"):
    """Create a fake output_message (assistant text response)."""
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}],
            "_type": "assistant"}


def _tool_result_msg(call_id, output="ok"):
    """Create a fake function response / tool_result message."""
    return {"call_id": call_id, "output": output, "_type": "tool_result"}


# ── Patch Converter so we don't need real openai types ───────────────

@pytest.fixture(autouse=True)
def _patch_converter():
    """Patch Converter methods to work with plain dicts."""
    def _maybe_easy_input(msg):
        if isinstance(msg, dict) and msg.get("_type") == "user":
            return msg
        return None

    def _maybe_input(msg):
        return None

    def _maybe_function_tool_call(msg):
        if isinstance(msg, dict) and msg.get("_type") == "assistant":
            return msg
        return None

    def _maybe_file_search(msg):
        return None

    def _maybe_reasoning(msg):
        return None

    def _maybe_response_output(msg):
        return None

    def _maybe_function_tool_call_output(msg):
        if isinstance(msg, dict) and msg.get("_type") == "tool_result":
            return msg
        return None

    with patch.multiple(
        "siada.agent_hub.context_filter.turn_prune_compaction_strategy.Converter",
        maybe_easy_input_message=_maybe_easy_input,
        maybe_input_message=_maybe_input,
        maybe_function_tool_call=_maybe_function_tool_call,
        maybe_file_search_call=_maybe_file_search,
        maybe_reasoning_message=_maybe_reasoning,
        maybe_response_output_message=_maybe_response_output,
        maybe_function_tool_call_output=_maybe_function_tool_call_output,
    ):
        yield


@pytest.fixture
def strategy():
    return TurnPruneSummaryCompaction()


# ── Test: _keep_recent_turns ─────────────────────────────────────────

class TestKeepRecentTurns:
    def test_fewer_turns_than_max(self, strategy):
        msgs = [_user_msg("a"), _user_msg("b")]
        result = strategy._keep_recent_turns(msgs, 5)
        assert len(result) == 2

    def test_exact_turns(self, strategy):
        msgs = [_user_msg("a"), _user_msg("b"), _user_msg("c")]
        result = strategy._keep_recent_turns(msgs, 3)
        assert len(result) == 3

    def test_truncates_old_turns(self, strategy):
        msgs = [
            _user_msg("1"),
            _assistant_msg(),
            _user_msg("2"),
            _assistant_msg(),
            _user_msg("3"),
        ]
        result = strategy._keep_recent_turns(msgs, 2)
        # should keep from 2nd user msg onward
        assert len(result) == 3
        assert result[0] == msgs[2]

    def test_max_turns_one(self, strategy):
        msgs = [_user_msg("1"), _user_msg("2"), _user_msg("3")]
        result = strategy._keep_recent_turns(msgs, 1)
        assert len(result) == 1
        assert result[0]["content"] == "3"


# ── Test: _repair_tool_pairs ────────────────────────────────────────

class TestRepairToolPairs:
    def test_removes_orphan_tool_result(self, strategy):
        """tool_result without matching tool_use should be removed."""
        msgs = [
            _tool_result_msg("id_orphan"),
            _user_msg("hi"),
        ]
        result = strategy._repair_tool_pairs(msgs)
        assert len(result) == 1
        assert result[0]["_type"] == "user"

    def test_removes_leading_orphan_tool_use(self, strategy):
        """Leading assistant with tool_use but no tool_result should be removed."""
        msgs = [
            _assistant_msg(["id_orphan"]),
            _user_msg("hi"),
        ]
        result = strategy._repair_tool_pairs(msgs)
        assert len(result) == 1
        assert result[0]["_type"] == "user"

    def test_keeps_matched_pairs(self, strategy):
        msgs = [
            _user_msg("hi"),
            _assistant_msg(["id1"]),
            _tool_result_msg("id1"),
            _user_msg("bye"),
        ]
        result = strategy._repair_tool_pairs(msgs)
        assert len(result) == 4

    def test_empty_messages(self, strategy):
        assert strategy._repair_tool_pairs([]) == []

    def test_ensures_first_message_is_user(self, strategy):
        """Non-user first messages should be stripped."""
        msgs = [
            _assistant_msg(["id1"]),
            _tool_result_msg("id1"),
            _user_msg("start"),
        ]
        result = strategy._repair_tool_pairs(msgs)
        assert result[0]["_type"] == "user"

    def test_removes_orphan_function_call_in_middle(self, strategy):
        """Orphan function_call in the middle (not just leading) should be removed."""
        msgs = [
            _user_msg("hi"),
            _assistant_msg(["orphan_id"]),  # no matching fco
            _user_msg("bye"),
        ]
        result = strategy._repair_tool_pairs(msgs)
        assert len(result) == 2
        assert all(m["_type"] == "user" for m in result)

    def test_removes_preceding_reasoning_and_output_with_orphan_fc(self, strategy):
        """When orphan function_call is removed, preceding reasoning and
        output_message from the same response group should also be removed."""
        msgs = [
            _user_msg("hi"),
            _reasoning_msg(),               # same response group
            _output_msg("thinking..."),      # same response group
            _assistant_msg(["orphan_id"]),   # orphan function_call
            _user_msg("bye"),
        ]
        result = strategy._repair_tool_pairs(msgs)
        assert len(result) == 2
        assert result[0]["content"] == "hi"
        assert result[1]["content"] == "bye"

    def test_does_not_remove_reasoning_from_different_group(self, strategy):
        """Reasoning before a matched function_call should NOT be removed."""
        msgs = [
            _user_msg("hi"),
            _reasoning_msg(),
            _output_msg("plan"),
            _assistant_msg(["id1"]),
            _tool_result_msg("id1"),
            _user_msg("bye"),
        ]
        result = strategy._repair_tool_pairs(msgs)
        assert len(result) == 6  # all kept

    def test_stops_backtrack_at_function_call_output_boundary(self, strategy):
        """Backtracking should stop at function_call_output (different group)."""
        msgs = [
            _user_msg("hi"),
            _assistant_msg(["id1"]),
            _tool_result_msg("id1"),
            _reasoning_msg(),               # new response group
            _output_msg("next step"),
            _assistant_msg(["orphan_id"]),   # orphan
            _user_msg("bye"),
        ]
        result = strategy._repair_tool_pairs(msgs)
        # orphan fc + its reasoning + output_msg removed, matched pair kept
        assert len(result) == 4
        assert result[0]["content"] == "hi"
        assert result[1]["type"] == "function_call"
        assert result[2]["_type"] == "tool_result"
        assert result[3]["content"] == "bye"

    def test_multi_fc_one_orphan_keeps_reasoning(self, strategy):
        """If one fc is matched and another orphan in same group,
        keep reasoning/output_msg (they belong to the matched fc too)."""
        msgs = [
            _user_msg("hi"),
            _reasoning_msg(),
            _output_msg("plan"),
            _assistant_msg(["id1"]),         # matched
            _assistant_msg(["orphan_id"]),    # orphan
            _tool_result_msg("id1"),
            _user_msg("bye"),
        ]
        result = strategy._repair_tool_pairs(msgs)
        # orphan fc removed, but reasoning/output_msg kept (matched fc between them)
        assert len(result) == 6
        types = [m.get("type") or m.get("_type") for m in result]
        assert "function_call" in types  # matched fc still there

    def test_multi_fc_all_orphan_removes_reasoning(self, strategy):
        """If all fcs in a group are orphaned, remove reasoning/output_msg too."""
        msgs = [
            _user_msg("hi"),
            _reasoning_msg(),
            _output_msg("plan"),
            _assistant_msg(["orphan1"]),
            _assistant_msg(["orphan2"]),
            _user_msg("bye"),
        ]
        result = strategy._repair_tool_pairs(msgs)
        assert len(result) == 2
        assert all(m["_type"] == "user" for m in result)


# ── Test: _truncate_tool_results ────────────────────────────────────

class TestTruncateToolResults:
    def test_short_result_unchanged(self, strategy):
        msgs = [_tool_result_msg("id1", "short output")]
        result = strategy._truncate_tool_results(msgs, 200_000)
        assert result[0]["output"] == "short output"

    def test_long_result_truncated(self, strategy):
        long_text = "x" * 500_000
        msgs = [_tool_result_msg("id1", long_text)]
        # context_window=200000 => max_chars = min(200000*4*0.3, 400000) = 240000
        result = strategy._truncate_tool_results(msgs, 200_000)
        assert "truncated" in result[0]["output"]
        assert len(result[0]["output"]) < len(long_text)

    def test_respects_hard_limit(self, strategy):
        long_text = "y" * 1_000_000
        msgs = [_tool_result_msg("id1", long_text)]
        # huge context_window => hits TOOL_RESULT_HARD_LIMIT=400000
        result = strategy._truncate_tool_results(msgs, 10_000_000)
        assert "truncated" in result[0]["output"]


# ── Test: _extract_tool_use_ids / _extract_tool_result_ids ──────────

class TestExtractIds:
    def test_extract_tool_use_ids_dict_function_call(self):
        """function_call item is a top-level message with call_id."""
        msg = {"type": "function_call", "call_id": "abc", "name": "test"}
        assert TurnPruneSummaryCompaction._extract_tool_use_ids(msg) == {"abc"}

    def test_extract_tool_use_ids_dict_tool_use(self):
        """tool_use item with id field."""
        msg = {"type": "tool_use", "id": "def"}
        assert TurnPruneSummaryCompaction._extract_tool_use_ids(msg) == {"def"}

    def test_extract_tool_use_ids_call_id_preferred_over_id(self):
        """call_id should be preferred over id (id may be __fake_id__)."""
        msg = {"type": "function_call", "call_id": "real_id", "id": "__fake_id__"}
        assert TurnPruneSummaryCompaction._extract_tool_use_ids(msg) == {"real_id"}

    def test_extract_tool_use_ids_empty(self):
        msg = {"content": "plain text"}
        assert TurnPruneSummaryCompaction._extract_tool_use_ids(msg) == set()

    def test_extract_tool_use_ids_object(self):
        """Test with object-style message (e.g. ResponseFunctionToolCall)."""
        obj = MagicMock()
        obj.type = "function_call"
        obj.call_id = "obj_call_id"
        obj.id = "__fake_id__"
        assert TurnPruneSummaryCompaction._extract_tool_use_ids(obj) == {"obj_call_id"}

    def test_extract_tool_result_ids_dict(self):
        """Only call_id should be extracted as the pairing key."""
        msg = {"call_id": "id1", "id": "item_own_id"}
        ids = TurnPruneSummaryCompaction._extract_tool_result_ids(msg)
        assert ids == {"id1"}

    def test_extract_tool_result_ids_object(self):
        """Only call_id should be extracted, id is the item's own identifier."""
        obj = MagicMock()
        obj.call_id = "c1"
        obj.id = "i1"
        ids = TurnPruneSummaryCompaction._extract_tool_result_ids(obj)
        assert ids == {"c1"}

    def test_extract_tool_result_ids_ignores_item_id(self):
        """The id field on FunctionCallOutput is NOT for pairing."""
        msg = {"type": "function_call_output", "call_id": "toolu_xxx",
               "output": "ok", "id": "item_abc"}
        ids = TurnPruneSummaryCompaction._extract_tool_result_ids(msg)
        assert "item_abc" not in ids
        assert ids == {"toolu_xxx"}


# ── Test: _get_tool_result_text / _set_tool_result_text ─────────────

class TestToolResultTextHelpers:
    def test_get_text_from_output(self):
        assert TurnPruneSummaryCompaction._get_tool_result_text({"output": "hi"}) == "hi"

    def test_get_text_from_content(self):
        assert TurnPruneSummaryCompaction._get_tool_result_text({"content": "hey"}) == "hey"

    def test_get_text_from_object(self):
        obj = MagicMock()
        obj.output = "obj_out"
        assert TurnPruneSummaryCompaction._get_tool_result_text(obj) == "obj_out"

    def test_get_text_none(self):
        assert TurnPruneSummaryCompaction._get_tool_result_text({}) is None

    def test_set_text_dict_output(self):
        msg = {"output": "old"}
        new = TurnPruneSummaryCompaction._set_tool_result_text(msg, "new")
        assert new["output"] == "new"
        assert msg["output"] == "old"  # original unchanged

    def test_set_text_dict_content(self):
        msg = {"content": "old"}
        new = TurnPruneSummaryCompaction._set_tool_result_text(msg, "new")
        assert new["content"] == "new"

    def test_set_text_object(self):
        obj = MagicMock()
        result = TurnPruneSummaryCompaction._set_tool_result_text(obj, "new")
        assert result.output == "new"


# ── Test: Layer 3 helpers ────────────────────────────────────────────

class TestSplitRecentTurns:
    """Tests for boundary-based _split_recent_turns.

    Boundaries are user messages and positions right after function_call_output.
    DEFAULT_RECENT_BOUNDARIES_PRESERVE = 6, so we keep 6 segment-start positions.
    """

    def test_few_boundaries_returns_all_as_recent(self, strategy):
        """When boundaries <= DEFAULT_RECENT_BOUNDARIES_PRESERVE, all are recent."""
        # 3 user msgs + 2 tool_outputs = 5 boundaries (user@0, tool_out+1@2, user@3, tool_out+1@5, user@6)
        # Wait, let's just use a small set: 3 user msgs = 3 boundaries < 6
        msgs = [_user_msg("a"), _assistant_msg(), _user_msg("b"), _user_msg("c")]
        recent, to_summarize = strategy._split_recent_turns(msgs)
        assert len(recent) == 4
        assert len(to_summarize) == 0

    def test_splits_at_boundary_with_many_tool_pairs(self, strategy):
        """Verify split works within a single user turn that has many tool calls.

        This is the key edge case the new logic fixes: a single user turn with
        10+ tool calls can now be split mid-turn at tool_output boundaries.
        """
        # Build: 1 user + 10 tool pairs = 11 boundaries (1 user + 10 after-tool-output)
        msgs = [_user_msg("task")]
        for i in range(10):
            tid = f"t{i}"
            msgs.extend([
                _reasoning_msg(),
                _output_msg(f"step {i}"),
                _assistant_msg([tid]),
                _tool_result_msg(tid, f"result {i}"),
            ])

        recent, to_summarize = strategy._split_recent_turns(msgs)

        # 11 boundaries total, preserve 6 => split at boundary[5] (0-indexed)
        # Boundaries: user@0, after_tool@5, after_tool@9, ..., after_tool@37, after_tool@41
        # The 6th from end should leave some in to_summarize
        assert len(to_summarize) > 0
        assert len(recent) > 0
        # to_summarize should end with a tool_result (complete pair)
        assert to_summarize[-1]["_type"] == "tool_result"

    def test_splits_at_user_boundary(self, strategy):
        """With enough user turns + tool pairs, split can land on a user boundary."""
        # 8 user turns with tool pairs each = 16 boundaries (8 user + 8 after-tool)
        msgs = []
        for i in range(8):
            tid = f"t{i}"
            msgs.extend([
                _user_msg(f"turn{i}"),
                _assistant_msg([tid]),
                _tool_result_msg(tid),
            ])

        recent, to_summarize = strategy._split_recent_turns(msgs)
        # 16 boundaries, preserve 6 => split at boundary[10] from start
        assert len(to_summarize) > 0
        assert len(recent) > 0

    def test_to_summarize_ends_cleanly(self, strategy):
        """to_summarize should always end with a tool_result or user msg
        (never mid-way through a reasoning/function_call group)."""
        msgs = [_user_msg("task")]
        for i in range(10):
            tid = f"t{i}"
            msgs.extend([
                _reasoning_msg(),
                _output_msg(f"step {i}"),
                _assistant_msg([tid]),
                _tool_result_msg(tid),
            ])

        recent, to_summarize = strategy._split_recent_turns(msgs)
        if to_summarize:
            last = to_summarize[-1]
            # Must end with tool_result or user (not reasoning/assistant)
            assert last.get("_type") in ("tool_result", "user")

    def test_recent_starts_after_tool_output_not_mid_group(self, strategy):
        """Recent section should start right after a tool_output boundary,
        which means it starts with reasoning/output_msg (the new response group)."""
        msgs = [_user_msg("task")]
        for i in range(10):
            tid = f"t{i}"
            msgs.extend([
                _reasoning_msg(),
                _output_msg(f"step {i}"),
                _assistant_msg([tid]),
                _tool_result_msg(tid),
            ])

        recent, to_summarize = strategy._split_recent_turns(msgs)
        if recent:
            first = recent[0]
            # Should start with reasoning (after tool_output) or user msg
            is_user = first.get("_type") == "user"
            is_reasoning = first.get("type") == "reasoning"
            assert is_user or is_reasoning

    def test_no_tool_calls_falls_back_to_user_boundaries(self, strategy):
        """When there are no tool calls, boundaries are only user messages.
        Behavior should be similar to old user-turn-based splitting."""
        # 8 user messages, no tool calls = 8 boundaries
        msgs = []
        for i in range(8):
            msgs.append(_user_msg(f"msg{i}"))
            msgs.append(_output_msg(f"reply{i}"))

        recent, to_summarize = strategy._split_recent_turns(msgs)
        # 8 boundaries (user msgs only), preserve 6 => split at boundary[2]
        assert len(to_summarize) > 0
        # recent should start at a user message
        assert recent[0].get("_type") == "user"

    def test_mixed_user_and_tool_boundaries(self, strategy):
        """Mix of user turns and tool call pairs produces correct boundaries."""
        # Carefully constructed: 15 items (indices 0-14)
        # Boundaries (set of segment-start indices):
        #   user@0, after_tool_result@3 (idx2+1), after_tool_result@5 (idx4+1=5, dedup with user@5),
        #   user@5, after_tool_result@8 (idx7+1=8, dedup with user@8),
        #   user@8, after_tool_result@11 (idx10+1), after_tool_result@13 (idx12+1)
        #   tool_result@14 has no i+1 (out of bounds)
        # Unique boundaries: {0, 3, 5, 8, 11, 13} = 6 boundaries = DEFAULT_RECENT_BOUNDARIES_PRESERVE
        # So with exactly 6, nothing to summarize. Add an extra turn to exceed 6.
        msgs = [
            _user_msg("0"),
            _assistant_msg(["a0"]), _tool_result_msg("a0"),
            # Turn 1: user + 2 tool pairs
            _user_msg("1"),
            _assistant_msg(["a1"]), _tool_result_msg("a1"),
            _assistant_msg(["a2"]), _tool_result_msg("a2"),
            # Turn 2: user + 1 tool pair
            _user_msg("2"),
            _assistant_msg(["b1"]), _tool_result_msg("b1"),
            # Turn 3: user + 3 tool pairs
            _user_msg("3"),
            _assistant_msg(["c1"]), _tool_result_msg("c1"),
            _assistant_msg(["c2"]), _tool_result_msg("c2"),
            _assistant_msg(["c3"]), _tool_result_msg("c3"),
            _user_msg("4"),  # trailing user to ensure last tool_result creates boundary
        ]
        recent, to_summarize = strategy._split_recent_turns(msgs)
        # Now we have >6 boundaries, so split should happen
        assert len(to_summarize) > 0
        assert len(recent) > 0

    def test_last_tool_output_is_last_message_no_boundary_after(self, strategy):
        """If the last message is a tool_output, no boundary is added after it
        (since i+1 would be out of bounds)."""
        msgs = [_user_msg("task")]
        for i in range(8):
            tid = f"t{i}"
            msgs.extend([_assistant_msg([tid]), _tool_result_msg(tid)])
        # Last msg is tool_result. Boundaries: user@0, after_tool@3, ..., after_tool@15
        # (last tool_result at index 16 has no i+1, so 8 boundaries from after_tool + 1 user = 8 total... wait)
        # Actually: user@0, then tool_results at 2,4,6,8,10,12,14,16
        # after_tool boundaries: 3,5,7,9,11,13,15 (7 of them, since last at 16 has no i+1)
        # Total = 1 + 7 = 8 boundaries > 6, so split happens
        recent, to_summarize = strategy._split_recent_turns(msgs)
        assert len(to_summarize) > 0


class TestExtractToolFailures:
    def test_detects_error_in_output(self, strategy):
        msgs = [
            _user_msg("go"),
            _assistant_msg(["tid1"]),
            _tool_result_msg("tid1", "Error: command failed with exit code 1"),
        ]
        failures = strategy._extract_tool_failures(msgs)
        assert len(failures) == 1
        assert failures[0]["call_id"] == "tid1"
        assert failures[0]["tool_name"] == "test"

    def test_no_failures(self, strategy):
        msgs = [
            _user_msg("go"),
            _assistant_msg(["tid1"]),
            _tool_result_msg("tid1", "success: all tests passed"),
        ]
        failures = strategy._extract_tool_failures(msgs)
        assert len(failures) == 0


class TestGenerateStatsDescription:
    def test_stats_fallback(self, strategy):
        msgs = [
            _user_msg("hi"),
            _assistant_msg(["t1"]),
            _tool_result_msg("t1"),
            _user_msg("bye"),
        ]
        stats = strategy._generate_stats_description(msgs)
        assert "<context>" in stats
        assert "2 user messages" in stats
        assert "1 tool calls" in stats


class TestAssembleCompacted:
    def test_with_user_first_in_recent(self, strategy):
        """When recent starts with user msg, ack is inserted."""
        recent = [_user_msg("recent")]
        result = strategy._assemble_compacted("<context>summary</context>", recent)
        # summary_msg + ack_msg + recent_user
        assert len(result) == 3
        assert result[0]["role"] == "user"  # summary
        assert result[1]["role"] == "assistant"  # ack
        assert result[2]["content"] == "recent"

    def test_with_assistant_first_in_recent(self, strategy):
        """When recent starts with assistant msg, no ack needed."""
        recent = [_assistant_msg(["t1"])]
        result = strategy._assemble_compacted("<context>summary</context>", recent)
        # summary_msg + assistant (no ack)
        assert len(result) == 2

    def test_empty_recent(self, strategy):
        result = strategy._assemble_compacted("<context>summary</context>", [])
        assert len(result) == 1  # just summary


class TestEstimateTokens:
    def test_basic_estimate(self, strategy):
        msgs = [_user_msg("hello world")]
        tokens = strategy._estimate_tokens(msgs)
        assert tokens > 0

    def test_more_messages_more_tokens(self, strategy):
        msgs1 = [_user_msg("a")]
        msgs2 = [_user_msg("a"), _user_msg("b"), _user_msg("c")]
        assert strategy._estimate_tokens(msgs2) > strategy._estimate_tokens(msgs1)


# ── Test: _prune_to_budget ───────────────────────────────────────────

class TestPruneToBudget:
    """Comprehensive tests for _prune_to_budget binary-search pruning."""

    @staticmethod
    def _make_context(context_window: int):
        """Create a fake context with the given context_window."""
        ctx = MagicMock()
        ctx.model_run_config.context_window = context_window
        ctx.model_run_config.model_name = "test-model"
        return ctx

    def test_no_user_messages_returns_empty(self, strategy):
        """When there are no user messages, return empty list."""
        msgs = [_assistant_msg(["id1"]), _tool_result_msg("id1")]
        ctx = self._make_context(100_000)
        result = strategy._prune_to_budget(msgs, ctx)
        assert result == []

    def test_empty_messages_returns_empty(self, strategy):
        """Empty input returns empty output."""
        ctx = self._make_context(100_000)
        result = strategy._prune_to_budget([], ctx)
        assert result == []

    def test_all_fit_within_budget_keeps_all(self, strategy):
        """When total tokens fit within budget, keep everything from first user turn."""
        msgs = [
            _user_msg("turn1"),
            _assistant_msg(["t1"]),
            _tool_result_msg("t1"),
            _user_msg("turn2"),
        ]
        # Use a huge context window so everything fits
        ctx = self._make_context(10_000_000)
        with patch.object(strategy, "_count_tokens", return_value=100):
            result = strategy._prune_to_budget(msgs, ctx)
        # Should keep from first user turn (index 0)
        assert len(result) == 4
        assert result[0]["content"] == "turn1"

    def test_nothing_fits_keeps_only_last_user_turn(self, strategy):
        """When even a single early turn exceeds budget, keep only the last user turn."""
        msgs = [
            _user_msg("turn1"),
            _assistant_msg(["t1"]),
            _tool_result_msg("t1"),
            _user_msg("turn2"),
            _assistant_msg(["t2"]),
            _tool_result_msg("t2"),
            _user_msg("turn3"),
        ]
        ctx = self._make_context(1000)
        # Only the last user turn (just "turn3") fits
        def fake_count(candidate, _ctx):
            if len(candidate) == 1:  # just the last user msg
                return 500
            return 99999  # anything more exceeds budget
        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        # budget = 1000 * 0.75 = 750, only last turn fits
        assert result[0]["content"] == "turn3"

    def test_binary_search_finds_optimal_boundary(self, strategy):
        """Binary search should find the earliest boundary that fits."""
        # 5 user turns with assistant msgs in between
        msgs = [
            _user_msg("t1"), _assistant_msg(["a1"]), _tool_result_msg("a1"),
            _user_msg("t2"), _assistant_msg(["a2"]), _tool_result_msg("a2"),
            _user_msg("t3"), _assistant_msg(["a3"]), _tool_result_msg("a3"),
            _user_msg("t4"), _assistant_msg(["a4"]), _tool_result_msg("a4"),
            _user_msg("t5"),
        ]
        ctx = self._make_context(1000)  # budget = 750

        # Simulate: turns 1-5 = 1000 tokens, turns 2-5 = 800, turns 3-5 = 600
        # So boundary at t3 (index 6) should be chosen (600 <= 750)
        user_indices = [0, 3, 6, 9, 12]  # positions of user msgs

        def fake_count(candidate, _ctx):
            length = len(msgs) - (len(msgs) - len(candidate))
            start_idx = len(msgs) - len(candidate)
            if start_idx == user_indices[0]:  # from t1
                return 1000
            elif start_idx == user_indices[1]:  # from t2
                return 800
            elif start_idx == user_indices[2]:  # from t3
                return 600
            elif start_idx == user_indices[3]:  # from t4
                return 400
            elif start_idx == user_indices[4]:  # from t5
                return 100
            return 9999

        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        # Should start from t3
        assert result[0]["content"] == "t3"

    def test_repairs_orphan_tool_pairs_after_pruning(self, strategy):
        """After pruning, orphan tool results at the boundary should be repaired."""
        # Scenario: pruning cuts in the middle of a tool call/result pair
        # t1 has a function_call, t2 starts but the tool_result for t1's call
        # is at the beginning of the kept portion
        msgs = [
            _user_msg("t1"),
            _assistant_msg(["fc_old"]),
            _tool_result_msg("fc_old"),
            _user_msg("t2"),
            _assistant_msg(["fc_new"]),
            _tool_result_msg("fc_new"),
        ]
        ctx = self._make_context(1000)

        # Force pruning to start from t2 (index 3)
        def fake_count(candidate, _ctx):
            if len(candidate) <= 3:  # t2 onwards
                return 500
            return 9999
        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        # t2 with its matched pair should be kept
        assert any(m.get("content") == "t2" for m in result)
        # The matched pair fc_new should be intact
        assert any(m.get("call_id") == "fc_new" and m.get("type") == "function_call" for m in result)
        assert any(m.get("call_id") == "fc_new" and m.get("_type") == "tool_result" for m in result)

    def test_orphan_tool_result_at_boundary_removed(self, strategy):
        """If pruning leaves an orphan tool_result at the start, it gets removed."""
        # assistant msg with fc_id1 is before the cut point,
        # but its tool_result is after the cut point
        msgs = [
            _user_msg("t1"),
            _assistant_msg(["fc_orphan"]),
            _user_msg("t2"),
            _tool_result_msg("fc_orphan"),  # orphan: its function_call is in t1
            _user_msg("t3"),
        ]
        ctx = self._make_context(1000)

        # Force prune to start from t2
        def fake_count(candidate, _ctx):
            if len(candidate) <= 3:
                return 500
            return 9999
        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        # Orphan tool_result should be removed by _repair_tool_pairs
        orphan_results = [m for m in result if m.get("call_id") == "fc_orphan" and m.get("_type") == "tool_result"]
        assert len(orphan_results) == 0

    def test_single_user_turn_always_kept(self, strategy):
        """With only one user turn, it should always be kept."""
        msgs = [_user_msg("only_turn"), _assistant_msg(["t1"]), _tool_result_msg("t1")]
        ctx = self._make_context(1000)
        with patch.object(strategy, "_count_tokens", return_value=9999):
            result = strategy._prune_to_budget(msgs, ctx)
        # Even if it exceeds budget, the last (only) user turn is the best we can do
        assert result[0]["content"] == "only_turn"

    def test_budget_calculation_uses_summary_budget_ratio(self, strategy):
        """Verify budget = context_window * SUMMARY_BUDGET_RATIO."""
        msgs = [_user_msg("t1"), _user_msg("t2")]
        ctx = self._make_context(10000)  # budget = 10000 * 0.75 = 7500

        recorded_budgets = []

        original_count = strategy._count_tokens
        def spy_count(candidate, _ctx):
            return 100  # everything fits

        with patch.object(strategy, "_count_tokens", side_effect=spy_count):
            result = strategy._prune_to_budget(msgs, ctx)
        # All should be kept since everything fits
        assert result[0]["content"] == "t1"

    def test_exact_budget_boundary(self, strategy):
        """Messages exactly at budget should be kept (<=)."""
        msgs = [
            _user_msg("t1"), _assistant_msg(["a1"]), _tool_result_msg("a1"),
            _user_msg("t2"),
        ]
        ctx = self._make_context(1000)  # budget = 750

        def fake_count(candidate, _ctx):
            if len(candidate) == 4:  # all msgs
                return 750  # exactly at budget
            return 200
        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        # Exactly at budget, should keep all from t1
        assert result[0]["content"] == "t1"
        assert len(result) == 4

    def test_just_over_budget_drops_first_turn(self, strategy):
        """Messages just over budget should drop earliest turn."""
        msgs = [
            _user_msg("t1"), _assistant_msg(["a1"]), _tool_result_msg("a1"),
            _user_msg("t2"), _assistant_msg(["a2"]), _tool_result_msg("a2"),
        ]
        ctx = self._make_context(1000)  # budget = 750

        def fake_count(candidate, _ctx):
            if len(candidate) == 6:  # from t1
                return 751  # just over budget
            if len(candidate) == 3:  # from t2
                return 400
            return 100
        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        assert result[0]["content"] == "t2"

    def test_many_turns_logarithmic_calls(self, strategy):
        """Verify binary search makes O(log N) token count calls, not O(N)."""
        n_turns = 64
        msgs = []
        for i in range(n_turns):
            msgs.append(_user_msg(f"turn_{i}"))

        ctx = self._make_context(1000)
        call_count = 0

        def fake_count(candidate, _ctx):
            nonlocal call_count
            call_count += 1
            # Keep last 32 turns
            if len(candidate) <= 32:
                return 500
            return 9999
        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            strategy._prune_to_budget(msgs, ctx)
        # Binary search on 64 items should need at most ~7 calls (log2(64) + 1)
        assert call_count <= 10, f"Expected O(log N) calls, got {call_count}"

    def test_preserves_assistant_and_tool_msgs_after_user_boundary(self, strategy):
        """Messages between user turns (assistant, tool_result) should be preserved."""
        msgs = [
            _user_msg("t1"),
            _assistant_msg(["a1"]),
            _tool_result_msg("a1"),
            _user_msg("t2"),
            _assistant_msg(["a2"]),
            _tool_result_msg("a2"),
            _user_msg("t3"),
            _assistant_msg(["a3"]),
            _tool_result_msg("a3"),
        ]
        ctx = self._make_context(1000)

        # Force prune to start from t2
        def fake_count(candidate, _ctx):
            if len(candidate) <= 6:  # from t2 onwards
                return 500
            return 9999
        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        assert result[0]["content"] == "t2"
        # Should have t2, a2, tool_a2, t3, a3, tool_a3 = 6 messages
        assert len(result) == 6

    def test_first_message_is_user_after_repair(self, strategy):
        """After pruning and repair, the first message should always be a user message."""
        msgs = [
            _user_msg("t1"),
            _assistant_msg(["orphan_fc"]),  # will become orphan after prune
            _user_msg("t2"),
            _tool_result_msg("orphan_fc"),  # orphan result
            _user_msg("t3"),
        ]
        ctx = self._make_context(1000)

        def fake_count(candidate, _ctx):
            if len(candidate) <= 3:
                return 500
            return 9999
        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        # First message must be user after repair
        assert result[0].get("_type") == "user" or result[0].get("role") == "user"

    def test_non_user_prefix_dropped(self, strategy):
        """Messages before the first user message are silently dropped."""
        msgs = [
            _assistant_msg(["pre_fc"]),      # non-user prefix
            _tool_result_msg("pre_fc"),       # non-user prefix
            _user_msg("t1"),
            _assistant_msg(["a1"]),
            _tool_result_msg("a1"),
        ]
        ctx = self._make_context(10_000_000)
        with patch.object(strategy, "_count_tokens", return_value=100):
            result = strategy._prune_to_budget(msgs, ctx)
        # Prefix before first user msg is dropped (cut at user_indices[0]=2)
        assert result[0]["content"] == "t1"
        # pre_fc pair should not be in result
        assert not any(m.get("call_id") == "pre_fc" for m in result)

    def test_two_turns_first_fits(self, strategy):
        """Minimal binary search: 2 user turns, first boundary fits."""
        msgs = [
            _user_msg("t1"),
            _assistant_msg(["a1"]),
            _tool_result_msg("a1"),
            _user_msg("t2"),
        ]
        ctx = self._make_context(1000)

        def fake_count(candidate, _ctx):
            return 500  # everything fits
        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        assert result[0]["content"] == "t1"
        assert len(result) == 4

    def test_two_turns_only_second_fits(self, strategy):
        """Minimal binary search: 2 user turns, only second fits."""
        msgs = [
            _user_msg("t1"),
            _assistant_msg(["a1"]),
            _tool_result_msg("a1"),
            _user_msg("t2"),
        ]
        ctx = self._make_context(1000)  # budget = 750

        def fake_count(candidate, _ctx):
            if len(candidate) == 4:
                return 800  # from t1: exceeds
            return 200  # from t2: fits
        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        assert result[0]["content"] == "t2"
        assert len(result) == 1

    def test_all_turns_exceed_budget_returns_last_turn(self, strategy):
        """When even the last user turn exceeds budget, still return it (best effort)."""
        msgs = [
            _user_msg("t1"),
            _user_msg("t2"),
            _user_msg("t3"),
        ]
        ctx = self._make_context(1000)  # budget = 750

        # Every candidate exceeds budget
        with patch.object(strategy, "_count_tokens", return_value=9999):
            result = strategy._prune_to_budget(msgs, ctx)
        # best = hi = last user turn, returned even though it exceeds
        assert result[0]["content"] == "t3"
        assert len(result) == 1

    def test_consecutive_user_messages_no_assistant(self, strategy):
        """Consecutive user messages without interleaved assistant msgs."""
        msgs = [
            _user_msg("t1"),
            _user_msg("t2"),
            _user_msg("t3"),
            _user_msg("t4"),
        ]
        ctx = self._make_context(1000)

        # From t3 onwards fits
        def fake_count(candidate, _ctx):
            if len(candidate) <= 2:
                return 500
            return 9999
        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        assert result[0]["content"] == "t3"
        assert len(result) == 2

    def test_non_monotonic_token_counts_binary_search_correctness(self, strategy):
        """Binary search assumes monotonicity (more msgs = more tokens).
        Verify it works correctly under that assumption."""
        # 4 user turns, tokens strictly decrease as we drop older turns
        msgs = [
            _user_msg("t1"), _assistant_msg(["a1"]), _tool_result_msg("a1"),
            _user_msg("t2"), _assistant_msg(["a2"]), _tool_result_msg("a2"),
            _user_msg("t3"),
            _user_msg("t4"),
        ]
        ctx = self._make_context(1000)  # budget = 750
        user_indices = [0, 3, 6, 7]

        def fake_count(candidate, _ctx):
            start = len(msgs) - len(candidate)
            # Monotonically decreasing: 900, 700, 400, 200
            token_map = {0: 900, 3: 700, 6: 400, 7: 200}
            return token_map.get(start, 9999)

        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        # t2 onwards = 700 tokens <= 750, should be chosen (earliest fit)
        assert result[0]["content"] == "t2"

    def test_large_gap_between_user_messages(self, strategy):
        """User messages separated by many assistant/tool msgs."""
        msgs = [
            _user_msg("t1"),
            _assistant_msg(["a1"]), _tool_result_msg("a1"),
            _assistant_msg(["a2"]), _tool_result_msg("a2"),
            _assistant_msg(["a3"]), _tool_result_msg("a3"),
            _user_msg("t2"),
        ]
        ctx = self._make_context(1000)

        def fake_count(candidate, _ctx):
            if len(candidate) == 8:  # from t1
                return 900
            return 300  # from t2
        with patch.object(strategy, "_count_tokens", side_effect=fake_count):
            result = strategy._prune_to_budget(msgs, ctx)
        assert result[0]["content"] == "t2"
        # Only t2 remains (no assistant/tool after it)
        assert len(result) == 1


class TestCompactionResult:
    def test_default_values(self):
        result = CompactionResult(messages=[])
        assert result.messages == []
        assert result.summary is None
        assert result.compacted is False

    def test_with_values(self):
        result = CompactionResult(
            messages=[{"role": "user"}],
            summary="test summary",
            compacted=True,
        )
        assert result.compacted is True
        assert result.summary == "test summary"

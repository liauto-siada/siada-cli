"""Offline coverage for reasoning snapshots, completion, and display limits."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from siada.tools.agent.sub_agent_notifier import MAX_ENTRY_TEXT_LENGTH
from siada.tools.agent.sub_agent_reasoning_stream import SubAgentReasoningStream


def event(event_type: str, **kwargs):
    return SimpleNamespace(type=f"response.{event_type}", **kwargs)


@pytest.mark.parametrize("family", ["reasoning_summary_text", "reasoning_text"])
def test_deltas_are_visible_before_completion_and_keep_identity(family):
    push, persist = Mock(), Mock()
    stream = SubAgentReasoningStream(push, persist)
    stream.handle_raw(event(f"{family}.delta", item_id="r1", delta="检查"))
    assert push.call_args.args == ("检查",)
    assert push.call_args.kwargs["is_complete"] is False
    entry_id = push.call_args.kwargs["entry_id"]
    persist.assert_not_called()

    stream.handle_raw(event(f"{family}.delta", item_id="r1", delta="调用链"))
    assert push.call_args.args == ("检查调用链",)
    assert push.call_args.kwargs["entry_id"] == entry_id
    stream.handle_raw(event(f"{family}.done", item_id="r1", text="检查调用链"))
    assert push.call_args.kwargs == {"entry_id": entry_id, "is_complete": True}
    persist.assert_called_once_with("检查调用链")

    stream.complete_item(SimpleNamespace(id="r1", summary=[SimpleNamespace(text="检查调用链")]))
    stream.finish()
    assert push.call_count == 3
    assert persist.call_count == 1


def test_completed_reasoning_without_deltas_is_shown_once():
    push, persist = Mock(), Mock()
    stream = SubAgentReasoningStream(push, persist)
    item = SimpleNamespace(
        id="r1", type="reasoning",
        summary=[SimpleNamespace(text="summary")],
        content=[SimpleNamespace(text="reasoning")],
    )
    stream.handle_raw(event("output_item.done", item=item))
    stream.complete_item(item)
    assert push.call_args.args == ("summary\nreasoning",)
    assert push.call_args.kwargs["is_complete"] is True
    persist.assert_called_once_with("summary\nreasoning")
    assert push.call_count == 1


def test_multiple_parts_and_items_keep_separate_entries():
    push = Mock()
    stream = SubAgentReasoningStream(push, Mock())
    for item_id, index in [("r1", 0), ("r1", 1), ("r2", 0)]:
        stream.handle_raw(event(
            "reasoning_summary_text.delta", item_id=item_id, summary_index=index, delta="text",
        ))
    assert len({call.kwargs["entry_id"] for call in push.call_args_list}) == 3
    stream.complete_item(SimpleNamespace(id="r1"))
    assert sum(call.kwargs["is_complete"] for call in push.call_args_list) == 2
    stream.finish()
    assert sum(call.kwargs["is_complete"] for call in push.call_args_list) == 3


def test_long_reasoning_keeps_latest_progress_with_bounded_snapshots():
    push = Mock()
    stream = SubAgentReasoningStream(push, Mock())
    stream.handle_raw(event("reasoning_text.delta", item_id="r1", delta="x" * 6000))
    stream.handle_raw(event("reasoning_text.delta", item_id="r1", delta="LATEST"))
    assert len(push.call_args.args[0]) == MAX_ENTRY_TEXT_LENGTH
    assert push.call_args.args[0].endswith("LATEST")
    stream.finish()
    assert push.call_args.args[0].endswith("LATEST")


def test_finish_closes_partial_reasoning_once_and_ignores_unrelated_events():
    push, persist = Mock(), Mock()
    stream = SubAgentReasoningStream(push, persist)
    stream.handle_raw(event("output_text.delta", item_id="m1", delta="answer"))
    stream.handle_raw(event("reasoning_text.delta", item_id="r1", delta="partial"))
    stream.finish()
    stream.finish()
    assert push.call_count == 2
    assert push.call_args.kwargs["is_complete"] is True
    persist.assert_called_once_with("partial")


def test_attempts_can_reuse_provider_item_ids():
    push = Mock()
    for _ in range(2):
        stream = SubAgentReasoningStream(push, Mock())
        stream.handle_raw(event("reasoning_text.delta", item_id="r1", delta="reasoning"))
        stream.finish()
    assert push.call_args_list[0].kwargs["entry_id"] != push.call_args_list[2].kwargs["entry_id"]


def test_model_turns_can_reuse_provider_item_ids_within_one_attempt():
    push = Mock()
    stream = SubAgentReasoningStream(push, Mock())
    for text in ("turn one", "turn two"):
        stream.handle_raw(event("created"))
        stream.handle_raw(event("reasoning_text.delta", item_id="r1", delta=text))
        stream.handle_raw(event("completed"))
    assert push.call_args_list[0].args == ("turn one",)
    assert push.call_args_list[2].args == ("turn two",)
    assert push.call_args_list[0].kwargs["entry_id"] != push.call_args_list[2].kwargs["entry_id"]
from unittest.mock import MagicMock

from siada.services.goal.prompts import (
    append_goal_reminder_to_messages,
    build_goal_reminder_text,
    merge_goal_reminder_into_input,
)


def _make_goal(objective="Ship the feature"):
    goal = MagicMock()
    goal.objective = objective
    return goal


# ---------------------------------------------------------------------------
# merge_goal_reminder_into_input
# ---------------------------------------------------------------------------

def test_merge_into_plain_string_input():
    """A plain-string turn input is wrapped into a single user message with
    two input_text content parts: the real text, then the hidden reminder."""
    goal = _make_goal()
    result = merge_goal_reminder_into_input("hello there", goal)

    assert isinstance(result, list)
    assert len(result) == 1
    msg = result[0]
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    assert len(msg["content"]) == 2
    assert msg["content"][0] == {"type": "input_text", "text": "hello there"}
    assert msg["content"][1]["type"] == "input_text"
    assert "<system-reminder>" in msg["content"][1]["text"]
    assert "Ship the feature" in msg["content"][1]["text"]


def test_merge_into_list_input_with_string_content():
    """When the turn input is already a list (e.g. built by an earlier
    step) and the last user item has plain-string content, the reminder is
    merged as an extra content part on that SAME item -- no new item/turn
    boundary is introduced."""
    goal = _make_goal()
    user_input = [{"role": "user", "content": "hello there"}]
    result = merge_goal_reminder_into_input(user_input, goal)

    assert len(result) == 1
    msg = result[0]
    assert msg["content"] == [
        {"type": "input_text", "text": "hello there"},
        {"type": "input_text", "text": result[0]["content"][1]["text"]},
    ]
    assert "<system-reminder>" in msg["content"][1]["text"]
    # Original input list must not be mutated.
    assert user_input[0]["content"] == "hello there"


def test_merge_into_multimodal_input_appends_content_part():
    """Multimodal input (text + image parts) keeps its existing parts and
    simply gains one more input_text part for the reminder."""
    goal = _make_goal()
    user_input = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "look at this"},
                {"type": "input_image", "image_url": "data:image/png;base64,xxx"},
            ],
        }
    ]
    result = merge_goal_reminder_into_input(user_input, goal)

    content = result[0]["content"]
    assert len(content) == 3
    assert content[0] == {"type": "input_text", "text": "look at this"}
    assert content[1]["type"] == "input_image"
    assert content[2]["type"] == "input_text"
    assert "<system-reminder>" in content[2]["text"]


def test_merge_targets_last_user_item_when_history_present():
    """When the input list carries prior history (e.g. session replay) plus
    a new user turn, the reminder is merged into the LAST user-role item,
    not an earlier one."""
    goal = _make_goal()
    user_input = [
        {"role": "user", "content": "old message"},
        {"type": "message", "role": "assistant", "content": "old reply"},
        {"role": "user", "content": "new message"},
    ]
    result = merge_goal_reminder_into_input(user_input, goal)

    assert result[0]["content"] == "old message"  # untouched
    assert result[2]["content"] == [
        {"type": "input_text", "text": "new message"},
        result[2]["content"][1],
    ]
    assert "<system-reminder>" in result[2]["content"][1]["text"]


def test_merge_fallback_appends_standalone_item_when_no_user_role_found():
    """Defensive fallback: if there is truly no user-role item in the list,
    append a standalone reminder message rather than silently dropping it."""
    goal = _make_goal()
    user_input = [{"type": "message", "role": "assistant", "content": "..."}]
    result = merge_goal_reminder_into_input(user_input, goal)

    assert len(result) == 2
    assert result[-1]["role"] == "user"
    assert "<system-reminder>" in result[-1]["content"][0]["text"]


def test_merge_leaves_unknown_input_shape_untouched():
    goal = _make_goal()
    result = merge_goal_reminder_into_input(12345, goal)  # not str, not list
    assert result == 12345


# ---------------------------------------------------------------------------
# build_goal_reminder_text(post_compaction=True)
# ---------------------------------------------------------------------------

def test_post_compaction_reminder_adds_compaction_note():
    """The compaction-adapted variant keeps the base reminder shape but adds
    a short note explaining why the reminder is repeating right after a
    compaction summary."""
    goal = _make_goal()
    normal = build_goal_reminder_text(goal)
    post_compaction = build_goal_reminder_text(goal, post_compaction=True)

    assert "compaction" not in normal.lower()
    assert "compaction" in post_compaction.lower()
    assert "<system-reminder>" in post_compaction
    assert "Ship the feature" in post_compaction


# ---------------------------------------------------------------------------
# build_goal_reminder_text(verifier_reason=..., verifier_next_action=..., ...)
# ---------------------------------------------------------------------------

def test_reminder_without_verifier_reason_has_no_verifier_result_section():
    """The ordinary once-per-activation / post-compaction reminder (no
    verifier round has happened yet) must not grow a "Completion verifier
    result" section -- there is nothing meaningful to report."""
    goal = _make_goal()
    text = build_goal_reminder_text(goal)

    assert "Completion verifier result" not in text


def test_reminder_with_verifier_feedback_renders_result_section():
    """After a failed verifier round, turn_hooks.maybe_run_goal_verifier now
    builds its forced-continuation feedback through this function (see
    replacement of the old GOAL_FEEDBACK_TEMPLATE one-liner). The rendered
    text must carry: the next action folded onto the opening sentence, and a
    "Completion verifier result" block with the full reason/next action/
    elapsed time. Token usage/budget are deliberately NOT reported -- the
    underlying session-usage figures aren't reliable enough to show the
    model as fact."""
    goal = _make_goal("还是不行 一直不好使，仔细debug一下")
    text = build_goal_reminder_text(
        goal,
        verifier_reason="目标要求定位绿条不生效根因、修复...",
        verifier_next_action="在 iTerm2 重跑 siada-cli 并确认绿条位置",
        elapsed_seconds=2983,
    )

    assert "<system-reminder>" in text
    assert "还是不行 一直不好使，仔细debug一下" in text
    # The next action is echoed right onto the opening sentence...
    assert (
        "Continue working toward the active session goal. "
        "在 iTerm2 重跑 siada-cli 并确认绿条位置" in text
    )
    # ...and again inside the full verifier-result block.
    assert "Completion verifier result:" in text
    assert "Reason: 目标要求定位绿条不生效根因、修复..." in text
    assert "Next action: 在 iTerm2 重跑 siada-cli 并确认绿条位置" in text
    assert "Time spent pursuing goal so far: 2983 seconds" in text
    assert "Tokens used" not in text
    assert "Token budget" not in text


def test_reminder_with_verifier_feedback_and_no_next_action():
    """When the verifier round had no useful next action, the opening
    sentence must stay unmodified (no trailing space/empty appendage)."""
    goal = _make_goal()
    text = build_goal_reminder_text(
        goal,
        verifier_reason="not done yet",
        verifier_next_action="",
        elapsed_seconds=10,
    )

    assert "Time spent pursuing goal so far: 10 seconds" in text
    assert "Next action: (none generated)" in text
    # No next action this round -- opening sentence must stay unmodified.
    assert text.split("\n", 1)[0] == "<system-reminder>"
    assert "Continue working toward the active session goal.\n" in text


# ---------------------------------------------------------------------------
# append_goal_reminder_to_messages
# ---------------------------------------------------------------------------


def test_append_after_compaction_merges_into_trailing_user_message():
    """The common case: compaction ran mid-turn, so the compacted history's
    last item is the current turn's (already-typed) user message -- the
    reminder should land there as an extra content part, not a new item."""
    goal = _make_goal()
    compacted = [
        {"role": "user", "content": "<summary of older turns>"},
        {"type": "message", "role": "assistant", "content": "Got it. Thanks for the additional context!"},
        {"role": "user", "content": "please continue"},
    ]
    result = append_goal_reminder_to_messages(compacted, goal)

    assert len(result) == 3
    assert result[2]["content"] == [
        {"type": "input_text", "text": "please continue"},
        result[2]["content"][1],
    ]
    assert "<system-reminder>" in result[2]["content"][1]["text"]
    assert "compaction" in result[2]["content"][1]["text"].lower()
    # Original list must not be mutated.
    assert compacted[2]["content"] == "please continue"


def test_append_after_manual_compact_merges_into_last_user_message():
    """Manual /compact's own compressed-history assembly always starts with
    a user-role summary message, so the reminder merges into that item as
    an extra content part rather than falling back to a standalone turn."""
    goal = _make_goal()
    compacted = [
        {"role": "user", "content": "<summary of older turns>"},
        {"type": "message", "role": "assistant", "content": "final reply"},
    ]
    result = append_goal_reminder_to_messages(compacted, goal)

    assert len(result) == 2
    assert result[0]["content"] == [
        {"type": "input_text", "text": "<summary of older turns>"},
        result[0]["content"][1],
    ]
    assert "<system-reminder>" in result[0]["content"][1]["text"]


def test_append_falls_back_to_standalone_message_when_no_user_item():
    """Defensive fallback: when the compacted history has no user-role item
    at all, the reminder must still reach the model as a standalone turn."""
    goal = _make_goal()
    compacted = [
        {"type": "message", "role": "assistant", "content": "final reply"},
    ]
    result = append_goal_reminder_to_messages(compacted, goal)

    assert len(result) == 2
    assert result[-1]["role"] == "user"
    assert result[-1]["content"] == [
        {"type": "input_text", "text": result[-1]["content"][0]["text"]}
    ]
    assert "<system-reminder>" in result[-1]["content"][0]["text"]

"""Tests for siada.support.message_classifier.format_native_items_for_display.

Focuses on the /resume + deferred-rendering UI history path: hidden
<system-reminder> blocks (merged into user input by
merge_goal_reminder_into_input) must never resurface as visible chat text
when a session is replayed.

Stripping is a WHOLE-match check (see _is_whole_system_reminder), not a
substring search-and-remove: only a content part / message that is
*entirely* a system-reminder block (starts with the opening tag, ends with
the matching closing tag) gets dropped. A reminder tag merely appearing
somewhere inside otherwise-real user text (e.g. a user quoting/pasting a
previously-rendered reminder back into a new message) must be left
untouched -- that's real conversation history, not a harness nudge, and
naively stripping substrings previously caused a worse bug: a combined
regex let a hyphen-opening tag pair with an underscore-closing tag (or
vice versa), leaving the rest of the outer block dangling in the render.
"""

from siada.support.message_classifier import format_native_items_for_display


def test_strips_system_reminder_from_list_content_user_message():
    """A goal-reminder-augmented user turn (list content with a separate
    input_text reminder part) should render with only the real text —
    the whole-reminder part itself must be dropped."""
    items = [
        {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": "please fix the bug"},
                {
                    "type": "input_text",
                    "text": (
                        "<system-reminder>\n"
                        "Continue working toward the active session goal.\n"
                        "<untrusted_objective>ship it</untrusted_objective>\n"
                        "</system-reminder>"
                    ),
                },
            ],
        }
    ]

    result = format_native_items_for_display(items)

    assert result == [{"role": "user", "content": "please fix the bug"}]
    assert "system-reminder" not in result[0]["content"]


def test_partial_reminder_embedded_in_real_text_is_left_untouched():
    """A reminder-looking tag that only appears *inside* otherwise-real
    text (not as a dedicated whole content part) must NOT be stripped —
    this is real conversation text (e.g. the user pasted it), not a
    harness nudge, since reminders are always injected as their own
    dedicated part/message, never spliced into existing text."""
    items = [
        {
            "type": "message",
            "role": "user",
            "content": (
                "hello there"
                "<system-reminder>Continue working toward the active session goal.</system-reminder>"
            ),
        }
    ]

    result = format_native_items_for_display(items)

    # Left completely unmodified — not a whole-message reminder.
    assert result == [
        {
            "role": "user",
            "content": (
                "hello there"
                "<system-reminder>Continue working toward the active session goal.</system-reminder>"
            ),
        }
    ]


def test_message_with_only_system_reminder_is_dropped():
    """If a turn's entire text content is the hidden reminder (no real
    text), it must not produce an empty/whitespace chat bubble."""
    items = [
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "<system-reminder>just a nudge</system-reminder>",
                },
            ],
        }
    ]

    assert format_native_items_for_display(items) == []


def test_message_with_only_underscore_system_reminder_is_dropped():
    """Legacy-format regression test: TodoReminderFilter used to inject its
    standalone reminder message with the underscore spelling
    "<system_reminder>" before being unified onto the same "<system-reminder>"
    (hyphen) tag as the goal reminder. Sessions persisted before that change
    still have the underscore spelling on disk, so it must keep being
    dropped on replay when it's the message's entire content."""
    items = [
        {
            "type": "message",
            "role": "user",
            "content": (
                "<system_reminder>\n"
                "The todo_write tool hasn't been used recently. If you're working on "
                "tasks that would benefit from tracking progress, consider using the "
                "todo_write tool to track progress.\n"
                "</system_reminder>"
            ),
        }
    ]

    assert format_native_items_for_display(items) == []


def test_normal_user_message_without_reminder_unaffected():
    items = [
        {"type": "message", "role": "user", "content": "hi there"},
    ]

    assert format_native_items_for_display(items) == [
        {"role": "user", "content": "hi there"}
    ]


def test_goal_command_with_pasted_reminder_keeps_real_part_drops_whole_reminder_part():
    """Real-world repro: a user quotes/pastes a previously leaked reminder
    bubble back into a new /goal command. The turn ends up with two
    content parts:
    - the real "/goal ..." text, which happens to *contain* a pasted
      underscore-tag reminder in the middle — not a whole reminder, so it
      must be preserved verbatim (it's real conversation text);
    - the freshly-injected hyphen-tag goal reminder, appended as its own
      dedicated content part by merge_goal_reminder_into_input, whose
      <untrusted_objective> happens to itself quote the same pasted
      underscore block — this whole part IS the reminder, so it must be
      dropped entirely.
    """
    pasted_part_text = (
        "/goal > <system_reminder>\n"
        "  The todo_write tool hasn't been used recently.\n"
        "  </system_reminder> 这个还是会渲染，是不是遗漏了某些消息格式？修复一下"
    )
    items = [
        {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": pasted_part_text},
                {
                    "type": "input_text",
                    "text": (
                        "<system-reminder>\n"
                        "Continue working toward the active session goal.\n"
                        "<untrusted_objective>\n"
                        "> <system_reminder>\n"
                        "  The todo_write tool hasn't been used recently.\n"
                        "  </system_reminder> 这个还是会渲染，是不是遗漏了某些消息格式？修复一下\n"
                        "</untrusted_objective>\n"
                        "Avoid repeating work that is already done.\n"
                        "</system-reminder>"
                    ),
                },
            ],
        }
    ]

    result = format_native_items_for_display(items)

    # The pasted-reminder part is real text and must survive verbatim;
    # the dedicated goal-reminder part must be gone entirely.
    assert result == [{"role": "user", "content": pasted_part_text}]
    content = result[0]["content"]
    assert "Avoid repeating work" not in content
    assert "untrusted_objective" not in content


def test_standalone_reminder_message_dropped_even_when_goal_command_is_a_separate_item():
    """First reported bug shape: TodoReminderFilter's standalone reminder
    (legacy underscore tag) is persisted as its own separate message item
    -- not spliced into the "/goal ..." command's own content. Each item
    is judged independently: the /goal command text is real and must be
    kept as-is, the standalone reminder-only item must be dropped."""
    items = [
        {"type": "message", "role": "user", "content": "/goal ship the feature"},
        {
            "type": "message",
            "role": "user",
            "content": (
                "<system_reminder>  The todo_write tool hasn't been used "
                "recently. Here are the existing contents of your todo list:  "
                "1. [completed] do the thing  </system_reminder>"
            ),
        },
    ]

    result = format_native_items_for_display(items)

    assert result == [{"role": "user", "content": "/goal ship the feature"}]

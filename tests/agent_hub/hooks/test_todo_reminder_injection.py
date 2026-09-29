"""Tests for TodoReminderProcessor.on_llm_start.

The reminder exists only to keep an EXISTING todo list up to date: once the
model has used todo_write, going too many assistant turns without another
todo_write earns a hidden reminder. A model that has not used todo_write yet
is never proactively nudged to start a list — not even while an active /goal
is set, and regardless of model family (the standing goal is carried by the
goal reminder merged into the turn input and enforced by its completion
verifier, so it needs no todo list of its own).
"""
from types import SimpleNamespace

import pytest

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.hooks.processors.todo_reminder_processor import (
    TodoReminderProcessor,
    TURNS_SINCE_WRITE_THRESHOLD,
    TURNS_BETWEEN_REMINDERS_THRESHOLD,
)


def _make_input_items(turns: int):
    """Build input_items yielding `turns` assistant turns since todo_write."""
    items = []
    for i in range(turns):
        items.append({"role": "user", "content": f"user {i}"})
        items.append({"type": "message", "role": "assistant", "content": []})
    return items


def _make_context(model_name, todos=None, goal=None):
    context = CodeAgentContext()
    context.session = SimpleNamespace(
        siada_config=SimpleNamespace(
            llm_config=SimpleNamespace(model_name=model_name)
        )
    )
    # Pre-seed the interval counter so both thresholds are already met.
    context.todo_turns_since_reminder = TURNS_BETWEEN_REMINDERS_THRESHOLD
    context.todos = todos or []
    context.goal = goal
    return context


def _active_goal():
    return SimpleNamespace(status="active", objective="Ship the feature")


def _make_agent():
    return SimpleNamespace(tools=[SimpleNamespace(name="todo_write")])


def _reminders_in(input_items):
    return [
        item
        for item in input_items
        if isinstance(item, dict) and "<system-reminder>" in str(item.get("content", ""))
    ]


async def _run(processor, context, input_items):
    await processor.on_llm_start(
        SimpleNamespace(context=context),
        agent=_make_agent(),
        system_prompt=None,
        input_items=input_items,
    )


# Models that track todos natively (Claude 5+, Kimi K3+, GLM-5.3+, GPT-6+,
# DeepSeek v4.1+) plus the older generations that rely on this processor for
# their todo hygiene: the no-nudge rule for an empty todo list holds for all
# of them.
EMPTY_TODOS_MODELS = [
    "claude-sonnet-5",
    "bailian-kimi-k3",
    "lpai-glm-5.3",
    "gpt-6-astra",
    "deepseek-v4_1-flash",
    "claude-sonnet-4",
    "gpt-5.6-luna",
    "kivy-deepseek-v4-flash-0731",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", EMPTY_TODOS_MODELS)
async def test_empty_todos_with_active_goal_is_never_nudged(model_name):
    """An active /goal alone must not ask the model to create a todo list."""
    processor = TodoReminderProcessor()
    context = _make_context(model_name, goal=_active_goal())
    input_items = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)

    await _run(processor, context, input_items)

    assert _reminders_in(input_items) == []
    assert context.pending_reminder_items == []
    # The skipped path leaves the reminder interval counter untouched.
    assert context.todo_turns_since_reminder == TURNS_BETWEEN_REMINDERS_THRESHOLD


@pytest.mark.asyncio
async def test_empty_todos_without_goal_is_a_noop():
    processor = TodoReminderProcessor()
    context = _make_context("claude-sonnet-4")
    input_items = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)

    await _run(processor, context, input_items)

    assert _reminders_in(input_items) == []
    assert context.pending_reminder_items == []


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["claude-sonnet-5", "claude-sonnet-4"])
async def test_existing_todos_get_the_update_reminder(model_name):
    """A model that already used todo_write keeps getting the update reminder."""
    processor = TodoReminderProcessor()
    todos = [SimpleNamespace(status="in_progress", content="task A")]
    context = _make_context(model_name, todos=todos)
    input_items = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)

    await _run(processor, context, input_items)

    reminders = _reminders_in(input_items)
    assert len(reminders) == 1
    assert "existing contents of your todo list" in reminders[0]["content"]
    assert "task A" in reminders[0]["content"]
    # Injected reminder is staged for durable persistence and the interval
    # counter is reset.
    assert len(context.pending_reminder_items) == 1
    assert context.todo_turns_since_reminder == 0


@pytest.mark.asyncio
async def test_existing_todos_with_active_goal_gets_no_goal_nudge_text():
    """With a todo list present the goal is never used to justify a reminder:
    the injected text is the plain todo-list reminder."""
    processor = TodoReminderProcessor()
    todos = [SimpleNamespace(status="pending", content="task B")]
    context = _make_context("claude-sonnet-4", todos=todos, goal=_active_goal())
    input_items = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)

    await _run(processor, context, input_items)

    reminders = _reminders_in(input_items)
    assert len(reminders) == 1
    assert "existing contents of your todo list" in reminders[0]["content"]
    assert "task B" in reminders[0]["content"]
    assert "Active goal objective" not in reminders[0]["content"]
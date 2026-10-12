"""Tests for TodoReminderProcessor.on_llm_start.

Once todo_write is registered and both thresholds are met (turns since the
last todo_write, turns since the previous reminder), the model gets one
hidden ``role=user`` reminder. Only GLM models get the proactive empty-list
reminder aligned with the public ZCode runtime; all models may get the
"keep it up to date" reminder for existing lists. The empty-list behaviour
has its own opt-out switch.
"""
from types import SimpleNamespace

import pytest

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.hooks.processors.todo_reminder_processor import (
    TODO_EMPTY_LIST_REMINDER_ENV,
    TodoReminderProcessor,
    TURNS_SINCE_WRITE_THRESHOLD,
    TURNS_BETWEEN_REMINDERS_THRESHOLD,
)


@pytest.fixture(autouse=True)
def _default_empty_list_switch(monkeypatch):
    """Every test starts from the default (enabled) switch state."""
    monkeypatch.delenv(TODO_EMPTY_LIST_REMINDER_ENV, raising=False)


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


def _make_agent(tool_names=("todo_write",)):
    return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in tool_names])


def _reminders_in(input_items):
    return [
        item
        for item in input_items
        if isinstance(item, dict) and "<system-reminder>" in str(item.get("content", ""))
    ]


async def _run(processor, context, input_items, agent=None):
    await processor.on_llm_start(
        SimpleNamespace(context=context),
        agent=agent or _make_agent(),
        system_prompt=None,
        input_items=input_items,
    )


# Proactive reminders are limited to GLM, including prefixed and older versions.
GLM_EMPTY_TODOS_MODELS = [
    "zhipuai/glm-5.3",
    "baidu-glm-5.3-flash",
    "openai/glm-6",
    "z-ai/glm-5.2",
]

OTHER_EMPTY_TODOS_MODELS = [
    "claude-sonnet-5",
    "bailian-kimi-k3",
    "gpt-6-astra",
    "deepseek-v4_1-flash",
    "claude-sonnet-4",
    "gpt-5.6-luna",
    "deepseek/deepseek-v4-flash-0731",
    "xglm-5.3",
    None,
]


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", GLM_EMPTY_TODOS_MODELS)
@pytest.mark.parametrize("goal", [None, _active_goal()], ids=["no-goal", "active-goal"])
async def test_glm_empty_todos_get_the_empty_list_reminder(model_name, goal):
    processor = TodoReminderProcessor()
    context = _make_context(model_name, goal=goal)
    input_items = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)

    await _run(processor, context, input_items)

    reminders = _reminders_in(input_items)
    assert len(reminders) == 1
    assert reminders[0]["role"] == "user"
    assert input_items[-1] is reminders[0]
    text = reminders[0]["content"]
    assert "consider using todo_write to start a todo list" in text
    # Never pretends there is an existing list, nor mentions the goal.
    assert "existing contents" not in text
    assert "Active goal objective" not in text
    assert context.pending_reminder_items == [reminders[0]]
    assert context.todo_turns_since_reminder == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", OTHER_EMPTY_TODOS_MODELS)
@pytest.mark.parametrize("goal", [None, _active_goal()], ids=["no-goal", "active-goal"])
async def test_non_glm_empty_todos_are_not_reminded(model_name, goal, monkeypatch):
    monkeypatch.setenv(TODO_EMPTY_LIST_REMINDER_ENV, "true")
    context = _make_context(model_name, goal=goal)
    input_items = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)

    await _run(TodoReminderProcessor(), context, input_items)

    assert _reminders_in(input_items) == []
    assert context.pending_reminder_items == []
    assert context.todo_turns_since_reminder == TURNS_BETWEEN_REMINDERS_THRESHOLD


@pytest.mark.asyncio
async def test_empty_todos_without_model_config_are_not_reminded():
    context = CodeAgentContext()
    context.todo_turns_since_reminder = TURNS_BETWEEN_REMINDERS_THRESHOLD
    input_items = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)

    await _run(TodoReminderProcessor(), context, input_items)

    assert _reminders_in(input_items) == []
    assert context.pending_reminder_items == []


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["0", "false", "off"])
async def test_empty_list_opt_out_restores_the_previous_behaviour(monkeypatch, value):
    monkeypatch.setenv(TODO_EMPTY_LIST_REMINDER_ENV, value)
    processor = TodoReminderProcessor()
    context = _make_context("zhipuai/glm-5.3", goal=_active_goal())
    input_items = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)

    await _run(processor, context, input_items)

    assert _reminders_in(input_items) == []
    assert context.pending_reminder_items == []
    # The skipped path leaves the reminder interval counter untouched.
    assert context.todo_turns_since_reminder == TURNS_BETWEEN_REMINDERS_THRESHOLD


@pytest.mark.asyncio
async def test_first_request_is_never_reminded():
    processor = TodoReminderProcessor()
    context = _make_context("zhipuai/glm-5.3")
    input_items = [{"role": "user", "content": "first request"}]

    await _run(processor, context, input_items)

    assert _reminders_in(input_items) == []
    assert context.pending_reminder_items == []


@pytest.mark.asyncio
async def test_empty_todos_below_either_threshold_are_not_reminded():
    processor = TodoReminderProcessor()

    context = _make_context("zhipuai/glm-5.3")
    input_items = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD - 1)
    await _run(processor, context, input_items)
    assert _reminders_in(input_items) == []

    context = _make_context("zhipuai/glm-5.3")
    context.todo_turns_since_reminder = TURNS_BETWEEN_REMINDERS_THRESHOLD - 2
    input_items = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)
    await _run(processor, context, input_items)
    assert _reminders_in(input_items) == []


@pytest.mark.asyncio
async def test_empty_todos_without_registered_todo_write_are_not_reminded():
    processor = TodoReminderProcessor()
    context = _make_context("zhipuai/glm-5.3")
    input_items = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)

    await _run(processor, context, input_items, agent=_make_agent(("run_cmd",)))

    assert _reminders_in(input_items) == []
    assert context.pending_reminder_items == []


@pytest.mark.asyncio
async def test_retried_call_stages_a_single_pending_reminder():
    """A retried on_llm_start recomputes the reminder; only one is persisted."""
    processor = TodoReminderProcessor()
    context = _make_context("zhipuai/glm-5.3")

    first_attempt = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)
    await _run(processor, context, first_attempt)
    # Same thresholds still hold for the retry of the same logical call.
    context.todo_turns_since_reminder = TURNS_BETWEEN_REMINDERS_THRESHOLD
    retry_attempt = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)
    await _run(processor, context, retry_attempt)

    assert len(_reminders_in(retry_attempt)) == 1
    assert len(context.pending_reminder_items) == 1


@pytest.mark.asyncio
async def test_retry_with_non_glm_model_drops_pending_empty_list_reminder():
    context = _make_context("zhipuai/glm-5.3")
    processor = TodoReminderProcessor()
    first_attempt = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)
    await _run(processor, context, first_attempt)
    assert len(context.pending_reminder_items) == 1

    context.session.siada_config.llm_config.model_name = "claude-sonnet-5"
    retry_attempt = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)
    await _run(processor, context, retry_attempt)

    assert _reminders_in(retry_attempt) == []
    assert context.pending_reminder_items == []


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["claude-sonnet-5", "claude-sonnet-4", "zhipuai/glm-5.3"])
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
async def test_opt_out_does_not_suppress_existing_list_reminder(monkeypatch):
    monkeypatch.setenv(TODO_EMPTY_LIST_REMINDER_ENV, "off")
    context = _make_context(
        "zhipuai/glm-5.3", todos=[SimpleNamespace(status="pending", content="task A")]
    )
    input_items = _make_input_items(TURNS_SINCE_WRITE_THRESHOLD + 1)

    await _run(TodoReminderProcessor(), context, input_items)

    assert len(_reminders_in(input_items)) == 1
    assert len(context.pending_reminder_items) == 1


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
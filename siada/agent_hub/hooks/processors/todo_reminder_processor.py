"""
Todo Reminder Processor

Injects a hidden todo reminder into the LLM input when the model has gone
too many assistant turns without calling todo_write, and durably persists
that reminder into the real Session.

This used to be split across two pieces: a ``TodoReminderFilter``
``call_model_input_filter`` (context_capture_filter.py) that injected the
reminder, plus a separate persistence processor. It's not a
``call_model_input_filter`` any more -- ``call_model_input_filter`` only
ever receives a ``copy.deepcopy()`` of ``ModelInputData`` (see
context_capture_filter.py), so it has no access to ``context.session`` and
any injection there only affects a throwaway copy. Both halves now live
here as a single ``AgentHooks`` processor:

- ``on_llm_start`` fires after ``call_model_input_filter`` has already
  produced the final, real ``input_items`` list that is about to be sent to
  the model for this call. Appending directly onto that real list
  guarantees the reminder is actually part of the input the model sees for
  *this* call.
- ``on_llm_end`` fires once per successful LLM call, with no retry
  ambiguity, and drains ``context.pending_reminder_items`` (staged by
  ``on_llm_start`` as a side effect) into the real Session, calling
  ``session.add_items()`` the same way the SDK persists real conversation
  turns via ``save_result_to_session()``. Without this, the reminder would
  only affect the single call it was injected for and vanish the moment
  that call returned, since the SDK's Runner loop only reads
  ``session.get_items()`` once at the very start of a run.
"""

import logging
import time
from typing import Any, List, Optional

from agents import Agent, ModelResponse, AgentHooks, TContext, RunContextWrapper

from siada.agent_hub.context_filter.utils import _normalize_to_responses_items
from siada.agent_hub.hooks.processors.reminder_persistence_utils import (
    persist_pending_reminder_items,
)
from siada.foundation.code_agent_context import CodeAgentContext

logger = logging.getLogger(__name__)

TURNS_SINCE_WRITE_THRESHOLD = 10
TURNS_BETWEEN_REMINDERS_THRESHOLD = 10


def _count_assistant_turns_since_todo_write(input_items: List) -> int:
    """
    Scan input_items in reverse order to count model turns since the last
    todo_write function call.

    A "model turn" is counted each time a model-produced item (function_call or
    assistant message) appears after a "boundary" — a function_call_output or
    user message that separates consecutive model call groups.

    This correctly handles:
    - Tool-only model calls (function_call with no accompanying text message)
    - Parallel function calls from the same model call (counted as 1 turn)
    - Mixed calls with both text and function calls

    - type == "reasoning" items are skipped (not counted as turns)
    - The function_call item for todo_write itself is not counted
    - Returns the total model turn count if no todo_write call is found

    IMPORTANT — provider-format bug fix:
    Some provider paths (e.g. li/Bedrock/ADK — see
    ``agent_hub/context_filter/utils.py::_normalize_to_responses_items``) write
    ChatCompletion-style dicts into ``task_message_state`` instead of pure
    Responses-API items, e.g.::

        {"role": "assistant", "content": "", "tool_calls": [...]}
        {"role": "tool", "tool_call_id": "...", "content": "..."}

    Neither of these carries a recognizable ``type`` field, so *without*
    normalization they match none of the branches below: they are not
    detected as "model output" (needs ``type == "message"``) nor as a "turn
    boundary" (needs ``type == "function_call_output"``). This silently made
    ``turns_since_write`` stay at 0 forever for those providers, so the
    reminder could never fire — this was one root cause of the reminder
    "never getting added" in practice. We normalize defensively here so turn
    counting works the same regardless of which provider produced the
    history.
    """
    normalized_items = _normalize_to_responses_items(input_items)
    turns_since_write = 0
    # after_boundary=True means we have just passed a turn boundary
    # (function_call_output or user message), so the next model-produced item
    # starts a new turn. Initialised to True so the very first model item we
    # encounter while scanning backwards is always counted.
    after_boundary = True
    for item in reversed(normalized_items):
        if not isinstance(item, dict):
            continue
        item_type = item.get("type", "")
        role = item.get("role", "")
        # Skip reasoning/thinking blocks
        if item_type == "reasoning":
            continue
        # Found the most recent todo_write call — stop here
        if item_type == "function_call" and item.get("name") == "todo_write":
            return turns_since_write
        # Turn boundaries: tool outputs or user messages
        if item_type == "function_call_output" or role == "user":
            after_boundary = True
            continue
        # Model-produced items: function_call or assistant message
        is_model_output = item_type == "function_call" or (
            item_type == "message" and role == "assistant"
        )
        if is_model_output and after_boundary:
            turns_since_write += 1
            after_boundary = False
    return turns_since_write


def _build_reminder_text(todos: List[Any], goal: Optional[Any] = None) -> str:
    """Build the hidden reminder injected as a user message.

    Two shapes:
    - todos non-empty: remind about the existing (possibly stale) list, same
      as before.
    - todos empty but an active /goal is present: nudge the agent to actually
      start using todo_write to break the goal down into trackable steps,
      rather than staying silent just because there is nothing to show yet.
      (See TodoReminderProcessor.on_llm_start — this branch is only reached
      when the caller has already confirmed there is something worth
      reminding about.)
    """
    if todos:
        lines = [f"{i + 1}. [{t.status}] {t.content}" for i, t in enumerate(todos)]
        todo_str = "\n".join(lines)
        return (
            "<system-reminder>\n"
            "The todo_write tool hasn't been used recently. If you're working on tasks that "
            "would benefit from tracking progress, consider using the todo_write tool to "
            "track progress. Also consider cleaning up the todo list if it has become stale "
            "and no longer matches what you are working on. Only use it if it's relevant "
            "to the current work. This is just a gentle reminder — ignore if not applicable.\n"
            "Make sure that you NEVER mention this reminder to the user.\n\n"
            f"Here are the existing contents of your todo list:\n\n{todo_str}\n"
            "</system-reminder>"
        )

    if goal is not None:
        objective = getattr(goal, "objective", "")
        return (
            "<system-reminder>\n"
            "You have an active session goal but no todo list has been created for it yet. "
            "If the goal involves multiple concrete steps, consider using the todo_write tool "
            "to break it down and track progress — this keeps the work visible and easy to "
            "resume if interrupted. Only use it if it's genuinely relevant to the current work. "
            "This is just a gentle reminder — ignore if not applicable.\n"
            "Make sure that you NEVER mention this reminder to the user.\n\n"
            f"Active goal objective:\n{objective}\n"
            "</system-reminder>"
        )

    # Fallback for direct callers that bypass TodoReminderProcessor's guard —
    # on_llm_start itself never reaches this branch (it only calls this
    # helper when todos is non-empty or an active goal is present).
    return (
        "<system-reminder>\n"
        "The todo_write tool hasn't been used recently. If you're working on tasks that "
        "would benefit from tracking progress, consider using the todo_write tool to "
        "track progress. This is just a gentle reminder — ignore if not applicable.\n"
        "Make sure that you NEVER mention this reminder to the user.\n\n"
        "Here are the existing contents of your todo list:\n\n(empty — no todos currently tracked)\n"
        "</system-reminder>"
    )


def _get_active_goal(context: "CodeAgentContext") -> Optional[Any]:
    """Return context.goal if it exists and its status is 'active', else None."""
    goal = getattr(context, "goal", None)
    if goal is not None and getattr(goal, "status", None) == "active":
        return goal
    return None


class TodoReminderProcessor(AgentHooks):
    """Injects a hidden todo reminder into the real model input when the
    model has gone too many assistant turns without calling todo_write, and
    durably persists it into the real Session. See module docstring.
    """

    async def on_llm_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        system_prompt: str | None,
        input_items: list,
    ) -> None:
        """Inject the hidden todo reminder directly into the real model input."""
        try:
            siada_context = context.context

            # Guard: only operate on non-empty list-format inputs
            if not isinstance(input_items, list) or not input_items:
                logger.debug(
                    "[TodoReminderProcessor] skip: input_items is not a non-empty list "
                    f"(type={type(input_items).__name__})"
                )
                return

            # Guard: skip if todo_write is not registered for this agent
            tools = getattr(agent, "tools", None) or []
            tool_names = {getattr(t, "name", None) for t in tools}
            if "todo_write" not in tool_names:
                logger.debug(
                    "[TodoReminderProcessor] skip: todo_write not registered on agent "
                    f"(agent_tools={sorted(n for n in tool_names if n)})"
                )
                return

            # Count assistant turns since last todo_write from the message history
            _t0 = time.perf_counter()
            turns_since_write = _count_assistant_turns_since_todo_write(input_items)
            logger.debug(
                "[PERF][TodoReminderProcessor] input_items=%d turns_since_write=%d | "
                "scan=%.1fms",
                len(input_items), turns_since_write,
                (time.perf_counter() - _t0) * 1000,
            )

            # Update the reminder interval counter
            if turns_since_write > 0:
                siada_context.todo_turns_since_reminder += 1
            else:
                siada_context.todo_turns_since_reminder = 0

            active_goal = _get_active_goal(siada_context)

            logger.debug(
                f"[TodoReminderProcessor] state: turns_since_write={turns_since_write} "
                f"(threshold={TURNS_SINCE_WRITE_THRESHOLD}), "
                f"todo_turns_since_reminder={siada_context.todo_turns_since_reminder} "
                f"(threshold={TURNS_BETWEEN_REMINDERS_THRESHOLD}), "
                f"todos_count={len(siada_context.todos)}, has_active_goal={active_goal is not None}, "
                f"input_len={len(input_items)}"
            )

            # Skip if neither threshold is met
            if turns_since_write < TURNS_SINCE_WRITE_THRESHOLD:
                logger.debug(
                    "[TodoReminderProcessor] skip: turns_since_write "
                    f"({turns_since_write}) < TURNS_SINCE_WRITE_THRESHOLD "
                    f"({TURNS_SINCE_WRITE_THRESHOLD})"
                )
                return
            if siada_context.todo_turns_since_reminder < TURNS_BETWEEN_REMINDERS_THRESHOLD:
                logger.debug(
                    "[TodoReminderProcessor] skip: todo_turns_since_reminder "
                    f"({siada_context.todo_turns_since_reminder}) < TURNS_BETWEEN_REMINDERS_THRESHOLD "
                    f"({TURNS_BETWEEN_REMINDERS_THRESHOLD})"
                )
                return

            # Normally there is nothing worth reminding about when the todo
            # list is empty. Exception: an active /goal exists but no todo
            # list has been created for it yet — in that case we still want
            # to nudge the agent to start using todo_write, instead of
            # staying silent forever just because there is nothing to show.
            # See _build_reminder_text.
            if not siada_context.todos and active_goal is None:
                logger.debug(
                    "[TodoReminderProcessor] skip: context.todos is empty and no active "
                    "goal, nothing to remind about"
                )
                return

            # Inject reminder as a hidden user message at the end of the
            # real input -- this is the actual list about to be sent to the
            # model for this call, so the reminder is guaranteed to be seen.
            reminder_item = {
                "role": "user",
                "content": _build_reminder_text(siada_context.todos, goal=active_goal),
            }
            input_items.append(reminder_item)

            # Stage a copy for durable persistence, drained by on_llm_end
            # below.
            #
            # IMPORTANT: overwrite, never append. on_llm_start can be
            # invoked more than once for what is logically a single outer
            # LLM call attempt (e.g. the SDK retrying on a transient error
            # before a response is ever returned to on_llm_end). Each
            # invocation here already recomputes a fresh, complete reminder
            # from current state, so there is never a need to keep more
            # than the single latest one pending -- appending would let
            # pre-success retries accumulate duplicate reminder items that
            # all get persisted together the moment the call finally
            # succeeds and the queue is drained.
            if hasattr(siada_context, "pending_reminder_items"):
                siada_context.pending_reminder_items = [dict(reminder_item)]

            # Reset reminder counter
            siada_context.todo_turns_since_reminder = 0

            logger.debug(
                f"[TodoReminderProcessor] Injected todo reminder "
                f"(turns_since_write={turns_since_write}, todos={len(siada_context.todos)}, "
                f"active_goal_nudge={not siada_context.todos and active_goal is not None})"
            )
        except Exception as e:
            logger.debug(f"[TodoReminderProcessor] failed to inject reminder: {e}")

    async def on_llm_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        siada_context = context.context
        pending: List[Any] = getattr(siada_context, "pending_reminder_items", None) or []
        try:
            await persist_pending_reminder_items(
                getattr(siada_context, "session", None), pending, "TodoReminderProcessor"
            )
        finally:
            # Always clear, whether persisted, dropped, or errored -- avoid
            # re-persisting/duplicating on the next on_llm_end call.
            if hasattr(siada_context, "pending_reminder_items"):
                siada_context.pending_reminder_items = []

    async def on_agent_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
    ) -> None:
        """Called when an agent starts execution."""
        pass

    async def on_agent_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        output: Any,
    ) -> None:
        """Called when an agent completes execution."""
        pass

    async def on_tool_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Any,
    ) -> None:
        """Called before a tool is executed."""
        pass

    async def on_tool_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Any,
        result: str,
    ) -> None:
        """Called after a tool completes execution."""
        pass

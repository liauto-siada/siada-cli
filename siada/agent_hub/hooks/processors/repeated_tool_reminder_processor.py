"""
Repeated Tool Call Reminder Processor (reviewed as "GLM53-R1")

Event-triggered — not periodic — reminder for the main coding agent on the
GLM-5.2-and-later family. When the three most recent model turns of the
current human turn each made exactly one call to the same tool with
equivalent (normalized) arguments, and all three calls already have their
results, the next model request gets ONE short hidden ``role=user``
reminder asking the model to use those results, change its next step or
state what blocks it.

Why this shape:
- Only sequential single-call turns count: a parallel batch, a different
  tool or different arguments breaks the streak, and a real human message
  ends the scan, so a new human turn never inherits an old streak. Hidden
  runtime user items (other reminders, the Git snapshot) are transparent.
- The streak must be EXACTLY three long, so a fourth identical call does
  not earn a second reminder for the same streak.
- The reminder is a separate ``role=user`` message whose text is wrapped in
  ``<system-reminder>`` only as an application-level boundary; the target
  chat protocols reject mid-conversation ``role=system`` messages.
- The tool name must be a tool registered on the agent and is escaped;
  arguments and tool output never appear in the reminder or in logs.

Delivery mirrors TodoReminderProcessor: ``on_llm_start`` appends to the
real per-call input and OVERWRITES its own pending queue (a retried call
recomputes the reminder, so retries never persist duplicates), and
``on_llm_end`` persists it into the Session only after the call succeeded.
"""

import json
import re
from typing import Any, List, Optional, Tuple

from agents import (
    Agent,
    AgentHooks,
    ModelResponse,
    RunContextWrapper,
    TContext,
    TResponseInputItem,
    Tool,
)

from siada.agent_hub.coder.prompt.selection.model_features import (
    uses_glm_repeated_tool_reminder,
)
from siada.agent_hub.context_filter.utils import _normalize_to_responses_items
from siada.agent_hub.hooks.processors.reminder_persistence_utils import (
    persist_pending_reminder_items,
)
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.logging import logger
from siada.support.message_classifier import is_hidden_runtime_content

REPEAT_THRESHOLD = 3

# The detector only needs the last few model turns; bounding the scanned
# tail keeps the per-call cost constant in long sessions.
_MAX_SCANNED_ITEMS = 400

# Only the main coding agent (the ``name`` CodeGenAgent registers with).
_MAIN_AGENT_NAMES = {"CodeGenAgent"}

_TOOL_OUTPUT_TYPES = {
    "function_call_output",
    "custom_tool_call_output",
    "computer_call_output",
    "local_shell_call_output",
    "shell_call_output",
    "apply_patch_call_output",
}

_SAFE_TOOL_NAME = re.compile(r"[^A-Za-z0-9_.:\-]")

REPEATED_TOOL_REMINDER_TEMPLATE = (
    '<system-reminder source="siada.runtime.repeated-tool">\n'
    "Three completed calls to {tool_name} used equivalent arguments in this task. "
    "Read their results before the next call. Choose a materially different argument "
    "or method based on the evidence. If the same call is warranted by a changed "
    "condition, explain that condition briefly; if you are blocked, say what is "
    "missing. Do not repeat this reminder to the user.\n"
    "</system-reminder>"
)


def _normalize_arguments(raw: Any) -> str:
    """Canonical form of tool arguments so key order / spacing don't matter."""
    if isinstance(raw, (dict, list)):
        value = raw
    else:
        text = "" if raw is None else str(raw).strip()
        if not text:
            return ""
        try:
            value = json.loads(text)
        except (TypeError, ValueError):
            return text
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def _single_call_key(turn: List[dict]) -> Optional[Tuple[str, str]]:
    """(tool name, normalized arguments) of a turn with exactly one function call."""
    if len(turn) != 1 or turn[0].get("type") != "function_call":
        return None
    call = turn[0]
    return str(call.get("name") or ""), _normalize_arguments(call.get("arguments"))


def find_repeated_tool_call(input_items: List[Any]) -> Optional[str]:
    """Return the tool name when the input ends with an exact repeat streak.

    The streak is REPEAT_THRESHOLD most recent model turns of the current
    human turn, each with exactly one ``function_call`` of the same tool and
    equivalent arguments, all already paired with a tool result — and the
    turn before them (if any) is not part of the same streak. Returns None
    otherwise.
    """
    if not isinstance(input_items, list) or not input_items:
        return None
    items = _normalize_to_responses_items(list(input_items[-_MAX_SCANNED_ITEMS:]))

    completed_call_ids = set()
    # Model turns, most recent first; each holds that turn's tool call items.
    turns: List[List[dict]] = []
    current: Optional[List[dict]] = None
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        role = item.get("role")
        if item_type == "reasoning" or role in ("system", "developer"):
            continue
        if item_type in _TOOL_OUTPUT_TYPES:
            completed_call_ids.add(item.get("call_id"))
            if current is not None:
                turns.append(current)
                current = None
                if len(turns) > REPEAT_THRESHOLD:
                    break
            continue
        if role == "user" and item_type in (None, "message"):
            if is_hidden_runtime_content(item.get("content")):
                # Other reminders / the Git snapshot are not human input.
                continue
            # A real human message ends the current human turn.
            break
        if current is None:
            current = []
        if item_type == "message":
            # Assistant text belongs to its turn but is not a tool call.
            continue
        current.append(item)
    if current is not None:
        turns.append(current)

    if len(turns) < REPEAT_THRESHOLD:
        return None
    keys = []
    for turn in turns[:REPEAT_THRESHOLD]:
        key = _single_call_key(turn)
        if key is None or turn[0].get("call_id") not in completed_call_ids:
            return None
        keys.append(key)
    if len(set(keys)) != 1 or not keys[0][0]:
        return None
    if len(turns) > REPEAT_THRESHOLD and _single_call_key(turns[REPEAT_THRESHOLD]) == keys[0]:
        # Longer streak: it was already reminded at its third call.
        return None
    return keys[0][0]


def build_repeated_tool_reminder_text(tool_name: str) -> str:
    """Render the reminder; the tool name is escaped and length-bounded."""
    safe_name = _SAFE_TOOL_NAME.sub("_", tool_name)[:64] or "the tool"
    return REPEATED_TOOL_REMINDER_TEMPLATE.format(tool_name=safe_name)


class RepeatedToolReminderProcessor(AgentHooks):
    """Remind GLM-5.2-and-later models once about a repeated unchanged tool call."""

    @staticmethod
    def _current_model_name(context: RunContextWrapper[CodeAgentContext]) -> Optional[str]:
        try:
            session = getattr(context.context, "session", None)
            cfg = getattr(session, "siada_config", None)
            return getattr(cfg.llm_config, "model_name", None) if cfg else None
        except Exception:
            return None

    @staticmethod
    def _is_runtime_tool(agent: Agent[TContext], tool_name: str) -> bool:
        """Whether ``tool_name`` comes from this run's registered tools.

        Function tools are listed on ``agent.tools``; MCP tools are resolved
        by the SDK at run time, so an agent with MCP servers also accepts the
        name (the call already produced a result, so the SDK resolved it).
        """
        names = {getattr(tool, "name", None) for tool in (getattr(agent, "tools", None) or [])}
        return tool_name in names or bool(getattr(agent, "mcp_servers", None))

    async def on_llm_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        system_prompt: Optional[str],
        input_items: list[TResponseInputItem],
    ) -> None:
        siada_context = context.context
        try:
            # The pending item always belongs to the call being started: a
            # call that never reached on_llm_end must not leak its reminder
            # into a later call's persistence.
            if hasattr(siada_context, "pending_repeated_tool_reminder_items"):
                siada_context.pending_repeated_tool_reminder_items = []

            if getattr(agent, "name", None) not in _MAIN_AGENT_NAMES:
                return
            if getattr(siada_context, "is_subagent", False):
                return
            if not uses_glm_repeated_tool_reminder(self._current_model_name(context)):
                return
            if not isinstance(input_items, list) or not input_items:
                return

            tool_name = find_repeated_tool_call(input_items)
            if tool_name is None or not self._is_runtime_tool(agent, tool_name):
                return

            reminder_item = {
                "role": "user",
                "content": build_repeated_tool_reminder_text(tool_name),
            }
            input_items.append(reminder_item)
            # OVERWRITE (never append): a retried call recomputes the same
            # reminder, so at most one copy is ever persisted.
            if hasattr(siada_context, "pending_repeated_tool_reminder_items"):
                siada_context.pending_repeated_tool_reminder_items = [dict(reminder_item)]
            logger.debug(
                "[RepeatedToolReminder] injected reminder after %d equivalent %s calls",
                REPEAT_THRESHOLD,
                _SAFE_TOOL_NAME.sub("_", tool_name)[:64],
            )
        except Exception as e:
            logger.debug(f"[RepeatedToolReminder] on_llm_start failed: {e}")

    async def on_llm_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        response: ModelResponse,
    ) -> None:
        """Persist the delivered reminder into the Session, then clear the queue."""
        siada_context = context.context
        pending = getattr(siada_context, "pending_repeated_tool_reminder_items", None) or []
        try:
            await persist_pending_reminder_items(
                getattr(siada_context, "session", None), pending, "RepeatedToolReminder"
            )
        finally:
            if hasattr(siada_context, "pending_repeated_tool_reminder_items"):
                siada_context.pending_repeated_tool_reminder_items = []

    # No-op implementations for the rest of the AgentHooks contract.
    async def on_agent_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
    ) -> None:
        pass

    async def on_agent_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        output: Any,
    ) -> None:
        pass

    async def on_tool_start(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
    ) -> None:
        pass

    async def on_tool_end(
        self,
        context: RunContextWrapper[CodeAgentContext],
        agent: Agent[TContext],
        tool: Tool,
        result: str,
    ) -> None:
        pass

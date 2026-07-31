import re
from typing import Optional, Any, Tuple, List, Dict

# One (open, close) tag pair per spelling — the hyphen spelling used by
# ``merge_goal_reminder_into_input`` and the legacy underscore spelling
# ``TodoReminderFilter`` used before it was unified onto the hyphen tag.
# Sessions persisted before that unification still have the underscore
# spelling on disk, so both must keep being recognized on replay.
_SYSTEM_REMINDER_WRAPPERS = (
    ("<system-reminder>", "</system-reminder>"),
    ("<system_reminder>", "</system_reminder>"),
)


def _is_whole_system_reminder(text: str) -> bool:
    """Return True only if ``text``, once surrounding whitespace is
    stripped, is a system-reminder block **from start to end** — i.e. the
    entire piece of text is the harness-injected reminder, not a reminder
    tag merely appearing somewhere inside otherwise-real text.

    This is a whole-string match, not a substring search-and-remove, by
    design. Reminders are always injected as a dedicated, reminder-only
    message or content part (see ``merge_goal_reminder_into_input``,
    which appends the reminder as its own separate content part rather
    than splicing it into existing text, and ``TodoReminderFilter``,
    which injects a dedicated standalone message) — never spliced into
    the middle of real user text. So "the whole part/message is exactly
    one reminder block" is both sufficient and safe to detect.

    Treating any *substring* occurrence as strippable would be unsafe in
    two ways:
    - It could erase real, legitimately-typed user text that happens to
      contain a reminder-looking tag (e.g. a user quoting/pasting a
      previously-rendered reminder back into a new message — that text
      is real conversation history, not a harness nudge, even though it
      contains the tag string).
    - A combined regex like
      ``<system[-_]reminder>.*?</system[-_]reminder>`` lets a hyphen
      *opening* tag pair with an underscore *closing* tag (or vice
      versa) when both spellings appear in the same string, silently
      leaving part of the block un-stripped.

    Matching only "starts with an opening tag AND ends with the *same
    spelling's* closing tag" sidesteps both problems: mixed-content
    messages are left completely untouched, and the two spellings can
    never cross-pair.
    """
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    return any(
        stripped.startswith(open_tag) and stripped.endswith(close_tag)
        for open_tag, close_tag in _SYSTEM_REMINDER_WRAPPERS
    )


def get_role_from_item(item: Any) -> Optional[str]:
    """
    Extract role information from a message item.
    
    Args:
        item: Message item to extract role from
        
    Returns:
        Optional[str]: Role string ('user', 'assistant', 'system', 'developer', 'tool') or None
    """
    role, _ = get_role_and_type_from_item(item)
    return role


def get_item_type_from_item(item: Any) -> Optional[str]:
    """
    Extract item type information from a message item.
    
    Args:
        item: Message item to extract type from
        
    Returns:
        Optional[str]: Item type string or None
    """
    _, item_type = get_role_and_type_from_item(item)
    return item_type


def get_role_and_type_from_item(item: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract both role and item type information from a message item.
    
    Args:
        item: Message item to extract role and type from
        
    Returns:
        Tuple[Optional[str], Optional[str]]: (role, item_type) where:
            - role: 'user', 'assistant', 'system', 'developer', 'tool' or None
            - item_type: specific item type string or None
    """
    
    if not isinstance(item, dict):
        return None, None
    
    item_type = item.get("type")
    
    # 1. First, check explicit type fields for all typed messages and tool calls
    if item_type == "message":
        role = item.get("role")
        if role in ("user", "assistant", "system", "developer"):
            return role, "message"
    
    # 3. Check tool call types from assistant
    if item_type == "function_call":
        return "assistant", "function_call"
    elif item_type == "file_search_call":
        return "assistant", "file_search_call"
    elif item_type == "computer_call":
        return "assistant", "computer_call"
    elif item_type == "function_web_search":
        return "assistant", "function_web_search"
    elif item_type == "code_interpreter_call":
        return "assistant", "code_interpreter_call"
    elif item_type == "image_generation_call":
        return "assistant", "image_generation_call"
    elif item_type == "local_shell_call":
        return "assistant", "local_shell_call"
    elif item_type == "mcp_call":
        return "assistant", "mcp_call"
    elif item_type == "custom_tool_call":
        return "assistant", "custom_tool_call"
    
    # 4. Check tool output types
    elif item_type == "function_call_output":
        return "tool", "function_call_output"
    elif item_type == "computer_call_output":
        return "tool", "computer_call_output"
    elif item_type == "local_shell_call_output":
        return "tool", "local_shell_call_output"
    elif item_type == "custom_tool_call_output":
        return "tool", "custom_tool_call_output"
    
    # 5. Reasoning content from assistant
    elif item_type == "reasoning":
        return "assistant", "reasoning"
    
    # 6. MCP types without specific roles
    elif item_type == "mcp_list_tools":
        return None, "mcp_list_tools"
    elif item_type == "mcp_approval_request":
        return None, "mcp_approval_request"
    elif item_type == "mcp_approval_response":
        return None, "mcp_approval_response"
    elif item_type == "item_reference":
        return None, "item_reference"
    
    # 2. Handle EasyInputMessageParam - simple format {content: ..., role: ...} without type
    # This handles both cases with and without explicit type field  
    elif item_type is None and "content" in item and "role" in item:
        role = item.get("role")
        if role in ("user", "assistant", "system", "developer"):
            return role, "easy_input_message"
    
    # 3. Handle unknown types or cases with type but no specific handling
    return None, item_type


def format_native_items_for_display(items: list) -> List[Dict[str, str]]:
    """Convert native OpenAI-format message items into display-ready dicts.

    Shared by Controller._send_session_sync (deferred rendering) and
    SlashCommands._send_history_to_ui (/resume).

    Each returned dict has keys: role, content, and optionally subtype.
    - function_call items are formatted via ToolCallFormatterFactory
    - function_call_output items are skipped
    - User messages have <task>...</task> wrappers stripped
    - Sentinel-wrapped injection blocks (holographic prefetch from
      ``CodeGenAgent`` and IM context blocks from ``LarkAgentExecutor``)
      are stripped from any role's text — these are internal LLM-priming
      details and must not surface in chat bubbles. Telemetry has its
      own (non-stripping) path in
      ``session_manager._format_history_for_telemetry``.
    - Hidden ``<system-reminder>...</system-reminder>`` content parts (the
      goal reminder appended by ``merge_goal_reminder_into_input``) and
      hidden ``<system-reminder>``/legacy ``<system_reminder>`` standalone
      messages (``TodoReminderFilter``) are dropped entirely — these are
      harness-internal nudges, not something the user actually typed, and
      must not reappear when a session is replayed via ``/resume`` or
      deferred-rendering sync. Only WHOLE reminder blocks are dropped
      (see ``_is_whole_system_reminder``): a reminder tag merely appearing
      inside otherwise-real user text (e.g. a user quoting/pasting a
      previously-rendered reminder back into a new message) is left
      untouched, since that's real conversation history, not a harness
      nudge.
    """
    from siada.tools.tool_call_format.formatter_factory import ToolCallFormatterFactory
    # Lazy-import the marker helpers so the holographic-memory module is
    # only pulled in when there's actually something to strip; cheap path
    # for plain conversations stays a single ``has_any_injection_block``
    # check.
    from siada.services.memory.holographic.marker import (
        has_any_injection_block,
        strip_all_injection_blocks,
    )

    messages: List[Dict[str, str]] = []
    for item in items:
        item_type = item.get("type", "")
        role = item.get("role", "assistant")

        # function_call: format via ToolCallFormatter
        if item_type == "function_call":
            try:
                name = item.get("name", "unknown")
                arguments = item.get("arguments", "{}")
                call_id = item.get("call_id", item.get("id", ""))
                formatter = ToolCallFormatterFactory.get_formatter(name)
                content, _ = formatter.format_input(call_id, name, arguments)
                if content:
                    messages.append({
                        "role": "assistant",
                        "content": content,
                        "subtype": "tool_use",
                    })
            except Exception:
                pass
            continue

        # function_call_output: skip (consistent with normal rendering flow)
        if item_type == "function_call_output":
            continue

        # Extract text content (supports str and list formats). A whole
        # reminder-only string content drops the message entirely; a
        # whole reminder-only content *part* within a list is skipped
        # (not concatenated in) while any sibling real-text parts are
        # kept — see _is_whole_system_reminder for why this must be a
        # whole-match check rather than a substring strip.
        content = item.get("content", "")
        text = ""
        if isinstance(content, str):
            text = "" if _is_whole_system_reminder(content) else content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") in (
                    "output_text", "text", "input_text",
                ):
                    part_text = part.get("text", "")
                    if _is_whole_system_reminder(part_text):
                        continue
                    text += part_text

        if not text:
            continue

        # Strip <task>...</task> wrapper from user messages
        if role == "user":
            text = re.sub(r"^\s*<task>\s*", "", text)
            text = re.sub(r"\s*</task>.*$", "", text, flags=re.DOTALL)
            text = text.strip()

        # Strip sentinel-wrapped injection blocks (holographic prefetch +
        # IM context). Cheap early-return for plain text — only does the
        # full regex strip when at least one BEGIN/END pair is present.
        if isinstance(text, str) and text and has_any_injection_block(text):
            text = strip_all_injection_blocks(text)

        if not text:
            continue

        messages.append({"role": role, "content": text})

    return messages

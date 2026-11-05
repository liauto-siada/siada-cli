import re
from typing import Optional, Any, Tuple, List, Dict

# Older Chrome clients persisted this generated preamble inside the user
# message. Match only its leading, generated shape; quoted tags elsewhere
# in a user's text remain part of the conversation.
_LEGACY_BROWSER_PREAMBLE = re.compile(
    r"^\s*<browser-context>\r?\n"
    r"(?:Current tab:|(?:\r?\n)?Selected text on the page:|(?:\r?\n)?Page content excerpt:)"
    r".*?</browser-context>(?:\r?\n){2}",
    re.DOTALL,
)


def _is_whole_system_reminder(text: str) -> bool:
    """Share input wrapping's whole-message boundary without eager imports."""
    # The memory package imports session services, which use this classifier.
    from siada.services.memory.holographic.marker import is_whole_system_reminder

    return is_whole_system_reminder(text)


def is_hidden_runtime_text(text: Any) -> bool:
    """Recognize whole reminders, including entrypoint-wrapped continuations."""
    if isinstance(text, str):
        from siada.services.memory.holographic.marker import USER_INPUT_BEGIN, USER_INPUT_END

        # Internal SwitchEvent continuations historically passed through the
        # same wrapper as human input. Unwrap only a whole enclosing pair;
        # quoted reminder tags inside real text must remain visible.
        stripped = text.strip()
        if stripped.startswith(USER_INPUT_BEGIN) and stripped.endswith(USER_INPUT_END):
            text = stripped[len(USER_INPUT_BEGIN):-len(USER_INPUT_END)]
    return _is_whole_system_reminder(text)


def is_hidden_runtime_content(content: Any) -> bool:
    """Whether message ``content`` (str or content-part list) is entirely hidden runtime text."""
    if isinstance(content, str):
        return is_hidden_runtime_text(content)
    if isinstance(content, list) and content:
        return all(
            isinstance(part, dict) and is_hidden_runtime_text(part.get("text"))
            for part in content
        )
    return False


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
    elif item_type == "shell_call":
        return "assistant", "shell_call"
    elif item_type == "web_search_call":
        return "assistant", "web_search_call"
    elif item_type == "mcp_call":
        return "assistant", "mcp_call"
    elif item_type == "custom_tool_call":
        return "assistant", "custom_tool_call"
    elif item_type == "apply_patch_call":
        return "assistant", "apply_patch_call"
    
    # 4. Check tool output types
    elif item_type == "function_call_output":
        return "tool", "function_call_output"
    elif item_type == "computer_call_output":
        return "tool", "computer_call_output"
    elif item_type == "local_shell_call_output":
        return "tool", "local_shell_call_output"
    elif item_type == "shell_call_output":
        return "tool", "shell_call_output"
    elif item_type == "custom_tool_call_output":
        return "tool", "custom_tool_call_output"
    elif item_type == "apply_patch_call_output":
        return "tool", "apply_patch_call_output"
    
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


def format_native_items_for_display(
    items: list, *, include_tool_metadata: bool = False,
) -> List[Dict[str, Any]]:
    """Convert native OpenAI-format message items into display-ready dicts.

    Shared by Controller._send_session_sync (deferred rendering) and
    SlashCommands._send_history_to_ui (/resume).

    Each returned dict has keys: role, content, and optionally subtype.
    ACP replay can opt into tool identity/input metadata to keep tools out
    of ordinary assistant text without changing the terminal history shape.
    - function_call items are formatted via ToolCallFormatterFactory
    - function_call_output items inform edit_file status but are not standalone rows
    - User messages have <task>...</task> wrappers stripped, as well as
      the <user_input>...</user_input> tag added at every input entry
      point (TUI, Feishu) — see ``marker.wrap_user_input``
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
    # Lazy-import the marker helpers so the holographic-memory module is
    # only pulled in when there's actually something to strip; cheap path
    # for plain conversations stays a single ``has_any_injection_block``
    # check.
    from siada.services.memory.holographic.marker import (
        has_any_injection_block,
        strip_all_injection_blocks,
        strip_user_input,
    )
    from siada.tools.coder.apply_patch_presentation import (
        render_apply_patch_history_preview,
    )
    from siada.tools.tool_call_format.formatter_factory import ToolCallFormatterFactory
    from siada.tools.coder.file_edit_presentation import (
        RESULT_UNAVAILABLE,
        is_file_edit_write,
        render_file_edit_display,
    )

    messages: List[Dict[str, Any]] = []
    tool_outputs = {
        item.get("call_id"): item.get("output")
        for item in items if item.get("type") == "function_call_output" and item.get("call_id")
    }
    for item_index, item in enumerate(items):
        item_type = item.get("type", "")
        role = item.get("role", "assistant")

        # function_call: format via ToolCallFormatter
        if item_type == "function_call":
            try:
                name = item.get("name", "unknown")
                arguments = item.get("arguments", "{}")
                call_id = item.get("call_id", item.get("id", ""))
                formatter = ToolCallFormatterFactory.get_formatter(name)
                if name == "edit_file" and is_file_edit_write(arguments):
                    content = render_file_edit_display(
                        call_id or f"history-edit-{item_index}", arguments,
                        output=tool_outputs.get(call_id, RESULT_UNAVAILABLE), history=True,
                    )
                else:
                    content, _ = formatter.format_input(call_id, name, arguments)
                if content:
                    message: Dict[str, Any] = {
                        "role": "assistant",
                        "content": content,
                        "subtype": "tool_use",
                    }
                    if include_tool_metadata:
                        message.update(tool_call_id=call_id, title=name, raw_input=arguments)
                    messages.append(message)
            except Exception:
                pass
            continue

        # Preserve the native patch's requested history preview. The
        # model-facing output remains skipped as a standalone row.
        if item_type == "apply_patch_call":
            message = {
                "role": "assistant",
                "content": render_apply_patch_history_preview(item),
                "subtype": "tool_use",
            }
            if include_tool_metadata:
                message.update(
                    tool_call_id=item.get("call_id", item.get("id", "")),
                    title="apply_patch",
                    raw_input=item.get("operation"),
                )
            messages.append(message)
            continue

        # Tool outputs are skipped consistently with normal live rendering.
        if item_type in ("function_call_output", "apply_patch_call_output"):
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
            text = "" if is_hidden_runtime_text(content) else content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") in (
                    "output_text", "text", "input_text",
                ):
                    part_text = part.get("text", "")
                    if is_hidden_runtime_text(part_text):
                        continue
                    text += part_text

        if not text:
            continue

        # Strip <task>...</task> wrapper from user messages
        if role == "user":
            text = re.sub(r"^\s*<task>\s*", "", text)
            text = re.sub(r"\s*</task>.*$", "", text, flags=re.DOTALL)
            text = text.strip()
            # Strip the <user_input>...</user_input> tag added at every user
            # input entry point (TUI, Feishu) — keeps the body, only removes
            # the literal tag strings, so the chat bubble shows exactly what
            # the human typed.
            text = strip_user_input(text)
            text = _LEGACY_BROWSER_PREAMBLE.sub("", text, count=1)

        # Strip sentinel-wrapped injection blocks (holographic prefetch +
        # IM context). Cheap early-return for plain text — only does the
        # full regex strip when at least one BEGIN/END pair is present.
        if isinstance(text, str) and text and has_any_injection_block(text):
            text = strip_all_injection_blocks(text)
            # Content-list producers (e.g. LarkAgentExecutor._build_user_input)
            # bake a blank-line separator into each item's own text so the
            # blocks read correctly when parts are concatenated with no
            # separator of their own. When a *trailing* block gets stripped
            # here, that separator has nothing left to separate from and
            # would otherwise leave a dangling blank line after the user's
            # real text in the chat bubble.
            text = text.strip()

        if not text:
            continue

        messages.append({"role": role, "content": text})

    return messages

"""Tool Call Batcher - groups consecutive tool calls for compact IM rendering.

Instead of sending one card per tool call in Lark, this batcher tracks
all tool calls and renders a live-updating summary + detail view in a
single streaming card.

Inspired by the frontend's groupToolCalls() + formatCompactSummary() pattern
in toolCallParser.ts.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("siada.tool_call_format.batcher")

# Tool name -> category mapping
TOOL_CATEGORY_MAP = {
    "edit_file": "file_op",
    "run_cmd": "command",
    "regex_search_files": "search",
    "list_code_definition_names": "search",
    "web_search": "web",
    "web_crawl": "web",
    "web_fetch": "web",
    "smart_search_memory": "memory",
    "get_memory": "memory",
    "ask_followup_question": "interaction",
    "manage_cron_task": "cron",
    "browser_operate": "browser",
}

# Category display config
CATEGORY_CONFIG = {
    "file_read": {"icon": "📖", "label": "Read"},
    "file_write": {"icon": "✏️", "label": "Edit"},
    "file_op": {"icon": "📄", "label": "File"},
    "command": {"icon": "⚡", "label": "Cmd"},
    "search": {"icon": "🔍", "label": "Search"},
    "web": {"icon": "🌐", "label": "Web"},
    "memory": {"icon": "🧠", "label": "Memory"},
    "interaction": {"icon": "💬", "label": "Ask"},
    "cron": {"icon": "⏰", "label": "Cron"},
    "browser": {"icon": "🌍", "label": "Browser"},
    "other": {"icon": "🔧", "label": "Tool"},
}

# Max result text length per tool in grouped card
_MAX_RESULT_LEN = 200


def classify_tool(tool_name: str, arguments: str = "") -> str:
    """Classify a tool call into a category.

    For edit_file, further distinguishes read (view) vs write operations.
    """
    if tool_name == "edit_file" and arguments:
        if '"view"' in arguments or "'view'" in arguments:
            return "file_read"
        return "file_write"
    return TOOL_CATEGORY_MAP.get(tool_name, "other")


@dataclass
class ToolCallEntry:
    """A single completed tool call with formatted content."""

    call_id: str
    tool_name: str
    formatted_input: str  # from format_input_im()
    category: str = "other"
    result_text: str = ""
    has_result: bool = False
    workspace: str = ""  # resolved workspace for this tool call


class ToolCallBatcher:
    """Tracks all tool calls in a turn for live-updating card rendering.

    Usage in _consume_stream():
      1. On tool call done: batcher.add_call(entry) -> update card with render_current()
      2. On tool result: batcher.add_result(call_id, text) -> update card
      3. On answer text / stream end: close card with render_final()
    """

    def __init__(self, default_workspace: str = ""):
        self._calls: list[ToolCallEntry] = []
        self._category_counts: dict[str, int] = {}
        self._default_workspace = default_workspace

    @property
    def has_pending(self) -> bool:
        return len(self._calls) > 0

    @property
    def count(self) -> int:
        return len(self._calls)

    def add_call(self, entry: ToolCallEntry) -> None:
        """Add a completed tool call."""
        self._calls.append(entry)
        self._category_counts[entry.category] = (
            self._category_counts.get(entry.category, 0) + 1
        )

    def add_result(self, call_id: str, result_text: str) -> None:
        """Attach a tool result to a call."""
        for entry in self._calls:
            if entry.call_id == call_id:
                entry.result_text = result_text
                entry.has_result = True
                break

    def get_summary(self) -> str:
        """Generate compact summary line like '✏️ Edit ×3 · ⚡ Cmd ×1'.

        This is used as the streaming card content that updates in real-time.
        """
        if not self._calls:
            return "🔧 Working..."

        parts = []
        for cat, n in self._category_counts.items():
            cfg = CATEGORY_CONFIG.get(cat, CATEGORY_CONFIG["other"])
            if n > 1:
                parts.append(f"{cfg['icon']} {cfg['label']} ×{n}")
            else:
                parts.append(f"{cfg['icon']} {cfg['label']}")
        return " · ".join(parts)

    def _render_grouped(self, max_detail_len: int = 300, default_workspace: str = "") -> str:
        """Render all tool calls grouped by workspace then category.

        Output format:
          📂 **默认**
          📖 **Read ×3**
          ✅ Read file **utils.py**

          📂 **/other/project**
          ⚡ **Cmd**
          ⏳ `ls -la`
        """
        if not self._calls:
            return "🔧 No tool calls"

        parts = []

        # Group by workspace first, then by category
        ws_grouped: dict[str, dict[str, list[ToolCallEntry]]] = {}
        for entry in self._calls:
            ws = entry.workspace or default_workspace or ""
            ws_grouped.setdefault(ws, {}).setdefault(entry.category, []).append(entry)

        # Determine if we need workspace headers (multiple workspaces)
        show_ws_headers = len(ws_grouped) > 1

        for ws, cat_grouped in ws_grouped.items():
            if show_ws_headers:
                # Show workspace label: default workspace → "default", others → actual path
                ws_label = "default" if (ws == default_workspace or not ws) else ws
                parts.append(f"\n---\n#### 📂 workdir [{ws_label}]")

            for cat, entries in cat_grouped.items():
                cfg = CATEGORY_CONFIG.get(cat, CATEGORY_CONFIG["other"])
                count_suffix = f" ×{len(entries)}" if len(entries) > 1 else ""
                parts.append(f"\n{cfg['icon']} **{cfg['label']}{count_suffix}**")
                for entry in entries:
                    status = "✅" if entry.has_result else "⏳"
                    detail = _truncate_detail(entry.formatted_input, max_detail_len)
                    # Code blocks need ``` on its own line; put status on line before
                    if "```" in detail:
                        parts.append(f"{status}\n{detail}")
                    else:
                        parts.append(f"{status} {detail}")

        return "\n".join(parts)

    def render_current(self) -> str:
        """Render current state for PATCH card update."""
        return self._render_grouped(max_detail_len=150, default_workspace=self._default_workspace)

    def render_final(self) -> str:
        """Render final grouped content when card is closed."""
        return self._render_grouped(max_detail_len=150, default_workspace=self._default_workspace)

    def clear(self) -> None:
        """Reset batcher state."""
        self._calls.clear()
        self._category_counts.clear()


def _truncate_detail(text: str, max_len: int) -> str:
    """Truncate formatted detail text for IM display, respecting markdown structure.

    - Inline code (`...`): truncate content inside backticks
    - Code blocks (```...```): truncate content inside the block
    - Plain text: simple truncation
    """
    if not text or len(text) <= max_len:
        return text

    # Inline code: `command here`
    if text.startswith("`") and not text.startswith("```"):
        # Truncate inside the backtick, keep it closed
        inner = text[1:].rstrip("`")
        cut = max_len - 5  # room for ` ... `
        if cut > 0 and len(inner) > cut:
            return f"`{inner[:cut]}...`"
        return text

    # Code block: ```lang\ncontent\n```
    if text.startswith("```"):
        lines = text.split("\n")
        # first line is ```lang, last is ```
        if len(lines) >= 3:
            header = lines[0]
            footer = lines[-1]
            body = "\n".join(lines[1:-1])
            cut = max_len - len(header) - len(footer) - 10
            if cut > 0 and len(body) > cut:
                return f"{header}\n{body[:cut]}...\n{footer}"
        return text

    # Plain text / mixed markdown
    truncated = text[:max_len - 3] + "..."
    # Ensure bold markers (**) are properly closed
    if truncated.count("**") % 2 != 0:
        truncated += "**"
    return truncated


def _truncate_result(text: str) -> str:
    """Truncate result text for IM display."""
    clean = text.replace("\n", " ").strip()
    if len(clean) <= _MAX_RESULT_LEN:
        return clean
    return clean[:_MAX_RESULT_LEN - 3] + "..."

"""
sub_agent_notifier: ACP display push for sub-agent (run_subtask) runs.

Mirrors the todo_write_tool.py two-layer pattern: pure logic helpers plus a
best-effort ACP push that never breaks tool execution.
"""
import uuid
from dataclasses import asdict, dataclass
from typing import Optional

from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.logging import logger as logging

# Entry text limit mirrors frontend MAX_TEXT_LENGTH
# (siada_cli_ui/src/constants/limits.ts).
MAX_ENTRY_TEXT_LENGTH = 5000
MAX_SUMMARY_LENGTH = 500
MAX_TITLE_LENGTH = 60


@dataclass
class SubAgentItem:
    id: str          # "sa_" + uuid4 hex[:8]
    title: str       # first non-empty line of the instruction, truncated
    status: str      # "running" | "completed" | "failed"
    summary: str = ""


def new_sub_agent_id() -> str:
    return f"sa_{uuid.uuid4().hex[:8]}"


def make_title(instruction: str) -> str:
    first_line = next(
        (ln.strip() for ln in (instruction or "").splitlines() if ln.strip()),
        "",
    )
    if not first_line:
        return "(sub agent)"
    if len(first_line) > MAX_TITLE_LENGTH:
        return first_line[:MAX_TITLE_LENGTH] + "…"
    return first_line


def truncate_text(text: Optional[str], limit: int = MAX_ENTRY_TEXT_LENGTH) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n… (truncated)"


def _send_notification(method: str, params: dict) -> None:
    """Best-effort ACP custom notification push (mirrors _push_todo_state_via_acp)."""
    try:
        from siada.foundation.global_cache import get_global_cache, ACP_LEGACY_ADAPTER
        adapter = get_global_cache(ACP_LEGACY_ADAPTER)
        if adapter is None or not adapter.acp_enabled:
            return
        adapter._send_if_acp(
            adapter.builder.build_custom_notification,
            method=method,
            params=params,
        )
    except Exception as e:
        logging.debug(f"[sub_agent_notifier] push failed: {e}")


def _snapshot(context: CodeAgentContext) -> dict:
    return {"items": [asdict(item) for item in context.sub_agent_items]}


def start_sub_agent(context: Optional[CodeAgentContext], instruction: str) -> SubAgentItem:
    """Register a running sub-agent item and push the state snapshot."""
    item = SubAgentItem(id=new_sub_agent_id(), title=make_title(instruction), status="running")
    if context is not None:
        context.sub_agent_items.append(item)
        _send_notification("context/subAgentState", _snapshot(context))
    return item


def push_sub_agent_message(
    sa_id: str, kind: str, text: Optional[str], tool_name: Optional[str] = None
) -> None:
    """Append one content entry for a sub-agent run (incremental push)."""
    entry = {"kind": kind, "text": truncate_text(text)}
    if tool_name:
        entry["toolName"] = tool_name
    _send_notification("context/subAgentMessage", {"id": sa_id, "entry": entry})


def finish_sub_agent(
    context: Optional[CodeAgentContext], sa_id: str, status: str, summary: Optional[str]
) -> None:
    """Mark a sub-agent item completed/failed and push the state snapshot."""
    if context is None:
        return
    for item in context.sub_agent_items:
        if item.id == sa_id:
            item.status = status
            item.summary = truncate_text(summary, MAX_SUMMARY_LENGTH)
            break
    _send_notification("context/subAgentState", _snapshot(context))

"""
Lark (Feishu) notification tools for agents.

Provides tools that allow agents to send messages via Lark IM
through the daemon IPC mechanism. Tools are only available when
the daemon process is running and has an active Lark controller.

Usage::

    from siada.tools.lark import get_available_lark_tools

    # In agent __init__:
    lark_tools = get_available_lark_tools()          # general agent
    lark_tools = get_available_lark_tools(proactive=True)  # proactive agent
"""

from typing import TYPE_CHECKING, List

from agents import function_tool, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext, RuntimeSource
from siada.foundation.ipc_client import DaemonIPCClient
from siada.foundation.logging import logger  # project logger → file, not console

if TYPE_CHECKING:
    from siada.agent_hub.proactive.daemon import SiadaDaemon


# ── Tool documentation ────────────────────────────────────────────────

SEND_LARK_NOTIFICATION_DOCS = """Send a notification message to the user's Lark (Feishu) chat.

Use this tool when you want to proactively notify the user about something
via their Lark chat, for example:
- Task completion notifications
- Important status updates
- Error alerts that need immediate attention
- Progress reports

The message is sent as a fire-and-forget notification (not written into
the agent session history).

Args:
    message (str): The notification message content to send. Supports plain text.
        Keep messages concise and informative.

Returns:
    str: Success or failure description.

Examples:
    send_lark_notification("✅ Task completed: Bug fix for login page has been applied.")
    send_lark_notification("⚠️ Build failed with 3 errors. Please check the output.")
"""

SEND_DAILY_SUMMARY_TO_LARK_DOCS = """Send the daily work summary report to the user's Lark (Feishu) chat.

This is a dedicated tool for sending the daily summary report. Use it AFTER
you have generated and saved the daily summary to file. It sends the complete
summary content as a notification to the user's Lark chat so they can review
it conveniently on mobile or desktop.

Args:
    summary (str): The complete daily summary content you have already generated.
        Pass the full markdown text of the daily summary report.

Returns:
    str: Success or failure description.
"""


# ── Implementation functions ──────────────────────────────────────────

def _send_via_ipc(
    content: str,
    content_type: str = "markdown",
    session_id: str | None = None,
) -> str:
    """Send a message via daemon IPC. Returns status string."""
    try:
        with DaemonIPCClient() as client:
            if not client.is_connected:
                return "Error: Daemon is not running. Cannot send Lark notification."

            if session_id:
                result = client.send_lark_message(
                    content, session_id=session_id, content_type=content_type
                )
            else:
                result = client.send_lark_notification(content, content_type=content_type)
            if result is None:
                return "Error: Failed to send notification. Lark controller may not be active."

            if result.get("sent"):
                return "Notification sent successfully to Lark chat."
            else:
                reason = result.get("reason", "unknown")
                return f"Error: Notification not sent. Reason: {reason}"
    except Exception as e:
        logger.error("Failed to send Lark notification: %s", e, exc_info=True)
        return f"Error: Failed to send Lark notification: {e}"


# ── Tool functions ────────────────────────────────────────────────────

@function_tool(
    name_override="send_lark_notification",
    description_override=SEND_LARK_NOTIFICATION_DOCS,
)
def send_lark_notification(
    context: RunContextWrapper[CodeAgentContext],
    message: str,
) -> str:
    """Send a notification message to user's Lark chat."""
    # Graceful degradation: when running from Lark controller, the user is
    # already reading the conversation in Lark, so a separate IPC-based
    # notification is redundant and would fail. Return a friendly message
    # instead of crashing with ModelBehaviorError "Tool not found".
    runtime_source = getattr(context.context, "runtime_source", RuntimeSource.CLI) if context.context else RuntimeSource.CLI
    if runtime_source == RuntimeSource.LARK_CONTROLLER:
        return (
            "Notice: You are already communicating with the user via Lark chat. "
            "Your response will be delivered directly — no separate notification needed. "
            "Simply include the information in your reply."
        )

    if not message or not message.strip():
        return "Error: Message cannot be empty."

    session_id = context.context.session_id if context.context else None
    return _send_via_ipc(message.strip(), session_id=session_id)


@function_tool(
    name_override="send_daily_summary_to_lark",
    description_override=SEND_DAILY_SUMMARY_TO_LARK_DOCS,
)
def send_daily_summary_to_lark(
    context: RunContextWrapper[CodeAgentContext],
    summary: str,
) -> str:
    """Send the daily work summary to user's Lark chat.

    This tool runs inside the daemon process, so it calls the daemon's
    IM controller directly instead of going through IPC.
    """
    if not summary or not summary.strip():
        return "Error: Summary content cannot be empty."

    try:
        from siada.agent_hub.proactive.ipc_server import (
            get_daemon_instance,
            send_lark_message_direct,
        )

        daemon = get_daemon_instance()
        if daemon is None:
            return "Error: Daemon instance not available. Cannot send Lark notification."

        if not has_initialized_daemon_lark_controller(daemon):
            return "Error: Lark controller is not initialized in daemon. Cannot send Lark notification."

        result = send_lark_message_direct(
            daemon=daemon, content=summary.strip(), content_type="markdown"
        )

        if result.get("sent"):
            return "Notification sent successfully to Lark chat."
        else:
            reason = result.get("reason", "unknown")
            return f"Error: Notification not sent. Reason: {reason}"
    except Exception as e:
        logger.error("Failed to send daily summary to Lark: %s", e, exc_info=True)
        return f"Error: Failed to send Lark notification: {e}"


# ── Daemon status check & tool loader ─────────────────────────────────

def has_initialized_daemon_lark_controller(daemon: "SiadaDaemon | None" = None) -> bool:
    """Check whether the in-process daemon has initialized a Lark controller.

    This check is intended for proactive tools that run inside the daemon
    process and can inspect the daemon instance directly.
    """
    if daemon is None:
        try:
            from siada.agent_hub.proactive.ipc_server import get_daemon_instance

            daemon = get_daemon_instance()
        except Exception:
            return False

    if daemon is None:
        return False

    for controller in getattr(daemon, "im_controllers", []) or []:
        pname = getattr(controller, "platform_name", None) or ""
        if pname.startswith("lark"):
            return True
        if controller.__class__.__name__ in {"LarkController", "RelayLarkController"}:
            return True

    return False

def is_lark_active() -> bool:
    """Check if daemon is running and Lark controller is active.

    Returns:
        True if daemon is reachable and has an active Lark controller.
    """
    try:
        with DaemonIPCClient(timeout=2.0) as client:
            if not client.is_connected:
                return False
            status = client.lark_status()
            if status is None:
                return False
            return status.get("active", False)
    except Exception:
        return False


def get_available_lark_tools(proactive: bool = False) -> List:
    """Return Lark tools if daemon Lark controller is active.

    Checks daemon lark.status via IPC. If the Lark controller is not
    active, returns an empty list so the model cannot see these tools.

    Args:
        proactive: If True, also include proactive-only tools
                   (send_daily_summary_to_lark).

    Returns:
        List of function tools, or empty list if Lark is unavailable.
    """
    if proactive:
        return get_available_proactive_lark_tools()

    if not is_lark_active():
        logger.debug("Lark controller not active, skipping Lark tools")
        return []

    tools = [send_lark_notification]
    logger.info(
        "Lark tools enabled: %s",
        [t.name for t in tools],
    )
    return tools


def get_available_proactive_lark_tools() -> List:
    """Return proactive Lark tools using direct daemon inspection when needed.

    - ``send_lark_notification`` still depends on daemon IPC active status.
    - ``send_daily_summary_to_lark`` only depends on whether the current
      daemon instance has already initialized a Lark controller.
    """
    tools = []

    if has_initialized_daemon_lark_controller():
        tools.append(send_daily_summary_to_lark)

    if not tools:
        logger.debug("No proactive Lark tools available")
        return []

    logger.debug(
        "Proactive Lark tools enabled: %s",
        [t.name for t in tools],
    )
    return tools

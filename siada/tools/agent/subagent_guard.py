"""
Recursion guard for sub-agent tool execution.

Historically ``run_subtask`` prevented sub-agents from spawning further
sub-agents by simply never including ``run_subtask`` in the sub-agent's tool
list (see ``SubTaskAgent._build_default_tools``). That structural exclusion
breaks down for ``fork=True`` runs, where the sub-agent's tool list is
required to be byte-for-byte identical to the parent's (including
``run_subtask`` itself) so the tool-schema layer of the model's prompt cache
prefix stays aligned.

This module replaces "structurally absent" with "present but rejected at
execution time": ``DISABLED_FOR_SUBAGENT`` lists tool names that must not
actually run while ``CodeAgentContext.is_subagent`` is True. The tool's own
schema (name/params/description) is untouched — only the invocation is
intercepted, so cache alignment is unaffected.

``run_subtask`` is special-cased: when
``CodeAgentContext.allow_recursive_subagents`` is True (opt-in,
conf.yaml ``sub_agent.allow_recursive_subagents``), it is only blocked once
the nesting depth cap is reached (see ``subagent_recursion.MAX_NESTING_DEPTH``)
rather than unconditionally. When the switch is off (default), the legacy
"always blocked for any sub-agent" behaviour is preserved exactly.
"""
from typing import Optional

# Tool names that must not execute when running inside a sub-agent
# (CodeAgentContext.is_subagent is True). The tool is still visible in the
# schema (needed for fork's tool-list byte alignment) — only actual
# invocation is blocked. ``run_subtask`` gets depth-aware treatment (see
# module docstring) when recursion is enabled; all other entries here remain
# unconditionally blocked.
DISABLED_FOR_SUBAGENT: frozenset[str] = frozenset({"run_subtask"})


def rejection_message_for(tool_name: str) -> str:
    """Return the plain-text message returned to the model instead of running the tool."""
    return (
        f"The `{tool_name}` tool is not available to you. "
        "You are running as a sub-agent and cannot spawn further sub-agents. "
        "Continue the task yourself using your other tools."
    )


def is_blocked_for_subagent(tool_name: str, agent_context: Optional[object]) -> bool:
    """Return True if `tool_name` must be rejected given the current context.

    Args:
        tool_name: The tool's registered name (e.g. "run_subtask").
        agent_context: The CodeAgentContext for the current call, or None.

    Returns:
        True when `agent_context.is_subagent` is True AND `tool_name` is on
        the disabled list; False otherwise (including when agent_context is
        None, e.g. in tests that call the impl function directly).

        For ``run_subtask`` specifically, when
        ``agent_context.allow_recursive_subagents`` is True, the block is
        depth-aware: only a context already at the nesting depth cap
        (``subagent_depth >= subagent_recursion.MAX_NESTING_DEPTH``) is
        blocked; a depth-1 sub-agent is allowed through so it can spawn its
        own depth-2 sub-sub-agent.
    """
    if agent_context is None:
        return False
    if not getattr(agent_context, "is_subagent", False):
        return False
    if tool_name not in DISABLED_FOR_SUBAGENT:
        return False

    if tool_name == "run_subtask" and getattr(agent_context, "allow_recursive_subagents", False):
        from siada.tools.agent.subagent_recursion import MAX_NESTING_DEPTH

        depth = getattr(agent_context, "subagent_depth", 0)
        return depth >= MAX_NESTING_DEPTH

    return True

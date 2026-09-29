"""
Recursive sub-agent policy: nesting-depth cap + concurrency cap.

Gated entirely behind ``sub_agent.allow_recursive_subagents`` (conf.yaml,
default False). When the switch is OFF, none of the functions in this module
are ever consulted by ``run_subtask`` — the pre-existing behaviour (a
sub-agent can never spawn another sub-agent) is completely untouched. This
module only exists to implement the OPT-IN extension:

- **Depth cap (hard limit: 2 levels)**: main agent = depth 0, its sub-agents
  = depth 1, their sub-sub-agents = depth 2. A depth-2 agent is never allowed
  to spawn a further nested agent, regardless of the switch.
- **Concurrency cap (hard limit: 12 simultaneously alive agents)**: counted
  per "agent tree" (keyed by ``root_session_id``, the main agent's session
  id) and includes the main agent itself. A ``run_subtask`` call that would
  push the tree's alive-agent count over the cap is rejected up front —
  the sub-agent is never started.

Both counters are process-local (module-level dict), which is sufficient
because a given agent tree's main agent, sub-agents, and sub-sub-agents all
run in the same OS process (sub-agents are ``asyncio`` tasks/coroutines, not
separate processes).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

# Hard caps — not user-configurable; see design rationale in the module
# docstring above.
MAX_NESTING_DEPTH: int = 2
MAX_CONCURRENT_AGENTS: int = 12

# root_session_id -> count of currently alive NON-main agents (sub-agents +
# sub-sub-agents) for that tree. The main agent itself always counts as 1
# additional agent, so the cap check compares
# ``1 + alive_count`` (post-spawn) against MAX_CONCURRENT_AGENTS.
_ALIVE_SUBAGENTS: dict[str, int] = {}
_LOCK = threading.Lock()


@dataclass(frozen=True)
class RecursionDecision:
    """Result of ``check_can_spawn``: whether a new nested agent may start."""

    allowed: bool
    reason: str = ""
    child_depth: int = 0


def check_can_spawn(parent_depth: int, root_session_id: Optional[str]) -> RecursionDecision:
    """Decide whether a new child agent may be spawned under ``parent_depth``.

    Args:
        parent_depth: The depth of the agent that is ABOUT TO CALL
            run_subtask (0 for the main agent, 1 for a sub-agent, ...).
        root_session_id: The main agent's session id (tracking key for the
            concurrency counter). When None (e.g. no live session — some
            test paths), the concurrency check is skipped (fail-open, same
            posture as other root_session_id-keyed features in this
            codebase) but the depth check still applies.

    Returns:
        A RecursionDecision. ``child_depth`` is ``parent_depth + 1`` and is
        meaningful only when ``allowed`` is True.
    """
    child_depth = parent_depth + 1
    if child_depth > MAX_NESTING_DEPTH:
        return RecursionDecision(
            allowed=False,
            reason=(
                f"Nesting depth limit reached (max {MAX_NESTING_DEPTH} levels): "
                "a sub-sub-agent cannot spawn further nested agents."
            ),
        )

    if root_session_id is not None:
        with _LOCK:
            alive = _ALIVE_SUBAGENTS.get(root_session_id, 0)
            # +1 for the main agent itself, +1 for the child about to be spawned.
            if 1 + alive + 1 > MAX_CONCURRENT_AGENTS:
                return RecursionDecision(
                    allowed=False,
                    reason=(
                        f"Maximum concurrent agent count reached "
                        f"(max {MAX_CONCURRENT_AGENTS}, currently {1 + alive} alive "
                        "including the main agent): cannot start another sub-agent "
                        "right now. Wait for an existing sub-agent to finish, or "
                        "reduce the number of concurrently running sub-agents."
                    ),
                )

    return RecursionDecision(allowed=True, child_depth=child_depth)


def register_alive(root_session_id: Optional[str]) -> None:
    """Record that one more non-main agent is now alive for ``root_session_id``."""
    if root_session_id is None:
        return
    with _LOCK:
        _ALIVE_SUBAGENTS[root_session_id] = _ALIVE_SUBAGENTS.get(root_session_id, 0) + 1


def release_alive(root_session_id: Optional[str]) -> None:
    """Record that one non-main agent has finished (success/failure/cancel) for ``root_session_id``.

    Safe to call even if the tree was never registered (no-op floor at 0).
    """
    if root_session_id is None:
        return
    with _LOCK:
        current = _ALIVE_SUBAGENTS.get(root_session_id, 0)
        if current <= 1:
            _ALIVE_SUBAGENTS.pop(root_session_id, None)
        else:
            _ALIVE_SUBAGENTS[root_session_id] = current - 1


def alive_count(root_session_id: Optional[str]) -> int:
    """Return the number of currently alive non-main agents for ``root_session_id``."""
    if root_session_id is None:
        return 0
    with _LOCK:
        return _ALIVE_SUBAGENTS.get(root_session_id, 0)

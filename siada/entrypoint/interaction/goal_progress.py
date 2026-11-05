"""Adapt shared goal lifecycle notifications to run-local console progress."""

from siada.foundation.execution_progress import publish_execution_progress


def publish_goal_progress(method: str, params: dict) -> None:
    """Present live goal events without replaying historical verification results."""
    if method != "context/goalState":
        return
    goal = params.get("goal")
    if not isinstance(goal, dict):
        return

    # latestResult belongs to UI history; only result describes a new verdict.
    result = params.get("result")
    result = result if isinstance(result, dict) else {}
    turns = result.get("turns", goal.get("turns", 0))
    elapsed = result.get("elapsedSeconds", goal.get("elapsedSeconds", 0))
    status = goal.get("status")

    if params.get("verifying"):
        label = "Goal verifying"
    elif result:
        if result.get("achieved") is True:
            label = "Goal achieved"
        elif status == "blocked":
            label = "Goal blocked"
        elif result.get("outcome") == "system_error":
            label = "Goal verification error"
        else:
            label = "Goal not achieved"
    else:
        label = {
            "active": "Goal started" if turns == 0 else "Goal continuing",
            "paused": "Goal paused",
            "blocked": "Goal blocked",
            "complete": "Goal complete",
        }.get(status, "Goal state")

    statistics = f"rounds: {turns}, elapsed: {int(elapsed)}s"
    tokens = result.get("tokensUsed")
    if tokens is not None:
        statistics += f", tokens: {tokens:,}"
    lines = [f"[{label}] {goal.get('objective', '')} ({statistics})"]
    for field, title in (("reason", "Reason"), ("nextAction", "Next action")):
        if result.get(field):
            lines.append(f"{title}: {result[field]}")
    if params.get("notice"):
        lines.append(f"Notice: {params['notice']}")

    publish_execution_progress("\n".join(lines))
"""Goal turn hooks shared by entrypoint policies.

Notifications use an injected callback; goal state and verification remain
independent of the transport and terminal presentation.
"""

import asyncio
from typing import Callable, Optional

from siada.foundation.logging import logger as logging
from siada.session.session_models import RunningSession


def push_goal_state_via_acp(
    send_acp_notification: Callable[[str, dict], None],
    goal,
    verifying: bool = False,
    notice: Optional[str] = None,
    result: Optional[dict] = None,
) -> None:
    """Push current goal state to the frontend via ACP custom notification.

    ``send_acp_notification`` is expected to already no-op safely when not
    running in ACP mode (mirrors Controller._send_acp_notification's own
    ``_send_if_acp`` guard), so no extra check is needed here.

    ``result`` is an optional one-shot payload (achieved/elapsedSeconds/
    turns/tokensUsed/objective/reason/nextAction) attached only on a
    verifier pass or a non-blocked fail — the frontend turns this into a
    persistent collapsible "Goal achieved / not yet achieved (...)" chat
    message (see App.tsx's effect on goalState.result), distinct from
    ``notice`` which only drives the transient flash banner.
    """
    params = {
        "goal": {
            "objective": goal.objective,
            "status": goal.status,
            # ISO-8601 'Z'-suffixed timestamp (Goal.created_at) — lets the
            # frontend status bar render a live "Nm Ns" elapsed-time counter
            # next to the status label without needing a server round trip
            # every second.
            "createdAt": goal.created_at,
            # Total verifier rounds run so far against this goal (see
            # Goal.turns / maybe_run_goal_verifier). Surfaced in the
            # persistent GoalStatusBar (not just the one-shot achieved/
            # not-yet-achieved `result` payload) so the user can see
            # progress ticking up in real time while verification is
            # still ongoing.
            "turns": goal.turns,
        },
        "verifying": verifying,
    }


    if notice:
        params["notice"] = notice
    if result:
        params["result"] = result
    send_acp_notification("context/goalState", params)


def maybe_reset_goal_on_new_turn(
    send_acp_notification: Callable[[str, dict], None],
    turn,
    session: RunningSession,
    session_dir,
    *,
    user_initiated: bool = True,
) -> None:
    """Normalize a stale goal right before a new conversation turn starts.

    - "complete": the objective was already verified as reached in a
      previous turn. A fresh user message means the user has moved on,
      so drop the goal entirely (context + goal.json) rather than leaving
      a "Goal complete" status bar lingering forever.
    - "blocked": the user typing again after N consecutive verifier
      failures is itself a signal they want to keep going. Reactivate
      the goal and reset the failure counter instead of requiring an
      explicit ``/goal resume``.

    Only applies to user-initiated conversation turns — slash commands and
    internal retry/background-feedback turns do not mean the user wants to
    resume a blocked goal.
    """
    from siada.entrypoint.interaction.turn.models import TurnType
    if not user_initiated or turn.get_turn_type() != TurnType.CONVERSATION:
        return

    from siada.services.siada_runner import SiadaRunner
    workspace = getattr(getattr(session, "siada_config", None), "workspace", None)
    context = None
    for (_, ws), ctx in SiadaRunner._context_cache.items():
        if ws == workspace:
            context = ctx
            break

    goal = getattr(context, "goal", None) if context is not None else None
    if goal is None:
        return

    from siada.services.goal import goal_storage

    if goal.status == "complete":
        if session_dir is not None:
            # Archive before clearing -- goal.json only ever holds the
            # current goal, so this is the only remaining record of it.
            goal_storage.append_goal_history(session_dir, goal)
        if context is not None:
            context.goal = None
        if session_dir is not None:
            goal_storage.clear_goal(session_dir)
        send_acp_notification("context/goalState", {"goal": None, "verifying": False})
        return

    if goal.status == "blocked":
        goal.status = "active"
        goal.consecutive_failures = 0
        goal.consecutive_system_errors = 0
        # Reactivating is a meaningful restart of work on this goal, so let
        # the model see the reminder again on the very next turn — mirrors
        # a brand new goal via Goal.create() (see
        # SiadaRunner._maybe_merge_goal_reminder / Goal.reminder_injected).
        goal.reminder_injected = False
        goal.touch()

        if session_dir is not None:
            goal_storage.save_goal(session_dir, goal)
        push_goal_state_via_acp(
            send_acp_notification,
            goal,
            verifying=False,
            notice="Goal resumed — continuing verification.",
        )


# OS-level notification APIs (e.g. macOS's osascript "display notification")
# have length limits and get truncated/garbled with very long strings --
# goal.objective is free-form user text and can be arbitrarily long, so it
# must be capped before being embedded in the notification message.
_NOTIFICATION_OBJECTIVE_MAX_LEN = 80


def _truncate_for_notification(text: str, max_len: int = _NOTIFICATION_OBJECTIVE_MAX_LEN) -> str:
    """Truncate free-form text (e.g. goal.objective) for a system notification."""
    if not text or len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _maybe_show_completion_notification(enable_notification: bool, message: str) -> None:
    """Fire the OS-level completion notification for a /goal terminal state.

    This is the *only* place a /goal task triggers the system notification.
    The generic per-turn notification in ConversationTurn.execute() is
    suppressed for as long as the goal stays "active" (see
    ConversationTurn._has_active_goal) specifically so it does not fire on
    every intermediate verifier retry round -- only once the goal actually
    reaches a terminal state (achieved, or blocked after too many
    consecutive failures) does the user get notified.

    ``message`` should already have any free-form text (e.g. goal.objective)
    truncated via ``_truncate_for_notification`` by the caller.
    """
    if not enable_notification:
        return
    try:
        from siada.notifications import show_completion_notification
        show_completion_notification(message=message)
    except Exception as e:
        logging.warning(f"[goal_turn_hooks] Failed to show completion notification: {e}")


def maybe_run_goal_verifier(
    send_acp_notification: Callable[[str, dict], None],
    turn,
    session: RunningSession,
    session_dir,
    result,
    enable_notification: bool = True,
):
    """After a conversation turn ends, if this session has an active
    /goal, run the independent verifier and either mark the goal
    complete/blocked or force another turn with the verifier's feedback.

    Deliberately NOT routed through the plugin HookRunner (hooks.json) —
    that system is for user-authored shell commands; this needs a real
    LLM call with structured output. See
    design_docs/goal-command-implementation-plan.md §3.1.

    Only runs for conversation turns — slash commands (including /goal
    itself) don't represent progress toward the goal, so checking after
    them would be meaningless (or, worse, would immediately re-question
    a just-issued /goal pause).

    ``enable_notification`` gates the OS-level system notification fired
    when the goal reaches a terminal state (achieved, or blocked after too
    many consecutive failures) -- see ``_maybe_show_completion_notification``.
    """
    from siada.entrypoint.interaction.turn.models import TurnType, TurnOutput
    if result is None or turn.get_turn_type() != TurnType.CONVERSATION:
        return result

    from siada.services.siada_runner import SiadaRunner
    workspace = getattr(getattr(session, "siada_config", None), "workspace", None)
    context = None
    for (_, ws), ctx in SiadaRunner._context_cache.items():
        if ws == workspace:
            context = ctx
            break

    goal = getattr(context, "goal", None) if context is not None else None
    if goal is None or getattr(goal, "status", None) != "active":
        return result

    file_session = session.openai_session
    if file_session is None or session_dir is None:
        return result

    from siada.services.goal.verifier import (
        run_goal_verification,
        elapsed_seconds_since,
        tokens_used_for,
    )
    from siada.services.goal import goal_storage
    from siada.services.goal.models import (
        GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS,
        GOAL_MAX_TURNS,
    )
    from siada.services.goal.prompts import build_goal_reminder_text
    from siada.support.slash_commands import SwitchEvent


    push_goal_state_via_acp(send_acp_notification, goal, verifying=True)

    # Every verifier round counts as one "turn" toward this goal,
    # regardless of the outcome — surfaced to the frontend as "N turns"
    # in the Goal achieved/not-yet-achieved summary line.
    goal.turns += 1
    try:
        max_turns = max(1, int(getattr(context, "goal_max_turns", GOAL_MAX_TURNS)))
    except (TypeError, ValueError):
        max_turns = GOAL_MAX_TURNS

    def block_goal(notice: str, verdict=None, next_action: str = ""):
        goal.status = "blocked"
        goal.touch()
        goal_storage.save_goal(session_dir, goal)
        result_payload = {
            "achieved": False,
            "elapsedSeconds": elapsed_seconds_since(goal.created_at),
            "turns": goal.turns,
            "tokensUsed": tokens_used_for(context),
            "objective": goal.objective,
        }
        if verdict is not None:
            result_payload.update({
                "reason": verdict.reason,
                "nextAction": next_action,
            })
        push_goal_state_via_acp(
            send_acp_notification,
            goal,
            verifying=False,
            notice=notice,
            result=result_payload,
        )
        _maybe_show_completion_notification(
            enable_notification,
            f"Goal paused: {_truncate_for_notification(goal.objective)}",
        )
        return result

    try:
        verdict = asyncio.run(
            run_goal_verification(file_session, goal, context)
        )
    except Exception as e:
        # run_goal_verification/verify_goal_with_context already fail safe on
        # every exception they know about and return a systemError=True
        # GoalVerdict instead of raising (see verifier.py) -- reaching this
        # except means something blew up even before a verdict could be
        # constructed (e.g. build_verifier_input itself). Treat it exactly
        # like a systemError verdict: count it against the small
        # GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS budget so a persistently broken
        # verifier still surfaces to the user quickly instead of retrying
        # forever with no counter moving at all.
        logging.warning(f"[goal_turn_hooks] Goal verification crashed: {e}")
        goal.consecutive_system_errors += 1
        if goal.consecutive_system_errors >= GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS:
            goal.status = "blocked"
            goal.touch()
            goal_storage.save_goal(session_dir, goal)
            push_goal_state_via_acp(
                send_acp_notification,
                goal,
                verifying=False,
                notice=(
                    f"Goal verification hit a system error "
                    f"{GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS} times in a row — "
                    "paused auto-retry. Review the goal or use /goal resume "
                    "to try again."
                ),
            )
            _maybe_show_completion_notification(
                enable_notification,
                f"Goal paused (system error): {_truncate_for_notification(goal.objective)}",
            )
            return result
        goal.touch()
        goal_storage.save_goal(session_dir, goal)
        push_goal_state_via_acp(send_acp_notification, goal, verifying=False)
        return result

    if verdict.passed:
        goal.status = "complete"
        goal.consecutive_system_errors = 0
        goal.touch()
        goal_storage.save_goal(session_dir, goal)
        achieved_result = {
            "achieved": True,
            "elapsedSeconds": elapsed_seconds_since(goal.created_at),
            "turns": goal.turns,
            "tokensUsed": tokens_used_for(context),
            "objective": goal.objective,
            "reason": verdict.reason,
        }
        push_goal_state_via_acp(
            send_acp_notification,
            goal,
            verifying=False,
            notice=f"Goal reached: {goal.objective}",
            result=achieved_result,
        )
        # The goal is now genuinely done -- this is the one and only point
        # a /goal task should trigger the OS-level completion notification,
        # not the per-round notification in ConversationTurn.execute().
        _maybe_show_completion_notification(
            enable_notification,
            f"Goal reached: {_truncate_for_notification(goal.objective)}",
        )
        return result

    if getattr(verdict, "systemError", False):
        # A system-error verdict is not a genuine verification judgment and
        # therefore has no model-generated nextAction to drive continuation.
        # Let the dedicated system-error breaker below govern retries.
        goal.consecutive_system_errors += 1
        if goal.consecutive_system_errors >= GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS:
            goal.status = "blocked"
            goal.touch()
            goal_storage.save_goal(session_dir, goal)
            push_goal_state_via_acp(
                send_acp_notification,
                goal,
                verifying=False,
                notice=(
                    f"Goal verification hit a system error "
                    f"{GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS} times in a row — "
                    "paused auto-retry. Review the goal or use /goal resume "
                    "to try again."
                ),
            )
            _maybe_show_completion_notification(
                enable_notification,
                f"Goal paused (system error): {_truncate_for_notification(goal.objective)}",
            )
            return result

        goal.touch()
        goal_storage.save_goal(session_dir, goal)

        next_action = getattr(verdict, "nextAction", "") or ""
        feedback = build_goal_reminder_text(
            goal,
            verifier_reason=verdict.reason,
            verifier_next_action=next_action,
            elapsed_seconds=elapsed_seconds_since(goal.created_at),
        )
        not_yet_result = {
            "achieved": False,
            "elapsedSeconds": elapsed_seconds_since(goal.created_at),
            "turns": goal.turns,
            "tokensUsed": tokens_used_for(context),
            "objective": goal.objective,
            "reason": verdict.reason,
            "nextAction": next_action,
        }
        push_goal_state_via_acp(
            send_acp_notification,
            goal,
            verifying=False,
            notice="Goal check hit a system error, retrying…",
            result=not_yet_result,
        )
        metadata = result.metadata if result is not None else {}
        return TurnOutput(
            output=SwitchEvent(ai_analysis_prompt=feedback),
            metadata=metadata,
            next_action=None,
        )

    # Genuine judgment (not a system error) -- reset the system-error streak
    # and fall through to the ordinary consecutive_failures bookkeeping.
    goal.consecutive_system_errors = 0

    goal.consecutive_failures += 1
    next_action = getattr(verdict, "nextAction", "") or ""
    next_action = next_action.strip()
    if not next_action:
        return block_goal(
            "Goal verifier returned no next action — paused automatic continuation.",
            verdict=verdict,
        )

    if goal.consecutive_failures >= max_turns:
        return block_goal(
            f"Goal failed verification {max_turns} consecutive times — "
            "paused auto-retry.",
            verdict=verdict,
            next_action=next_action,
        )

    goal.touch()
    goal_storage.save_goal(session_dir, goal)
    # Reuses the same rich <system-reminder> shape the model already sees
    # on the ordinary once-per-activation / post-compaction reminders,
    # instead of the old bare "Goal check feedback:\n[objective]: reason"
    # one-liner (GOAL_FEEDBACK_TEMPLATE) — see build_goal_reminder_text's
    # verifier_reason/verifier_next_action docstring for the full
    # rationale. This carries the objective, the verifier's own reason,
    # next action, and elapsed time in one consistent format.

    feedback = build_goal_reminder_text(
        goal,
        verifier_reason=verdict.reason,
        verifier_next_action=next_action,
        elapsed_seconds=elapsed_seconds_since(goal.created_at),
    )


    not_yet_result = {

        "achieved": False,
        "elapsedSeconds": elapsed_seconds_since(goal.created_at),
        "turns": goal.turns,
        "tokensUsed": tokens_used_for(context),
        "objective": goal.objective,
        "reason": verdict.reason,
        "nextAction": next_action,
    }
    push_goal_state_via_acp(
        send_acp_notification,
        goal,
        verifying=False,
        notice="Goal check: not yet met, continuing…",
        result=not_yet_result,
    )

    metadata = result.metadata if result is not None else {}
    return TurnOutput(
        output=SwitchEvent(ai_analysis_prompt=feedback),
        metadata=metadata,
        next_action=None,
    )

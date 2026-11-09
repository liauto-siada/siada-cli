"""Goal turn hooks shared by entrypoint policies.

Notifications use an injected callback; goal state and verification remain
independent of the transport and terminal presentation.
"""

import uuid
from typing import TYPE_CHECKING, Callable, Optional

from siada.foundation.logging import logger as logging
from siada.session.session_models import RunningSession

if TYPE_CHECKING:
    from pathlib import Path
    from siada.services.goal.models import Goal


def goal_state_payload(goal: "Goal") -> dict:
    """Build the same lifecycle/timing snapshot for every Goal notification."""
    from siada.services.goal.models import _now_iso

    timestamp = _now_iso()
    return {
        "objective": goal.objective,
        "status": goal.status,
        "createdAt": goal.created_at,
        "updatedAt": goal.updated_at,
        "turns": goal.turns,
        "elapsedSeconds": goal.elapsed_seconds(timestamp),
        "elapsedUpdatedAt": timestamp,
    }


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

    ``result`` is a one-shot display verdict, including failures and system
    errors. Persisted records provide stable identities for UI replay.
    ``latestResult`` remains available during subsequent verification, while
    ``notice`` only drives a transient flash.
    """
    params = {
        "goal": goal_state_payload(goal),
        "verifying": verifying,
    }


    if notice:
        params["notice"] = notice
    if result:
        params["result"] = result
    records = getattr(goal, "verification_results", None)
    if records:
        params["latestResult"] = records[-1]
    send_acp_notification("context/goalState", params)


def _record_goal_result(
    session_dir: "Path", goal: "Goal", payload: dict, *,
    outcome: str, continuing: bool = False,
) -> None:
    """Persist a display verdict with an identity stable across UI reconnects."""
    from siada.services.goal import goal_storage
    from siada.services.goal.models import _now_iso

    payload.update({
        "id": uuid.uuid4().hex,
        "timestamp": _now_iso(),
        "outcome": outcome,
        "continuing": continuing,
    })
    goal.verification_results.append(dict(payload))
    goal.touch()
    goal_storage.save_goal(session_dir, goal)


def pause_goal_on_interrupt(
    send_acp_notification: Callable[[str, dict], None],
    session: RunningSession,
    session_dir,
    *,
    notice: Optional[str] = None,
) -> bool:
    """Freeze an active goal's clock when a turn is interrupted or the CLI exits.

    An interruption does not abandon the objective, so the goal only moves to
    ``paused``: ``maybe_reset_goal_on_new_turn`` reactivates it when the user
    sends the next conversational message. Persisting the transition is what
    stops ``Goal.elapsed_seconds()`` from counting the idle gap, both in the
    status bar and after the session is restored.

    Returns True when an active goal was paused, False when there was nothing
    to pause (no goal, or it is already blocked/paused/complete).
    """
    from siada.services.goal import goal_storage
    from siada.services.siada_runner import SiadaRunner

    context = SiadaRunner.find_session_context(session)
    goal = getattr(context, "goal", None) if context is not None else None
    state = getattr(session, "state", None)
    pending_goal = getattr(state, "pending_goal", None)
    # Mirror the resolution order of maybe_reset_goal_on_new_turn: a staged
    # goal (e.g. restored by /resume) wins over a stale cached context.
    if getattr(state, "pending_goal_loaded", False) or pending_goal is not None:
        goal = pending_goal
    if goal is None and session_dir is not None:
        goal = goal_storage.load_goal(session_dir)
    if goal is None or getattr(goal, "status", None) != "active":
        return False

    goal.set_status("paused")
    if session_dir is not None:
        goal_storage.save_goal(session_dir, goal)
    push_goal_state_via_acp(
        send_acp_notification, goal, verifying=False, notice=notice,
    )
    return True


def maybe_reset_goal_on_new_turn(
    send_acp_notification: Callable[[str, dict], None],
    turn,
    session: RunningSession,
    session_dir,
    *,
    user_initiated: bool = True,
) -> None:
    """Normalize the standing goal right before a new conversation turn starts.

    - "complete": display the final state while waiting. Archive and clear
      it when the user starts a new conversational turn.
    - "blocked": the user typing again after N consecutive verifier
      failures is itself a signal they want to keep going. Reactivate
      the goal and reset the failure counter when the user sends a new
      conversational message.
    - "paused": the turn pursuing the goal was interrupted (see
      ``pause_goal_on_interrupt``) or the CLI exited. A new user message is
      the signal to continue, so reactivate the goal while keeping both the
      accumulated elapsed time and the failure counters — pausing is not a
      fresh retry budget.
    - anything else (active): re-push the unchanged snapshot so the
      frontend can recover its status bar after losing local state.

    Only applies to user-initiated conversation turns. Slash commands and
    internal retry/background-feedback turns preserve completed goals and
    do not resume blocked goals.
    """
    from siada.entrypoint.interaction.turn.models import TurnType
    if not user_initiated or turn.get_turn_type() != TurnType.CONVERSATION:
        return

    from siada.services.siada_runner import SiadaRunner
    context = SiadaRunner.find_session_context(session)

    goal = getattr(context, "goal", None) if context is not None else None
    # TurnPolicy runs before the runner consumes resumed state. A staged
    # goal (including an explicit clear) takes precedence over cached context.
    state = getattr(session, "state", None)
    pending_goal = getattr(state, "pending_goal", None)
    goal_staged = getattr(state, "pending_goal_loaded", False) or pending_goal is not None
    if goal_staged:
        goal = pending_goal
    if goal is None:
        return

    from siada.services.goal import goal_storage

    if goal.status == "complete":
        if session_dir is not None:
            goal_storage.append_goal_history(session_dir, goal)
        if context is not None:
            context.goal = None
        if goal_staged:
            state.pending_goal = None
        if session_dir is not None:
            goal_storage.clear_goal(session_dir)
        send_acp_notification("context/goalState", {"goal": None, "verifying": False})
        return

    if goal.status == "blocked":
        goal.set_status("active")
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
        return

    if goal.status == "paused":
        # An interrupted (or exited) goal keeps its accumulated time and
        # failure counters; only a genuine blocked->active retry resets them.
        goal.set_status("active")
        if session_dir is not None:
            goal_storage.save_goal(session_dir, goal)
        push_goal_state_via_acp(
            send_acp_notification,
            goal,
            verifying=False,
            notice="Goal resumed — continuing verification.",
        )
        return

    # An unchanged active goal still gets a fresh snapshot on every
    # user-initiated conversation turn. The status bar is rendered purely from
    # these pushes, so a frontend that lost its local copy -- history
    # replacement (e.g. /model's ui/loadHistory, which resets goalState), a
    # dropped notification, or a verifying=True push whose verification round
    # was interrupted -- would otherwise show no goal (or a stuck "Verifying…")
    # until the next verifier round, which can be hours away mid-turn.
    push_goal_state_via_acp(send_acp_notification, goal, verifying=False)


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


async def maybe_run_goal_verifier(
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
    them would be meaningless.

    ``enable_notification`` gates the OS-level system notification fired
    when the goal reaches a terminal state (achieved, or blocked after too
    many consecutive failures) -- see ``_maybe_show_completion_notification``.
    """
    from siada.entrypoint.interaction.turn.models import (
        GOAL_VERIFICATION_METADATA_KEY, TurnType, TurnOutput,
    )
    if result is None or turn.get_turn_type() != TurnType.CONVERSATION:
        return result

    from siada.services.siada_runner import SiadaRunner
    context = SiadaRunner.find_session_context(session)

    goal = getattr(context, "goal", None) if context is not None else None
    if goal is None or getattr(goal, "status", None) != "active":
        return result

    file_session = session.openai_session
    if file_session is None or session_dir is None:
        return result

    from siada.services.goal.verifier import (
        run_goal_verification,
        tokens_used_for,
    )
    from siada.services.goal import goal_storage
    from siada.services.goal.models import (
        GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS,
        GOAL_MAX_TURNS,
        GoalVerdict,
    )
    from siada.services.goal.prompts import build_goal_reminder_text
    from siada.support.slash_commands import SwitchEvent


    # Every verifier round counts as one "turn" toward this goal,
    # regardless of the outcome — surfaced to the frontend as "N turns"
    # in the Goal achieved/not-yet-achieved summary line.
    goal.turns += 1
    goal.touch()
    goal_storage.save_goal(session_dir, goal)
    push_goal_state_via_acp(send_acp_notification, goal, verifying=True)
    try:
        max_turns = max(1, int(getattr(context, "goal_max_turns", GOAL_MAX_TURNS)))
    except (TypeError, ValueError):
        max_turns = GOAL_MAX_TURNS

    system_error_notice = (
        f"Goal verification hit a system error "
        f"{GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS} times in a row — "
        "paused auto-retry. Send a new message to resume work "
        "and retry verification."
    )

    def record_blocked_goal(notice: str, verdict: GoalVerdict | None = None) -> TurnOutput:
        result.metadata = {
            **result.metadata,
            GOAL_VERIFICATION_METADATA_KEY: {
                "status": "blocked",
                "objective": goal.objective,
                "reason": getattr(verdict, "reason", "") or notice,
                "notice": notice,
            },
        }
        return result

    def block_goal(notice: str, verdict=None, next_action: str = ""):
        goal.set_status("blocked")
        goal_storage.save_goal(session_dir, goal)
        result_payload = {
            "achieved": False,
            "elapsedSeconds": int(goal.elapsed_seconds()),
            "turns": goal.turns,
            "tokensUsed": tokens_used_for(context),
            "objective": goal.objective,
        }
        if verdict is not None:
            result_payload.update({
                "reason": verdict.reason,
                "nextAction": next_action,
            })
        _record_goal_result(session_dir, goal, result_payload, outcome="blocked")
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
        return record_blocked_goal(notice, verdict)

    try:
        verdict = await run_goal_verification(file_session, goal, context)
    except Exception as e:
        # Input assembly can fail before the verifier constructs a verdict.
        # Use the same bounded continuation path as returned system errors.
        logging.warning(f"[goal_turn_hooks] Goal verification crashed: {e}")
        verdict = GoalVerdict(
            passed=False,
            reason=f"Goal verification could not finish: {e}",
            systemError=True,
        )

    if verdict.passed:
        goal.set_status("complete")
        goal.consecutive_system_errors = 0
        goal.touch()
        goal_storage.save_goal(session_dir, goal)
        achieved_result = {
            "achieved": True,
            "elapsedSeconds": int(goal.elapsed_seconds()),
            "turns": goal.turns,
            "tokensUsed": tokens_used_for(context),
            "objective": goal.objective,
            "reason": verdict.reason,
        }
        _record_goal_result(session_dir, goal, achieved_result, outcome="achieved")
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
            goal.set_status("blocked")
            goal_storage.save_goal(session_dir, goal)
            error_result = {
                "achieved": False,
                "elapsedSeconds": int(goal.elapsed_seconds()),
                "turns": goal.turns,
                "tokensUsed": tokens_used_for(context),
                "objective": goal.objective,
                "reason": verdict.reason,
                "nextAction": "Send a new message to retry, or use /goal clear to remove the goal.",
            }
            _record_goal_result(session_dir, goal, error_result, outcome="system_error")
            push_goal_state_via_acp(
                send_acp_notification,
                goal,
                verifying=False,
                notice=system_error_notice,
                result=error_result,
            )
            _maybe_show_completion_notification(
                enable_notification,
                f"Goal paused (system error): {_truncate_for_notification(goal.objective)}",
            )
            return record_blocked_goal(system_error_notice, verdict)

        goal.touch()
        goal_storage.save_goal(session_dir, goal)

        next_action = getattr(verdict, "nextAction", "") or ""
        feedback = build_goal_reminder_text(
            goal,
            verifier_reason=verdict.reason,
            verifier_next_action=next_action,
            elapsed_seconds=int(goal.elapsed_seconds()),
        )
        not_yet_result = {
            "achieved": False,
            "elapsedSeconds": int(goal.elapsed_seconds()),
            "turns": goal.turns,
            "tokensUsed": tokens_used_for(context),
            "objective": goal.objective,
            "reason": verdict.reason,
            "nextAction": next_action,
        }
        _record_goal_result(session_dir, goal, not_yet_result, outcome="system_error", continuing=True)
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
        elapsed_seconds=int(goal.elapsed_seconds()),
    )


    not_yet_result = {

        "achieved": False,
        "elapsedSeconds": int(goal.elapsed_seconds()),
        "turns": goal.turns,
        "tokensUsed": tokens_used_for(context),
        "objective": goal.objective,
        "reason": verdict.reason,
        "nextAction": next_action,
    }
    _record_goal_result(session_dir, goal, not_yet_result, outcome="not_achieved", continuing=True)
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

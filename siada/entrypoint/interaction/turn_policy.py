"""
Turn Policy Module

Turn-level policy layer extracted from ``Controller``: hook ordering around a
turn (PreTurn -> UserPromptSubmit -> Stop -> PostTurn / OnError), auto-retry
priority over goal verification, background sub-agent completion awaiting, and
session start/end lifecycle hooks.

The policy deliberately owns no input-loop and no UI responsibilities:

* background sub-agent *wakeup* registration stays with the controller's input
  loop (``_on_background_subtask_wakeup`` / ``register_session_wakeup`` are NOT
  migrated here);
* all WaitingSpinner/Rich rendering is dropped -- notifications are emitted
  through the injected ``send_notification`` callback;
* an ownership conflict makes ``execute`` return ``None`` so the controller
  can stop the animation after the IO warning.

Construction is light: no agent preloading, no real IO.
"""

import asyncio
from typing import TYPE_CHECKING

from siada.foundation.logging import logger as logging
from siada.session.session_models import RunningSession

if TYPE_CHECKING:
    from siada.entrypoint.interaction.running_config import RunningConfig
    from siada.support.slash_commands import SlashCommands


class TurnPolicy:
    """Executes turn-level policy: session lifecycle, hook ordering, retry,
    goal verification and background sub-agent completion awaiting."""

    # Max consecutive automatic retries for any single retry_reason.
    # Bounded so a persistently broken provider/model doesn't retry forever.
    _MAX_AUTO_RETRIES = 3

    # Grace period given to still-running run_subtask(async=True) background
    # sub-agent tasks when a conversation turn's model output looks final
    # (no more tool calls) -- see _maybe_await_background_subtask_summary.
    _BACKGROUND_SUBTASK_AWAIT_TIMEOUT = 30.0

    def __init__(
        self,
        config: "RunningConfig",
        slash_commands: "SlashCommands",
        send_notification,
    ):
        """Create the turn policy.

        ``config`` and ``slash_commands`` are the same objects the controller
        holds. Construction performs no preload or IO; execution reports hook
        and ownership warnings through ``config.io``.

        ``send_notification`` is the injected notification callback with the
        signature ``(method: str, params: dict) -> None`` (replaces the
        controller's ``_send_acp_notification`` which wrote through
        ``config.io.acp_adapter``).
        """
        self.config = config
        self.slash_commands = slash_commands
        self._send_acp_notification = send_notification
        self._session_end_fired = False  # Prevent SessionEnd firing twice
        self._auto_retry_count = 0  # Consecutive-retry streak for _maybe_retry_turn's retry_reason mechanism

    # ── session lifecycle ────────────────────────────────────────────────

    def start_session(self, session: RunningSession) -> None:
        """Fire the SessionStart hook once with the session context."""
        hook_runner = getattr(self.slash_commands, "hook_runner", None)
        if hook_runner is None:
            return
        try:
            hook_runner.run("SessionStart", self._build_session_hook_context(session))
        except Exception as e:
            logging.warning(f"[TurnPolicy] SessionStart hook error: {e}")

    def end_session(self, session: RunningSession, exit_reason: str) -> None:
        """Fire SessionEnd hook exactly once regardless of exit path."""
        if self._session_end_fired:
            return
        self._session_end_fired = True

        # Await (or cancel, on timeout) any still-running run_subtask(async=True)
        # background tasks for this session so none are silently dropped when
        # the process exits.
        #
        # These tasks were scheduled via asyncio.create_task() on
        # ConversationTurn's dedicated background-loop thread (see
        # _ensure_dedicated_loop), NOT on whatever loop asyncio.run() would
        # spin up here on the main thread. asyncio.gather()-ing Tasks that
        # belong to a different loop raises immediately, so this must be
        # dispatched onto that same dedicated loop via
        # run_coroutine_threadsafe -- mirroring how conversation_turn.py
        # itself talks to that loop.
        try:
            from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
            from siada.tools.agent.subagent_async import (
                has_pending_background_subtasks,
                shutdown_session_background_subtasks,
            )
            session_id = session.session_id
            dedicated_loop = ConversationTurn._dedicated_loop
            if has_pending_background_subtasks(session_id):
                if dedicated_loop is not None and not dedicated_loop.is_closed():
                    future = asyncio.run_coroutine_threadsafe(
                        shutdown_session_background_subtasks(session_id),
                        dedicated_loop,
                    )
                    future.result(timeout=35.0)
                else:
                    # No dedicated loop alive (e.g. background tasks somehow
                    # outlived their loop's thread) -- fall back to a fresh
                    # loop; the awaited tasks are already done()/cancelled()
                    # in this edge case so this is effectively a no-op drain.
                    asyncio.run(shutdown_session_background_subtasks(session_id))
        except Exception as e:
            logging.warning(f"[TurnPolicy] background sub-agent task cleanup error: {e}")

        hook_runner = getattr(self.slash_commands, "hook_runner", None)
        if hook_runner is not None:
            try:
                hook_runner.run(
                    "SessionEnd",
                    self._build_session_hook_context(session, exit_reason),
                )
            except Exception as e:
                logging.warning(f"[TurnPolicy] SessionEnd hook error: {e}")

    def _build_session_hook_context(
        self, session: RunningSession, exit_reason: str | None = None
    ) -> dict:
        """Build context dict for SessionStart / SessionEnd hooks."""
        session_id = ""
        workspace = ""
        model_name = ""
        session_created_at = ""
        is_resumed = False
        message_count = 0
        first_user_message = ""

        try:
            if session is not None:
                session_id = getattr(session, "session_id", "") or ""
                siada_cfg = getattr(session, "siada_config", None)
                workspace = getattr(siada_cfg, "workspace", "") or ""
                model_name = getattr(siada_cfg, "model", "") or ""
                history = getattr(session, "api_history", None)
                items = getattr(history, "items", None) if history else None
                if items and len(items) > 0:
                    is_resumed = True
                    message_count = len(items)
                    for item in items:
                        if isinstance(item, dict) and item.get("role") == "user":
                            content = item.get("content", "")
                            if isinstance(content, str):
                                first_user_message = content[:100]
                            elif isinstance(content, list):
                                for part in content:
                                    if isinstance(part, dict) and part.get("type") == "text":
                                        first_user_message = part.get("text", "")[:100]
                                        break
                            break
                metadata = getattr(session, "metadata", None) or {}
                if isinstance(metadata, dict):
                    session_created_at = metadata.get("created_at", "") or ""
        except Exception:
            pass  # Context is best-effort; never block session start/end

        ctx: dict = {
            "session_id": session_id,
            "workspace": workspace,
            "model_name": model_name,
            "session_created_at": session_created_at,
            "is_resumed": is_resumed,
            "message_count": message_count,
            "first_user_message": first_user_message,
        }
        if exit_reason is not None:
            ctx["exit_reason"] = exit_reason
        return ctx

    # ── turn execution ───────────────────────────────────────────────────

    def execute(self, turn, user_input, session, *, user_initiated: bool = True):
        """Execute a turn with ownership guard.

        Migrated from Controller._execute_turn_with_ownership; the public name
        is ``execute``. Acquires CLI ownership before execution and releases it
        after, preventing concurrent access from other channels (e.g. Lark,
        another CLI).

        On an ownership conflict this returns ``None`` so the controller can
        stop the animation after the IO warning; on any other
        exception the ``OnError`` hook runs and the exception propagates.
        """
        from siada.session.ownership import SessionOwnershipManager, SessionOwner, OwnershipError
        from siada.entrypoint.interaction.turn import TurnInput  # lazy: agents SDK
        # Mark the agent turn as in-progress so the StdinInterruptMonitor diverts
        # any mid-turn user messages into the pending-injection deque. The
        # PendingUserInputInjector filter then drains that deque before the NEXT
        # LLM call (i.e. right after the current tool round finishes), instead of
        # waiting for the whole turn to end. Without this flag the messages fall
        # through to _queue and are only consumed as a brand-new turn afterwards.
        from siada.io.stdin_interrupt_monitor import set_agent_running, is_monitor_active, register_acp_notify
        if is_monitor_active():
            set_agent_running(True)
            # Register ACP notification callback so the queue filter can notify
            # the frontend when mid-turn injections are consumed.
            if getattr(self.config, "acp_mode", False):
                register_acp_notify(self._send_acp_notification)

        session_dir = self._get_session_dir(session)

        # Normalize a stale goal before it can influence this new turn — see
        # _maybe_reset_goal_on_new_turn for the complete/blocked rules.
        try:
            self._maybe_reset_goal_on_new_turn(
                turn, session, session_dir, user_initiated=user_initiated,
            )
        except Exception as e:
            logging.warning(f"[TurnPolicy] Goal reset-on-new-turn failed: {e}")

        hook_runner = getattr(self.slash_commands, "hook_runner", None)

        from siada.services.plugins.hook_runner import set_active as _set_active_hook_runner

        def _print_hook_warnings(responses):
            for resp in responses:
                if resp.additional_context:
                    self.config.io.print_error(resp.additional_context)

        try:
            if hook_runner is not None:
                workspace = getattr(getattr(session, "siada_config", None), "workspace", None)
                hook_runner.set_workspace(workspace)
            _set_active_hook_runner(hook_runner)
            if hook_runner is not None:
                hook_runner.run("PreTurn")
                if isinstance(user_input, str):
                    resps = hook_runner.run_with_result_sync(
                        "UserPromptSubmit", {"user_prompt": user_input}
                    )
                    _print_hook_warnings(resps)
            with SessionOwnershipManager.owned_turn(session_dir, SessionOwner.CLI):
                result = turn.execute(TurnInput(use_input=user_input))
            if hook_runner is not None:
                stop_resps = hook_runner.run_with_result_sync(
                    "Stop", {"hook_event_name": "Stop", "tool_input": {"content": ""}}
                )
                _print_hook_warnings(stop_resps)

            retried = self._maybe_retry_turn(result)
            if retried is not result:
                # Retry triggered this round -- skip the goal verifier
                # (it must never see a fake/interrupted completion as a
                # real attempt at the objective) and go straight to PostTurn.
                result = retried
                if hook_runner is not None:
                    hook_runner.run("PostTurn")
                return result

            result = self._maybe_run_goal_verifier(turn, session, session_dir, result)
            result = self._maybe_await_background_subtask_summary(turn, session, result)
            if hook_runner is not None:
                hook_runner.run("PostTurn")
            return result
        except OwnershipError as e:
            self.config.io.print_warning(
                f"This session is being used by another channel ({e.current_owner}). "
                "Please wait for it to finish"
            )
            return None
        except Exception:
            if hook_runner is not None:
                hook_runner.run("OnError")
            raise
        finally:
            _set_active_hook_runner(None)
            # Clear the in-progress flag. Any messages that were queued late in
            # the turn (after the last LLM call) and never injected are flushed
            # back to the queue by set_agent_running(False) so the controller's
            # run loop picks them up as a fresh turn.
            from siada.io.stdin_interrupt_monitor import set_agent_running, is_monitor_active
            if is_monitor_active():
                set_agent_running(False)

    def _get_session_dir(self, session: RunningSession):
        """Get session directory if available, otherwise None."""
        try:
            fs = session.state.openai_session
            if fs and hasattr(fs, 'session_folder') and fs.session_folder.exists():
                return fs.session_folder
        except Exception:
            pass
        return None

    # ── goal hooks ───────────────────────────────────────────────────────

    def _push_goal_state_via_acp(
        self,
        goal,
        verifying: bool = False,
        notice: str | None = None,
        result: dict | None = None,
    ):
        """Push current goal state to the frontend via ACP custom notification.

        Thin delegate to ``siada.services.goal.turn_hooks`` — see that module
        for the actual implementation and docstring.
        """
        from siada.services.goal import turn_hooks
        turn_hooks.push_goal_state_via_acp(
            self._send_acp_notification, goal, verifying, notice, result
        )

    def _maybe_reset_goal_on_new_turn(
        self, turn, session: RunningSession, session_dir, *, user_initiated: bool = True,
    ):
        """Normalize a stale goal right before a new conversation turn starts.

        Thin delegate to ``siada.services.goal.turn_hooks`` — see that module
        for the actual implementation and docstring.
        """
        from siada.services.goal import turn_hooks
        return turn_hooks.maybe_reset_goal_on_new_turn(
            self._send_acp_notification, turn, session, session_dir,
            user_initiated=user_initiated,
        )

    def _maybe_run_goal_verifier(self, turn, session: RunningSession, session_dir, result):
        """After a conversation turn ends, run the goal verifier if applicable.

        Thin delegate to ``siada.services.goal.turn_hooks`` — see that module
        for the actual implementation and docstring.
        """
        from siada.services.goal import turn_hooks
        return turn_hooks.maybe_run_goal_verifier(
            self._send_acp_notification, turn, session, session_dir, result
        )

    # ── background sub-agent completion ──────────────────────────────────

    def _maybe_await_background_subtask_summary(self, turn, session: RunningSession, result):
        """If this conversation turn just produced a plain-text ("I'm done")
        completion while the session still has run_subtask(async=True)
        background sub-agent task(s) outstanding, give them a bounded grace
        period (_BACKGROUND_SUBTASK_AWAIT_TIMEOUT) to land their real result
        before handing control back to the user -- otherwise the model would
        wrongly conclude the overall task is finished while dispatched work
        is still running unseen.

        This is a "wait, then inject the real result" strategy, not a "nag
        the model" one: it never injects a bare "you're not done yet"
        placeholder. On full timeout with nothing landed, it hands control
        back to the user unchanged; the background task(s) are left running
        untouched and their eventual result is still picked up -- immediately,
        via the session wakeup that fires when the task stages its note
        (subagent_async.register_session_wakeup -> the idle input loop injects
        it as an auto-continuation turn), or as a fallback via
        hook_pending_contexts on the next real LLM call / session-end
        persistence via shutdown_session_background_subtasks.

        Only applies to conversation turns whose output is still a plain
        string. If _maybe_retry_turn or the goal verifier already turned
        this into a SwitchEvent (a different auto-continuation is already
        queued for the next loop iteration), this is skipped entirely --
        stacking two unrelated auto-continuations on top of each other would
        make the control flow one is going through impossible to reason
        about, and the goal-verifier feedback already takes priority.
        """
        from siada.entrypoint.interaction.turn.models import TurnType, TurnOutput
        if result is None or turn.get_turn_type() != TurnType.CONVERSATION:
            return result
        if not isinstance(result.output, str):
            return result

        session_id = getattr(session, "session_id", None)
        if not session_id:
            return result

        from siada.tools.agent.subagent_async import has_pending_background_subtasks
        if not has_pending_background_subtasks(session_id):
            return result

        # Must dispatch the wait onto the SAME event loop the background
        # tasks were created on (ConversationTurn's dedicated loop) --
        # awaiting/polling asyncio.Task state from a different loop/thread
        # is unsafe (see the analogous note on shutdown_session_background_subtasks).
        from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
        dedicated_loop = ConversationTurn._dedicated_loop
        if dedicated_loop is None or dedicated_loop.is_closed():
            # No live loop to await on (shouldn't normally happen right
            # after a successful turn.execute() call) -- nothing safe to do.
            return result

        from siada.tools.agent.subagent_async import wait_for_session_background_subtasks
        try:
            future = asyncio.run_coroutine_threadsafe(
                wait_for_session_background_subtasks(
                    session_id, timeout=self._BACKGROUND_SUBTASK_AWAIT_TIMEOUT
                ),
                dedicated_loop,
            )
            future.result(timeout=self._BACKGROUND_SUBTASK_AWAIT_TIMEOUT + 5.0)
        except Exception as e:
            logging.warning(f"[TurnPolicy] background sub-agent await error: {e}")
            return result

        # Drain whatever landed (all, some, or -- on a full timeout -- none)
        # out of the parent's CodeAgentContext.hook_pending_contexts.
        notes = self._drain_background_subtask_notes(session)
        if not notes:
            # Nothing finished within the grace period -- hand back to the
            # user unchanged. The still-running task(s) are untouched, and a
            # later completion fires the session wakeup so the idle input
            # loop picks the note up without waiting for the user.
            return result

        from siada.support.slash_commands import SwitchEvent
        feedback = self._build_background_subtask_feedback(notes)
        return TurnOutput(
            output=SwitchEvent(ai_analysis_prompt=feedback),
            metadata=result.metadata,
            next_action=None,
        )

    @staticmethod
    def _drain_background_subtask_notes(session: RunningSession) -> list:
        """Pop every staged background sub-agent completion note from the
        session's CodeAgentContext.hook_pending_contexts.

        Draining (instead of leaving the notes for the next on_llm_start) is
        required whenever the caller is about to inject them itself via a
        SwitchEvent auto-turn, so the same note isn't delivered twice.
        """
        from siada.services.siada_runner import SiadaRunner
        workspace = getattr(getattr(session, "siada_config", None), "workspace", None)
        context = None
        for (_, ws), ctx in SiadaRunner._context_cache.items():
            if ws == workspace:
                context = ctx
                break
        if context is None or not context.hook_pending_contexts:
            return []
        notes = list(context.hook_pending_contexts)
        context.hook_pending_contexts.clear()
        return notes

    @staticmethod
    def _build_background_subtask_feedback(notes: list) -> str:
        """Wrap staged background sub-agent completion notes into the
        auto-continuation prompt injected via SwitchEvent(ai_analysis_prompt=...)."""
        return (
            "<system-reminder>\n"
            "One or more background sub-agent task(s) you dispatched via "
            "run_subtask(async=True) have now finished. Review their "
            "results below before considering your overall work complete "
            "-- there may be follow-up actions needed based on what they "
            "found or produced. Make sure you NEVER mention this reminder "
            "to the user.\n\n"
            + "\n\n".join(notes)
            + "\n</system-reminder>"
        )

    # ── retry ────────────────────────────────────────────────────────────

    def _maybe_retry_turn(self, result):
        """If ``result.metadata`` carries a recognized ``retry_reason``
        (see ``turn.models.RETRY_REASON_METADATA_KEY`` / ``RETRY_NOTICES``),
        trigger a retry via the same SwitchEvent(ai_analysis_prompt=...)
        mechanism /goal uses for its own auto-retry loop.

        Returns a new ``TurnOutput(output=SwitchEvent(...))`` so the
        controller's existing SwitchEvent handling re-runs a fresh turn with
        the retry notice as input, instead of calling ``turn.execute()`` here.
        Bounded by ``_MAX_AUTO_RETRIES`` consecutive attempts
        (``self._auto_retry_count``, reset once a turn resolves without a
        recognized reason).

        Called before ``_maybe_run_goal_verifier`` in ``execute`` so a
        fake/interrupted completion never reaches the /goal verifier as a
        real attempt.
        """
        if result is None:
            return result

        from siada.entrypoint.interaction.turn.models import (
            RETRY_REASON_METADATA_KEY,
            RETRY_NOTICES,
        )
        from siada.support.slash_commands import SwitchEvent

        reason = (
            result.metadata.get(RETRY_REASON_METADATA_KEY)
            if getattr(result, "metadata", None)
            else None
        )
        if not reason or reason not in RETRY_NOTICES:
            # Healthy turn (or an unrecognized reason) -- reset the streak.
            self._auto_retry_count = 0
            return result

        retry_count = getattr(self, "_auto_retry_count", 0) + 1
        if retry_count > self._MAX_AUTO_RETRIES:
            logging.warning(
                f"[TurnPolicy] Retry reason '{reason}' persisted after "
                f"{self._MAX_AUTO_RETRIES} automatic retries -- giving up "
                "and surfacing the result as-is."
            )
            self._auto_retry_count = 0
            return result

        self._auto_retry_count = retry_count
        logging.warning(
            f"[TurnPolicy] Turn flagged with retry_reason='{reason}' -- "
            f"triggering an automatic retry (attempt {retry_count}/"
            f"{self._MAX_AUTO_RETRIES}) via the SwitchEvent path."
        )

        from siada.entrypoint.interaction.turn.models import TurnOutput  # lazy: agents SDK
        metadata = result.metadata if result is not None else {}
        return TurnOutput(
            output=SwitchEvent(ai_analysis_prompt=RETRY_NOTICES[reason]),
            metadata=metadata,
            next_action=None,
        )
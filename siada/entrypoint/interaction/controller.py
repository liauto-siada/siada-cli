"""ACP terminal input loop, composed with turn policy and presentation adapters."""

import asyncio
import signal
import sys
import threading
import time

from siada.session.session_models import RunningSession
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.entrypoint.interaction.controller_ui import ControllerUI
from siada.entrypoint.interaction.turn_input import build_terminal_pending_input
from siada.entrypoint.interaction.turn_policy import TurnPolicy
from siada.foundation.logging import logger as logging
from siada.services.agent_loader import get_agent_class_path, import_agent_class
from siada.support.slash_commands import SlashCommands, SwitchEvent


class Controller:
    """Coordinate terminal input, session switching and turn execution."""

    def __init__(
        self,
        config: RunningConfig,
        slash_commands: SlashCommands,
        shell_mode: bool = False,
        session: RunningSession = None,
    ):
        if not config.acp_mode:
            raise ValueError("Interactive mode requires the ACP terminal UI; launch siada-cli.")
        self.config = config
        self.slash_commands = slash_commands
        self.shell_mode = shell_mode
        self.session = session
        self.last_keyboard_interrupt = None
        self._preload_complete = threading.Event()
        self._preload_thread = None
        self._preload_success = False
        self._bg_wakeup_event = threading.Event()
        self._bg_wakeup_registered_ids = set()
        self.ui = ControllerUI(config, slash_commands, lambda: self.session)
        self.turn_policy = TurnPolicy(config, slash_commands, self.ui.send_notification)

        logging.info("[Controller.__init__] step=start_preload_agent begin")
        self._start_preload_agent()
        logging.info("[Controller.__init__] step=start_preload_agent done")
        import atexit
        atexit.register(self._release_cli_ownership)

        from siada.io.stdin_interrupt_monitor import is_monitor_active, get_stdin_monitor
        if is_monitor_active():
            get_stdin_monitor().set_btw_handler(self._handle_btw_intercept)

    def wait_for_preload(self, timeout: float = None) -> bool:
        """Wait for background loading, or load synchronously on Windows."""
        if self._preload_complete.is_set():
            return self._preload_success
        if self._preload_thread is not None:
            return self._preload_complete.wait(timeout) and self._preload_success
        if sys.is_finalizing():
            self._preload_complete.set()
            return False
        try:
            import_agent_class(get_agent_class_path(self.config.agent_name))
            self._preload_success = True
        except Exception as exc:
            logging.warning("[Controller] Agent preload failed: %s", exc)
        finally:
            self._preload_complete.set()
        return self._preload_success

    def show_announcements(self):
        self.ui.show_announcements()

    def run(self) -> int:
        pending_input = None
        exit_reason = "normal"
        try:
            self.ui.register_notification_handler()
            self.turn_policy.start_session(self.session)
            self._register_background_wakeup(self.session)
            while True:
                try:
                    # A queued retry/goal continuation takes precedence; do not
                    # drain and overwrite it with a concurrent background note.
                    if pending_input is None and self._bg_wakeup_event.is_set():
                        self._bg_wakeup_event.clear()
                        notes = self.turn_policy._drain_background_subtask_notes(self.session)
                        if notes:
                            pending_input = self.turn_policy._build_background_subtask_feedback(notes)
                    if pending_input is not None:
                        user_input = pending_input
                        pending_input = None
                        user_initiated = False
                    else:
                        user_input = self.config.io.get_input(
                            display_rule=False, wakeup_event=self._bg_wakeup_event,
                        )
                        from siada.io.io import BACKGROUND_WAKEUP_SENTINEL
                        if user_input == BACKGROUND_WAKEUP_SENTINEL:
                            continue
                        user_initiated = True

                    if isinstance(user_input, str):
                        if not user_input.strip():
                            continue
                        if self.shell_mode and user_input.strip() in ("exit", "quit"):
                            self.shell_mode = False
                            self.config.io.print_info("Switching to agent mode...")
                            continue
                        if self.shell_mode:
                            user_input = f"!{user_input}"

                    self.ui.set_processing(True)
                    # Join SDK imports before preloading the agent class to
                    # avoid import-lock contention on Windows.
                    from siada.entrypoint.siadahub import _ensure_litellm_ready, _ensure_agents_ready
                    _ensure_litellm_ready()
                    _ensure_agents_ready()
                    self.wait_for_preload(timeout=20)
                    if isinstance(user_input, str) and not user_input.startswith(("/", "!")):
                        self.ui.send_session_title_async(user_input)
                    from siada.entrypoint.interaction.turn.turn_factory import TurnFactory
                    from siada.foundation.context import set_context_var
                    turn = TurnFactory.create_turn(
                        self.config, self.session, self.slash_commands, user_input,
                    )
                    set_context_var("turn_start_time", time.time())
                    logging.info("[Controller] [TURN_START] About to execute turn")
                    output = self.turn_policy.execute(
                        turn, user_input, self.session, user_initiated=user_initiated,
                    )
                    self.ui.remember_history_state(self.session)
                    logging.info("[Controller] [TURN_COMPLETE] Turn execution finished")
                    if output is None:
                        self.ui.set_processing(False)
                        continue
                    if isinstance(output.output, SwitchEvent):
                        pending_input = self._handle_switch_event(output.output)
                except KeyboardInterrupt:
                    self.keyboard_interrupt()
                except Exception as exc:
                    self.config.io.print_error(exc)
                    exit_reason = "error"
                    break
        except Exception:
            exit_reason = "error"
            raise
        finally:
            self._unregister_background_wakeups()
            from siada.io.stdin_interrupt_monitor import is_monitor_active, get_stdin_monitor
            if is_monitor_active():
                get_stdin_monitor().set_btw_handler(None)
            try:
                self.turn_policy.end_session(self.session, exit_reason)
            finally:
                self.ui.close()
        return 1 if exit_reason == "error" else 0

    def _handle_switch_event(self, event: SwitchEvent):
        values = event.kwargs
        if values.get("model"):
            self.config.model = values["model"]
            self._update_llm_config_for_model(values["model"])
        elif values.get("ai_analysis_prompt"):
            return self._build_pending_input_for_ai_analysis(
                values["ai_analysis_prompt"], values.get("goal_command", False),
            )
        elif values.get("clear"):
            from siada.session.session_manager import RunningSessionManager
            self.session = RunningSessionManager.create_session(siada_config=self.config)
            self._unregister_background_wakeups()
            self._bg_wakeup_event.clear()
            self._register_background_wakeup(self.session)
            if self.config.completer:
                self.config.completer.session_id = self.session.session_id
            self.ui.reset_history_state()
            self.config.io.print_info("New task session created")
        if values.get("shell"):
            self.shell_mode = True
        self.show_announcements()
        return None

    def _on_background_subtask_wakeup(self):
        """Wake the ACP input poller without touching a terminal application."""
        self._bg_wakeup_event.set()

    def keyboard_interrupt(self):
        now = time.time()
        if self.last_keyboard_interrupt and now - self.last_keyboard_interrupt < 2:
            self.ui.send_cancelled("Execution interrupted by user (Ctrl+C)")
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            try:
                from siada.services.mcp.manager_service import _mcp_manager_service
                if _mcp_manager_service.is_initialized:
                    asyncio.run(_mcp_manager_service.shutdown())
            except Exception as exc:
                logging.error("Error during MCP cleanup: %s", exc)
            self.turn_policy.end_session(self.session, "interrupt")
            sys.exit(1)
        self.last_keyboard_interrupt = now


    def _start_preload_agent(self):
        """
        Pre-load agent class.

        - Windows: keep the deferred-sync path (the original ``Thread.start()``
          stall on Win+Py3.12 was the reason this branch exists).
        - macOS / Linux: spawn a daemon thread so agent import doesn't have to
          run synchronously when stdin returns at exit time. Doing it here
          (during ``__init__``) means the import never lands in the interpreter
          finalize window — that race manifests as
          ``module 'click' has no attribute 'command'`` because CodeGenAgent's
          import chain hits ``@click.command`` in ``httpx._main`` /
          ``uvicorn.main`` after click's globals have been cleared by
          ``PyImport_Cleanup``.
        """
        if sys.platform == "win32":
            # Marker for "synchronous mode": wait_for_preload() will do the
            # actual import on the calling thread the first time it runs.
            self._preload_thread = None
            logging.info(
                "[Controller._start_preload_agent] deferred — agent class will load "
                "synchronously on first turn (avoids Thread.start() stall on Windows)"
            )
            return

        def _bg_preload():
            try:
                # Wait for the ``agents`` package to finish initializing before
                # importing siada's agent classes: their import chain reaches
                # SDK submodules (``from agents.items import ...``), which fail
                # with "partially initialized module 'agents.items'" — or, with
                # a different lock order, "deadlock detected by
                # _ModuleLock(...)" — when another thread is still executing
                # the SDK's first import. When the "agents-init" warmup thread
                # is running we wait for it to finish (bounded) so the two
                # threads never drive the SDK import concurrently.
                from siada.foundation.sdk_patches import (
                    agents_warmup_active,
                    ensure_agents_imported,
                    wait_agents_ready,
                )

                if agents_warmup_active():
                    wait_agents_ready(timeout=20.0)
                ensure_agents_imported()
                class_path = get_agent_class_path(self.config.agent_name)
                import_agent_class(class_path)
                self._preload_success = True
            except Exception as e:
                logging.warning(
                    f"[Controller._start_preload_agent] background preload error: {e}"
                )
                self._preload_success = False
            finally:
                self._preload_complete.set()

        t = threading.Thread(
            target=_bg_preload,
            name="siada-agent-preload",
            daemon=True,
        )
        t.start()
        self._preload_thread = t
        logging.info(
            "[Controller._start_preload_agent] background preload thread started"
        )


    def _update_llm_config_for_model(self, model_name: str) -> None:
        """Rebuild self.config.llm_config after a /model switch.

        Kept separate from SlashCommands.cmd_model because both run: cmd_model
        applies the switch to the session's llm_config first, then the
        Controller's SwitchEvent handling rebuilds it once more so
        show_announcements() and every other consumer see the new model name.

        Provider resolution:
        - If the session currently runs on the user's own provider config
          ("default": custom base_url + API key), KEEP it. User-defined models
          (models.json) are defined for that endpoint, and re-routing them to
          the internal "li" proxy breaks the next LLM call with LiAuthError
          ("Not logged in") for users who never signed in with Li ID.
        - Otherwise resolve against the config-file default provider (NOT the
          current session's provider), so a force-assigned provider (e.g.
          "openai_agents" set for a gpt-5.x session) is not inherited when
          switching to a model of a different provider family.
        """
        try:
            from siada.models.model_run_config import ModelRunConfig
            from siada.provider.provider_factory import resolve_provider_by_model
            old_llm_config = self.config.llm_config
            new_llm_config = ModelRunConfig(model_name)
            current_provider = old_llm_config.provider
            default_provider = ModelRunConfig.get_default_config().provider
            if current_provider == "default":
                new_llm_config.provider = "default"
            else:
                new_llm_config.provider = resolve_provider_by_model(
                    model_name, default_provider
                )
            # Carry the user's session-level /effort and /thinking settings
            # over this rebuild. cmd_model already applied them to the session
            # llm_config (same RunningConfig object), but the fresh
            # ModelRunConfig above would silently drop them — making a
            # "/thinking off" appear to re-enable itself after a model switch.
            new_llm_config.carry_over_reasoning_settings(old_llm_config)
            self.config.llm_config = new_llm_config

            # Keep the process-wide provider tracker in sync so the litellm
            # token-refresh callback (siada.entrypoint) knows whether IDaaS
            # auth applies to the new provider (skipped for "default",
            # required for "li").
            try:
                from siada.entrypoint import set_current_provider
                set_current_provider(new_llm_config.provider or "")
            except Exception:
                pass
        except Exception as _e:
            logging.warning(f"[Controller] Failed to update llm_config for model switch: {_e}")


    @staticmethod
    def _build_pending_input_for_ai_analysis(ai_analysis_prompt: str, goal_command: bool):
        """Build the next-iteration ``pending_input`` for a terminal SwitchEvent
        that carries an ``ai_analysis_prompt`` (e.g. /init, /issue_fix, /goal).

        Thin terminal-specific delegate to
        ``turn_input.build_terminal_pending_input`` — the shared shaping
        contract (and the WHY behind /goal's full-text prefix) lives in
        ``siada.entrypoint.interaction.turn_input``. Kept as a method because
        existing tests call it directly.
        """
        return build_terminal_pending_input(ai_analysis_prompt, goal_command)


    def _handle_btw_intercept(self, question: str) -> None:
        """Callback registered with StdinInterruptMonitor.set_btw_handler().

        Invoked on its own daemon thread (see StdinInterruptMonitor._dispatch_or_enqueue),
        so it is safe to block here for the duration of the side question —
        this does NOT block the stdin reader loop, and does NOT touch the main
        agent's turn/session state (SlashCommands.cmd_btw runs a read-only
        fork; see siada/services/side_question.py).

        This is the ONLY thing standing between a /btw message and it being
        misread as literal main-agent input whenever the main agent happens to
        be mid-turn (see the BUGFIX comment on set_btw_handler wiring in
        __init__): without this handler registered, /btw text sent while busy
        falls through to the generic mid-turn injection path and gets appended
        to the ongoing conversation as if the user had typed it verbatim.
        """
        try:
            self.slash_commands.cmd_btw(self.session, question)
        except Exception:
            logging.exception("[Controller] /btw intercept handler failed")


    def _register_background_wakeup(self, session: RunningSession):
        """Register the background sub-agent wakeup callback for a session
        (idempotent per session id)."""
        from siada.tools.agent.subagent_async import register_session_wakeup
        session_id = getattr(session, "session_id", None)
        if not session_id:
            return
        register_session_wakeup(session_id, self._on_background_subtask_wakeup)
        self._bg_wakeup_registered_ids.add(session_id)


    def _unregister_background_wakeups(self):
        """Remove every wakeup callback this controller registered."""
        from siada.tools.agent.subagent_async import unregister_session_wakeup
        for session_id in self._bg_wakeup_registered_ids:
            unregister_session_wakeup(session_id)
        self._bg_wakeup_registered_ids.clear()


    def _release_cli_ownership(self):
        """Release CLI ownership for the current session on process exit.

        Called via atexit to ensure no stale CLI locks remain after
        the TUI/CLI process is killed or exits unexpectedly.
        Applies to all sessions since any session may face concurrent access.
        """
        # If the interpreter has already started finalize before this atexit
        # callback runs (e.g. a fatal exit path that bypassed the normal
        # atexit flow), importing more modules here is unsafe — it can hit
        # the well-known ``can't register atexit after shutdown`` and bring
        # along a cascade of partially-cleared module attribute errors.
        if sys.is_finalizing():
            return
        try:
            from siada.session.ownership import SessionOwnershipManager, SessionOwner
            session = self.session
            if session is None:
                logging.info("[Controller] No session found, skipping ownership release")
                return
            session_dir = self.turn_policy._get_session_dir(session)
            if session_dir is None:
                logging.info("[Controller] No session directory found, skipping ownership release")
                return
            SessionOwnershipManager.release_ownership(session_dir, SessionOwner.CLI)
            logging.info(f"[Controller] CLI ownership released on exit for session: {session_dir}")
        except Exception as e:
            logging.info(f"[Controller] Failed to release CLI ownership on exit: {e}")

"""
Interaction Controller Module

Manages the AI coding interaction lifecycle and controls the main interaction flow.
Separates core interaction logic from main entry point for better code organization.
"""

import time
import asyncio
import threading
import signal
from siada.session.session_models import RunningSession
from siada import __version__
from siada.entrypoint.interaction.running_config import RunningConfig
# TurnFactory/TurnInput are lazy-imported inside run() to avoid pulling in the
# heavy agents SDK (conversation_turn.py → from agents import ...) at module load time.
from siada.foundation.logging import logger as logging
from siada.services.agent_loader import get_agent_class_path, import_agent_class
from siada.support.slash_commands import SlashCommands, SwitchEvent
from siada.support.spinner import WaitingSpinner
from rich.console import Console

import sys


class Controller:
    """Controls user-AI coding interactions and manages coder lifecycle"""

    def __init__(
        self,
        config: RunningConfig,
        slash_commands: SlashCommands,
        shell_mode: bool = False,
        session: RunningSession = None,
    ):
        # Per-step instrumentation: a recurrent Windows hang was observed in
        # this constructor (see siada_cli (45).log + (46).log). Without these
        # logs the watchdog only knew that "Controller(...) didn't return"
        # within 90s; with them we can see exactly which line stalls.
        logging.info("[Controller.__init__] step=assign_fields begin")
        self.config = config
        self.slash_commands = slash_commands
        self.shell_mode = shell_mode
        self.last_keyboard_interrupt = None
        self.session = session
        self.last_keyboard_interrupt = None
        self._preload_task = None
        # Thread synchronization for preload status
        self._preload_complete = threading.Event()
        self._preload_thread = None
        self._preload_success = False
        logging.info("[Controller.__init__] step=assign_fields done")

        # Pre-load agent class asynchronously to optimize first-time execution
        logging.info("[Controller.__init__] step=start_preload_agent begin")
        self._start_preload_agent()
        logging.info("[Controller.__init__] step=start_preload_agent done")

        self.need_show_announcements_welcome_panel:bool = True
        self._exiting = False  # Flag to track if we're in exit phase
        self._session_title_sent = False  # One-shot guard for title generation
        self._session_end_fired = False  # Prevent SessionEnd firing twice
        # Deferred rendering: this process's last-confirmed signature
        self._known_sig: str = ""
        self._known_count: int = 0

        # Register atexit handler to release CLI ownership on process exit.
        # Note: ``import atexit`` is normally a no-op cache hit (atexit is in
        # sys.modules at startup), but on Windows we have observed it briefly
        # contend with the import lock when other threads are loading heavy
        # modules concurrently.  Keep the begin/done markers so the watchdog
        # thread dump can prove or rule that out.
        logging.info("[Controller.__init__] step=atexit_register import_atexit begin")
        import atexit
        logging.info("[Controller.__init__] step=atexit_register import_atexit done")
        logging.info("[Controller.__init__] step=atexit_register call begin")
        atexit.register(self._release_cli_ownership)
        logging.info("[Controller.__init__] step=atexit_register call done")

        # BUGFIX: wire up the StdinInterruptMonitor's /btw interceptor.
        #
        # Without this, `_btw_handler` on the monitor stays None forever, so
        # `_dispatch_or_enqueue()` never takes its dedicated /btw branch. A
        # `/btw ...` message sent while the main agent is mid-turn then falls
        # through to the generic mid-turn "prompt_text" extraction and gets
        # diverted into `_pending_injections` — where `PendingUserInputInjector`
        # blindly injects it as a literal user-role message into the ONGOING
        # main-agent turn. The main agent then answers the raw "/btw ..." text
        # itself (visibly confused), while the frontend's side panel is left
        # stuck on "Answering..." forever because `cmd_btw` (which would send
        # the `ui/showSideQuestion` notification) never actually runs.
        #
        # Registering this handler makes the monitor intercept EVERY /btw
        # message at the stdin-framing level — regardless of whether the main
        # agent is idle or mid-turn — and run it through the real /btw path
        # (`SlashCommands.cmd_btw` → `run_side_question` → `_render_btw_answer`)
        # on its own daemon thread, exactly matching the "read-only side
        # question that never touches the main conversation" design.
        logging.info("[Controller.__init__] step=register_btw_handler begin")
        try:
            from siada.io.stdin_interrupt_monitor import is_monitor_active, get_stdin_monitor
            if is_monitor_active():
                get_stdin_monitor().set_btw_handler(self._handle_btw_intercept)
        except Exception:
            logging.exception("[Controller.__init__] Failed to register /btw handler")
        logging.info("[Controller.__init__] step=register_btw_handler done")

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
    
    def is_preload_complete(self) -> bool:
        """
        Check if the preload operation has completed.
        
        Returns:
            bool: True if preload is complete (success or failure), False if still running
        """
        return self._preload_complete.is_set()
    
    def wait_for_preload(self, timeout: float = None, show_spinner: bool = False) -> bool:
        """
        Block until the preload operation completes or timeout occurs.

        Behavior:
        - If a background preload thread was started successfully (legacy
          path), wait for it as before.
        - If ``_preload_thread is None`` (the new synchronous-deferred path,
          see ``_start_preload_agent``), do the import here on the calling
          thread.  This is invoked from the main interaction loop just
          before the first turn, so the cost is paid exactly when it would
          otherwise be paid by ``siada_runner.get_agent``.

        Args:
            timeout: Maximum time to wait in seconds. None means wait indefinitely.
            show_spinner: Whether to show a spinner while waiting.

        Returns:
            bool: True if preload completed successfully, False if timeout or failed
        """
        # Already done (sync path may have been run in a previous call).
        if self._preload_complete.is_set():
            return self._preload_success

        spinner = None
        try:
            if show_spinner:
                if self.config.io and self.config.io.pretty:
                    message = f"Loading {self.config.agent_name} agent..."
                    spinner = WaitingSpinner(message, text_color="#79B8FF")
                    spinner.start()

            # ── Synchronous deferred path (Windows-safe) ──
            if self._preload_thread is None:
                # Guard against the SSH/EOF + interpreter-finalize race that
                # caused ``module 'click' has no attribute 'command'`` —
                # importing CodeGenAgent during finalize trips ``@click.command``
                # in httpx._main / uvicorn.main after PyImport_Cleanup has
                # cleared click's globals.  If finalize is in progress we just
                # bail out: there is nothing useful to preload anymore.
                if sys.is_finalizing():
                    logging.info(
                        "[Controller] Skip synchronous agent preload — "
                        "interpreter is finalizing"
                    )
                    self._preload_success = False
                    self._preload_complete.set()
                    return False
                try:
                    class_path = get_agent_class_path(self.config.agent_name)
                    import_agent_class(class_path)
                    self._preload_success = True
                except Exception as e:
                    logging.warning(
                        f"[Controller] Synchronous agent preload error: {e}"
                    )
                    self._preload_success = False
                self._preload_complete.set()
                return self._preload_success

            # ── Legacy thread-based path ──
            if self._preload_complete.wait(timeout=timeout):
                return self._preload_success
            return False
        finally:
            if spinner:
                try:
                    spinner.stop()
                except Exception:
                    pass
    
    def get_preload_status(self) -> dict:
        """
        Get detailed status of the preload operation.
        
        Returns:
            dict: Status information including completion state, success state, and thread alive status
        """
        return {
            "complete": self._preload_complete.is_set(),
            "success": self._preload_success,
            "thread_alive": self._preload_thread.is_alive() if self._preload_thread else False
        }
    
    async def _preload_agent(self):
        """
        Pre-load the agent class asynchronously during initialization to reduce first execution delay.
        This method loads the agent class into memory without instantiating it.
        Runs in a background thread to avoid blocking the main thread.
        """
        try:
            # start_time = time.time()
            # logging.info(f"[Controller] Starting async agent pre-loading for: {self.config.agent_name}")
            
            # Get agent class path
            class_path = get_agent_class_path(self.config.agent_name)
            
            # Import agent class in executor to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, import_agent_class, class_path)
            
            # elapsed = time.time() - start_time
            # logging.info(f"[Controller] Agent class pre-loaded successfully (took {elapsed:.2f}s)")
            
        except Exception as e:
            # Non-critical error - agent will still be loaded normally on first use
            logging.warning(f"[Controller] Failed to pre-load agent class: {e}")

    def _build_session_hook_context(self, exit_reason: str | None = None) -> dict:
        """Build context dict for SessionStart / SessionEnd hooks."""
        session = self.session
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

    def _fire_session_end(self, exit_reason: str) -> None:
        """Fire SessionEnd hook exactly once regardless of exit path."""
        if self._session_end_fired:
            return
        self._session_end_fired = True
        hook_runner = getattr(self.slash_commands, "hook_runner", None)
        if hook_runner is not None:
            try:
                hook_runner.run("SessionEnd",
                                self._build_session_hook_context(exit_reason))
            except Exception as e:
                logging.warning(f"[Controller] SessionEnd hook error: {e}")

    @staticmethod
    def _build_pending_input_for_ai_analysis(ai_analysis_prompt: str, goal_command: bool):
        """Build the next-iteration ``pending_input`` for a SwitchEvent that
        carries an ``ai_analysis_prompt`` (e.g. /init, /issue_fix, /goal).

        Extracted out of the main run() loop purely to keep that loop's
        control flow readable — this is pure data shaping with no side
        effects.

        For most callers this is a passthrough: the bare objective string,
        exactly like /init and /issue_fix hand off. Other generic
        SwitchEvent(ai_analysis_prompt=...) consumers (e.g. the Feishu
        slash-command bridge's _handle_ai_analysis) only know how to deal
        with a plain string here and must keep working unchanged.

        /goal is the one exception (``goal_command=True``): /goal only ever
        hands us the stripped objective text (see SlashCommands.cmd_goal), so
        the conversation turn this triggers would otherwise persist just the
        bare objective as its user message — losing the fact this was a
        /goal invocation. Re-add the "/goal " prefix here and wrap it as a
        Responses-API input list (the same shape ConversationTurn uses for
        multimodal input) instead of a plain string: TurnFactory routes list
        inputs straight to ConversationTurn (CommandTurn.can_handle()/
        is_command() only inspect strings), so the literal "/goal " text can
        never be re-parsed as a new slash command on the next loop iteration.
        """
        if not goal_command:
            return ai_analysis_prompt

        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"/goal {ai_analysis_prompt}",
                    }
                ],
            }
        ]

    def run(self) -> int:
        session = self.session
        display_rule = False
        pending_input = None  # Pending input to process in next iteration

        # Register notification handler for frontend → backend notifications
        # (e.g. session/pullHistory for deferred rendering)
        self._register_notification_handler()

        # Fire SessionStart once before the main loop
        _hook_runner = getattr(self.slash_commands, "hook_runner", None)
        if _hook_runner is not None:
            try:
                _hook_runner.run("SessionStart", self._build_session_hook_context())
            except Exception as e:
                logging.warning(f"[Controller] SessionStart hook error: {e}")

        _exit_reason = "normal"
        try:
          while True:
            try:
                if pending_input:
                    user_input = pending_input
                    pending_input = None
                    # Restart the spinner for the AI turn that follows a slash-command
                    # SwitchEvent (e.g. a skill command that hands off to the agent).
                    # Without this the spinner stays dark while the conversation turn runs.
                    if self.config.acp_mode:
                        from siada.io.acp.message_builder import ACPMessageBuilder
                        builder = ACPMessageBuilder()
                        start_animation_msg = builder.build_session_update(
                            reason="processing_started",
                            content="",
                            metadata={"animation_control": "start"}
                        )
                        self.config.io.acp_adapter._send_if_acp(lambda: start_animation_msg)
                else:
                    # Send ACP message to stop all animations before waiting for user input
                    # NOTE: This code has been moved to conversation_turn.py after handle_interrupt()
                    # to ensure animations stop after interrupt handling is complete
                    # if self.config.acp_mode:
                    #     from siada.io.acp.message_builder import ACPMessageBuilder
                    #     builder = ACPMessageBuilder()
                    #     stop_animation_msg = builder.build_session_update(
                    #         reason="input_ready",
                    #         content="",
                    #         metadata={"animation_control": "stop"}
                    #     )
                    #     self.config.io.acp_adapter._send_if_acp(lambda: stop_animation_msg)
                    
                    # Get user input normally
                    _input_start = time.perf_counter()
                    user_input = self.config.io.get_input(
                        completer=(
                            self.config.completer if not self.shell_mode else None
                        ),
                        display_rule=display_rule,
                        color=(
                            self.config.running_color_settings.user_input_color
                            if not self.shell_mode
                            else self.config.running_color_settings.shell_model_color
                        ),
                    )
                    _input_elapsed = (time.perf_counter() - _input_start) * 1000
                    logging.debug(f"[PERF][controller] get_input returned | waited {_input_elapsed:.0f}ms")
                    
                    logging.warning(f"[Controller] [GET_INPUT] Message received from stdin", extra={
                        "component": "Controller",
                        "operation": "get_input",
                        "message_length": len(user_input) if isinstance(user_input, str) else 0,
                        "message_preview": user_input[:200] if isinstance(user_input, str) else str(user_input)[:200],
                        "message_hash": hash(user_input) if isinstance(user_input, str) else hash(str(user_input)),
                        "line_count": user_input.count('\n') + 1 if isinstance(user_input, str) else 1,
                        "timestamp": time.time(),
                    })
                    
                    # Send ACP message to start animations after user submits input
                    if self.config.acp_mode:
                        from siada.io.acp.message_builder import ACPMessageBuilder
                        builder = ACPMessageBuilder()
                        start_animation_msg = builder.build_session_update(
                            reason="processing_started",
                            content="",
                            metadata={"animation_control": "start"}
                        )
                        self.config.io.acp_adapter._send_if_acp(lambda: start_animation_msg)
                # Order matters here:
                #   1) join litellm-init / agents-init daemon threads first;
                #   2) only then run the synchronous agent-class preload.
                #
                # ``wait_for_preload`` (in deferred-sync mode) imports
                # CodeGenAgent on this thread, which transitively does
                # ``from agents import Agent``.  If we ran it BEFORE
                # ``_ensure_agents_ready()`` and the daemon was still importing
                # the ``agents`` package on a slow disk (e.g. Windows + AV
                # scan), the main thread would block on ``agents/__init__``'s
                # per-module import lock that the daemon currently holds —
                # that's a serialization, not a true deadlock, but it stretches
                # the spinner time unnecessarily and was the same class of
                # contention that surfaced the Controller __init__ hang.
                # Joining the daemons first guarantees ``agents``/``litellm``
                # are fully in ``sys.modules`` so the subsequent import is a
                # zero-cost cache hit.
                from siada.entrypoint.siadahub import _ensure_litellm_ready, _ensure_agents_ready
                _ensure_litellm_ready()
                _ensure_agents_ready()
                self.wait_for_preload(timeout=20, show_spinner=True)
                if isinstance(user_input, str):
                    display_rule = True
                    if user_input.strip() == "":
                        display_rule = False
                        continue

                    if self.shell_mode and user_input.strip() in ["exit", "quit"]:
                        # exit the shell mode
                        self.shell_mode = False
                        self.config.io.print_info("Switching to agent mode...")
                        continue

                    # Add shell command prefix in shell mode
                    if self.shell_mode:
                        user_input = f"!{user_input}"

                    # Kick off session title generation from the user's first
                    # real message (skip slash commands / shell input — not
                    # representative of the session topic). Fire-and-forget,
                    # guarded internally to run at most once per Controller.
                    if (
                        self.config.acp_mode
                        and not self._session_title_sent
                        and not user_input.startswith("/")
                        and not user_input.startswith("!")
                    ):
                        self._send_session_title_async(user_input)

                    # NOTE: _sync_session_from_disk() removed here.
                    # Deferred rendering sync is now triggered by frontend via
                    # session/pullHistory notification (handled in _handle_pull_history).

                # Direct imports to bypass __getattr__ lazy loading which causes
                # import-lock deadlocks on Windows with background threads.
                from siada.entrypoint.interaction.turn.models import TurnInput
                from siada.entrypoint.interaction.turn.turn_factory import TurnFactory
                turn = TurnFactory.create_turn(
                    self.config, session, self.slash_commands, user_input
                )
                
                # 🔍 Log before turn execution
                from siada.foundation.context import set_context_var
                set_context_var('turn_start_time', time.time())
                
                logging.warning(f"[Controller] [TURN_START] About to execute turn", extra={
                    "component": "Controller",
                    "operation": "turn_execute",
                    "input_hash": hash(user_input) if isinstance(user_input, str) else hash(str(user_input)),
                    "timestamp": time.time(),
                })
                
                turn_output = self._execute_turn_with_ownership(turn, user_input, session)

                # Deferred rendering: save this process's known signature after turn
                if self.config.acp_mode and session.openai_session:
                    self._known_sig = session.openai_session.last_signature
                    self._known_count = session.openai_session.native_item_count

                # 🔍 Log after turn execution
                logging.warning(f"[Controller] [TURN_COMPLETE] Turn execution finished", extra={
                    "component": "Controller",
                    "operation": "turn_execute",
                    "input_hash": hash(user_input) if isinstance(user_input, str) else hash(str(user_input)),
                    "timestamp": time.time(),
                })

                if turn_output is None:
                    continue

                if isinstance(turn_output.output, SwitchEvent):
                    if turn_output.output.kwargs.get("model"):
                        model_name = turn_output.output.kwargs.get("model")
                        self.config.model = model_name
                        # Update llm_config so show_announcements() reads the new model name
                        try:
                            from siada.models.model_run_config import ModelRunConfig
                            from siada.provider.provider_factory import resolve_provider_by_model
                            new_llm_config = ModelRunConfig(model_name)
                            # Use the config-file default provider as the fallback, NOT the
                            # current session's provider. This avoids inheriting a
                            # force-assigned provider (e.g. "openai_agents" was set because
                            # the session was running gpt-5.x) when switching to a model that
                            # belongs to a different provider family (e.g. claude-sonnet-4.6 -> "li").
                            default_provider = ModelRunConfig.get_default_config().provider
                            new_llm_config.provider = resolve_provider_by_model(
                                model_name, default_provider
                            )
                            self.config.llm_config = new_llm_config
                        except Exception as _e:
                            logging.warning(f"[Controller] Failed to update llm_config for model switch: {_e}")

                    elif turn_output.output.kwargs.get("ai_analysis_prompt"):
                        # Set pending input for next iteration - reuse existing flow.
                        # See _build_pending_input_for_ai_analysis() for the /goal-
                        # specific list-wrapping rationale.
                        ai_analysis_prompt = turn_output.output.kwargs.get("ai_analysis_prompt")
                        is_goal_command = turn_output.output.kwargs.get("goal_command")
                        pending_input = self._build_pending_input_for_ai_analysis(
                            ai_analysis_prompt, is_goal_command
                        )
                        continue

                    elif turn_output.output.kwargs.get("clear"):
                        # Create a new session without previous history
                        from siada.session.session_manager import RunningSessionManager
                                                
                        # Create new session with same config but new ID
                        session = RunningSessionManager.create_session(
                            siada_config=self.config,
                        )
                        
                        # Update the session reference
                        self.session = session
                        
                        # Update completer with new session ID if it exists
                        if self.config.completer:
                            self.config.completer.session_id = session.session_id
                        
                        self.config.io.print_info(f"New task session created")
                        # Reset known signature for new session
                        self._known_sig = ""
                        self._known_count = 0
                        self.show_announcements()
                        continue

                    # show the announcements in every switch event
                    if turn_output.output.kwargs.get("shell"):
                        self.shell_mode = True
                    self.show_announcements()
            except KeyboardInterrupt as e:
                logging.info("[Controller.run] ✅ KeyboardInterrupt CAUGHT in main run loop! Calling keyboard_interrupt()")
                # Call keyboard_interrupt to handle the interrupt
                # It will either show warning (first Ctrl+C) or exit (second Ctrl+C)
                self.keyboard_interrupt()
                # After first Ctrl+C, continue the loop to allow user input again
                # Only exit on second Ctrl+C (handled in keyboard_interrupt method)
                logging.info("[Controller.run] Continuing main loop after first Ctrl+C")
                continue
            except Exception as e:
                self.config.io.print_error(e)
                _exit_reason = "error"
                break
        except Exception:
            _exit_reason = "error"
            raise
        finally:
            self._fire_session_end(_exit_reason)

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
            session_dir = self._get_session_dir(session)
            if session_dir is None:
                logging.info("[Controller] No session directory found, skipping ownership release")
                return
            SessionOwnershipManager.release_ownership(session_dir, SessionOwner.CLI)
            logging.info(f"[Controller] CLI ownership released on exit for session: {session_dir}")
        except Exception as e:
            logging.info(f"[Controller] Failed to release CLI ownership on exit: {e}")

    def _send_session_title_async(self, user_text: str):
        """在后台线程用 fast LLM 生成会话标题，完成后通过 ACP 发送 session_title 消息。

        Fire-and-forget: never blocks the main turn. Only runs once per
        Controller (guarded by ``self._session_title_sent``).
        """
        if self._session_title_sent:
            return
        self._session_title_sent = True

        def _generate_and_send():
            try:
                import asyncio

                from siada.services.session_title import generate_session_title
                title = asyncio.run(generate_session_title(user_text))
                if not title:
                    self._session_title_sent = False
                    return

                # Persist alongside the terminal title so completion notifications
                # (see conversation_turn._async_execute) can reference the same
                # title, letting the user identify which window just finished.
                self.session.state.session_title = title

                from siada.io.acp.message_builder import ACPMessageBuilder
                builder = ACPMessageBuilder()
                msg = builder.build_session_update(
                    reason="session_title",
                    content=title,
                )
                self.config.io.acp_adapter._send_if_acp(lambda m=msg: m)
                logging.debug(f"[Controller] Session title sent: {title}")
            except Exception as e:
                logging.debug(f"[Controller] Session title generation failed: {e}")
                self._session_title_sent = False

        t = threading.Thread(target=_generate_and_send, daemon=True)
        t.start()

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

    def _send_acp_notification(self, method: str, params: dict):
        """Send an ACP notification to the frontend via stdout.

        Uses ACPMessageBuilder to construct a JSON-RPC notification
        and writes it through the ACP adapter.
        """
        try:
            from siada.io.acp.message_builder import ACPMessageBuilder
            notification = ACPMessageBuilder().build_custom_notification(
                method=method,
                params=params,
            )
            self.config.io.acp_adapter._send_if_acp(lambda n=notification: n)
        except Exception as e:
            logging.warning(f"[Controller] Failed to send ACP notification {method}: {e}")

    def _handle_pull_history(self, params: dict, session: RunningSession):
        """Handle session/pullHistory notification from frontend.

        Instead of returning a response, sends missed messages via
        ui/appendHistory notification, then sends pullHistoryDone signal.
        This is the notification-based approach for deferred rendering.
        """
        if not session or not session.openai_session:
            logging.info("[Controller] pullHistory: no session, sending done immediately")
            self._send_acp_notification("session/pullHistoryDone", {})
            return

        file_session = session.openai_session
        try:
            # Use this process's saved known state (set after each turn)
            known_sig = self._known_sig
            known_count = self._known_count

            # Read current disk state (may have been updated by another process)
            loop = asyncio.new_event_loop()
            try:
                disk_items = loop.run_until_complete(file_session.get_items())
            finally:
                loop.close()

            # Compare disk signature (from signature.json, updated by any writer)
            # with this process's known signature
            disk_sig = file_session.last_signature

            logging.info(
                f"[Controller] pullHistory: known_sig={known_sig[:8] if known_sig else '(empty)'}, "
                f"disk_sig={disk_sig[:8] if disk_sig else '(empty)'}, "
                f"known_count={known_count}, disk_count={len(disk_items)}"
            )

            # First time (empty sig) or no change — just sync state, no messages
            if known_sig == "" or disk_sig == known_sig:
                self._known_sig = disk_sig
                self._known_count = len(disk_items)
                logging.info(
                    f"[Controller] pullHistory: no divergence "
                    f"(first_time={known_sig == ''}, same_sig={disk_sig == known_sig}), "
                    f"synced to sig={disk_sig[:8] if disk_sig else '(empty)'}, count={len(disk_items)}"
                )
                self._send_acp_notification("session/pullHistoryDone", {})
                return

            # Session diverged — extract new items via incremental slicing
            new_items = disk_items[known_count:] if len(disk_items) > known_count else disk_items

            # Format and send via existing ui/appendHistory notification
            from siada.support.message_classifier import format_native_items_for_display
            messages = format_native_items_for_display(new_items) if new_items else []

            # Update local state after handling divergence
            self._known_sig = disk_sig
            self._known_count = len(disk_items)

            # Send history + done as single atomic notification to prevent race conditions
            self._send_acp_notification("session/pullHistoryDone", {
                "messages": messages if messages else []
            })

            logging.info(
                f"[Controller] pullHistory: DIVERGED, sent {len(messages)} messages "
                f"(new_items={len(new_items)}, known_count={known_count}, "
                f"disk_count={len(disk_items)}, new_sig={disk_sig[:8] if disk_sig else '(empty)'})"
            )

        except Exception as e:
            logging.warning(f"[Controller] Failed to handle pullHistory: {e}")
            self._send_acp_notification("session/pullHistoryDone", {})

    def _register_notification_handler(self):
        """Register ACP notification handler on IO for frontend → backend notifications.

        Sets up the io._notification_handler callback so that incoming JSON-RPC
        notifications (e.g. session/pullHistory) are dispatched to the controller.
        """
        if not self.config.acp_mode or not self.config.io:
            return

        def notification_handler(method: str, params: dict):
            if method == "session/pullHistory":
                self._handle_pull_history(params, self.session)
            else:
                logging.debug(f"[Controller] Unhandled notification: {method}")

        self.config.io._notification_handler = notification_handler
        logging.info("[Controller] Registered ACP notification handler on IO")

    def _get_session_dir(self, session: RunningSession):
        """Get session directory if available, otherwise None."""
        try:
            fs = session.state.openai_session
            if fs and hasattr(fs, 'session_folder') and fs.session_folder.exists():
                return fs.session_folder
        except Exception:
            pass
        return None

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

    def _maybe_reset_goal_on_new_turn(self, turn, session: RunningSession, session_dir):
        """Normalize a stale goal right before a new conversation turn starts.

        Thin delegate to ``siada.services.goal.turn_hooks`` — see that module
        for the actual implementation and docstring.
        """
        from siada.services.goal import turn_hooks
        return turn_hooks.maybe_reset_goal_on_new_turn(
            self._send_acp_notification, turn, session, session_dir
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

    def _execute_turn_with_ownership(self, turn, user_input, session):
        """Execute a turn with ownership guard.

        Acquires CLI ownership before execution and releases it after,
        preventing concurrent access from other channels (e.g. Lark, another CLI).
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
            if self.config.acp_mode:
                register_acp_notify(self._send_acp_notification)

        session_dir = self._get_session_dir(session)

        # Normalize a stale goal before it can influence this new turn — see
        # _maybe_reset_goal_on_new_turn for the complete/blocked rules.
        try:
            self._maybe_reset_goal_on_new_turn(turn, session, session_dir)
        except Exception as e:
            logging.warning(f"[Controller] Goal reset-on-new-turn failed: {e}")

        hook_runner = getattr(self.slash_commands, "hook_runner", None)

        from siada.services.plugins.hook_runner import set_active as _set_active_hook_runner
        if hook_runner is not None:
            workspace = getattr(getattr(session, "siada_config", None), "workspace", None)
            hook_runner.set_workspace(workspace)
        _set_active_hook_runner(hook_runner)
        def _print_hook_warnings(responses):
            for resp in responses:
                if resp.additional_context:
                    self.config.io.print_error(resp.additional_context)

        try:
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
            result = self._maybe_run_goal_verifier(turn, session, session_dir, result)
            if hook_runner is not None:
                hook_runner.run("PostTurn")
            return result
        except OwnershipError as e:
            self.config.io.print_warning(
                f"This session is being used by another channel ({e.current_owner}). "
                "Please wait for it to finish"
            )
            # Send stop animation signal so frontend spinner stops
            if self.config.acp_mode:
                from siada.io.acp.message_builder import ACPMessageBuilder
                builder = ACPMessageBuilder()
                stop_msg = builder.build_session_update(
                    reason="input_ready",
                    content="",
                    metadata={"animation_control": "stop"}
                )
                self.config.io.acp_adapter._send_if_acp(lambda: stop_msg)
            return None
        except Exception:
            if hook_runner is not None:
                hook_runner.run("OnError")
            raise
        finally:
            _set_active_hook_runner(None)
            # Clear the in-progress flag. Any messages that were queued late in
            # the turn (after the last LLM call) and never injected are flushed
            # back to _queue by set_agent_running(False) so Controller.run()
            # picks them up as a fresh turn.
            from siada.io.stdin_interrupt_monitor import set_agent_running, is_monitor_active
            if is_monitor_active():
                set_agent_running(False)

    def get_announcements(self):
        import os

        
        lines = []
        # lines.append(f"Siada CLI v{__version__} supported by Li Auto")
        
        # Add current working directory
        current_dir = os.getcwd()
        lines.append(f"Working Directory: {current_dir}")

        output = f"Agent: {self.config.agent_name}, Provider: {self.config.llm_config.provider}, Model: {self.config.llm_config.model_name}"

        # Check for thinking token budget
        thinking_tokens = self.config.llm_config.get_thinking_tokens()
        if thinking_tokens:
            if thinking_tokens == "adaptive":
                output += f", adaptive thinking"
            else:
                output += f", {thinking_tokens} think tokens"

        # Check for reasoning effort
        reasoning_effort = self.config.llm_config.get_reasoning_effort()
        if reasoning_effort:
            output += f", reasoning {reasoning_effort}"

        # if self.shell_mode:
        #     output += ", shell mode"
        # else:
        #     output += ", agent mode"
        
        lines.append(output)
        return lines

    def show_announcements(self):
        import os 
        
        logging.info(f"[Controller] show_announcements called, acp_mode={self.config.acp_mode}")
        
        # ACP mode: send structured banner info FIRST (before clear)
        if self.config.acp_mode:
            import json
            from siada.io.acp.message_builder import ACPMessageBuilder
            
            # Get available slash commands
            slash_commands = []
            if hasattr(self, 'slash_commands') and self.slash_commands:
                try:
                    # Get commands with session context to include custom commands
                    session = getattr(self, 'session', None)
                    commands = self.slash_commands.get_commands(session)
                    
                    # Build command list with descriptions
                    for cmd in commands:
                        cmd_name = cmd[1:]  # Remove leading /
                        cmd_method_name = f"cmd_{cmd_name}".replace("-", "_")
                        cmd_method = getattr(self.slash_commands, cmd_method_name, None)
                        
                        description = ""
                        if cmd_method and cmd_method.__doc__:
                            description = cmd_method.__doc__.strip()
                        
                        slash_commands.append({
                            "name": cmd_name,
                            "description": description
                        })
                except Exception as e:
                    logging.warning(f"[Controller] Failed to get slash commands: {e}")
            
            # Get checkpoint files list
            checkpoints = []
            try:
                session = getattr(self, 'session', None)
                if session and hasattr(session, 'checkpoint_service') and session.checkpoint_service:
                    checkpoint_files = session.checkpoint_service.list_checkpoint_files(session.session_id)
                    # Limit to 50 most recent checkpoints
                    for cp_file in checkpoint_files[:50]:
                        checkpoints.append({
                            "file_name": cp_file.file_name,
                            "timestamp": cp_file.timestamp_str,
                            "tool": cp_file.tool_placeholder,
                            "modified_files": cp_file.modified_files_placeholder
                        })
                    logging.info(f"[Controller] Found {len(checkpoints)} checkpoint files")
            except Exception as e:
                logging.warning(f"[Controller] Failed to get checkpoint files: {e}")
            
            # Get session ID and project hash
            session_id = None
            project_hash = None
            session = getattr(self, 'session', None)
            if session:
                session_id = getattr(session, 'session_id', None)
                workspace = getattr(self.config, 'workspace', None)
                if workspace:
                    from siada.utils import DirectoryUtils
                    project_hash = DirectoryUtils.get_file_path_hash(workspace)
            
            # Resolve current memory enabled status from RunningConfig (mirrored from conf.yaml at startup).
            # Avoids importing siada_runner here, which would synchronously pull in the agents SDK
            # on the main thread and block startup by 10+ seconds (fighting the BG agents-init
            # thread for the per-module import lock).
            _memory_enabled = getattr(self.config, 'memory_enabled', True)

            banner_info = {
                "version": __version__,
                "working_dir": os.getcwd(),
                "agent": self.config.agent_name,
                "provider": self.config.llm_config.provider,
                "model": self.config.llm_config.model_name,
                "thinking_tokens": self.config.llm_config.get_thinking_tokens(),
                "reasoning_effort": self.config.llm_config.get_reasoning_effort(),
                "parallel_tool_calls": self.config.llm_config.parallel_tool_calls,
                "slash_commands": slash_commands,  # Add slash commands list
                "checkpoints": checkpoints,  # Add checkpoint files list
                "session_id": session_id,  # Add session ID
                "project_hash": project_hash,  # Add project hash
                "memory_enabled": _memory_enabled,  # Memory master switch status
            }
            
            logging.info(f"[Controller] Sending banner_info in ACP mode with {len(slash_commands)} commands")
            
            try:
                builder = ACPMessageBuilder()
                
                # Use _send_if_acp helper method
                result = self.config.io.acp_adapter._send_if_acp(
                    lambda: builder.build_session_update(
                        reason="banner_info",
                        content=json.dumps(banner_info),
                        metadata={"type": "banner"}
                    )
                )
                
                logging.info(f"[Controller] Banner info sent via _send_if_acp, result={result}")
            except Exception as e:
                logging.error(f"[Controller] Failed to send banner_info: {e}", exc_info=True)

            # In ACP mode, don't clear terminal or show traditional banner
            return
        
        # Traditional mode: clear terminal
        os.system('clear' if os.name != 'nt' else 'cls')
        
        # Check if banner is enabled in config
        if not self.config.banner:
            # Banner is disabled, skip showing it
            return
        if self.need_show_announcements_welcome_panel:
            # only once
            self.need_show_announcements_welcome_panel = False
            self.show_announcements_welcome_panel()  
        else:
            for line in self.get_announcements():
                self.config.io.print_info(line)
    
    def show_announcements_welcome_panel(self, console: Console = None):
        from siada.io.banner import BannerDisplay

        announcements = self.get_announcements()
        BannerDisplay.show_welcome_panel(announcements=announcements, console=console
                                         , siada_version=f"Siada CLI v{__version__}")

    def keyboard_interrupt(self):
        # Ensure cursor is visible on exit
        Console().show_cursor(True)

        now = time.time()
        if self.last_keyboard_interrupt and (
            now - self.last_keyboard_interrupt < 2
        ):
            # Check if running in ACP mode
            if self.config.acp_mode:
                # In ACP mode, send JSON message for interrupt
                import json
                from siada.io.acp.message_builder import ACPMessageBuilder
                
                builder = ACPMessageBuilder()
                interrupt_msg = builder.build_cancelled("Execution interrupted by user (Ctrl+C)")
                
                # Print JSON message to stdout for siada-cli-ui to capture
                print(interrupt_msg.to_json(), flush=True)
                
            else:
                # Non-ACP mode: print normal warning
                self.config.io.print_warning("\n\n^C KeyboardInterrupt")
            
            # Set exiting flag and ignore further SIGINT signals
            # This ensures the third Ctrl+C won't interrupt cleanup
            self._exiting = True
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            try:
                from siada.services.mcp.manager_service import _mcp_manager_service as mcp_service
                if mcp_service.is_initialized:
                    asyncio.run(mcp_service.shutdown())
            except Exception as e:
                logging.error(f"Error during MCP cleanup: {e}")

            try:
                sid = self.session.session_id
                print(f"\nTo continue this session, run: siada-cli --resume {sid}")
            except Exception:
                pass

            self._fire_session_end("interrupt")
            sys.exit(1)

        # First Ctrl+C: send interrupt notification in ACP mode
        if self.config.acp_mode:
            # Commented out backend interrupt message sending, keeping only frontend messages
            # import json
            # from siada.io.acp.message_builder import ACPMessageBuilder
            
            # builder = ACPMessageBuilder()
            # interrupt_msg = builder.build_session_update(
            #     reason="cancelled",
            #     content="Execution interrupted (Ctrl+C). Press Ctrl+C again to exit."
            # )
            
            # # Print JSON message to stdout for siada-cli-ui to capture
            # print(interrupt_msg.to_json(), flush=True)
            
            pass
        else:
            self.config.io.print_warning("\n\n^C again to exit")
        
        self.last_keyboard_interrupt = now

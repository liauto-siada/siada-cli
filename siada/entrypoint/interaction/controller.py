"""Async ACP input dispatch, turn policy and presentation adapters."""

import asyncio
import signal
import sys
import threading
import time
from collections import deque
from uuid import uuid4

from siada.session.session_models import RunningSession
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.entrypoint.interaction.controller_ui import ControllerUI
from siada.entrypoint.interaction.turn_input import build_terminal_pending_input
from siada.entrypoint.interaction.turn_policy import TurnPolicy
from siada.foundation.logging import logger as logging
from siada.services.agent_loader import get_agent_class_path, import_agent_class
from siada.support.slash_commands import SlashCommands, SwitchEvent
from siada.entrypoint.interaction.command_input import CommandInput


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
        self._bg_wakeup_event = asyncio.Event()
        self._bg_wakeup_registered_ids = set()
        self._effort_command_lock = threading.Lock()
        self._loop = None
        self._active_task = None
        self._exit_requested = False
        self._exit_reason = "normal"
        self._pending_commands: deque[CommandInput] = deque()
        self._commands_available = asyncio.Event()
        self._command_tasks: set[asyncio.Task[None]] = set()
        self._accepting_commands = False
        self._executing_serial_command = False
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
            get_stdin_monitor().set_effort_handler(self._handle_effort_intercept)

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
        """Own one event loop and provider runtime for the entire session."""
        from siada.provider.provider_factory import run_in_provider_runtime

        return asyncio.run(run_in_provider_runtime(self.run_async()))

    async def run_async(self) -> int:
        pending_input = None
        exit_reason = "normal"
        from siada.io.stdin_interrupt_monitor import (
            get_stdin_monitor, install_sigint_handler, is_monitor_active,
        )
        self._loop = asyncio.get_running_loop()
        self._accepting_commands = True
        previous_sigint = signal.getsignal(signal.SIGINT)
        monitor = get_stdin_monitor() if is_monitor_active() else None
        if monitor is not None:
            monitor.bind_async_reader(self._request_shutdown)
            monitor.set_command_handler(self._route_command, self._request_command_cancel)
        install_sigint_handler(self._request_interrupt)
        try:
            self.ui.register_notification_handler()
            await self.turn_policy.start_session(self.session)
            self._register_background_wakeup(self.session)
            while not self._exit_requested:
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
                        self._active_task = asyncio.create_task(self._read_input())
                        user_input = await self._active_task
                        if isinstance(user_input, CommandInput):
                            command = user_input
                            name = command.prompt.split(maxsplit=1)[0][1:]
                            if command.prompt.startswith("/") and self.slash_commands.get_execution_mode(name) == "immediate":
                                self._accept_command(command)
                                continue
                            user_input = command.prompt
                            self.config.io._input_request_id = command.request_id
                            self.config.io._pending_image_paths = []
                            if command.queue_id:
                                self.ui.send_notification("session/update", {
                                    "reason": "queue_item_consumed", "content": "",
                                    "metadata": {"id": command.queue_id, "content": command.prompt},
                                })
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
                    from siada.foundation.context import set_context_var
                    from siada.foundation.log_context import REQUEST_ID
                    request_id = getattr(self.config.io, "_input_request_id", None)
                    if user_initiated and request_id:
                        set_context_var(REQUEST_ID, str(request_id))
                    set_context_var("turn_start_time", time.time())
                    logging.info("[Controller] [TURN_START] About to execute turn")
                    self._active_task = asyncio.create_task(
                        self._execute_turn(user_input, user_initiated),
                        name=f"conversation-turn-{self.session.session_id}",
                    )
                    output = await self._active_task
                    self.ui.remember_history_state(self.session)
                    logging.info("[Controller] [TURN_COMPLETE] Turn execution finished")
                    if output is None:
                        self.ui.set_processing(False)
                        continue
                    if isinstance(output.output, SwitchEvent):
                        pending_input = self._handle_switch_event(output.output)
                except KeyboardInterrupt:
                    self.keyboard_interrupt()
                except asyncio.CancelledError:
                    # A user interrupt cancels the child, not this dispatcher.
                    if asyncio.current_task().cancelling():
                        raise
                    self.ui.set_processing(False)
                    if self._exit_requested:
                        exit_reason = self._exit_reason
                except EOFError:
                    break
                except Exception as exc:
                    from siada.entrypoint.interaction.turn.command_turn import ControllerExit
                    if isinstance(exc, ControllerExit):
                        break
                    self.config.io.print_error(exc)
                    exit_reason = "error"
                    break
                finally:
                    self._active_task = None
        except asyncio.CancelledError:
            exit_reason = "interrupt"
            raise
        except Exception:
            exit_reason = "error"
            raise
        finally:
            self._accepting_commands = False
            if monitor is not None:
                monitor.set_command_handler(None)
            if self._command_tasks:
                for task in tuple(self._command_tasks):
                    task.cancel()
                await asyncio.gather(*tuple(self._command_tasks), return_exceptions=True)
            self._pending_commands.clear()
            self._unregister_background_wakeups()
            from siada.io.stdin_interrupt_monitor import is_monitor_active, get_stdin_monitor
            if is_monitor_active():
                get_stdin_monitor().set_btw_handler(None)
            try:
                try:
                    await self.turn_policy.end_session(self.session, exit_reason)
                finally:
                    from siada.services.mcp.manager_service import _mcp_manager_service
                    if _mcp_manager_service.is_initialized:
                        await _mcp_manager_service.shutdown()
            finally:
                if monitor is not None:
                    monitor.unbind_async_reader()
                signal.signal(signal.SIGINT, previous_sigint)
                self._loop = None
                self.ui.close()
        return 1 if exit_reason in ("error", "interrupt") else 0

    async def _read_input(self):
        """Wait for input or background completion, preserving input on ties."""
        from siada.io.io import BACKGROUND_WAKEUP_SENTINEL

        # Apply already-queued commands before consuming another ordinary prompt.
        if self._pending_commands:
            command = self._pending_commands.popleft()
            if not self._pending_commands:
                self._commands_available.clear()
            return command

        input_task = asyncio.create_task(self.config.io.get_input_async())
        wake_task = asyncio.create_task(self._bg_wakeup_event.wait())
        command_task = asyncio.create_task(self._commands_available.wait())
        try:
            await asyncio.wait(
                (input_task, wake_task, command_task), return_when=asyncio.FIRST_COMPLETED,
            )
            if input_task.done():
                return input_task.result()
            if self._pending_commands:
                command = self._pending_commands.popleft()
                if not self._pending_commands:
                    self._commands_available.clear()
                return command
            return BACKGROUND_WAKEUP_SENTINEL
        finally:
            for task in (input_task, wake_task, command_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(input_task, wake_task, command_task, return_exceptions=True)

    def _route_command(self, prompt: str, queue_id: object, request_id: object) -> bool:
        """Reader-thread routing never executes commands or consumes tool replies."""
        prompt = prompt.strip()
        loop = self._loop
        if loop is None or not self._accepting_commands or not self.slash_commands.is_command(prompt):
            return False
        request = CommandInput(
            prompt=prompt, command_id=uuid4().hex,
            request_id=request_id if isinstance(request_id, str) else uuid4().hex,
            queue_id=queue_id if isinstance(queue_id, str) else None,
        )
        try:
            loop.call_soon_threadsafe(self._accept_command, request)
        except RuntimeError:
            return False
        return True

    def _accept_command(self, command: CommandInput) -> None:
        """Serialize mutations, while approved queries get their own short task."""
        if not self._accepting_commands or self._exit_requested:
            return
        name = command.prompt.split(maxsplit=1)[0][1:]
        immediate = (
            command.prompt.startswith("/")
            and self.slash_commands.get_execution_mode(name) == "immediate"
            and not self._executing_serial_command
        )
        queue = self._command_tasks if immediate else self._pending_commands
        if len(queue) >= 64:
            self._send_command_result(command, "Too many pending commands", error=True)
        elif immediate:
            task = asyncio.create_task(
                self._execute_immediate_command(command),
                name=f"command-{name}-{command.command_id}",
            )
            self._command_tasks.add(task)
            task.add_done_callback(self._command_tasks.discard)
        else:
            self._pending_commands.append(command)
            self._commands_available.set()
            logging.info("[COMMAND_QUEUED] command=%s commandId=%s", name, command.command_id)

    async def _execute_immediate_command(self, command: CommandInput) -> None:
        from siada.entrypoint.interaction.turn.command_turn import CommandTurn
        from siada.entrypoint.interaction.turn.models import TurnInput
        from siada.foundation.context import set_context_var
        from siada.foundation.log_context import REQUEST_ID

        set_context_var(REQUEST_ID, command.request_id)
        try:
            turn = CommandTurn(self.config, self.session, self.slash_commands)
            result = await turn.execute_immediate(TurnInput(use_input=command.prompt))
            self._send_command_result(command, result.output)
        except Exception as exc:
            logging.warning("[Controller] Immediate command failed: %s", exc)
            self._send_command_result(command, str(exc), error=True)

    def _send_command_result(
        self, command: CommandInput, content: str, *, error: bool = False,
    ) -> None:
        params = {
            "commandId": command.command_id,
            "command": command.prompt.split(maxsplit=1)[0][1:],
            "content": content, "error": error, "queueId": command.queue_id,
        }
        self.ui.send_notification("ui/commandResult", params)
        logging.info("[COMMAND_RESULT] command=%s commandId=%s error=%s",
                     params["command"], command.command_id, error)

    def _request_command_cancel(self) -> None:
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(self._clear_pending_commands)
            except RuntimeError:
                pass  # The session loop has already closed.

    def _clear_pending_commands(self) -> None:
        self._pending_commands.clear()
        self._commands_available.clear()

    async def _execute_turn(self, user_input, user_initiated):
        from siada.entrypoint.siadahub import _ensure_litellm_ready, _ensure_agents_ready
        from siada.entrypoint.interaction.turn.turn_factory import TurnFactory

        turn = None
        try:
            await asyncio.to_thread(_ensure_litellm_ready)
            await asyncio.to_thread(_ensure_agents_ready)
            await asyncio.to_thread(self.wait_for_preload, timeout=20)
            if isinstance(user_input, str) and not user_input.startswith(("/", "!")):
                self.ui.send_session_title_async(user_input)
            turn = TurnFactory.create_turn(
                self.config, self.session, self.slash_commands, user_input,
            )
            from siada.entrypoint.interaction.turn.command_turn import CommandTurn
            self._executing_serial_command = isinstance(turn, CommandTurn)
            try:
                return await self.turn_policy.execute(
                    turn, user_input, self.session, user_initiated=user_initiated,
                )
            finally:
                self._executing_serial_command = False
        except asyncio.CancelledError:
            if turn is None and isinstance(user_input, str):
                from siada.io.acp.message_builder import ACPMessageBuilder
                self.ui._send_if_acp(ACPMessageBuilder().build_session_update(
                    reason="restore_input", content=user_input, metadata={},
                ))
            raise

    def _request_interrupt(self):
        """Schedule cancellation rather than raising through the event loop."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self.keyboard_interrupt)

    def _request_shutdown(self):
        """A closed UI pipe ends the session, including an active turn."""
        self._exit_requested = True
        if self._active_task is not None and not self._active_task.done():
            if not self._active_task.cancelling():
                from siada.tools.coder.cmd_runner import cancel_current_command
                cancel_current_command()
                self._active_task.cancel()

    def _handle_switch_event(self, event: SwitchEvent):
        values = event.kwargs
        if values.get("model"):
            self.config.model = values["model"]
            self._update_llm_config_for_model(values["model"])
        elif values.get("ai_analysis_prompt"):
            return self._build_pending_input_for_ai_analysis(
                values["ai_analysis_prompt"], values.get("goal_command", False),
            )
        elif values.get("fork_data") is not None:
            from siada.support.session_restore import restore_into_fresh_session

            data = values["fork_data"]
            new_session = restore_into_fresh_session(
                data, target_workspace=self.config.workspace,
                siada_config=self.config, session_id=data.session_id,
            )
            self._release_cli_ownership()
            self.session = new_session
            self._unregister_background_wakeups()
            self._bg_wakeup_event.clear()
            self._register_background_wakeup(self.session)
            if self.config.completer:
                self.config.completer.session_id = self.session.session_id
            self.ui.reset_history_state()
            self.show_announcements()
            if self.config.io.acp_adapter is not None:
                self.slash_commands._send_history_to_ui(data.items)
                self.slash_commands._push_resumed_goal_state_to_ui(self.session)
            self.config.io.print_info(
                f"Forked session {data.metadata['parent_session_id']} → {data.session_id}"
            )
            return None
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
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._bg_wakeup_event.set)
        else:
            self._bg_wakeup_event.set()

    def keyboard_interrupt(self):
        now = time.time()
        if self.last_keyboard_interrupt and now - self.last_keyboard_interrupt < 2:
            self.ui.send_cancelled("Execution interrupted by user (Ctrl+C)")
            self._exit_requested = True
            self._exit_reason = "interrupt"
        self.last_keyboard_interrupt = now
        if self._active_task is not None and not self._active_task.done():
            # A second tap requests exit without cancelling cleanup a second time.
            if not self._active_task.cancelling():
                from siada.tools.coder.cmd_runner import cancel_current_command
                from siada.io.stdin_interrupt_monitor import get_stdin_monitor
                cancel_current_command()
                get_stdin_monitor().interrupt_sync_readers()
                self._active_task.cancel()


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

            # Keep the resolved provider available to shared request callbacks.
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

    def _handle_effort_intercept(self, level: str) -> None:
        """Serialize effort settings without admitting a new agent request."""
        with self._effort_command_lock:
            try:
                self.slash_commands.cmd_effort(self.session, level)
            except Exception:
                logging.exception("[Controller] /effort intercept handler failed")
                self.config.io.print_error("Failed to update reasoning effort. Please retry.")


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

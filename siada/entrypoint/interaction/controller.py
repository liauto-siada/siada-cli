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
from siada.entrypoint.interaction.turn import TurnFactory, TurnInput
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
        # Pre-load agent class asynchronously to optimize first-time execution
        self._start_preload_agent()
        self.need_show_announcements_welcome_panel:bool = True
        self._exiting = False  # Flag to track if we're in exit phase

        # Register atexit handler to release CLI ownership on process exit
        import atexit
        atexit.register(self._release_cli_ownership)
    
    def _start_preload_agent(self):
        """
        Start pre-loading the agent class in a background thread.
        This method initiates the async preload without blocking the main thread.
        """
        def run_async_preload():
            """Run the async preload in a new event loop"""
            try:
                # Create a new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._preload_agent())
                
                self._preload_success = True
            except Exception as e:
                logging.warning(f"[Controller] Background preload thread error: {e}")
                self._preload_success = False
            finally:
                loop.close()
                # Signal that preload is complete (success or failure)
                self._preload_complete.set()
        
        # Start preload in a daemon thread so it doesn't block program exit
        self._preload_thread = threading.Thread(target=run_async_preload, daemon=True)
        self._preload_thread.start()
        # logging.info(f"[Controller] Agent pre-loading started in background thread")
    
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
        
        Args:
            timeout: Maximum time to wait in seconds. None means wait indefinitely.
            show_spinner: Whether to show a spinner while waiting.
        
        Returns:
            bool: True if preload completed successfully, False if timeout or failed
        """
        spinner = None
        try:
            # Create spinner for visual feedback if requested and preload is not complete
            if show_spinner and not self._preload_complete.is_set():
                if self.config.io and self.config.io.pretty:
                    message = f"Loading {self.config.agent_name} agent..."
                    spinner = WaitingSpinner(message, text_color="#79B8FF")
                    spinner.start()
            
            if self._preload_complete.wait(timeout=timeout):
                return self._preload_success
            return False
        finally:
            # Stop spinner if it was created
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

    def run(self) -> int:
        session = self.session
        display_rule = False
        pending_input = None  # Pending input to process in next iteration

        while True:
            try:
                if pending_input:
                    user_input = pending_input
                    pending_input = None
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
                    
                    # 🔍 Log input received for analysis
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

                turn = TurnFactory.create_turn(
                    self.config, session, self.slash_commands, user_input
                )
                
                # 🔍 Log before turn execution
                logging.warning(f"[Controller] [TURN_START] About to execute turn", extra={
                    "component": "Controller",
                    "operation": "turn_execute",
                    "input_hash": hash(user_input) if isinstance(user_input, str) else hash(str(user_input)),
                    "timestamp": time.time(),
                })
                
                turn_output = self._execute_turn_with_ownership(turn, user_input, session)
                
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
                            new_llm_config = ModelRunConfig(model_name)
                            new_llm_config.provider = self.config.llm_config.provider
                            self.config.llm_config = new_llm_config
                        except Exception as _e:
                            logging.warning(f"[Controller] Failed to update llm_config for model switch: {_e}")

                    elif turn_output.output.kwargs.get("ai_analysis_prompt"):
                        # Set pending input for next iteration - reuse existing flow
                        pending_input = turn_output.output.kwargs.get("ai_analysis_prompt")
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
                break

    def _release_cli_ownership(self):
        """Release CLI ownership for the current session on process exit.

        Called via atexit to ensure no stale CLI locks remain after
        the TUI/CLI process is killed or exits unexpectedly.
        Only applies to IM (Lark) sessions; regular CLI sessions have no ownership.
        """
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
            if not SessionOwnershipManager.is_im_session(session_dir):
                logging.info(f"[Controller] Not an IM session, skipping ownership release: {session_dir}")
                return
            SessionOwnershipManager.release_ownership(session_dir, SessionOwner.CLI)
            logging.info(f"[Controller] CLI ownership released on exit for session: {session_dir}")
        except Exception as e:
            logging.info(f"[Controller] Failed to release CLI ownership on exit: {e}")

    def _get_session_dir(self, session: RunningSession):
        """Get session directory if available, otherwise None."""
        try:
            fs = session.state.openai_session
            if fs and hasattr(fs, 'session_folder') and fs.session_folder.exists():
                return fs.session_folder
        except Exception:
            pass
        return None

    def _execute_turn_with_ownership(self, turn, user_input, session):
        """Execute a turn with ownership guard for IM sessions.

        For sessions created by Lark, acquires CLI ownership before execution
        and releases it after, preventing concurrent access from the Lark side.
        For regular CLI sessions this is a no-op passthrough.
        """
        from siada.session.ownership import SessionOwnershipManager, SessionOwner, OwnershipError

        session_dir = self._get_session_dir(session)
        try:
            with SessionOwnershipManager.owned_turn(session_dir, SessionOwner.CLI):
                return turn.execute(TurnInput(use_input=user_input))
        except OwnershipError:
            self.config.io.print_warning(
                "⚠️ This session is being used by Lark bot. "
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

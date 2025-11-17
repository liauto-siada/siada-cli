"""
Interaction Controller Module

Manages the AI coding interaction lifecycle and controls the main interaction flow.
Separates core interaction logic from main entry point for better code organization.
"""

import time
import asyncio
import threading
from regex import T
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
                    # Get user input normally
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
                turn_output = turn.execute(TurnInput(use_input=user_input))

                if isinstance(turn_output.output, SwitchEvent):
                    if turn_output.output.kwargs.get("model"):
                        self.config.model = turn_output.output.kwargs.get("model")

                    elif turn_output.output.kwargs.get("ai_analysis_prompt"):
                        # Set pending input for next iteration - reuse existing flow
                        pending_input = turn_output.output.kwargs.get("ai_analysis_prompt")
                        continue

                    elif turn_output.output.kwargs.get("clear"):
                        # Create a new session without previous history
                        from siada.session.session_manager import RunningSessionManager
                        import time
                                                
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
                self.keyboard_interrupt()
            except Exception as e:
                self.config.io.print_error(e)
                break

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
            output += f", {thinking_tokens} think tokens"

        # Check for reasoning effort
        reasoning_effort = self.config.llm_config.get_reasoning_effort()
        if reasoning_effort:
            output += f", reasoning {reasoning_effort}"

        if self.shell_mode:
            output += ", shell mode"
        else:
            output += ", agent mode"

        lines.append(output)
        return lines

    def show_announcements(self):
            # Clear terminal using system clear command
        import os 
        os.system('clear' if os.name != 'nt' else 'cls')
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
            self.config.io.print_warning("\n\n^C KeyboardInterrupt")
            sys.exit(1)

        self.config.io.print_warning("\n\n^C again to exit")
        self.last_keyboard_interrupt = now

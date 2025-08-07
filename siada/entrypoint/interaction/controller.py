"""
Interaction Controller Module

Manages the AI coding interaction lifecycle and controls the main interaction flow.
Separates core interaction logic from main entry point for better code organization.
"""

from siada.session.session_models import RunningSession
from siada import __version__
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.entrypoint.interaction.turn import TurnFactory, TurnInput
from siada.support.slash_commands import SlashCommands, SwitchEvent
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

    def run(self) -> int:
        session = self.session
        display_rule = True
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

                    # show the announcements in every switch event
                    if turn_output.output.kwargs.get("shell"):
                        self.shell_mode = True
                    self.show_announcements()
            except KeyboardInterrupt as e:
                self.keyboard_interrupt()
                break
            except Exception as e:
                self.config.io.print_error(e)
                break

    def get_announcements(self):
        lines = []
        lines.append(f"Siada CLI v{__version__} supported by Li Auto")

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
        for line in self.get_announcements():
            self.config.io.print_info(line)

    def keyboard_interrupt(self):
        # Ensure cursor is visible on exit
        Console().show_cursor(True)

        self.config.io.print_warning("\n\n^C KeyboardInterrupt")
        sys.exit()

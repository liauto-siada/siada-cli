"""
Interaction Controller Module

Manages the AI coding interaction lifecycle and controls the main interaction flow.
Separates core interaction logic from main entry point for better code organization.
"""

from dataclasses import dataclass

import siada.support.completer
from siada import __version__
from siada.entrypoint.interaction.config import InteractionConfig
from siada.entrypoint.interaction.run_turn import TurnFactory
from siada.io.io import InputOutput
from siada.models.model_setting import ModelConfig
from siada.session.session_manager import InteractionSessionManager
from siada.support.slash_commands import SlashCommands, SwitchEvent


class InteractionController:
    """Controls user-AI coding interactions and manages coder lifecycle"""


    def __init__(self, config: InteractionConfig):
        self.config = config


    def run(self) -> int:
        session = InteractionSessionManager.create_session(
            interaction_config=self.config,
        )
        while True:
            try:
                user_input = self.config.io.get_input(
                    root=self.config.workspace,
                    completer=self.config.completer,
                )
                turn = TurnFactory.create_turn(self.config, session, user_input)
                turn_output = turn.execute(user_input)

                if isinstance(turn_output.output, SwitchEvent):
                    if turn_output.output.kwargs.get("agent"):

                        self.config.agent_name = turn_output.output.kwargs.get("agent")
                        # clear the session to avoid the previous agent's messages
                        session.state.openai_session.clear_session()

                    elif turn_output.output.kwargs.get("model"):
                        self.config.model = turn_output.output.kwargs.get("model")
                    # show the announcements in every switch event
                    self.show_announcements()
            except Exception as e:
                self.config.io.print_error(e)
                break

    def get_announcements(self):
        lines = []
        lines.append(f"SiadaHub v{__version__}")

        output = f"Agent: {self.config.agent_name}"

        # Check for thinking token budget
        thinking_tokens = self.config.model.get_thinking_tokens()
        if thinking_tokens:
            output += f", {thinking_tokens} think tokens"

        # Check for reasoning effort
        reasoning_effort = self.config.model.get_reasoning_effort()
        if reasoning_effort:
            output += f", reasoning {reasoning_effort}"

        return output

    def show_announcements(self):
        for line in self.get_announcements():
            self.config.io.print_info(line)

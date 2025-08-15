from typing import Any

from siada.entrypoint.interaction.base_turn import RunTurn
from siada.entrypoint.interaction.config import RunningConfig
from siada.entrypoint.interaction.turn.run_turn import CommandTurn, ConversationTurn


class TurnFactory:
    """Factory for creating appropriate turn instances"""

    @staticmethod
    def create_turn(
        config: RunningConfig, session: Any, slash_commands: Any, user_input: str
    ) -> RunTurn:
        """Create appropriate turn for user input

        Args:
            user_input: Raw user input

        Returns:
            RunTurn: Appropriate turn handler
        """
        # Always create new instances to avoid state pollution
        turn_types = [
            CommandTurn,
            ConversationTurn,
        ]

        for turn_class in turn_types:
            # Create a temporary instance to test if it can handle the input
            temp_turn = turn_class(config, session, slash_commands)
            if temp_turn.can_handle(user_input):
                return temp_turn

        raise ValueError(f"No turn can handle the input: {user_input}") 
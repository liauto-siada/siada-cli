"""
Turn Factory Module

Factory for creating appropriate turn instances based on user input.
"""

from typing import List, Any

# Import existing InteractionConfig
from ..running_config import RunningConfig

# Import turn classes
from .conversation_turn import ConversationTurn
from .command_turn import CommandTurn
from .interface import RunTurn


class TurnFactory:
    """Factory for creating appropriate turn instances"""

    @staticmethod
    def create_turn(
        config: RunningConfig, session: Any, slash_commands: Any, user_input: str | List[Any]
    ) -> RunTurn:
        """Create appropriate turn for user input

        Args:
            config: Running configuration
            session: Current session
            slash_commands: Slash commands handler
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
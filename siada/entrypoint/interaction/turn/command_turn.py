"""
Command Turn Module

Handles slash command execution turns.
"""

from typing import List, Any

# Import existing InteractionConfig

# Import models and interface from the same directory
from .models import TurnType, TurnInput, TurnOutput
from .interface import RunTurn


class CommandTurn(RunTurn):
    """Handles slash command turns"""

    def get_turn_type(self) -> TurnType:
        return TurnType.COMMAND

    def can_handle(self, user_input: str | List[Any]) -> bool:
        """Handle slash commands"""
        if isinstance(user_input, list):
            return False
        return self.slash_commands.is_command(user_input)

    def execute(self, turn_input: TurnInput) -> TurnOutput:
        """Execute slash command

        Args:
            turn_input: Command input

        Returns:
            TurnOutput: Command result
        """
        self.input_data = turn_input
        self.start_time = self._get_timestamp()

        try:
            result = self.slash_commands.run(self.session, turn_input.use_input)
            self.end_time = self._get_timestamp()

            output = TurnOutput(
                output=result,
                metadata={"execution_time": self.end_time - self.start_time},
                next_action=None,
            )

            return output

        except Exception as e:
            self.end_time = self._get_timestamp()
            return self.handle_error(e)
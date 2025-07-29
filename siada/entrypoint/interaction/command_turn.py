from siada.entrypoint.interaction.base_turn import RunTurn
from siada.entrypoint.interaction.turn_models import TurnInput, TurnOutput, TurnType


class CommandTurn(RunTurn):
    """Handles slash command turns"""

    def get_turn_type(self) -> TurnType:
        return TurnType.COMMAND

    def can_handle(self, user_input: str) -> bool:
        """Handle slash commands"""
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
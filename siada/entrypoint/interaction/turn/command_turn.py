"""
Command Turn Module

Handles slash command execution turns.
"""

from typing import List, Any

# Import existing InteractionConfig

# Import models and interface from the same directory
from .models import TurnType, TurnInput, TurnOutput
from .interface import RunTurn


class ControllerExit(Exception):
    """A slash command requested a normal controller shutdown."""


class CommandTurn(RunTurn):
    """Handles slash command turns"""

    async def execute_immediate(self, turn_input: TurnInput) -> TurnOutput:
        """Run a read-only formatter without turn hooks or input_ready events."""
        token = turn_input.use_input.strip().split(maxsplit=1)[0]
        if not token.startswith("/") or token.startswith("//"):
            raise ValueError("Immediate execution requires a slash command")
        name = token[1:]
        if self.slash_commands.get_execution_mode(name) != "immediate":
            raise ValueError(f"/{name} requires serial execution")
        if name == "status":
            content = self.slash_commands.get_status_text(self.session)
        elif name == "help":
            content = self.slash_commands.get_help_text()
        else:
            raise ValueError(f"/{name} has no immediate handler")
        return TurnOutput(output=content, metadata={"command": name}, next_action=None)

    def get_turn_type(self) -> TurnType:
        return TurnType.COMMAND

    def can_handle(self, user_input: str | List[Any]) -> bool:
        """Handle slash commands"""
        if isinstance(user_input, list):
            return False
        return self.slash_commands.is_command(user_input)

    async def execute(self, turn_input: TurnInput) -> TurnOutput:
        """Execute slash command

        Args:
            turn_input: Command input

        Returns:
            TurnOutput: Command result
        """
        self.input_data = turn_input
        self.start_time = self._get_timestamp()

        try:
            import asyncio

            async def run_command():
                try:
                    return await asyncio.to_thread(
                        self.slash_commands.run, self.session, turn_input.use_input,
                    )
                except SystemExit:
                    raise ControllerExit() from None
                except KeyboardInterrupt:
                    raise asyncio.CancelledError() from None

            # Drain the worker before another turn can mutate the same session.
            command_task = asyncio.create_task(run_command())
            try:
                result = await asyncio.shield(command_task)
            except asyncio.CancelledError:
                from siada.tools.coder.cmd_runner import cancel_current_command
                from siada.io.stdin_interrupt_monitor import get_stdin_monitor
                cancel_current_command()
                get_stdin_monitor().interrupt_sync_readers()
                await asyncio.gather(command_task, return_exceptions=True)
                raise
            self.end_time = self._get_timestamp()

            output = TurnOutput(
                output=result,
                metadata={"execution_time": self.end_time - self.start_time},
                next_action=None,
            )

            return output

        except ControllerExit:
            raise
        except Exception as e:
            self.end_time = self._get_timestamp()
            return self.handle_error(e)
        finally:
            # Stop animation in ACP mode
            if self.config.acp_mode:
                from siada.io.acp.message_builder import ACPMessageBuilder
                builder = ACPMessageBuilder()
                stop_animation_msg = builder.build_session_update(
                    reason="input_ready",
                    content="",
                    metadata={"animation_control": "stop"}
                )
                # The adapter's synchronous sender is independent of loop state.
                self.config.io.acp_adapter._send_if_acp_robust(lambda: stop_animation_msg)

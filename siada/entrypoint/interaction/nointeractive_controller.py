from types import SimpleNamespace
import asyncio
from typing import TYPE_CHECKING

from siada.entrypoint.interaction.running_config import RunningConfig
from siada.session.session_models import RunningSession

if TYPE_CHECKING:
    from siada.entrypoint.interaction.console_progress import ConsoleProgressPresenter
    from siada.support.slash_commands import SlashCommands


class NoInteractiveController:
    """Execute shared conversation turns without a user-input or rendering loop."""

    def __init__(
        self, config: RunningConfig, session: RunningSession,
        slash_commands: "SlashCommands | None" = None,
    ):
        self.config = config
        self.session = session
        self.slash_commands = (
            slash_commands if slash_commands is not None else SimpleNamespace(hook_runner=None)
        )

    def run(self, user_input: str) -> int:
        from siada.provider.provider_factory import run_in_provider_runtime

        try:
            return asyncio.run(run_in_provider_runtime(self.run_async(user_input)))
        except (KeyboardInterrupt, asyncio.CancelledError):
            return 130

    async def run_async(self, user_input: str) -> int:
        from siada.entrypoint.interaction.console_progress import ConsoleProgressPresenter
        from siada.foundation.execution_progress import execution_progress_scope

        if not self.config.console_output or self.config.acp_mode:
            with execution_progress_scope(None):
                return await self._run(user_input)

        with ConsoleProgressPresenter() as presenter:
            with execution_progress_scope(presenter.channel):
                return await self._run(user_input, presenter)

    async def _run(self, user_input: str, presenter: "ConsoleProgressPresenter | None" = None) -> int:
        from siada.entrypoint.siadahub import _ensure_litellm_ready, _ensure_agents_ready
        _ensure_litellm_ready()
        _ensure_agents_ready()

        from siada.entrypoint.interaction.goal_progress import publish_goal_progress
        from siada.entrypoint.interaction.turn.command_turn import CommandTurn
        from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
        from siada.entrypoint.interaction.turn_input import build_terminal_pending_input
        from siada.entrypoint.interaction.turn.models import (
            GOAL_VERIFICATION_METADATA_KEY, RETRY_NOTICES, RETRY_REASON_METADATA_KEY,
        )
        from siada.entrypoint.interaction.turn_policy import TurnPolicy
        from siada.support.slash_commands import SlashCommands, SwitchEvent

        goal_parts = user_input.strip().split(maxsplit=1)
        is_goal_prompt = bool(goal_parts and goal_parts[0] == "/goal")
        commands = self.slash_commands
        if is_goal_prompt and not callable(getattr(commands, "run", None)):
            commands = await asyncio.to_thread(SlashCommands, io=self.config.io)
        command_turn = CommandTurn(self.config, self.session, commands) if is_goal_prompt else None
        turn = ConversationTurn(
            self.config, self.session, commands, render_stream=False,
        )
        policy = TurnPolicy(self.config, commands, publish_goal_progress)
        exit_reason = "error"
        try:
            await policy.start_session(self.session)
            pending_input = user_input.strip() if is_goal_prompt else user_input
            user_initiated = True
            while True:
                current_turn = command_turn if command_turn is not None else turn
                result = await policy.execute(
                    current_turn, pending_input, self.session, user_initiated=user_initiated,
                )
                if result is None or current_turn.error is not None:
                    return 1
                goal_verification = result.metadata.get(GOAL_VERIFICATION_METADATA_KEY)
                if goal_verification and goal_verification.get("status") == "blocked":
                    if presenter is not None:
                        presenter.flush()
                    if isinstance(result.output, str):
                        self.config.io.print(result.output)
                    details = goal_verification["notice"]
                    if goal_verification["reason"] != details:
                        details = f"{goal_verification['reason']} {details}"
                    self.config.io.print_error(
                        f"Goal not achieved: {goal_verification['objective']}. {details}"
                    )
                    return 1
                if isinstance(result.output, SwitchEvent):
                    followup = result.output.kwargs.get("ai_analysis_prompt")
                    if not followup:
                        raise RuntimeError("Non-interactive execution cannot request user interaction")
                    goal_command = bool(result.output.kwargs.get("goal_command"))
                    pending_input = build_terminal_pending_input(followup, goal_command)
                    # A goal kickoff is the user's first conversation, not a retry.
                    user_initiated = goal_command
                    command_turn = None
                    continue
                if command_turn is not None:
                    if presenter is not None:
                        presenter.flush()
                    # Only clear completes without a follow-up; missing or failed
                    # objectives must not silently exit as successful work.
                    cleared = len(goal_parts) > 1 and goal_parts[1].lower() == "clear"
                    exit_reason = "completed" if cleared else "error"
                    return 0 if cleared else 1
                if result.metadata.get(RETRY_REASON_METADATA_KEY) in RETRY_NOTICES:
                    if presenter is not None:
                        presenter.flush()
                    self.config.io.print_error("Agent response remained incomplete after automatic retries")
                    return 1
                if presenter is not None:
                    presenter.flush()
                self.config.io.print(result.output)
                exit_reason = "completed"
                return 0
        except KeyboardInterrupt:
            exit_reason = "interrupt"
            return 130
        except asyncio.CancelledError:
            exit_reason = "interrupt"
            raise
        except Exception as e:
            if presenter is not None:
                presenter.flush()
            self.config.io.print_error(f"Error running agent: {e}")
            return 1
        finally:
            try:
                await policy.end_session(self.session, exit_reason)
            finally:
                from siada.services.mcp.manager_service import _mcp_manager_service
                if _mcp_manager_service.is_initialized:
                    await _mcp_manager_service.shutdown()

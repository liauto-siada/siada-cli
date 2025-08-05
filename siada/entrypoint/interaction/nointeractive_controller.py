import asyncio
from unittest import result
from siada.entrypoint.interaction.config import RunningConfig
from siada.services.siada_runner import SiadaRunner
from siada.session.session_manager import RunningSessionManager


class NoInteractiveController:
    """Controls user-AI coding interactions and manages coder lifecycle"""

    def __init__(self, config: RunningConfig):
        self.config = config

    def run(self, user_input: str) -> int:
        session = RunningSessionManager.create_session(
            siada_config=self.config,
        )
        result = asyncio.run(
            SiadaRunner.run_agent(
                agent_name=self.config.agent_name,
                user_input=user_input,
                workspace=self.config.workspace,
                session=session,
            )
        )
        self.config.io.print(result)
        return 0

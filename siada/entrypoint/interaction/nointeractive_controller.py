import asyncio
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.session.session_models import RunningSession


class NoInteractiveController:
    """Controls user-AI coding interactions and manages coder lifecycle"""

    def __init__(self, config: RunningConfig, session: RunningSession):
        self.config = config
        self.session = session

    def run(self, user_input: str) -> int:
        from siada.services.siada_runner import SiadaRunner

        result = asyncio.run(
            SiadaRunner.run_agent(
                agent_name=self.config.agent_name,
                user_input=user_input,
                workspace=self.config.workspace,
                session=self.session,
            )
        )
        self.config.io.print(result)
        return 0

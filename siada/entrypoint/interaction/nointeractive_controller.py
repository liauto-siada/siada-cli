import asyncio
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.services import mcp_service
from siada.session.session_models import RunningSession


class NoInteractiveController:
    """Controls user-AI coding interactions and manages coder lifecycle"""

    def __init__(self, config: RunningConfig, session: RunningSession):
        self.config = config
        self.session = session

    def run(self, user_input: str) -> int:
        from siada.services.siada_runner import SiadaRunner
        
        async def run_async():
            # Initialize MCP service
            await mcp_service.initialize()
            
            try:
                # Run the agent
                result = await SiadaRunner.run_agent(
                    agent_name=self.config.agent_name,
                    user_input=user_input,
                    workspace=self.config.workspace,
                    session=self.session,
                )
                return result
            finally:
                # Shutdown MCP service
                await mcp_service.shutdown()
        
        try:
            result = asyncio.run(run_async())
            self.config.io.print(result)
        except Exception as e:
            self.config.io.print_error(f"Error running agent: {e}")
            return 1

        return 0

import importlib
from pathlib import Path
from siada.session.session_models import RunningSession
from typing import Dict, Type, Optional, Literal, overload

import yaml
from agents import RunResult, RunResultStreaming, Agent, set_trace_processors, TResponseInputItem

from siada.agent_hub.coder.tracing import create_detailed_logger
from siada.agent_hub.siada_agent import SiadaAgent
from siada.foundation.logging import logger as logging



class SiadaRunner:

    @staticmethod
    async def build_context(
        agent: SiadaAgent,
        workspace: Optional[str] = None,
        session: Optional[RunningSession] = None
    ):
        """
        Build the execution context for an agent.

        Args:
            agent: The SiadaAgent instance.
            workspace: Workspace path, optional.
            session: The running session object, optional.

        Returns:
            The configured context object.
        """
        context = await agent.get_context()

        if workspace:
            context.root_dir = workspace

        if session:
            context.session = session
            context.checkpoint_tracker = session.checkpoint_tracker
            if context.checkpoint_tracker:
                # start add current changes to save current state
                context.checkpoint_tracker.start()

        return context

    @overload
    @staticmethod
    async def run_agent(
        agent_name: str,
        user_input: str | list[TResponseInputItem],
        workspace: str = None,
        session: RunningSession = None,
        *,
        stream: Literal[True],
    ) -> RunResultStreaming: ...

    @overload
    @staticmethod
    async def run_agent(
        agent_name: str,
        user_input: str | list[TResponseInputItem],
        workspace: str = None,
        session: RunningSession = None,
        *,
        stream: Literal[False],
    ) -> RunResult: ...

    @staticmethod
    async def run_agent(
        agent_name: str,
        user_input: str | list[TResponseInputItem],
        workspace: str = None,
        session: RunningSession = None,
        stream: bool = False,
    ) -> RunResult | RunResultStreaming:
        """
        Run the specified Agent.

        Args:
            agent_name: Name of the Agent.
            user_input: User input.
            workspace: Workspace path, optional.
            session: The running session object, optional.
            stream: Whether to enable streaming output, defaults to False.

        Returns:
            Union[RunResult, RunResultStreaming]: Returns a regular or streaming result based on the stream parameter.
        """
        agent = await SiadaRunner.get_agent(agent_name)
        context = await SiadaRunner.build_context(agent, workspace, session)

        # Load user memory from siada.md file
        if workspace or (session and session.siada_config.workspace):
            workspace_path = workspace or session.siada_config.workspace
            try:
                from siada.services.siada_memory import load_siada_memory
                user_memory = load_siada_memory(workspace_path)
                context.user_memory = user_memory
            except Exception as e:
                logging.debug(f"Failed to load user memory: {e}")

        # set_trace_processors([create_detailed_logger(output_file="agent_trace.log")])
        console_output = session.siada_config.console_output if session else True
        set_trace_processors([create_detailed_logger(console_output=console_output)])

        if stream:
            # Stream execution
            result = await agent.run_streamed(user_input, context)
        else:
            # Normal execution
            result = await agent.run(user_input, context)

        return result

    @staticmethod
    async def get_agent(agent_name: str) -> SiadaAgent:
        """
        Get the corresponding Agent instance based on agent name
        
        Args:
            agent_name: Agent name, supports case-insensitive matching
                       e.g.: 'bugfix', 'BugFix', 'bug_fix', etc.
        
        Returns:
            Agent: The corresponding Agent instance
            
        Raises:
            ValueError: Raised when the corresponding Agent type is not found
            FileNotFoundError: Raised when the configuration file does not exist
            ImportError: Raised when unable to import Agent class
        """
        # Normalize agent name: convert to lowercase and remove underscores and hyphens
        normalized_name = agent_name.lower().replace('_', '').replace('-', '')

        # Load Agent mapping from configuration file
        agent_configs = SiadaRunner._load_agent_config()

        # Find the corresponding Agent configuration
        agent_config = agent_configs.get(normalized_name)

        if agent_config is None:
            supported_agents = [name for name, config in agent_configs.items() 
                              if config.get('enabled', False) and config.get('class')]
            raise ValueError(
                f"Unsupported agent type: '{agent_name}'. "
                f"Supported agent types: {supported_agents}"
            )

        # Check if Agent is enabled
        if not agent_config.get('enabled', False):
            raise ValueError(f"Agent '{agent_name}' is disabled")

        # Check if Agent class is implemented
        class_path = agent_config.get('class')
        if not class_path:
            raise ValueError(f"Agent '{agent_name}' is not implemented yet")

        # Dynamically import and instantiate Agent class
        try:
            agent_class = SiadaRunner._import_agent_class(class_path)
            agent = agent_class()
            
            # Configure MCP servers for the agent
            await SiadaRunner._configure_mcp_servers(agent)
            
            return agent
        except (ImportError, AttributeError) as e:
            raise ImportError(f"Failed to import agent class '{class_path}': {e}")

    @staticmethod
    def _load_agent_config() -> Dict[str, Dict]:
        """
        Load Agent configuration from configuration file

        Returns:
            Dict[str, Dict]: Agent configuration dictionary
        """
        # Get the configuration file path in the project root directory
        current_dir = Path(__file__).parent.parent.parent  # Go back to project root directory
        config_path = current_dir / "agent_config.yaml"

        if not config_path.exists():
            raise FileNotFoundError(f"Agent configuration file not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        return config.get('agents', {})

    @staticmethod
    def _import_agent_class(class_path: str) -> Type[Agent]:
        """
        Dynamically import Agent class

        Args:
            class_path: Complete import path of Agent class, e.g. 'siada.agent_hub.coder.bug_fix_agent.BugFixAgent'

        Returns:
            Type[Agent]: Agent class
        """
        module_path, class_name = class_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    @staticmethod
    async def _configure_mcp_servers(agent: SiadaAgent):
        """
        Configure MCP servers for the agent using delayed connection strategy
        
        Args:
            agent: The agent instance to configure
        """
        try:
            from siada.services.mcp_service import mcp_service
            
            # Check if MCP configuration is available
            if not mcp_service.has_config():
                logging.debug("No MCP configuration available, skipping MCP server configuration")
                return
                        
            # Get MCP servers from the initialized service
            mcp_servers = mcp_service.get_mcp_servers_for_agent()
            if mcp_servers:
                # Configure the agent with MCP servers using official SDK mechanism
                agent.mcp_servers = mcp_servers
                agent.mcp_config = {"convert_schemas_to_strict": True}
                
                for server in mcp_servers:
                    logging.debug(f"   - {server.name}")
            else:
                logging.warning("MCP service initialized but no servers available for agent configuration")
                
        except Exception as e:
            logging.error(f"Failed to configure MCP servers for agent: {e}")

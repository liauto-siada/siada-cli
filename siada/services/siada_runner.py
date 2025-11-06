import asyncio
import time
from siada.session.session_models import RunningSession
from typing import Optional, Literal, overload

from agents import RunResult, RunResultStreaming, set_trace_processors, TResponseInputItem

from siada.agent_hub.coder.tracing import create_detailed_logger
from siada.agent_hub.siada_agent import SiadaAgent
from siada.foundation.constants import CHECKPOINT_INIT_TIMEOUT
from siada.foundation.logging import logger as logging
from siada.services.agent_loader import get_agent_class_path, import_agent_class
from siada.support.spinner import WaitingSpinner


class SiadaRunner:

    @staticmethod
    async def _prepare_checkpoint_with_timeout(context, session):
        """
        Initialize checkpoint tracker with timeout protection.
        
        This method attempts to start or create snapshot for the checkpoint tracker with a timeout.
        - If _is_initialized is False: calls start() to initialize
        - If _is_initialized is True: calls create_snapshot() to create a new snapshot
        If initialization takes too long or fails, checkpoint functionality
        will be gracefully disabled.
        
        Args:
            context: The agent execution context
            session: The running session object
        """
        def stop_spinner(spinner_ref):
            """Helper function to safely stop and cleanup spinner"""
            if spinner_ref:
                try:
                    spinner_ref.stop()
                except Exception:
                    pass
        
        if not context.checkpoint_tracker:
            return

        # Check if already initialized
        is_initialized = hasattr(context.checkpoint_tracker, '_is_initialized') and context.checkpoint_tracker._is_initialized

        # Create spinner for visual feedback during checkpoint initialization
        spinner = None
        if (
            session.siada_config
            and session.siada_config.io
            and session.siada_config.io.pretty
        ):
            if not is_initialized:
                message = "Preparing checkpoint..."
                spinner = WaitingSpinner(message, text_color="yellow")
                spinner.start()

        try:
            if not is_initialized:
                # First time: initialize the tracker
                start_time = time.time()
                await asyncio.wait_for(
                    asyncio.to_thread(context.checkpoint_tracker.start),
                    timeout=CHECKPOINT_INIT_TIMEOUT,
                )
                elapsed_time = time.time() - start_time
                logging.info(f"Checkpoint initialized for session {session.session_id} (took {elapsed_time:.2f}s)")
                # Stop spinner if it was created
                stop_spinner(spinner)
                spinner = None
            else:
                # we need to create snapshot because we need conform to keep the snapshot stay before the tool running
                # todo only create snapshot when tool is write operation
                # Already initialized: create a new snapshot
                message = f"Snapshot for session {session.session_id}"
                start_time = time.time()
                await asyncio.wait_for(
                    asyncio.to_thread(
                        context.checkpoint_tracker.create_snapshot, message
                    ),
                    timeout=CHECKPOINT_INIT_TIMEOUT,
                )
                elapsed_time = time.time() - start_time
                logging.info(f"Checkpoint snapshot created for session {session.session_id} (took {elapsed_time:.2f}s)")
        except asyncio.TimeoutError:
            # Stop spinner if it was created
            stop_spinner(spinner)
            spinner = None
            # Timeout handling: disable checkpoint functionality
            context.checkpoint_tracker = None
            session.checkpoint_tracker = None

            # Use session's IO object to display warning
            if session.siada_config and session.siada_config.io:
                session.siada_config.io.print_warning(
                    f"\nCheckpoint creation failed due to large project size "
                    f"(timeout after {CHECKPOINT_INIT_TIMEOUT}s).\n"
                    f"Tip: Try running siada-cli from a subdirectory or use --no-checkpointing to disable checkpoints."
                )
        except Exception as e:
            # Ensure spinner is stopped
            stop_spinner(spinner)
            spinner = None
            # Disable checkpoint on other exceptions as well
            context.checkpoint_tracker = None
            session.checkpoint_tracker = None
            logging.error(f"Failed to create checkpoint: {e}")
        finally:
            # Stop spinner if it was created
            stop_spinner(spinner)
            spinner = None

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
            context.siadaignore_controller = session.siada_config.siadaignore_controller
            await SiadaRunner._prepare_checkpoint_with_timeout(context, session)

        # Load user memory from siada.md file
        if workspace or (session and session.siada_config.workspace):
            workspace_path = workspace or session.siada_config.workspace
            try:
                from siada.services.siada_memory import load_siada_memory
                user_memory = load_siada_memory(workspace_path)
                context.user_memory = user_memory
            except Exception as e:
                logging.debug(f"Failed to load user memory: {e}")

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
        session_id = session.session_id if session else "N/A"
        logging.info(f"[Runner] Starting agent execution - agent: {agent_name}, session: {session_id}, stream: {stream}")
        
        # Get agent
        start_time = time.time()
        agent = await SiadaRunner.get_agent(agent_name)
        elapsed = time.time() - start_time
        logging.info(f"[Runner] Agent loaded (took {elapsed:.2f}s)")
        
        # Build context
        start_time = time.time()
        context = await SiadaRunner.build_context(agent, workspace, session)
        elapsed = time.time() - start_time
        logging.info(f"[Runner] Context built (took {elapsed:.2f}s)")

        # set_trace_processors([create_detailed_logger(output_file="agent_trace.log")])
        console_output = session.siada_config.console_output if session else True
        set_trace_processors([create_detailed_logger(console_output=console_output)])
        logging.info("[Runner] Trace processors configured")

        # Start spinner before running agent (if injected via session)
        if session and session.spinner:
            session.spinner.start()

        # Execute agent
        start_time = time.time()
        if stream:
            # Stream execution
            logging.info("[Runner] Starting streamed agent execution")
            result = await agent.run_streamed(user_input, context)
        else:
            # Normal execution
            logging.info("[Runner] Starting normal agent execution")
            result = await agent.run(user_input, context)
        elapsed = time.time() - start_time
        logging.info(f"[Runner] Agent execution completed (took {elapsed:.2f}s)")

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
        logging.info(f"[get_agent] Starting to load agent: {agent_name}")

        # Get agent class path from configuration
        class_path = get_agent_class_path(agent_name)

        # Dynamically import and instantiate Agent class
        try:
            # Import agent class
            start_time = time.time()
            agent_class = import_agent_class(class_path)
            elapsed = time.time() - start_time
            logging.info(f"[get_agent] Agent class imported (took {elapsed:.3f}s)")
            
            # Instantiate agent
            start_time = time.time()
            agent = agent_class()
            elapsed = time.time() - start_time
            logging.info(f"[get_agent] Agent instantiated (took {elapsed:.3f}s)")

            # Configure MCP servers for the agent
            start_time = time.time()
            await SiadaRunner._configure_mcp_servers(agent)
            elapsed = time.time() - start_time
            logging.info(f"[get_agent] MCP servers configured (took {elapsed:.3f}s)")

            logging.info(f"[get_agent] Agent {agent_name} loaded successfully")
            return agent
        except (ImportError, AttributeError) as e:
            raise ImportError(f"Failed to import agent class '{class_path}': {e}")


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

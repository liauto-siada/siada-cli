import asyncio
import time

from siada.foundation.context import set_context_var, MODEL_PROVIDER_NAME, LLM_CONFIG, AGENT_NAME
from siada.session.session_models import RunningSession
from typing import Optional, Literal, overload

from agents import RunResult, RunResultStreaming, set_trace_processors, TResponseInputItem

from siada.agent_hub.coder.tracing import create_detailed_logger
from siada.agent_hub.siada_agent import SiadaAgent
from siada.foundation.constants import CHECKPOINT_INIT_TIMEOUT
from siada.foundation.logging import logger as logging
from siada.services.agent_loader import get_agent_class_path, import_agent_class
from siada.support.spinner import WaitingSpinner
from siada.provider.provider_factory import get_provider
from agents import RunConfig
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelProviderWrapper
from siada.agent_hub.context_filter.context_capture_filter import context_capture_filter
from siada.session import RunningSessionManager

class SiadaRunner:

    _context_cache: dict[tuple, object] = {}

    @staticmethod
    async def _prepare_checkpoint_with_timeout(session):
        """
        Initialize checkpoint tracker with timeout protection.
        
        This method attempts to start or create snapshot for the checkpoint tracker with a timeout.
        - If _is_initialized is False: calls start() to initialize
        - If _is_initialized is True: calls create_snapshot() to create a new snapshot
        If initialization takes too long or fails, checkpoint functionality
        will be gracefully disabled.
        
        Args:
            session: The running session object
        """
        def stop_spinner(spinner_ref):
            """Helper function to safely stop and cleanup spinner"""
            if spinner_ref:
                try:
                    spinner_ref.stop()
                except Exception:
                    pass
        
        if not session.checkpoint_tracker:
            return

        # Check if already initialized
        is_initialized = hasattr(session.checkpoint_tracker, '_is_initialized') and session.checkpoint_tracker._is_initialized

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
                    asyncio.to_thread(session.checkpoint_tracker.start),
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
                        session.checkpoint_tracker.create_snapshot, message
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
        Build the execution context for an agent, including run configuration.

        Args:
            agent: The SiadaAgent instance.
            workspace: Workspace path, optional.
            session: The running session object, optional.

        Returns:
            Tuple of (context, run_config, openai_session)
        """
        # Resolve session first — it's a prerequisite for both context and run_config
        running_session = session or RunningSessionManager.get_default_session()

        # Build context — cached per (agent_name, workspace) to avoid repeated heavy I/O
        context = await SiadaRunner.get_context(agent, running_session, workspace)

        await SiadaRunner._prepare_context_for_run(context, running_session)

        run_config = SiadaRunner._build_run_config(context, running_session)
        openai_session = running_session.state.openai_session

        return context, run_config, openai_session

    @staticmethod
    async def get_context(agent: SiadaAgent, running_session: RunningSession | None, workspace: str | None) :
        workspace_path = workspace or (running_session.siada_config.workspace if running_session else None)
        cache_key = (agent.name, workspace_path)
        if cache_key not in SiadaRunner._context_cache:
            context = await SiadaRunner._build_agent_context(agent, workspace, running_session)
            SiadaRunner._context_cache[cache_key] = context
        else:
            context = SiadaRunner._context_cache[cache_key]
        return context

    @staticmethod
    async def _prepare_context_for_run(context, running_session: RunningSession):
        """
        Prepare per-run context state before each agent execution.

        This runs unconditionally on every invocation, regardless of whether
        context was loaded from cache or built fresh.

        Args:
            context: The agent execution context.
            running_session: The current running session.
        """
        context.session = running_session
        await SiadaRunner._prepare_checkpoint_with_timeout(running_session)

    @staticmethod
    async def _build_agent_context(
        agent: SiadaAgent,
        workspace: Optional[str],
        running_session: Optional[RunningSession]
    ):
        """
        Build and fully enrich the agent execution context.

        Covers: base context, root_dir,
        workspace resources (user_memory / rule_memory / siadaignore),
        and agent configuration (pre_plan / preferred_language).

        Session binding and checkpoint operations are handled in build_context
        (per-run) and are intentionally excluded here to allow safe caching.
        """
        context = await agent.get_context()

        if workspace:
            context.root_dir = workspace

        # Load workspace-scoped resources
        workspace_path = workspace or (running_session.siada_config.workspace if running_session else None)
        if workspace_path:
            # Load and combine all memory sources into a single field
            memory_parts = []

            # 1. Load hierarchical context from siada_rule.md files (rule_memory)
            try:
                from siada.services.rule_memory import load_hierarchical_context
                rule_content, rule_count, _ = load_hierarchical_context(workspace_path)
                if rule_count > 0 and rule_content:
                    memory_parts.append(rule_content)
            except Exception as e:
                logging.warning(f"Failed to load rule_memory: {e}")

            # 2. Load user memory from siada.md
            try:
                from siada.services.siada_memory import load_siada_memory
                user_mem = load_siada_memory(workspace_path)
                if user_mem:
                    memory_parts.append(user_mem)
            except Exception as e:
                logging.debug(f"Failed to load user memory: {e}")

            # 3. Load structured memory (from ~/.siada-cli/workspace/memory)
            try:
                from siada.agent_hub.coder.prompt.base.memory_section import get_memory_section
                structured_mem = get_memory_section()
                if structured_mem:
                    memory_parts.append(structured_mem)
            except Exception as e:
                logging.debug(f"Failed to load structured memory: {e}")

            # Combine all memory sources into a single field
            context.combined_memory = "\n\n".join(memory_parts) if memory_parts else None

            # Initialize SiadaIgnore controller
            try:
                from siada.foundation.siadaignore_controller import SiadaIgnoreController
                controller = SiadaIgnoreController(workspace_path)
                controller.initialize()
                context.siadaignore_controller = controller
            except Exception as e:
                logging.warning(f"Failed to init SiadaIgnoreController: {e}")

        # Load agent configuration (pre_plan / preferred_language) fresh from conf.yaml
        try:
            from siada.config.config_loader import load_conf
            from siada.config.language_config import get_agent_default_language
            _conf = load_conf()
            context.pre_plan = bool(_conf.pre_plan) if _conf.pre_plan else False
            agent_name = running_session.siada_config.agent_name if running_session else None
            context.preferred_language = _conf.preferred_language or get_agent_default_language(agent_name)
        except Exception as e:
            logging.warning(f"Failed to load conf.yaml for pre_plan/preferred_language: {e}")
            context.pre_plan = False
            if running_session:
                from siada.config.language_config import get_agent_default_language
                context.preferred_language = get_agent_default_language(running_session.siada_config.agent_name)

        return context

    @staticmethod
    def _build_run_config(context, running_session: RunningSession) -> RunConfig:
        """
        Build the RunConfig for the agent execution.

        Resolves the LLM provider, wraps it, writes provider info into the
        context and context vars, then constructs and returns a RunConfig.
        """
        llm_config = running_session.siada_config.llm_config
        model_settings = ModelSettingsConverter.convert_model_settings(llm_config)
        model_provider_name = llm_config.provider
        model_provider = get_provider(model_provider_name)

        provider_wrapper = ModelProviderWrapper(
            base_provider=model_provider,
            input_processor=process_input
        )

        # Store provider name (string) in context for client factory
        context.provider = model_provider_name
        set_context_var(LLM_CONFIG, llm_config)

        return RunConfig(
            tracing_disabled=running_session.siada_config.tracing_disabled,
            model=llm_config.model_name,
            model_provider=provider_wrapper,
            model_settings=model_settings,
            call_model_input_filter=context_capture_filter
        )

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
        
        # Detect im_mode from session metadata on disk (single source of truth)
        from siada.session.ownership import SessionOwnershipManager
        im_mode = SessionOwnershipManager.is_im_session(session) if session else False
        start_time = time.time()
        agent = await SiadaRunner.get_agent(agent_name, im_mode=im_mode)
        elapsed = time.time() - start_time
        logging.info(f"[Runner] Agent loaded (took {elapsed:.2f}s)")
        
        # Set agent_name in contextvars BEFORE Runner.run so child tasks inherit it
        set_context_var(AGENT_NAME, agent_name)

        # Build context (now returns context, run_config, and openai_session)
        start_time = time.time()
        context, run_config, openai_session = await SiadaRunner.build_context(agent, workspace, session)
        elapsed = time.time() - start_time
        logging.info(f"[Runner] Context and run config built (took {elapsed:.2f}s)")

        # set_trace_processors([create_detailed_logger(output_file="agent_trace.log")])
        console_output = session.siada_config.console_output if session else True
        set_trace_processors([create_detailed_logger(console_output=console_output)])
        logging.info("[Runner] Trace processors configured")

        # Start spinner before running agent (if injected via session)
        if session and session.spinner:
            session.spinner.start()

        # Execute agent with run_config and openai_session
        start_time = time.time()
        if stream:
            # Stream execution
            logging.info("[Runner] Starting streamed agent execution")
            result = await agent.run_streamed(user_input, context, run_config=run_config, openai_session=openai_session)
        else:
            # Normal execution
            logging.info("[Runner] Starting normal agent execution")
            result = await agent.run(user_input, context, run_config=run_config, openai_session=openai_session)
        elapsed = time.time() - start_time
        logging.info(f"[Runner] Agent execution completed (took {elapsed:.2f}s)")

        return result


    @staticmethod
    async def get_agent(agent_name: str, im_mode: bool = False) -> SiadaAgent:
        """
        Get the corresponding Agent instance based on agent name
        
        Args:
            agent_name: Agent name, supports case-insensitive matching
                       e.g.: 'bugfix', 'BugFix', 'bug_fix', etc.
            im_mode: Whether to enable IM mode for the agent.

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
            agent = agent_class(im_mode=im_mode)
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
        Configure MCP servers for the agent using lazy initialization strategy.
        
        MCP connections are established here (on first use) rather than during
        startup, ensuring they live in the same event loop that will use them.
        This avoids the asyncio event loop lifecycle issue where connections
        created in an ephemeral asyncio.run() would be destroyed when that
        loop closes.
        
        Args:
            agent: The agent instance to configure
        """
        try:
            from siada.services.mcp.manager_service import _mcp_manager_service

            # Check if MCP configuration is available
            if not _mcp_manager_service.has_config():
                logging.debug("No MCP configuration available, skipping MCP server configuration")
                return

            # Check and refresh lark-mcp token if needed (only requires config, not connections).
            logging.debug("Checking lark-mcp token status...")
            await _mcp_manager_service.check_and_refresh_lark_token()

            # Lazy initialization: establish connections in the current event loop.
            # This ensures MCP stdio connections live in the same loop that uses them.
            if not _mcp_manager_service.is_initialized:
                logging.info("Initializing MCP connections (lazy init in agent's event loop)...")
                await _mcp_manager_service.initialize()
                logging.info("MCP service connected successfully")

            # Get MCP servers from the initialized service
            mcp_servers = _mcp_manager_service.get_mcp_servers_for_agent()
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

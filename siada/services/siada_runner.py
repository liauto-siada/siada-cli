import asyncio
import time

from siada.foundation.context import set_context_var, set_session_id, MODEL_PROVIDER_NAME, LLM_CONFIG, AGENT_NAME

from siada.foundation.code_agent_context import RuntimeSource
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

from siada.services.memory.combined_memory import build_combined_memory


class SiadaRunner:

    _context_cache: dict[tuple, object] = {}
    _agent_cache: dict[str, object] = {}
    _agent_cache_refreshing: set[str] = set()

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
                logging.debug(f"Checkpoint initialized for session {session.session_id} (took {elapsed_time:.2f}s)")
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
                logging.debug(f"Checkpoint snapshot created for session {session.session_id} (took {elapsed_time:.2f}s)")
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
        session: Optional[RunningSession] = None,
        runtime_source: str = RuntimeSource.CLI,
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

        await SiadaRunner._prepare_context_for_run(context, running_session, runtime_source)

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
    async def _prepare_context_for_run(
        context,
        running_session: RunningSession,
        runtime_source: str = RuntimeSource.CLI,
    ):
        """
        Prepare per-run context state before each agent execution.

        This runs unconditionally on every invocation, regardless of whether
        context was loaded from cache or built fresh.

        Args:
            context: The agent execution context.
            running_session: The current running session.
        """
        context.session = running_session
        context.runtime_source = runtime_source
        await SiadaRunner._prepare_checkpoint_with_timeout(running_session)

        # Consume pending_todos staged by ResumeService after session restore
        if running_session.state.pending_todos and not context.todos:
            context.todos = running_session.state.pending_todos
            running_session.state.pending_todos = None
            logging.debug(f"[todo] Applied {len(context.todos)} recovered todos to context")

        # Consume pending_goal staged by ResumeService after session restore
        if running_session.state.pending_goal is not None and context.goal is None:
            context.goal = running_session.state.pending_goal
            running_session.state.pending_goal = None
            logging.debug("[goal] Applied recovered goal to context")

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

        # Resolve workspace and initialize the per-workspace controller.
        # Memory-layer assembly (rule_memory + siada.md + MEMORY/USER + guidance)
        # happens at the bottom via ``build_combined_memory`` so this method
        # stays focused on lifecycle wiring.
        workspace_path = workspace or (running_session.siada_config.workspace if running_session else None)

        if workspace_path:
            try:
                from siada.foundation.siadaignore_controller import SiadaIgnoreController
                controller = SiadaIgnoreController(workspace_path)
                controller.initialize()
                context.siadaignore_controller = controller
            except Exception as e:
                logging.warning(f"Failed to init SiadaIgnoreController: {e}")

        # Load agent configuration (pre_plan / preferred_language / max_turns) fresh from conf.yaml
        try:
            from siada.config.config_loader import load_conf
            from siada.config.language_config import get_agent_default_language
            _conf = load_conf()
            context.pre_plan = bool(_conf.pre_plan) if _conf.pre_plan else False
            agent_name = running_session.siada_config.agent_name if running_session else None
            context.preferred_language = _conf.preferred_language or get_agent_default_language(agent_name)
            context.max_turns = _conf.code_agent_config.max_turns
            # Web tools tri-state switch (None=auto, True=on, False=off). The
            # provider-based default is resolved at tool-config time using
            # context.provider, which is set per-run in _build_run_config.
            context.web_tools_enabled = _conf.web_config.enabled

            # Initialize MemoryStore and inject inline memory blocks.
            # memory_config.enabled acts as the master switch: when False, all
            # memory tools and memory-related system prompt sections are suppressed.
            mc = _conf.memory_config
            if not mc.enabled:
                # Master switch is OFF — disable all memory features.
                context.memory_tools_enabled = False
                context.memory_store = None
                context.holographic_provider = None
                logging.info("[memory] master switch OFF — memory tools and system prompt disabled")
            else:
                # Master switch is ON — initialize sub-layers per their own flags.
                context.memory_tools_enabled = True

                # Inline memory (MEMORY.md / USER.md)
                if mc.memory_facts_enabled or mc.user_profile_enabled:
                    try:
                        from siada.services.memory.memory_store import MemoryStore
                        store = MemoryStore(
                            memory_char_limit=mc.memory_char_limit,
                            user_char_limit=mc.user_char_limit,
                            memory_facts_enabled=mc.memory_facts_enabled,
                            user_profile_enabled=mc.user_profile_enabled,
                        )
                        store.load_from_disk()
                        context.memory_store = store
                        # NOTE: snapshot blocks (MEMORY.md / USER.md / inline guidance)
                        # are pulled from this store by ``build_combined_memory`` below.
                    except Exception as e:
                        logging.warning(f"Failed to initialize MemoryStore: {e}")
                        context.memory_store = None
                else:
                    context.memory_store = None

                # Holographic structured fact memory (third tier).
                # Only initialized when the master switch is ON; the holographic
                # sub-flag ``hc.enabled`` further gates the feature.
                hc = _conf.holographic_config
                if hc.enabled:
                    try:
                        from siada.services.memory.holographic.provider import (
                            HolographicProvider,
                        )
                        provider = HolographicProvider.from_config(hc)
                        provider.initialize()
                        context.holographic_provider = provider
                    except Exception as e:
                        logging.warning(
                            f"Failed to initialize HolographicProvider: {e}"
                        )
                        context.holographic_provider = None
                else:
                    context.holographic_provider = None
        except Exception as e:
            logging.warning(f"Failed to load conf.yaml for pre_plan/preferred_language: {e}")
            context.pre_plan = False
            context.memory_store = None
            context.holographic_provider = None
            if running_session:
                from siada.config.language_config import get_agent_default_language
                context.preferred_language = get_agent_default_language(running_session.siada_config.agent_name)

        # Build the combined_memory snapshot (rule_memory + siada.md + MEMORY/USER
        # blocks + memory/holographic guidance). Called once here at session
        # start; rebuilt on context-compaction events from
        # ``api_message_transfer_filter``. NEVER called from per-turn paths.
        context.combined_memory = build_combined_memory(
            workspace_path,
            context.memory_store,
            context.holographic_provider,
        )

        # Resolve git info for the workspace once at session start so telemetry
        # can report real repo_id / branch / commit without repeating the lookup
        # on every conversation turn.
        try:
            from siada.support.git_info import get_workspace_git_info
            logging.debug(f"Resolving git info for workspace: {workspace_path}")
            context.git_context = get_workspace_git_info(workspace_path)
            logging.debug(
                f"Git info resolved: repo_url={context.git_context.repo_url!r}, "
                f"branch={context.git_context.branch!r}, "
                f"commit={context.git_context.commit!r}"
            )
        except Exception as e:
            logging.debug(f"Failed to resolve git info for telemetry: {e}")

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
        # Auto-route model family (e.g. gpt-5.x) to required provider, so users
        # don't need to care about the provider concept.
        from siada.provider.provider_factory import resolve_provider_by_model
        model_provider_name = resolve_provider_by_model(
            llm_config.model_name, llm_config.provider
        )
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
        runtime_source: str = RuntimeSource.CLI,
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
        runtime_source: str = RuntimeSource.CLI,
    ) -> RunResult: ...

    @staticmethod
    async def run_agent(
        agent_name: str,
        user_input: str | list[TResponseInputItem],
        workspace: str = None,
        session: RunningSession = None,
        stream: bool = False,
        runtime_source: str = RuntimeSource.CLI,
        run_config: Optional["RunConfig"] = None,
    ) -> RunResult | RunResultStreaming:
        """
        Run the specified Agent.

        Args:
            agent_name: Name of the Agent.
            user_input: User input.
            workspace: Workspace path, optional.
            session: The running session object, optional.
            stream: Whether to enable streaming output, defaults to False.
            run_config: Optional pre-built RunConfig. When provided, bypasses
                _build_run_config so callers (e.g. cron tasks) can pin model/provider
                while still going through the full SiadaRunner telemetry path.

        Returns:
            Union[RunResult, RunResultStreaming]: Returns a regular or streaming result based on the stream parameter.
        """
        session_id = session.session_id if session else "N/A"

        # Re-bind the coroutine-local session_id to the session actually being
        # run. The context var is otherwise only set once at session creation
        # (RunningSessionManager.create_session), which goes stale for reused
        # sessions in long-lived multi-session hosts (e.g. Lark) and after
        # /resume (where the RunningSession object is reused but its session_id
        # is mutated in place). Without this, per-request tracing headers such
        # as X-Siada-Task-ID could carry a different session's id, mismatching
        # the conversation telemetry that reads session.session_id directly.
        # set_session_id is contextvar-based and Task-isolated, so concurrent
        # runs never interfere with each other.
        if session is not None:
            set_session_id(session.session_id)

        from siada.foundation.context import get_context_var
        t_start = get_context_var('turn_start_time')
        t_extra = f" (waited {time.time() - t_start:.3f}s from turn_start)" if t_start else ""
        logging.info(f"[Runner] Starting agent execution - agent: {agent_name}, session: {session_id}, stream: {stream}{t_extra}")

        start_time = time.time()
        agent = await SiadaRunner.get_agent(agent_name)
        elapsed = time.time() - start_time
        logging.debug(f"[Runner] Agent loaded (took {elapsed:.3f}s)")
        

        # Build context (now returns context, run_config, and openai_session)
        start_time = time.time()
        context, built_run_config, openai_session = await SiadaRunner.build_context(
            agent,
            workspace,
            session,
            runtime_source=runtime_source,
        )
        # Allow caller to override run_config (e.g. cron tasks that pin a specific model)
        run_config = run_config or built_run_config
        elapsed = time.time() - start_time
        logging.debug(f"[Runner] Context and run config built (took {elapsed:.3f}s)")

        # set_trace_processors([create_detailed_logger(output_file="agent_trace.log")])
        console_output = session.siada_config.console_output if session else True
        set_trace_processors([create_detailed_logger(console_output=console_output)])
        logging.info("[Runner] Trace processors configured")

        # Start spinner before running agent (if injected via session)
        if session and session.spinner:
            session.spinner.start()

        # Ensure the agents-SDK monkey-patches (e.g. soft-handling of
        # hallucinated tool names) are applied before any turn runs. This is
        # idempotent — the normal path patches inside the agents-init warmup
        # thread; this call is a safety net for entry points that bypass
        # siadahub.py (tests, external scripts).
        try:
            from siada.foundation.sdk_patches import apply_sdk_patches
            apply_sdk_patches()
        except Exception:
            pass

        user_input = SiadaRunner._maybe_merge_goal_reminder(context, user_input)


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
        logging.debug(f"[Runner] Agent execution completed (took {elapsed:.2f}s)")

        return result


    @staticmethod
    def _maybe_merge_goal_reminder(context, user_input):
        """Merge the hidden /goal reminder into ``user_input``, but only
        ONCE per goal activation — not on every turn.

        Replaces the old per-LLM-call ``GoalReminderFilter``. Doing it here,
        before the run starts, means the reminder becomes part of the real
        ``input`` the SDK's ``Runner`` receives, so the SDK's own session
        persistence writes it to ``api_history.json`` like any other turn
        input — see ``merge_goal_reminder_into_input``'s docstring for the
        full rationale on *why* this moved out of the filter chain.

        That persistence is exactly why this must be gated to "once per
        activation" via ``goal.reminder_injected``: unlike the old ephemeral
        per-call injection (thrown away after each LLM call, so repeating it
        every turn was free), a merged-in reminder now lives in
        ``api_history.json`` forever. Re-merging it on every subsequent
        turn while the goal stays active would keep appending the same
        multi-paragraph block into persisted history turn after turn.
        ``goal.reminder_injected`` is reset to False whenever the goal
        (re)activates — a brand new goal via ``Goal.create()``, or a
        "blocked" goal reactivated by
        ``turn_hooks.maybe_reset_goal_on_new_turn`` — so it still gets
        freshly reminded at each meaningful activation point, just not on
        every single turn in between.
        """
        goal = getattr(context, "goal", None)
        if goal is None or getattr(goal, "status", None) != "active":
            return user_input
        if getattr(goal, "reminder_injected", False):
            return user_input

        from siada.services.goal.prompts import merge_goal_reminder_into_input
        user_input = merge_goal_reminder_into_input(user_input, goal)

        goal.reminder_injected = True
        goal.touch()

        # Persist the flag immediately so it isn't lost if the process
        # restarts mid-turn (the reminder text itself is already safely on
        # its way into api_history.json via the SDK's own persistence).
        running_session = getattr(context, "session", None)
        session_folder = None
        if running_session is not None:
            openai_session = running_session.state.openai_session
            if openai_session is not None:
                session_folder = openai_session.session_folder
        if session_folder is not None:
            try:
                from siada.services.goal import goal_storage
                goal_storage.save_goal(session_folder, goal)
            except Exception as e:
                logging.warning(f"[goal] Failed to persist reminder_injected flag: {e}")

        return user_input

    @staticmethod
    async def _refresh_agent_background(agent_name: str) -> None:

        """Rebuild agent in background and update cache (stale-while-revalidate)."""
        SiadaRunner._agent_cache_refreshing.add(agent_name)
        try:
            class_path = get_agent_class_path(agent_name)
            agent_class = import_agent_class(class_path)
            agent = agent_class()
            await SiadaRunner._configure_mcp_servers(agent)
            SiadaRunner._agent_cache[agent_name] = agent
            logging.info(f"[get_agent] Background refresh complete: {agent_name}")
        except Exception as e:
            logging.warning(f"[get_agent] Background refresh failed for {agent_name}: {e}")
        finally:
            SiadaRunner._agent_cache_refreshing.discard(agent_name)

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
        # Return cached agent immediately; trigger a background refresh so the next
        # turn gets an updated instance (stale-while-revalidate).
        if agent_name in SiadaRunner._agent_cache:
            logging.info(f"[get_agent] Returning cached agent: {agent_name}")
            if agent_name not in SiadaRunner._agent_cache_refreshing:
                asyncio.create_task(SiadaRunner._refresh_agent_background(agent_name))
            return SiadaRunner._agent_cache[agent_name]

        logging.info(f"[get_agent] Starting to load agent: {agent_name}")

        # Get agent class path from configuration
        class_path = get_agent_class_path(agent_name)

        # Dynamically import and instantiate Agent class
        try:
            # Import agent class
            start_time = time.time()
            agent_class = import_agent_class(class_path)
            elapsed = time.time() - start_time
            logging.debug(f"[get_agent] Agent class imported (took {elapsed:.3f}s)")
            
            # Instantiate agent
            start_time = time.time()
            agent = agent_class()
            elapsed = time.time() - start_time
            logging.debug(f"[get_agent] Agent instantiated (took {elapsed:.3f}s)")

            # Configure MCP servers for the agent
            start_time = time.time()
            await SiadaRunner._configure_mcp_servers(agent)
            elapsed = time.time() - start_time
            logging.debug(f"[get_agent] MCP servers configured (took {elapsed:.3f}s)")

            logging.info(f"[get_agent] Agent {agent_name} loaded successfully")
            SiadaRunner._agent_cache[agent_name] = agent
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
            from siada.services.mcp.manager_service import _mcp_manager_service, MCPServerFactory

            # ── Global MCP servers (from conf.yaml / mcp_config.json) ──────────
            mcp_servers: list = []
            global_mcp_task = None
            if _mcp_manager_service.has_config():
                # Check and refresh lark-mcp token if needed (only requires config, not connections).
                logging.debug("Checking lark-mcp token status...")
                await _mcp_manager_service.check_and_refresh_lark_token()

                # Lazy initialization: establish connections in the current event loop.
                # This ensures MCP stdio connections live in the same loop that uses them.
                if not _mcp_manager_service.is_initialized:
                    logging.info("Initializing MCP connections (lazy init in agent's event loop)...")
                    # Background task for parallel non-blocking global MCP initialization
                    import asyncio
                    global_mcp_task = asyncio.create_task(_mcp_manager_service.initialize())
                else:
                    mcp_servers = _mcp_manager_service.get_mcp_servers_for_agent() or []
                    for server in mcp_servers:
                        logging.debug(f"   global MCP: {server.name}")
            else:
                logging.debug("No global MCP configuration available")

            # ── Plugin MCP servers (from plugin.json mcpServers / .mcp.json) ───
            plugin_mcp_servers: list = []
            try:
                import asyncio
                import time
                t_plugin_start = time.time()
                from siada.services.plugins.plugin_loader import (
                    PluginLoader,
                    extract_plugin_mcp_configs,
                )

                plugins = PluginLoader().load_all()
                plugin_configs = extract_plugin_mcp_configs(
                    [p for p in plugins if p.enabled]
                )
                logging.debug(f"Plugin loader loaded {len(plugins)} plugins ({len(plugin_configs)} configs) in {time.time() - t_plugin_start:.3f}s")
                
                async def connect_with_timeout(scoped_name, srv_config):
                    t_connect_start = time.time()
                    try:
                        server = MCPServerFactory.create_server(scoped_name, srv_config)
                        if server:
                            logging.info(f"Connecting to plugin MCP server: {scoped_name} ({srv_config.url if hasattr(srv_config, 'url') else 'stdio'})")
                            # Parallel non-blocking connection with 3s timeout
                            await asyncio.wait_for(server.connect(), timeout=3.0)
                            logging.debug(f"Plugin MCP server connected: {scoped_name} (took {time.time() - t_connect_start:.3f}s)")
                            return server
                    except asyncio.TimeoutError:
                        logging.warning(
                            f"Plugin MCP server '{scoped_name}' connection timed out after 3.0s"
                        )
                    except Exception as srv_err:
                        logging.warning(
                            f"Plugin MCP server '{scoped_name}' failed to connect: {srv_err}"
                        )
                    return None

                # Launch all plugin MCP server connections concurrently
                tasks = [
                    connect_with_timeout(scoped_name, srv_config)
                    for scoped_name, srv_config in plugin_configs
                ]
                
                if global_mcp_task:
                    # Gather BOTH global and plugin connections concurrently.
                    # Cap global MCP init at 8s so a slow server (e.g. li-mate 30s timeout)
                    # doesn't block the first turn indefinitely.
                    _GLOBAL_MCP_TIMEOUT = 8.0
                    bounded_global = asyncio.ensure_future(
                        asyncio.wait_for(asyncio.shield(global_mcp_task), timeout=_GLOBAL_MCP_TIMEOUT)
                    )
                    results = await asyncio.gather(bounded_global, *tasks, return_exceptions=True)
                    global_res = results[0]
                    if isinstance(global_res, Exception):
                        logging.warning(
                            f"Global MCP init did not complete within {_GLOBAL_MCP_TIMEOUT}s, "
                            f"proceeding without global servers (init continues in background)"
                        )
                    elif isinstance(global_res, list):
                        mcp_servers = _mcp_manager_service.get_mcp_servers_for_agent() or []
                    plugin_res = results[1:]
                else:
                    plugin_res = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

                for srv in plugin_res:
                    if srv:
                        plugin_mcp_servers.append(srv)
            except Exception as plugin_err:
                logging.warning(f"Failed to load plugin MCP servers: {plugin_err}")

            # ── Attach merged server list to agent ───────────────────────────
            all_servers = mcp_servers + plugin_mcp_servers
            if all_servers:
                agent.mcp_servers = all_servers
                agent.mcp_config = {"convert_schemas_to_strict": True}
                logging.info(
                    f"MCP configured: {len(mcp_servers)} global + "
                    f"{len(plugin_mcp_servers)} plugin server(s)"
                )

        except Exception as e:
            logging.error(f"Failed to configure MCP servers for agent: {e}")

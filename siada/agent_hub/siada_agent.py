from abc import ABC, abstractmethod
from typing import Generic
import yaml
import os

from agents import Agent, RunConfig, RunHooks, RunResult, RunResultStreaming, Runner, TContext, TResponseInputItem, set_trace_processors
from siada.agent_hub.hooks.siada_run_hooks import SiadaRunHooks
from siada.tools.coder.repo_map.repo_map import RepoMap
from siada.tools.coder.repo_map.token_counter import TokenCounterModel
from siada.tools.coder.repo_map.io import SilentIO

from siada.foundation.logging import logger as logging
from siada.agent_hub.hooks.siada_agent_hooks import SiadaAgentHooks

class SiadaAgent(Agent[Generic[TContext]], ABC):

    def __init__(self, *args, **kwargs):
        # Remove im_mode if not consumed by subclass, to avoid passing unknown kwarg to Agent
        kwargs.pop('im_mode', None)

        if 'hooks' not in kwargs:
            kwargs['hooks'] = SiadaAgentHooks()

        super().__init__(
            *args,
            **kwargs
        )

    @abstractmethod
    async def get_context(self) -> TContext:
        """
        Get the context object for this agent.
        
        Returns:
            TContext: The context object containing relevant information for the agent's execution.
        """
        pass

    @abstractmethod
    async def run(self, user_input: str, context: TContext, run_config: RunConfig = None, openai_session = None) -> RunResult:
        """
        Execute the agent with the given user input and context.
        
        Args:
            user_input (str): The input provided by the user.
            context (TContext): The context object containing relevant information for execution.
            run_config (RunConfig): Optional run configuration. If not provided, will be built from context.
            openai_session: Optional OpenAI session. If not provided, will be built from context.
            
        Returns:
            RunResult: The result of the agent's execution.
        """
        pass

    @abstractmethod
    async def run_streamed(self, user_input: str, context: TContext, run_config: RunConfig = None, openai_session = None) -> RunResultStreaming:
        """
        Execute Streamed the agent with the given user input and context
                
        Args:
            user_input (str): The input provided by the user.
            context (TContext): The context object containing relevant information for execution.
            run_config (RunConfig): Optional run configuration. If not provided, will be built from context.
            openai_session: Optional OpenAI session. If not provided, will be built from context.
            
        Returns:
            RunResultStreaming: The stream result of the agent's execution.
        """
        pass

    def get_interactive_mode(self) -> bool:
        """
        Get the current interactive mode status
        
        Returns:
            bool: True for interactive mode, False for non-interactive mode
        """
        # Check if there's a --prompt argument, if so it's non-interactive mode
        import sys
        return '--prompt' not in sys.argv and '-p' not in sys.argv

    def get_repo_map_model_name(self) -> str:
        """
        Get the model name used for repo map generation
        
        Returns:
            str: Model name, defaults to claude-sonnet-4
        """
        try:
            # Read configuration file
            config_path = os.path.join(os.getcwd(), "agent_config.yaml")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    llm_config = config.get('llm_config', {})
                    return llm_config.get('model_name', 'claude-sonnet-4')
        except Exception as e:
            logging.warning(f"Failed to read agent config file for repo map model name: {str(e)}")

        # If reading configuration fails, use default value
        return 'claude-sonnet-4'

    def get_repo_map_instance(self, root_dir: str):
        """
        Get RepoMap instance
        
        Args:
            root_dir (str): Repository root directory
            
        Returns:
            RepoMap: Configured RepoMap instance
        """
        try:

            # Read configuration
            config_path = os.path.join(os.getcwd(), "agent_config.yaml")
            llm_config = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                        llm_config = config.get('llm_config', {})
                except Exception as e:
                    logging.warning(f"Failed to read agent config file for repo map instance: {str(e)}")

            # Get configuration parameters
            model_name = llm_config.get('model_name', 'claude-sonnet-4')
            repo_map_tokens = llm_config.get('repo_map_tokens', 8192)
            repo_map_mul_no_files = llm_config.get('repo_map_mul_no_files', 16)
            repo_verbose = llm_config.get('repo_verbose', True)

            # Create components
            token_counter = TokenCounterModel(model_name)
            io = SilentIO()  # Use silent IO to avoid output interference

            return RepoMap(
                root=root_dir,
                main_model=token_counter,
                io=io,
                verbose=repo_verbose,
                map_tokens=repo_map_tokens,
                map_mul_no_files=repo_map_mul_no_files
            )
        except Exception as e:
            logging.warning(f"Failed to create RepoMap instance for root directory '{root_dir}': {str(e)}")
            # If creation fails, return None
            return None

    async def run_impl(
        self,
        starting_agent: Agent[TContext],
        input: str | list[TResponseInputItem],
        context: TContext | None = None,
        max_turns: int = 10,
        hooks: RunHooks[TContext] | None = None,
        run_config: RunConfig | None = None,
        openai_session = None,
        previous_response_id: str | None = None,
    ) -> RunResult:
        """
        Internal implementation for running the agent.
        
        Args:
            starting_agent: The agent to start with
            input: User input
            context: Execution context
            max_turns: Maximum number of turns
            hooks: Run hooks for callbacks
            run_config: Run configuration (should be provided by SiadaRunner)
            openai_session: OpenAI session (should be provided by SiadaRunner)
            previous_response_id: Previous response ID for continuation
            
        Returns:
            RunResult: The result of execution
        """
        # Use SiadaAgentHooks with default processors if no hooks provided
        if hooks is None:
            hooks = SiadaRunHooks()

        return await Runner.run(
            starting_agent=starting_agent,
            input=input,
            context=context,
            max_turns=max_turns,
            hooks=hooks,
            run_config=run_config,
            previous_response_id=previous_response_id,
            session=openai_session,
        )

    async def run_streamed_impl(
        self,
        starting_agent: Agent[TContext],
        input: str | list[TResponseInputItem],
        context: TContext | None = None,
        max_turns: int = 10,
        hooks: RunHooks[TContext] | None = None,
        run_config: RunConfig | None = None,
        openai_session = None,
        previous_response_id: str | None = None,
    ) -> RunResultStreaming:
        """
        Internal implementation for running the agent in streaming mode.
        
        Args:
            starting_agent: The agent to start with
            input: User input
            context: Execution context
            max_turns: Maximum number of turns
            hooks: Run hooks for callbacks
            run_config: Run configuration (should be provided by SiadaRunner)
            openai_session: OpenAI session (should be provided by SiadaRunner)
            previous_response_id: Previous response ID for continuation
            
        Returns:
            RunResultStreaming: The streaming result of execution
        """
        # Use SiadaAgentHooks with default processors if no hooks provided
        if hooks is None:
            hooks = SiadaRunHooks()

        return Runner.run_streamed(
            starting_agent=starting_agent,
            input=input,
            context=context,
            max_turns=max_turns,
            hooks=hooks,
            run_config=run_config,
            previous_response_id=previous_response_id,
            session=openai_session,
        )

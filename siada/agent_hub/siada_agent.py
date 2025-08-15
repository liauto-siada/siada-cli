from abc import ABC, abstractmethod
from typing import Generic
import yaml
import os

from agents import Agent, RunConfig, RunHooks, RunResult, RunResultStreaming, Runner, TContext, TResponseInputItem, set_trace_processors
from siada.agent_hub.coder.tracing.logger_tracing_processor import create_detailed_logger
from siada.foundation.code_agent_context import CodeAgentContext
from siada.models.converter import ModelSettingsConverter
from siada.provider.provider_factory import get_provider
from siada.session import RunningSessionManager
from siada.tools.coder.ask_followup_question import ask_followup_question
from siada.tools.coder.repo_map.repo_map import RepoMap
from siada.tools.coder.repo_map.token_counter import TokenCounterModel
from siada.tools.coder.repo_map.io import SilentIO

import logging

class SiadaAgent(Agent[Generic[TContext]], ABC):

    @abstractmethod
    async def get_context(self) -> TContext:
        """
        Get the context object for this agent.
        
        Returns:
            TContext: The context object containing relevant information for the agent's execution.
        """
        pass

    @abstractmethod
    async def run(self, user_input: str, context: TContext) -> RunResult:
        """
        Execute the agent with the given user input and context.
        
        Args:
            user_input (str): The input provided by the user.
            context (TContext): The context object containing relevant information for execution.
            
        Returns:
            RunResult: The result of the agent's execution.
        """
        pass

    @abstractmethod
    async def run_streamed(self, user_input: str, context: TContext) -> RunResultStreaming:
        """
        Execute Streamed the agent with the given user input and context
                
        Args:
            user_input (str): The input provided by the user.
            context (TContext): The context object containing relevant information for execution.
            
        Returns:
            RunResultStreaming: The stream result of the agent's execution.
        """
        pass

    def get_interactive_mode(self) -> bool:
        """
        获取当前的交互模式状态
        
        Returns:
            bool: True为交互模式，False为非交互模式
        """
        # 检查是否有--prompt参数，如果有则为非交互模式
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

    async def prepare_run_environment(
        self,
        context: TContext | None = None,
    ):
        running_session = context.session
        if running_session is None:
            running_session = RunningSessionManager.get_default_session()
            context.session = running_session

        llm_config = running_session.siada_config.llm_config
        model_settings = ModelSettingsConverter.convert_model_settings(llm_config)
        model_provider_name = llm_config.provider
        model_provider = get_provider(model_provider_name)
        
        # Store provider name (string) in context for client factory
        context.provider = model_provider_name

        # if running_session.running_config.interactive:
        #     ## in the interactive mode, we need to add the ask_followup_question tool
        #     if ask_followup_question not in self.tools:
        #         self.tools.append(ask_followup_question)

        run_config = RunConfig(
            tracing_disabled=running_session.siada_config.tracing_disabled,
            model=llm_config.model_name,
            model_provider=model_provider,
            model_settings=model_settings
        )

        session = running_session.state.openai_session
        return run_config, session

    async def run_impl(
        self,
        starting_agent: Agent[TContext],
        input: str | list[TResponseInputItem],
        context: TContext | None = None,
        max_turns: int = 10,
        hooks: RunHooks[TContext] | None = None,
        previous_response_id: str | None = None,
    ) -> RunResult:

        run_config, session = await self.prepare_run_environment(context)

        return await Runner.run(
            starting_agent=starting_agent,
            input=input,
            context=context,
            max_turns=max_turns,
            hooks=hooks,
            run_config=run_config,
            previous_response_id=previous_response_id,
            session=session,
        )

    async def run_streamed_impl(
        self,
        starting_agent: Agent[TContext],
        input: str | list[TResponseInputItem],
        context: TContext | None = None,
        max_turns: int = 10,
        hooks: RunHooks[TContext] | None = None,
        run_config: RunConfig | None = None,
        previous_response_id: str | None = None,
    ) -> RunResultStreaming:

        run_config, session = await self.prepare_run_environment(context)

        return Runner.run_streamed(
            starting_agent=starting_agent,
            input=input,
            context=context,
            max_turns=max_turns,
            hooks=hooks,
            run_config=run_config,
            previous_response_id=previous_response_id,
            session=session,
        )

import asyncio
import importlib
import os
from pathlib import Path
from siada.session.session_models import RunningSession
from typing import Dict, Type, Optional, Union, Literal, overload

import yaml
from agents import RunResult, RunResultStreaming, Agent, set_trace_processors

from siada.agent_hub.coder.tracing import create_detailed_logger
from siada.agent_hub.siada_agent import SiadaAgent

import logging

from siada.services.code_context_manager import ContextTracingProcessor

class SiadaRunner:

    @overload
    @staticmethod
    async def run_agent(
        agent_name: str,
        user_input: str,
        workspace: str = None,
        session: RunningSession = None,
        *,
        stream: Literal[True],
    ) -> RunResultStreaming: ...

    @overload
    @staticmethod
    async def run_agent(
        agent_name: str,
        user_input: str,
        workspace: str = None,
        session: RunningSession = None,
        *,
        stream: Literal[False],
    ) -> RunResult: ...

    @staticmethod
    async def run_agent(
        agent_name: str,
        user_input: str,
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
        context = await agent.get_context()
        console_output = False
        if workspace:
            context.root_dir = workspace
        if session:
            context.session = session

        # set_trace_processors([create_detailed_logger(output_file="agent_trace.log")])
        console_output = session.siada_config.console_output if session else True
        context_tracing_processor = ContextTracingProcessor(context)

        set_trace_processors([create_detailed_logger(console_output=console_output),
                              context_tracing_processor])

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
            return agent_class()
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

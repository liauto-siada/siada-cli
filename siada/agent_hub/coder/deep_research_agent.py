"""
Deep Research Agent Module

Provides specialized Agent implementation for web-based research and report generation tasks.
"""
import os
from typing import List

from agents import RunContextWrapper, RunResult, RunResultStreaming, TResponseInputItem
from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.siada_agent import SiadaAgent
from siada.tools.coder.file_operator import edit
from siada.tools.coder.run_cmd import run_cmd
from siada.foundation.setting import settings
from siada.tools.web import web_search
from siada.agent_hub.coder.prompt import deep_research_prompt
from siada.agent_hub.coder.prompt.base.tool_use import should_enable_parallel_tool_calls_in_prompt
from siada.services.handle_at_command import handle_at_command
import logging


logging.getLogger().setLevel(logging.INFO)


class DeepResearchAgent(SiadaAgent[CodeAgentContext]):
    """
    Deep Research Agent
    
    Specialized Agent implementation for web-based research and report generation tasks.
    This agent uses web search capabilities to gather information from the internet,
    analyze and synthesize content from multiple sources, and generate comprehensive
    research reports.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the Deep Research Agent
        
        Args:
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments
                - name: Agent name (default: "DeepResearchAgent")
                - tools: List of tools available to the agent (default: [edit, run_cmd, web_search])
        """
        if 'name' not in kwargs:
            kwargs['name'] = "DeepResearchAgent"

        if 'tools' not in kwargs:
            base_tools = [edit, run_cmd]
            if web_search is not None:
                base_tools.append(web_search)
            kwargs['tools'] = base_tools

        super().__init__(
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        """
        Generate the system prompt for the deep research agent
        
        Args:
            run_context: Runtime context wrapper containing agent context
            
        Returns:
            The formatted system prompt string
        """
        root_dir = run_context.context.root_dir
        
        # Get combined memory from context (prepared by SiadaRunner)
        combined_memory = run_context.context.combined_memory
        
        # Get preferred language and agent name from session config
        preferred_language = run_context.context.preferred_language
        agent_name = run_context.context.session.siada_config.agent_name
        
        # Get pre_plan setting from context
        pre_plan = run_context.context.pre_plan
        
        enable_parallel = should_enable_parallel_tool_calls_in_prompt(run_context)
        system_prompt = deep_research_prompt.get_system_prompt(
            root_dir,
            run_context.context.interactive_mode,
            combined_memory,
            preferred_language,
            agent_name,
            pre_plan,
            enable_parallel_tool_calls=enable_parallel
        )
        return system_prompt

    async def get_context(self) -> CodeAgentContext:
        """
        Create and return the agent context
        
        Returns:
            CodeAgentContext with current working directory and interactive mode
        """
        current_working_dir = os.getcwd()
        interactive_mode = self.get_interactive_mode()

        context = CodeAgentContext(
            root_dir=current_working_dir,
            interactive_mode=interactive_mode
        )
        return context

    async def process_at_commands(
        self,
        user_input: str | List[TResponseInputItem],
        context: CodeAgentContext
    ) -> str:
        """
        Process @ commands in user input and return processed input
        
        Args:
            user_input: Original user input that may contain @ commands
            context: Code agent context
            
        Returns:
            Processed user input with @ command content injected
        """
        try:
            # Check if input contains @ commands
            if '@' not in user_input:
                return user_input

            # Create configuration object for at command processing
            class AtCommandConfig:
                def __init__(self, root_dir: str, interactive: bool = False, io=None):
                    # Root directory used for resolving @ paths
                    self.root_dir = root_dir
                    # Whether we are in interactive mode (controls spinner behavior)
                    self.interactive = interactive
                    # Optional IO instance, if available (for rich panel-aware spinner)
                    self.io = io

            # Determine interactive flag and IO from context if available
            interactive = getattr(context, "interactive_mode", False)
            io_instance = None
            if getattr(context, "session", None) and getattr(context.session, "siada_config", None):
                io_instance = context.session.siada_config.io

            config = AtCommandConfig(context.root_dir, interactive=interactive, io=io_instance)

            # Create callback functions
            def add_item(item, message_id):
                # Log the item for debugging
                logging.debug(f"AtCommand item added: {item}")

            def on_debug_message(message):
                # Log debug messages
                logging.debug(f"AtCommand debug: {message}")

            # Process at commands
            result = await handle_at_command(
                query=user_input,
                config=config,
                add_item=add_item,
                on_debug_message=on_debug_message,
                message_id=1
            )

            if result.should_proceed and result.processed_query:
                # Combine all text parts from processed query
                processed_text = ""
                for part in result.processed_query:
                    if isinstance(part, dict) and 'text' in part:
                        processed_text += part['text']

                return processed_text.strip() if processed_text else user_input
            else:
                # If processing failed, return original input
                return user_input

        except Exception as e:
            # If any error occurs, log it and return original input
            logging.warning(f"Failed to process @ commands: {e}")
            return user_input

    async def run(
        self,
        user_input: str | List[TResponseInputItem],
        context: CodeAgentContext,
        run_config=None,
        openai_session=None
    ) -> RunResult:
        """
        Execute deep research task.

        Args:
            user_input: User's research request with topic and requirements
            context: Context object providing project information
            run_config: Run configuration (provided by SiadaRunner)
            openai_session: OpenAI session (provided by SiadaRunner)

        Returns:
            Research result containing final output and execution details
        """
        # Process @ commands first
        processed_input = await self.process_at_commands(user_input, context)

        input_with_env = self.assemble_user_input(processed_input, context)
        result = await self.run_impl(
            starting_agent=self,
            input=input_with_env,
            max_turns=settings.MAX_TURNS,
            context=context,
            run_config=run_config,
            openai_session=openai_session,
        )

        return result

    async def run_streamed(
        self,
        user_input: str | List[TResponseInputItem],
        context: CodeAgentContext,
        run_config=None,
        openai_session=None
    ) -> RunResultStreaming:
        """
        Execute deep research task with streaming output.

        Args:
            user_input: User's research request with topic and requirements
            context: Context object providing project information
            
        Returns:
            A streaming result of the research, containing final output and execution details.
        """
        # Process @ commands first
        processed_input = await self.process_at_commands(user_input, context)

        input_with_env = self.assemble_user_input(processed_input, context)
        result = await self.run_streamed_impl(
            starting_agent=self,
            input=input_with_env,
            context=context,
            max_turns=settings.MAX_TURNS,
        )

        return result

    def assemble_user_input(
        self,
        user_input: str | List[TResponseInputItem],
        context: CodeAgentContext
    ) -> any:
        """
        Assemble the user input with task wrapper
        
        Args:
            user_input: User's input (string or list of items)
            context: Code agent context
            
        Returns:
            Formatted input for the agent
        """
        if isinstance(user_input, list):
            return user_input
        
        task = f"<task>\n{user_input}\n</task>"
        return task

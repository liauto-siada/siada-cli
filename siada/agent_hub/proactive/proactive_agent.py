"""
Proactive Agent Module

Provides specialized Agent implementation for proactive task discovery and management.
"""
import os
import logging
from typing import Optional

from agents import RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.siada_agent import SiadaAgent
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.memory import smart_search_memory, get_memory
from siada.tools.memory.list_memory_files import list_memory_files
from siada.tools.memory.search_memory_by_date import search_memory_by_date
from siada.agent_hub.proactive.prompts.system_prompt import PROACTIVE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ProactiveAgent(SiadaAgent[CodeAgentContext]):
    """
    Proactive Agent
    
    Specialized Agent implementation for proactive task discovery and management.
    
    ProactiveAgent is a general-purpose proactive agent supporting multiple capabilities:
    - Task discovery from memory analysis
    - Daily work summaries
    - Work planning and prioritization
    - Proactive insights and suggestions
    
    The agent uses react pattern (tools + model inference) to complete tasks.
    Task instructions are sent as user messages by the scheduler.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize ProactiveAgent with memory and task management tools.
        
        Args:
            *args: Positional arguments passed to parent SiadaAgent
            **kwargs: Keyword arguments passed to parent SiadaAgent
        """
        if 'name' not in kwargs:
            kwargs['name'] = "ProactiveAgent"

        if 'tools' not in kwargs:
            # Proactive agent tools:
            # 1. Memory search tools for analyzing history
            # 2. General tools for file read/write and command execution
            tools = [
                # Memory search tools
                smart_search_memory,
                # General tools
                edit,
                regex_search_files,
                run_cmd
            ]
            
            kwargs['tools'] = tools
            logger.info("[ProactiveAgent] Initialized with %d tools", len(tools))

        super().__init__(*args, **kwargs)

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> Optional[str]:
        """
        Get system prompt for ProactiveAgent.
        
        Returns the general proactive agent system prompt that emphasizes:
        - Proactive analysis and insights
        - Memory system usage
        - Conservative assumptions
        - Structured output
        
        Does NOT list tools (framework provides automatically) or limit capabilities.
        
        Args:
            run_context: Run context wrapper containing agent context
            
        Returns:
            System prompt string
        """
        # ProactiveAgent uses a general system prompt for all proactive tasks
        # Specific task instructions (e.g., task discovery, daily summary) 
        # are sent as user messages by the scheduler
        return PROACTIVE_SYSTEM_PROMPT

    async def get_context(self) -> CodeAgentContext:
        """
        Get agent context for ProactiveAgent.
        
        ProactiveAgent reuses CodeAgentContext - no custom context needed.
        Configuration is accessed via context.session.siada_config.proactive_config.
        
        Returns:
            CodeAgentContext instance with current working directory
        """
        current_working_dir = os.getcwd()
        interactive_mode = self.get_interactive_mode()

        context = CodeAgentContext(
            root_dir=current_working_dir,
            interactive_mode=interactive_mode
        )
        return context

    async def run(self, user_input: str, context: CodeAgentContext, run_config=None, openai_session=None):
        """
        Execute proactive task.
        
        Args:
            user_input: Task instruction (e.g., discover tasks, create summary)
                       Sent by scheduler as user message
            context: Context object providing agent information
            run_config: Run configuration (provided by SiadaRunner)
            openai_session: OpenAI session (provided by SiadaRunner)
            
        Returns:
            Execution result containing agent output (typically JSON)
        """
        from siada.foundation.setting import settings
        
        # ProactiveAgent uses react pattern - user_input is the task instruction
        result = await self.run_impl(
            starting_agent=self,
            input=user_input,
            max_turns=settings.MAX_TURNS,
            context=context,
            run_config=run_config,
            openai_session=openai_session,
        )
        
        return result

    async def run_streamed(self, user_input: str, context: CodeAgentContext, run_config=None, openai_session=None):
        """
        Execute proactive task with streaming output.
        
        Args:
            user_input: Task instruction (e.g., discover tasks, create summary)
            context: Context object providing agent information
            run_config: Run configuration (provided by SiadaRunner)
            openai_session: OpenAI session (provided by SiadaRunner)
            
        Returns:
            Streaming result of the execution
        """
        from siada.foundation.setting import settings
        
        result = await self.run_streamed_impl(
            starting_agent=self,
            input=user_input,
            context=context,
            max_turns=settings.MAX_TURNS,
            run_config=run_config,
            openai_session=openai_session,
        )
        
        return result

"""
Code Generation Agent Module

Provides specialized Agent implementation for code generation tasks.
"""
import os

from agents import RunContextWrapper, RunResult, RunResultStreaming
from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.siada_agent import SiadaAgent
from siada.tools.ast.ast_tool import list_code_definition_names
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.foundation.config import settings
from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.services.handle_at_command import handle_at_command
import logging


logging.getLogger().setLevel(logging.INFO)

class CodeGenAgent(SiadaAgent[CodeAgentContext]):
    """
    Code Generation Agent
    
    Specialized Agent implementation for code generation tasks.
    """

    def __init__(self, *args, **kwargs):

        if 'name' not in kwargs:
            kwargs['name'] = "CodeGenAgent"

        if 'tools' not in kwargs:
            kwargs['tools'] = [edit, regex_search_files, run_cmd, list_code_definition_names]

        super().__init__(
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        interactive_mode = run_context.context.interactive_mode
        system_prompt = code_gen_prompt.get_system_prompt(root_dir, interactive_mode)
        return system_prompt

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        interactive_mode = self.get_interactive_mode()
            
        context = CodeAgentContext(
            root_dir=current_working_dir,
            interactive_mode=interactive_mode
        )
        return context

    async def process_at_commands(self, user_input: str, context: CodeAgentContext) -> str:
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
                def __init__(self, root_dir: str):
                    self.root_dir = root_dir
            
            config = AtCommandConfig(context.root_dir)
            
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

    async def run(self, user_input: str, context: CodeAgentContext) -> RunResult:
        """
        Execute code generation task.

        Args:
            user_input: User's code generation request with requirements and specifications
            context: Context object providing project information
        Returns:
            Generation result containing final output and execution details
        """

        # Process @ commands first
        processed_input = await self.process_at_commands(user_input, context)
        
        input_with_env = self.assemble_user_input(processed_input, context)
        result = await self.run_impl(
            starting_agent=self,
            input=input_with_env,
            max_turns=settings.MAX_TURNS,
            context=context,
        )

        return result

    async def run_streamed(
        self, user_input: str, context: CodeAgentContext
    ) -> RunResultStreaming:
        """
        Execute code generation task with streaming output.

        Args:
            user_input: User's code generation request with requirements and specifications
            context: Context object providing project information
        Returns:
            A streaming result of the generation, containing final output and execution details.
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

    def assemble_user_input(self, user_input: str, context: CodeAgentContext) -> str:
        task = f'<task>\n{user_input}\n</task>'
        return task
        # repo_map_content = self.generate_repo_map(context)

        # if repo_map_content:
        #     project_structure = f"Repository Map:\n{repo_map_content}"
        # else:
        #     project_structure = "Repository Map: Unable to generate repository map"

        # environment_details = f'<environment_details>\n{project_structure}\n</environment_details>'
        # return task + '\n' + environment_details

    def generate_repo_map(self, context: CodeAgentContext) -> str:
        """
        Generate repository map for project structure analysis.
        
        Args:
            context: Code agent context containing project information
            
        Returns:
            Repository map content as string
        """
        try:
            if not context.root_dir:
                return ""

            repo_map = self.get_repo_map_instance(context.root_dir)
            if not repo_map:
                return ""

            python_files = []
            for root, dirs, files in os.walk(context.root_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [
                    '__pycache__', 'node_modules', '.git', '.venv', 'venv', 'env'
                ]]

                for file in files:
                    if file.endswith('.py') and not file.startswith('.'):
                        filepath = os.path.join(root, file)
                        python_files.append(filepath)

            substantial_files = []
            for filepath in python_files:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if len(content) > 100:
                            lines = [line.strip() for line in content.split('\n') if line.strip()]
                            non_comment_lines = [line for line in lines if not line.startswith('#')]
                            if len(non_comment_lines) > 5:
                                substantial_files.append(filepath)
                except Exception:
                    continue

            if len(substantial_files) > 50:
                substantial_files = substantial_files[:50]

            result = repo_map.get_repo_map(
                chat_files=[],
                other_files=substantial_files,
                mentioned_fnames=set(),
                mentioned_idents=set(['class', 'def', 'function'])
            )

            return result or ""

        except Exception as e:
            return f"Generate repo map failed: {str(e)}"

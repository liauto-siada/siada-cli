"""
Code Generation Agent Module

Provides specialized Agent implementation for code generation tasks.
"""
import os

from agents import RunContextWrapper, RunResult, Runner, RunConfig
from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.siada_agent import SiadaAgent
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.foundation.config import settings
from siada.models.provider import SiadaProvider
from siada.agent_hub.coder.prompt import code_gen_prompt
import logging

logging.getLogger().setLevel(logging.INFO)

class CodeGenAgent(SiadaAgent[CodeAgentContext]):
    """
    Code Generation Agent
    
    Specialized Agent implementation for code generation tasks.
    """

    def __init__(self, *args, **kwargs):
        provider = SiadaProvider()
        model = provider.get_model(settings.Claude_4_0_SONNET)
        
        if 'name' not in kwargs:
            kwargs['name'] = "CodeGenAgent"
        
        if 'tools' not in kwargs:
            kwargs['tools'] = [edit, regex_search_files, run_cmd]
            
        if 'model' not in kwargs:
            kwargs['model'] = model
        
        super().__init__(
            *args,
            **kwargs
        )


    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        system_prompt = code_gen_prompt.get_system_prompt(root_dir)
        return system_prompt

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        context = CodeAgentContext(root_dir=current_working_dir)
        return context


    async def run(self, user_input: str, context: CodeAgentContext) -> RunResult:
        """
        Execute code generation task.
        
        Args:
            user_input: User's code generation request with requirements and specifications
            context: Context object providing project information
        Returns:
            Generation result containing final output and execution details
        """
        config = RunConfig(tracing_disabled=False)
        input_with_env = self.assemble_user_input(user_input, context)
        result = await Runner.run(
            starting_agent=self,
            input=input_with_env,
            max_turns=settings.MAX_TURNS,
            run_config=config,
            context=context
        )
        
        return result


    def assemble_user_input(self, user_input: str, context: CodeAgentContext) -> str:
        task = f'<task>\n{user_input}\n</task>'
        repo_map_content = self.generate_repo_map(context)
        
        if repo_map_content:
            project_structure = f"Repository Map:\n{repo_map_content}"
        else:
            project_structure = "Repository Map: Unable to generate repository map"
        
        environment_details = f'<environment_details>\n{project_structure}\n</environment_details>'
        return task + '\n' + environment_details

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

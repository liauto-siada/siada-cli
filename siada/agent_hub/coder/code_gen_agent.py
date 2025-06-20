"""
Bug修复Agent模块

提供专门用于代码bug修复的Agent实现
"""
import os
from typing import Any

from agents import RunContextWrapper, RunResult, Runner, RunConfig, add_trace_processor, TContext

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.siada_agent import SiadaAgent
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.foundation.config import settings
from siada.models.provider import SiadaProvider
from siada.agent_hub.coder.prompt import bug_fix_prompt
from siada.agent_hub.coder.tracing import create_detailed_logger
import logging

logging.getLogger().setLevel(logging.INFO)

class CodeGenAgent(SiadaAgent[CodeAgentContext]):
    """
    代码生成Agent

    专门用于代码生成的Agent实现
    """

    def __init__(self, *args, **kwargs):
        # 使用SiadaProvider提供的默认模型
        provider = SiadaProvider()
        model = provider.get_model(settings.Claude_4_0_SONNET)
        
        # 如果没有传递name参数，则使用默认值
        if 'name' not in kwargs:
            kwargs['name'] = "CodeGenAgent"
        
        # 如果没有传递tools参数，则使用默认值
        if 'tools' not in kwargs:
            kwargs['tools'] = [edit, regex_search_files, run_cmd]
            
        # 如果没有传递model参数，则使用默认值
        if 'model' not in kwargs:
            kwargs['model'] = model
        
        # 设置Bug修复相关的指令和工具
        super().__init__(
            *args,
            **kwargs
        )


    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        root_dir = run_context.context.root_dir
        system_prompt = bug_fix_prompt.get_system_prompt(root_dir)
        return system_prompt

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        context = CodeAgentContext(root_dir=current_working_dir)
        return context


    async def run(self, user_input: str, context: CodeAgentContext) -> RunResult:
        """
        执行Bug修复任务
        
        Args:
            user_input: 用户描述的Bug问题，包括错误信息、相关文件路径等
            context: 用于提供上下文信息的上下文对象
        Returns:
            修复结果，包含最终输出、执行轮数等信息
        """

        config = RunConfig(tracing_disabled=False)
        add_trace_processor(create_detailed_logger(output_file="agent_trace.log"))

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

        # 生成 repo map
        repo_map_content = self.generate_repo_map(context)
        
        # 构建项目结构信息
        if repo_map_content:
            project_structure = f"Repository Map:\n{repo_map_content}"
        else:
            project_structure = "Repository Map: 无法生成仓库地图"
        
        environment_details = f'<environment_details>\n{project_structure}\n</environment_details>'

        return task + '\n' + environment_details

    def generate_repo_map(self, context: CodeAgentContext) -> str:
        """
        生成仓库地图
        
        Args:
            context: 代码上下文
            
        Returns:
            str: 仓库地图内容
        """
        try:
            if not context.root_dir:
                return ""
                
            # 获取 RepoMap 实例
            repo_map = self.get_repo_map_instance(context.root_dir)
            if not repo_map:
                return ""
            
            # 收集 Python 文件（参考测试用例的逻辑）
            python_files = []
            for root, dirs, files in os.walk(context.root_dir):
                # 跳过不需要的目录
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [
                    '__pycache__', 'node_modules', '.git', '.venv', 'venv', 'env'
                ]]
                
                for file in files:
                    if file.endswith('.py') and not file.startswith('.'):
                        filepath = os.path.join(root, file)
                        python_files.append(filepath)
            
            # 过滤出有实际内容的文件
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
            
            # 限制文件数量
            if len(substantial_files) > 50:
                substantial_files = substantial_files[:50]
            
            # 生成 repo map
            result = repo_map.get_repo_map(
                chat_files=[],  # 没有特定的聊天文件
                other_files=substantial_files,
                mentioned_fnames=set(),
                mentioned_idents=set(['class', 'def', 'function'])
            )
            
            return result or ""
            
        except Exception as e:
            # 如果生成失败，返回错误信息但不中断流程
            return f"Generate repo map failed: {str(e)}"

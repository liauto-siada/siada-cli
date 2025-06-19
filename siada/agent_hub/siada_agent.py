from abc import ABC, abstractmethod
from typing import Generic
import yaml
import os

from agents import Agent, RunResult, TContext


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
    
    def get_repo_map_model_name(self) -> str:
        """
        获取用于 repo map 生成的模型名称
        
        Returns:
            str: 模型名称，默认使用 claude-3-5-sonnet-20241022
        """
        try:
            # 读取配置文件
            config_path = os.path.join(os.getcwd(), "agent_config.yaml")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    llm_config = config.get('llm_config', {})
                    return llm_config.get('model_name', 'claude-3-5-sonnet-20241022')
        except Exception:
            pass
        
        # 如果读取配置失败，使用默认值
        return 'claude-3-5-sonnet-20241022'
    
    def get_repo_map_instance(self, root_dir: str):
        """
        获取 RepoMap 实例
        
        Args:
            root_dir (str): 仓库根目录
            
        Returns:
            RepoMap: 配置好的 RepoMap 实例
        """
        try:
            from siada.tools.coder.repo_map.repo_map import RepoMap
            from siada.tools.coder.repo_map.token_counter import TokenCounterModel
            from siada.tools.coder.repo_map.io import SilentIO
            
            # 读取配置
            config_path = os.path.join(os.getcwd(), "agent_config.yaml")
            llm_config = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                        llm_config = config.get('llm_config', {})
                except Exception:
                    pass
            
            # 获取配置参数
            model_name = llm_config.get('model_name', 'claude-3-5-sonnet-20241022')
            repo_map_tokens = llm_config.get('repo_map_tokens', 8192)
            repo_map_mul_no_files = llm_config.get('repo_map_mul_no_files', 16)
            repo_verbose = llm_config.get('repo_verbose', True)
            
            # 创建组件
            token_counter = TokenCounterModel(model_name)
            io = SilentIO()  # 使用静默 IO 避免输出干扰
            
            return RepoMap(
                root=root_dir,
                main_model=token_counter,
                io=io,
                verbose=repo_verbose,
                map_tokens=repo_map_tokens,
                map_mul_no_files=repo_map_mul_no_files
            )
        except Exception as e:
            # 如果创建失败，返回 None
            return None

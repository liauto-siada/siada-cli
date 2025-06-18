import importlib
import os
from pathlib import Path
from typing import Dict, Type, Optional

import yaml
from agents import RunResult, Agent


class SiadaRunner:

    @staticmethod
    async def run_agent(agent_name : str, user_input: str) -> RunResult:
        pass

    @staticmethod
    def _load_agent_config() -> Dict[str, Dict]:
        """
        从配置文件加载Agent配置
        
        Returns:
            Dict[str, Dict]: Agent配置字典
        """
        # 获取项目根目录下的配置文件路径
        current_dir = Path(__file__).parent.parent.parent  # 回到项目根目录
        config_path = current_dir / "agent_config.yaml"
        
        if not config_path.exists():
            raise FileNotFoundError(f"Agent配置文件不存在: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        return config.get('agents', {})
    
    @staticmethod
    def _import_agent_class(class_path: str) -> Type[Agent]:
        """
        动态导入Agent类
        
        Args:
            class_path: Agent类的完整导入路径，如 'siada.agent_hub.coder.bug_fix_agent.BugFixAgent'
        
        Returns:
            Type[Agent]: Agent类
        """
        module_path, class_name = class_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    
    @staticmethod
    async def get_agent(agent_name: str) -> Agent:
        """
        根据agent名称获取对应的Agent实例
        
        Args:
            agent_name: Agent名称，支持大小写不敏感匹配
                       例如: 'bugfix', 'BugFix', 'bug_fix' 等
        
        Returns:
            Agent: 对应的Agent实例
            
        Raises:
            ValueError: 当找不到对应的Agent类型时抛出异常
            FileNotFoundError: 当配置文件不存在时抛出异常
            ImportError: 当无法导入Agent类时抛出异常
        """
        # 标准化agent名称：转小写并移除下划线和连字符
        normalized_name = agent_name.lower().replace('_', '').replace('-', '')
        
        # 从配置文件加载Agent映射
        agent_configs = SiadaRunner._load_agent_config()
        
        # 查找对应的Agent配置
        agent_config = agent_configs.get(normalized_name)
        
        if agent_config is None:
            supported_agents = [name for name, config in agent_configs.items() 
                              if config.get('enabled', False) and config.get('class')]
            raise ValueError(
                f"不支持的Agent类型: '{agent_name}'. "
                f"支持的Agent类型: {supported_agents}"
            )
        
        # 检查Agent是否启用
        if not agent_config.get('enabled', False):
            raise ValueError(f"Agent '{agent_name}' 已被禁用")
        
        # 检查Agent类是否已实现
        class_path = agent_config.get('class')
        if not class_path:
            raise ValueError(f"Agent '{agent_name}' 尚未实现")
        
        # 动态导入并实例化Agent类
        try:
            agent_class = SiadaRunner._import_agent_class(class_path)
            return agent_class()
        except (ImportError, AttributeError) as e:
            raise ImportError(f"无法导入Agent类 '{class_path}': {e}")

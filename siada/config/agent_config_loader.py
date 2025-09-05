from dataclasses import dataclass
from typing import Dict, Optional
import yaml
import os
from pathlib import Path

@dataclass
class AgentConfig:
    """单个Agent的配置"""
    class_path: str
    description: str
    enabled: bool
    supported_modes: str = "non_interactive"

@dataclass 
class AgentConfigCollection:
    """所有Agent的配置集合"""
    agents: Dict[str, AgentConfig]
    
    def get_agent_config(self, agent_name: str) -> Optional[AgentConfig]:
        """获取指定agent的配置"""
        return self.agents.get(agent_name)

def load_agent_config(config_path: Optional[Path] = None) -> AgentConfigCollection:
    """加载agent配置"""
    if config_path is None:
        config_path = Path.cwd() / "agent_config.yaml"
    
    agents = {}
    
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                agent_configs = config.get('agents', {})
                
                for agent_name, agent_data in agent_configs.items():
                    agents[agent_name] = AgentConfig(
                        class_path=agent_data.get('class', ''),
                        description=agent_data.get('description', ''),
                        enabled=agent_data.get('enabled', False),
                        supported_modes=agent_data.get('supported_modes', 'non_interactive')
                    )
        except Exception as e:
            print(f"Warning: Failed to load agent config: {e}")
    
    return AgentConfigCollection(agents=agents)

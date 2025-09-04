





import os
import yaml
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, Dict, Any
from siada.config.mcp_config import MCPConfig
from siada.config.mcp_config_loader import MCPConfigLoader


@dataclass(frozen=True)
class LLMConfig:
    """LLM configuration class"""
    model: Optional[str] = None
    provider: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMConfig':
        """Create LLMConfig instance from dictionary"""
        return cls(
            model=data.get('model'),
            provider=data.get('provider')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass(frozen=True)
class CheckpointConfig:
    """Checkpoint configuration class"""
    enable: Optional[bool] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CheckpointConfig':
        """Create CheckpointConfig instance from dictionary"""
        return cls(
            enable=data.get('enable')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


def _get_default_config_path() -> Path:
    """Get default configuration file path"""
    home_dir = Path.home()
    return home_dir / '.siada-cli' / 'conf.yaml'

@dataclass(frozen=True)
class Config:
    """Main configuration class (immutable)"""
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    checkpoint_config: CheckpointConfig = field(default_factory=CheckpointConfig)
    mcp_config: MCPConfig = field(default_factory=MCPConfig)

def load_conf(config_path: Optional[Path] = None) -> 'Config':
    """Load configuration from separated YAML and JSON files"""
    if config_path is None:
        config_path = _get_default_config_path()
    
    llm_config = LLMConfig()
    checkpoint_config = CheckpointConfig()

    # 1. Load LLM configuration from YAML file
    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as file:
                data = yaml.safe_load(file) or {}
                
                # Load LLM configuration
                if 'llm_config' in data:
                    llm_config = LLMConfig.from_dict(data['llm_config'])

                # Load Checkpoint configuration
                if 'checkpoint_config' in data:
                    checkpoint_config = CheckpointConfig.from_dict(data['checkpoint_config'])
        # If config file doesn't exist, return default values without creating directories
            
    except yaml.YAMLError as e:
        print(f"Warning: Configuration file format error: {e}")
    except Exception as e:
        print(f"Warning: Failed to load configuration file: {e}")
    
    # 2. Load MCP configuration from dedicated JSON file using specialized loader
    mcp_config = MCPConfigLoader.load_config()

    return Config(llm_config=llm_config, checkpoint_config=checkpoint_config , mcp_config=mcp_config)


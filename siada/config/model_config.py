"""Model configuration module for loading user-defined model settings"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path
import json


@dataclass
class UserModelConfig:
    """User-defined model configuration"""
    model_name: str
    context_window: int
    max_tokens: Optional[int] = None
    supports_images: bool = False
    supports_prompt_cache: bool = False
    supports_extra_params: Optional[List[str]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserModelConfig':
        """Create UserModelConfig instance from dictionary"""
        return cls(
            model_name=data['model_name'],
            context_window=data['context_window'],
            max_tokens=data.get('max_tokens'),
            supports_images=data.get('supports_images', False),
            supports_prompt_cache=data.get('supports_prompt_cache', False),
            supports_extra_params=data.get('supports_extra_params')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'model_name': self.model_name,
            'context_window': self.context_window,
            'max_tokens': self.max_tokens,
            'supports_images': self.supports_images,
            'supports_prompt_cache': self.supports_prompt_cache,
            'supports_extra_params': self.supports_extra_params
        }


@dataclass
class ModelCollectionConfig:
    """Model collection configuration"""
    default_model: Optional[str] = None
    models: List[UserModelConfig] = None

    def __post_init__(self):
        if self.models is None:
            self.models = []

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelCollectionConfig':
        """Create ModelCollectionConfig instance from dictionary"""
        models = [UserModelConfig.from_dict(m) for m in data.get('models', [])]
        return cls(
            default_model=data.get('default_model'),
            models=models
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'default_model': self.default_model,
            'models': [m.to_dict() for m in self.models]
        }


def _get_default_model_config_path() -> Path:
    """Get default model configuration file path"""
    home_dir = Path.home()
    return home_dir / '.siada-cli' / 'models.json'


def load_user_model_config(config_path: Optional[Path] = None) -> Optional[ModelCollectionConfig]:
    """Load user-defined model configuration from JSON file
    
    Args:
        config_path: Path to the model configuration file. If None, uses default path.
        
    Returns:
        ModelCollectionConfig if file exists and is valid, None otherwise
    """
    if config_path is None:
        config_path = _get_default_model_config_path()
    
    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                return ModelCollectionConfig.from_dict(data)
    except json.JSONDecodeError as e:
        print(f"Warning: Model configuration file format error: {e}")
    except Exception as e:
        print(f"Warning: Failed to load model configuration file: {e}")
    
    return None


def create_example_model_config(config_path: Optional[Path] = None) -> None:
    """Create an example model configuration file
    
    Args:
        config_path: Path where to create the example file. If None, uses default path.
    """
    if config_path is None:
        config_path = _get_default_model_config_path()
    
    # Create directory if it doesn't exist
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Example configuration
    example_config = {
        "default_model": "gpt-4",
        "models": [
            {
                "model_name": "gpt-4",
                "context_window": 128000,
                "max_tokens": 4096,
                "supports_images": True,
                "supports_prompt_cache": False,
                "supports_extra_params": []
            },
            {
                "model_name": "gpt-3.5-turbo",
                "context_window": 16385,
                "max_tokens": 4096,
                "supports_images": False,
                "supports_prompt_cache": False,
                "supports_extra_params": []
            },
            {
                "model_name": "claude-3-opus",
                "context_window": 200000,
                "max_tokens": 4096,
                "supports_images": True,
                "supports_prompt_cache": True,
                "supports_extra_params": []
            }
        ]
    }
    
    with open(config_path, 'w', encoding='utf-8') as file:
        json.dump(example_config, file, indent=2, ensure_ascii=False)
    
    print(f"Example model configuration created at: {config_path}")

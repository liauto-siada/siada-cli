from dataclasses import dataclass, fields
from typing import Optional

from siada.models.model_base_config import ModelBaseConfig, get_model_config

import os
from pathlib import Path

import logging
import yaml
@dataclass()
class ModelRunConfig(ModelBaseConfig):
    
    reasoning_effort : Optional[str] = None
    thinking_tokens : Optional[int] = None
    temperature : Optional[float] = None
    extra_params : Optional[dict] = None
    provider: Optional[str] = None



    def __init__(self, model): 
        self.configure_model_settings(model)


    def _copy_fields(self, source):
        """Helper to copy fields from a ModelSettings instance to self"""
        for field in fields(ModelBaseConfig):
            val = getattr(source, field.name)
            setattr(self, field.name, val)


    def configure_model_settings(self, model):
        # Look for exact model match
        model_config = get_model_config(model)
        if model_config:
            self._copy_fields(model_config)
        else:
            raise ValueError(f"Model {model} not found in model settings")
        

    def set_reasoning_effort(self, reasoning_effort):
        self.reasoning_effort = reasoning_effort


    def get_raw_thinking_tokens(self):
        """Get formatted thinking token budget if available"""
        return self.thinking_tokens

    def get_thinking_tokens(self):
        budget = self.get_raw_thinking_tokens()

        if budget is not None:
            # Format as xx.yK for thousands, xx.yM for millions
            if budget >= 1024 * 1024:
                value = budget / (1024 * 1024)
                if value == int(value):
                    return f"{int(value)}M"
                else:
                    return f"{value:.1f}M"
            else:
                value = budget / 1024
                if value == int(value):
                    return f"{int(value)}k"
                else:
                    return f"{value:.1f}k"
        return None
    
    def get_reasoning_effort(self):
        """Get reasoning effort value if available"""
        return self.reasoning_effort
    

    def set_reasoning_effort(self, effort):
        """Set the reasoning effort parameter for models that support it"""
        if effort is not None:
            self.reasoning_effort = effort
    

    def set_thinking_tokens(self, value):
        """
        Set the thinking token budget for models that support it.
        Accepts formats: 8096, "8k", "10.5k", "0.5M", "10K", etc.
        Pass "0" to disable thinking tokens.
        """
        if value is not None:
            num_tokens = self.parse_token_value(value)
            self.temperature = None
            if num_tokens > 0:
                self.thinking_tokens = num_tokens
            else:
                self.thinking_tokens = None


    def parse_token_value(self, value):
        """
        Parse a token value string into an integer.
        Accepts formats: 8096, "8k", "10.5k", "0.5M", "10K", etc.

        Args:
            value: String or int token value

        Returns:
            Integer token value
        """
        if isinstance(value, int):
            return value

        if not isinstance(value, str):
            return int(value)  # Try to convert to int

        value = value.strip().upper()

        if value.endswith("K"):
            multiplier = 1024
            value = value[:-1]
        elif value.endswith("M"):
            multiplier = 1024 * 1024
            value = value[:-1]
        else:
            multiplier = 1

        # Convert to float first to handle decimal values like "10.5k"
        return int(float(value) * multiplier)
    

    @staticmethod
    def get_default_config():
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "agent_config.yaml"
        llm_config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    llm_config = config.get('llm_config', {})
            except Exception as e:
                    logging.warning(f"Failed to read agent config file for repo map instance: {str(e)}")
        model_name = llm_config.get('model_name')
        provider = llm_config.get('provider')

        model_config = ModelRunConfig(model_name)

        model_config.provider = provider
        return model_config









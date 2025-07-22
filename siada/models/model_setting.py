import agents
from dataclasses import dataclass, fields
from typing import Optional

from siada.models.model_settings import ModelSettings, get_model_config



class Model(ModelSettings):

    def __init__(self, model): 
        self.configure_model_settings(model)


    def _copy_fields(self, source):
        """Helper to copy fields from a ModelSettings instance to self"""
        for field in fields(ModelSettings):
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


    def set_thinking_tokens(self, thinking_tokens):
        self.thinking_tokens = thinking_tokens








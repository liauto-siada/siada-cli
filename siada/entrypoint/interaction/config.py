"""
Configuration classes for interaction module
"""

from dataclasses import dataclass
from rlcompleter import Completer

from siada.io.io import InputOutput
from siada.models.model_setting import ModelConfig


@dataclass
class InteractionConfig:
    """Configuration data class for interaction controller"""

    # Model and IO
    model: ModelConfig
    io: InputOutput
    workspace: str
    agent_name: str
    completer: Completer
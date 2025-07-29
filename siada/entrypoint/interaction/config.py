"""
Configuration classes for interaction module
"""

from dataclasses import dataclass
from rlcompleter import Completer

from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig


@dataclass
class RunningConfig:
    """Configuration data class for interaction controller"""

    # Model and IO
    model: ModelRunConfig
    max_turns: int = 10
    tracing_disabled: bool = False
    console_output: bool = False
    io: InputOutput
    workspace: str
    agent_name: str
    interactive: bool = True
    completer: Completer
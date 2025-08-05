"""
Configuration classes for interaction module
"""

from dataclasses import dataclass
from typing import Optional
from rlcompleter import Completer

from siada.io.color_settings import RunningConfigColorSettings
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig


@dataclass
class RunningConfig:
    """Configuration data class for interaction controller"""

    # Required fields (no default values)
    llm_config: ModelRunConfig
    io: InputOutput
    workspace: str
    agent_name: str
    
    # Optional fields (with default values)
    completer: Optional[Completer] = None
    running_color_settings: Optional[RunningConfigColorSettings] = None
    max_turns: int = 10
    tracing_disabled: bool = False
    console_output: bool = False
    interactive: bool = True

"""
Configuration classes for interaction module
"""

from dataclasses import dataclass
from typing import Optional
from rlcompleter import Completer

from siada.io.color_settings import RunningConfigColorSettings
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig
from siada.config.mcp_config import MCPConfig
from siada.config.config_loader import CheckpointConfig
from siada.foundation.siadaignore_controller import SiadaIgnoreController


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
    user_memory: Optional[str] = None  # User memory content from siada.md
    checkpointing_config: Optional[CheckpointConfig] = None  # Checkpointing configuration
    mcp_config: Optional[MCPConfig] = None  # MCP configuration
    mcp_service = None  # MCP service instance (will be initialized later)
    auto_compact: bool = True  # Enable automatic context compression
    siadaignore_controller: Optional[SiadaIgnoreController] = None  # SiadaIgnore controller for file access control
    preferred_language: str = None  # Preferred language for AI responses: "en" (English) or "zh-CN" (Chinese)
    startup_warning: Optional[str] = None  # Warning message to display at startup (for Textual mode)

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
    checkpointing_config: Optional[CheckpointConfig] = None  # Checkpointing configuration
    mcp_config: Optional[MCPConfig] = None  # MCP configuration
    mcp_service = None  # MCP service instance (will be initialized later)
    auto_compact: bool = True  # Enable automatic context compression
    compaction_strategy: Optional[str] = None  # Compaction strategy override (e.g. "header_summary", "turn_prune_summary")
    startup_warning: Optional[str] = None  # Warning message to display at startup (for Textual mode)
    banner: bool = True  # Enable/disable welcome banner display
    acp_mode: bool = False  # Enable/disable ACP mode for structured communication
    memory_enabled: bool = True  # Memory subsystem master switch (mirror of conf.memory_config.enabled)
    enable_notification: bool = True  # Task completion notification switch (mirror of conf.enable_notification)

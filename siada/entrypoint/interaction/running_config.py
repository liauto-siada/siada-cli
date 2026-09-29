"""
Configuration classes for interaction module
"""

from dataclasses import dataclass
from typing import Any, Optional
from rlcompleter import Completer

from siada.io.color_settings import RunningConfigColorSettings
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig
from siada.config.mcp_config import MCPConfig
from siada.config.config_loader import CheckpointConfig, Config


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


def build_running_config_from_conf(
    conf: Optional[Config],
    *,
    llm_config: ModelRunConfig,
    io: InputOutput,
    workspace: str,
    agent_name: str,
    **overrides: Any,
) -> RunningConfig:
    """Build a RunningConfig from conf.yaml-derived fields; surface-specific fields come in via **overrides."""
    fields: dict[str, Any] = {
        "llm_config": llm_config,
        "io": io,
        "workspace": workspace,
        "agent_name": agent_name,
        "mcp_config": conf.mcp_config if conf else None,
        "compaction_strategy": conf.compaction_strategy if conf else None,
        "memory_enabled": conf.memory_config.enabled if conf else True,
        "enable_notification": conf.enable_notification if conf else True,
    }
    fields.update(overrides)
    return RunningConfig(**fields)

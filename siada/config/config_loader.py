import logging
import os
import yaml
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, Dict, Any
from siada.config.mcp_config import MCPConfig
from siada.config.mcp_config_loader import MCPConfigLoader
from siada.config.model_config import ModelCollectionConfig, load_user_model_config
from siada.foundation.constants import SIADA_HOME
from siada.io.io import InputOutput

logger = logging.getLogger("siada.config")


@dataclass(frozen=True)
class LLMConfig:
    """LLM configuration class"""
    model: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    thinking: Optional[bool] = None  # Enable/disable thinking (default: True for models that support it)
    parallel_tool_calls: Optional[bool] = None  # Enable/disable parallel tool calls (default: True for models that support it)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMConfig':
        return cls(
            model=data.get('model'),
            provider=data.get('provider'),
            base_url=data.get('base_url'),
            api_key=data.get('api_key'),
            thinking=bool(data['thinking']) if 'thinking' in data and data['thinking'] is not None else None,
            parallel_tool_calls=bool(data['parallel_tool_calls']) if 'parallel_tool_calls' in data and data['parallel_tool_calls'] is not None else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CheckpointConfig:
    """Checkpoint configuration class"""
    enable: Optional[bool] = None
    max_checkpoint_files: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CheckpointConfig':
        return cls(
            enable=data.get('enable'),
            max_checkpoint_files=data.get('max_checkpoint_files')
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)



@dataclass(frozen=True)
class SubAgentRegistryConfig:
    """Sub Agent Registry configuration class"""
    enabled: bool = True
    backend_url: str = "agent-manager.inner.chj.cloud"
    timeout: int = 10
    environment: str = "prod"  # prod/dev/local

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SubAgentRegistryConfig':
        return cls(
            enabled=data.get('enabled', True),
            backend_url=data.get('backend_url', 'agent-manager.inner.chj.cloud'),
            timeout=data.get('timeout', 10),
            environment=data.get('environment', 'prod')
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProactiveConfig:
    """Proactive agent configuration class"""
    enabled: bool = True
    work_hours: str = "09:00-18:00"
    trigger_interval: int = 60  # minutes
    daily_task_execution_time: str = "08:30"
    auto_execute_enabled: bool = False  # Auto-execute tasks without confirmation (default: False for safety)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProactiveConfig':
        enabled_val = data.get('enabled', True)
        enabled = bool(enabled_val) if enabled_val is not None else True
        interval_val = data.get('trigger_interval', 60)
        trigger_interval = int(interval_val) if interval_val is not None else 60
        auto_execute_val = data.get('auto_execute_enabled', False)
        auto_execute_enabled = bool(auto_execute_val) if auto_execute_val is not None else False
        return cls(
            enabled=enabled,
            work_hours=data.get('work_hours', '09:00-18:00'),
            trigger_interval=trigger_interval,
            daily_task_execution_time=data.get('daily_task_execution_time', '08:30'),
            auto_execute_enabled=auto_execute_enabled
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _get_default_config_path() -> Path:
    return SIADA_HOME / 'conf.yaml'


def _create_default_config_file(config_path: Path) -> None:
    """Create default configuration file with comments"""
    config_template = """# Siada Configuration File
# This file contains the main configuration for Siada

# User Information
# Your user identifier for telemetry and tracking (internal use only)
# Format: username@domain.com
# user_id: "yunan@lixiang.com"

# LLM Configuration
# Configure your Language Model provider settings
llm_config:
  # Model name (e.g., claude-3-5-sonnet-20241022, gpt-4, etc.)
  # model: "claude-3-5-sonnet-20241022"
  
  # Provider name (e.g., anthropic, openai, etc.)
  # provider: "anthropic"
  
  # Base URL for the API endpoint (optional, use default if not specified)
  # base_url: "https://api.anthropic.com"
  
  # API key for authentication (required for most providers)
  # api_key: "your-api-key-here"
  
  # Enable thinking mode for supported models (default: true for models that support it)
  # thinking: true
  
  # Enable parallel tool calls (default: true for models that support it)
  # parallel_tool_calls: true

# Checkpoint Configuration
# Configure session checkpoint settings
checkpoint_config:
  # Enable checkpoint functionality (default: true)
  # enable: true
  
  # Maximum number of checkpoint files to keep (default: 10)
  # max_checkpoint_files: 10

# Proactive Agent Configuration
# Configure the proactive agent that monitors and assists your work
proactive:
  # Enable proactive agent (default: true)
  enabled: true
  
  # Work hours when proactive agent is active (format: "HH:MM-HH:MM")
  work_hours: "09:00-18:00"
  
  # Time for daily notifications (format: "HH:MM")
  daily_task_execution_time: "08:30"
  
  # Auto-execute tasks switch (default: false for safety)
  # When enabled: tasks with needs_confirmation=false will be executed automatically
  # When disabled: all tasks require user confirmation
  auto_execute_enabled: false

# Command Timeout Configuration
# Timeout in seconds for command execution (optional)
# command_timeout: 300

# Pre-plan mode: agent shows a plan and waits for approval before executing (default: false)
# pre_plan: false

# Preferred language for AI responses: "en" (English) or "zh-CN" (Chinese)
# preferred_language: null

# Compaction strategy for context compression (optional)
# If not set, auto-detects based on session mode:
#   - CLI/TUI mode default: "header_summary"
#   - IM mode default: "turn_prune_summary"
# Available options:
#   - "header_summary": Conservative, keeps first user-assistant pair as header
#   - "turn_prune_summary": Multi-layer pipeline (turn limit + tool truncation + LLM summary)
# compaction_strategy: null

# Lark IM Configuration
# Configure Lark bot integration mode
# lark:
#   # Mode: "relay" (via IM Gateway) or "direct" (Lark WS SDK)
#   mode: relay
#   # workspace: /path/to/your/workspace  # Optional, defaults to ~/.siada-cli/workspace/lark
#
#   # Direct mode settings (only needed when mode=direct)
#   # direct:
#   #   app_id: "your_app_id"
#   #   app_secret: "your_app_secret"
#   #
#   #   # DM access control (only for direct mode)
#   #   access:
#   #     dm_policy: open  # open | allowlist
#   #     allow_from:
#   #       - "ou_xxx"
#
#   # Relay mode settings (optional - defaults are hardcoded)
#   # relay:
#   #   server_url: "ws://siada-im-gateway-dev.inner.chj.cloud/ws/relay"
#   #   heartbeat_interval: 10
#   #   reconnect_backoff: [3, 5, 10, 30, 60]
"""

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(config_template)


@dataclass(frozen=True)
class Config:
    """Main configuration class (immutable)"""
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    checkpoint_config: CheckpointConfig = field(default_factory=CheckpointConfig)
    mcp_config: MCPConfig = field(default_factory=MCPConfig)
    model_config: Optional[ModelCollectionConfig] = None
    command_timeout: Optional[int] = None
    sub_agent_registry_config: Optional[SubAgentRegistryConfig] = None
    proactive_config: ProactiveConfig = field(default_factory=ProactiveConfig)
    pre_plan: Optional[bool] = None
    preferred_language: Optional[str] = None
    compaction_strategy: Optional[str] = None
    lark_config: Optional[Dict[str, Any]] = None


def _load_lark_config(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract lark config from raw conf.yaml data.

    Relay defaults are merged lazily in build_relay_config() at runtime.

    Returns:
        Dict with structure {"lark": {...}}, or None if no valid lark config.
    """
    lark_section = data.get("lark")
    if not lark_section or not isinstance(lark_section, dict):
        return None

    mode = lark_section.get("mode")
    if not mode:
        logger.debug("No lark mode set, skipping lark config")
        return None

    # Wrap in {"lark": ...} for backward compatibility with callers
    lark_config = {"lark": lark_section}

    logger.info(f"Lark config loaded, mode={mode}")
    return lark_config


def _load_sub_agent_registry_config() -> Optional[SubAgentRegistryConfig]:
    """Load SubAgentRegistryConfig from agent_config.yaml in the project root."""
    try:
        agent_config_path = Path(__file__).parent.parent.parent / "agent_config.yaml"
        if not agent_config_path.exists():
            return None
        with open(agent_config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        if 'sub_agent_registry' in data:
            return SubAgentRegistryConfig.from_dict(data['sub_agent_registry'])
        return None
    except Exception as e:
        print(f"Warning: Failed to load sub agent registry config: {e}")
        return None


def load_conf(config_path: Optional[Path] = None) -> 'Config':
    """Load configuration from separated YAML and JSON files"""
    if config_path is None:
        config_path = _get_default_config_path()

    if not config_path.exists():
        _create_default_config_file(config_path)

    llm_config = LLMConfig()
    checkpoint_config = CheckpointConfig()
    proactive_config = ProactiveConfig()
    lark_config: Optional[Dict[str, Any]] = None
    command_timeout: Optional[int] = None
    pre_plan: Optional[bool] = None
    preferred_language: Optional[str] = None
    compaction_strategy: Optional[str] = None

    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as file:
                data = yaml.safe_load(file) or {}
                if 'llm_config' in data and data['llm_config'] is not None:
                    llm_config = LLMConfig.from_dict(data['llm_config'])
                    if llm_config.base_url is not None and llm_config.api_key is not None:
                        os.environ['BASE_URL'] = llm_config.base_url
                        os.environ['API_KEY'] = llm_config.api_key
                if 'checkpoint_config' in data and data['checkpoint_config'] is not None:
                    checkpoint_config = CheckpointConfig.from_dict(data['checkpoint_config'])
                if 'proactive' in data and data['proactive'] is not None:
                    proactive_config = ProactiveConfig.from_dict(data['proactive'])
                # Load lark IM config
                lark_config = _load_lark_config(data)
                command_timeout = data.get('command_timeout')
                pre_plan = data.get('pre_plan')
                preferred_language = data.get('preferred_language')
                compaction_strategy = data.get('compaction_strategy')
    except yaml.YAMLError as e:
        try:
            io = InputOutput.get_instance()
            if io:
                io.print_error(f"Warning: Configuration file format error: {e}")
        except Exception:
            pass
    except Exception as e:
        try:
            io = InputOutput.get_instance()
            if io:
                io.print_error(f"Warning: Failed to load configuration file: {e}")
        except Exception:
            pass

    mcp_config = MCPConfigLoader.load_config()
    model_config = load_user_model_config()
    sub_agent_registry_config = _load_sub_agent_registry_config()

    return Config(
        llm_config=llm_config,
        checkpoint_config=checkpoint_config,
        mcp_config=mcp_config,
        model_config=model_config,
        command_timeout=command_timeout,
        sub_agent_registry_config=sub_agent_registry_config,
        proactive_config=proactive_config,
        pre_plan=pre_plan,
        preferred_language=preferred_language,
        compaction_strategy=compaction_strategy,
        lark_config=lark_config,
    )


def save_conf_field(key: str, value, config_path: Optional[Path] = None) -> bool:
    """Update a single field in conf.yaml, preserving comments and formatting.

    key supports dotted notation for nested fields, e.g. 'llm_config.model'.
    """
    from ruamel.yaml import YAML

    if config_path is None:
        config_path = _get_default_config_path()
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        ryaml = YAML()
        ryaml.preserve_quotes = True
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = ryaml.load(f) or {}
        else:
            data = {}
        parts = key.split('.')
        node = data
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value
        with open(config_path, 'w', encoding='utf-8') as f:
            ryaml.dump(data, f)
        return True
    except Exception as e:
        print(f"Warning: Failed to save conf.yaml field '{key}': {e}")
        return False

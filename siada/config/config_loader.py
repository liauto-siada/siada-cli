import logging
import os
import re
import shutil
from datetime import datetime
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, Dict, Any
from siada.config.mcp_config import MCPConfig
from siada.config.mcp_config_loader import MCPConfigLoader
from siada.config.model_config import ModelCollectionConfig, load_user_model_config
from siada.foundation.constants import SIADA_HOME
from siada.io.io import InputOutput
from siada.services.goal.models import GOAL_MAX_TURNS

logger = logging.getLogger("siada.config")


@dataclass(frozen=True)
class LLMConfig:
    """LLM configuration class"""
    model: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    thinking: Optional[bool] = None  # Enable/disable thinking (default: True for models that support it)
    enable_thinking: Optional[bool] = None  # Alias for thinking: controls the enable_thinking API param (v4 flash etc.)
    parallel_tool_calls: Optional[bool] = None  # Enable/disable parallel tool calls (default: True for models that support it)
    reasoning_effort: Optional[str] = None  # Default reasoning effort level ("low"/"medium"/"high") for models that support it
    vision_model: Optional[str] = None  # Dedicated vision engine for text-only main models (open-source vision bridge)
    vision_provider: Optional[str] = None  # Provider for vision_model (defaults to provider when omitted)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMConfig':
        return cls(
            model=data.get('model'),
            provider=data.get('provider'),
            base_url=data.get('base_url'),
            api_key=data.get('api_key'),
            thinking=bool(data['thinking']) if 'thinking' in data and data['thinking'] is not None else None,
            enable_thinking=bool(data['enable_thinking']) if 'enable_thinking' in data and data['enable_thinking'] is not None else None,
            parallel_tool_calls=bool(data['parallel_tool_calls']) if 'parallel_tool_calls' in data and data['parallel_tool_calls'] is not None else None,
            reasoning_effort=data.get('reasoning_effort'),
            vision_model=data.get('vision_model'),
            vision_provider=data.get('vision_provider'),
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
class ProactiveConfig:
    """Proactive agent configuration class"""
    enabled: bool = True
    work_hours: str = "09:00-18:00"
    trigger_interval: int = 60  # minutes
    daily_task_execution_time: str = "06:00"  # LLM tasks start time (staggered over 2h window)
    daily_im_send_time: str = "08:30"  # Earliest IM send time (staggered over 30min after this)
    auto_execute_enabled: bool = False  # Auto-execute tasks without confirmation (default: False for safety)
    send_daily_summary_to_im: bool = False  # Send daily summary to IM controllers after generation
    llm_config: Optional['LLMConfig'] = None  # Default model for cron tasks (overrides global llm_config)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProactiveConfig':
        enabled_val = data.get('enabled', True)
        enabled = bool(enabled_val) if enabled_val is not None else True
        interval_val = data.get('trigger_interval', 60)
        trigger_interval = int(interval_val) if interval_val is not None else 60
        auto_execute_val = data.get('auto_execute_enabled', False)
        auto_execute_enabled = bool(auto_execute_val) if auto_execute_val is not None else False
        send_summary_val = data.get('send_daily_summary_to_im', False)
        send_daily_summary_to_im = bool(send_summary_val) if send_summary_val is not None else False
        llm_cfg_data = data.get('llm_config')
        llm_config = LLMConfig.from_dict(llm_cfg_data) if llm_cfg_data else None
        return cls(
            enabled=enabled,
            work_hours=data.get('work_hours', '09:00-18:00'),
            trigger_interval=trigger_interval,
            daily_task_execution_time=data.get('daily_task_execution_time', '06:00'),
            daily_im_send_time=data.get('daily_im_send_time', '08:30'),
            auto_execute_enabled=auto_execute_enabled,
            send_daily_summary_to_im=send_daily_summary_to_im,
            llm_config=llm_config,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SubAgentConfig:
    """Sub-agent (run_subtask) configuration class"""
    llm_config: Optional['LLMConfig'] = None  # Default model for sub-agents (overrides parent llm_config)

    # Master switch for the sub-agent feature (run_subtask). Default ON:
    # the main agent keeps the `run_subtask` tool plus the matching
    # system-prompt guidance and may delegate self-contained work to a
    # sub-agent. When False, the tool is left out of the tool list and the
    # prompt guidance is dropped, so all work stays in the main agent's own
    # context.
    enabled: bool = True

    # Master switch for recursive sub-agent nesting. Default OFF: the
    # sub-agent system behaves exactly as before (a sub-agent can never spawn
    # another sub-agent — see subagent_guard.py / SubTaskAgent tool trimming).
    # When True, sub-agents (depth=1) are additionally allowed to call
    # run_subtask themselves, spawning "sub-sub-agents" (depth=2), which are
    # then blocked from spawning further nested agents (hard 2-level cap).
    # See siada/tools/agent/subagent_recursion.py for the depth/concurrency
    # policy this flag gates. Only meaningful while ``enabled`` is True.
    allow_recursive_subagents: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SubAgentConfig':
        llm_cfg_data = data.get('llm_config')
        llm_config = LLMConfig.from_dict(llm_cfg_data) if llm_cfg_data else None
        enabled_val = data.get('enabled', True)
        enabled = bool(enabled_val) if enabled_val is not None else True
        allow_val = data.get('allow_recursive_subagents', False)
        allow_recursive_subagents = bool(allow_val) if allow_val is not None else False
        # Recursion is an extension of the sub-agent feature itself, so it can
        # never stay on while the master switch is off.
        if not enabled:
            allow_recursive_subagents = False
        return cls(
            llm_config=llm_config,
            enabled=enabled,
            allow_recursive_subagents=allow_recursive_subagents,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AutoUpdateConfig:
    """Background auto-update configuration."""

    enabled: bool = True
    check_interval_minutes: int = 30
    channel: str = "prod"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AutoUpdateConfig':
        enabled_val = data.get('enabled', True)
        enabled = bool(enabled_val) if enabled_val is not None else True
        interval_val = data.get('check_interval_minutes', 30)
        check_interval_minutes = int(interval_val) if interval_val is not None else 30
        channel = str(data.get('channel', 'prod') or 'prod').strip().lower()
        if channel not in {'prod', 'beta', 'test'}:
            channel = 'prod'
        return cls(
            enabled=enabled,
            check_interval_minutes=max(1, check_interval_minutes),
            channel=channel,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CodeAgentConfig:
    """Code agent configuration class"""
    max_turns: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CodeAgentConfig':
        return cls(
            max_turns=int(data['max_turns']) if data.get('max_turns') is not None else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GoalConfig:
    """Automatic retry budget for standing goals."""
    max_turns: int = GOAL_MAX_TURNS

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GoalConfig':
        try:
            max_turns = (
                int(data.get('max_turns', GOAL_MAX_TURNS))
                if isinstance(data, dict)
                else GOAL_MAX_TURNS
            )
        except (TypeError, ValueError):
            max_turns = GOAL_MAX_TURNS
        return cls(max_turns=max(1, max_turns))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryConfig:
    """Inline memory (MEMORY.md / USER.md) configuration."""
    enabled: bool = True
    user_profile_enabled: bool = True
    memory_facts_enabled: bool = True
    memory_char_limit: int = 2200
    user_char_limit: int = 1375

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryConfig':
        def _bool(key, default):
            v = data.get(key, default)
            return bool(v) if v is not None else default
        def _int(key, default):
            v = data.get(key, default)
            return int(v) if v is not None else default
        return cls(
            enabled=_bool('enabled', True),
            user_profile_enabled=_bool('user_profile_enabled', True),
            memory_facts_enabled=_bool('memory_facts_enabled', True),
            memory_char_limit=_int('memory_char_limit', 2200),
            user_char_limit=_int('user_char_limit', 1375),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HolographicConfig:
    """Holographic structured fact memory configuration.

    Layered on top of inline memory: persists atomic facts with entity-binding
    (HRR vectors) and trust scoring in a SQLite + FTS5 database. Enables
    fact_store / fact_feedback tools and prefetch injection.
    See design_docs/siada-holographic-memory-introduction.md.
    """
    enabled: bool = True               # default ON — set false in conf.yaml to disable
    hrr_enabled: bool = True           # disable HRR even when numpy available
    hrr_dim: int = 1024                # phase vector length (matches hermes default)
    default_trust: float = 0.5         # initial trust for new facts
    min_trust_threshold: float = 0.3   # facts below this excluded from default search
    temporal_decay_half_life: int = 0  # 0=disabled; >0=age-based exponential decay (days)
    prefetch_limit: int = 5            # top-N facts injected per turn
    db_path: Optional[str] = None      # default: ~/.siada-cli/workspace/memory/holographic/facts.db
    custom_dict: list = field(default_factory=list)  # extra jieba terms

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HolographicConfig':
        def _bool(key, default):
            v = data.get(key, default)
            return bool(v) if v is not None else default
        def _int(key, default):
            v = data.get(key, default)
            return int(v) if v is not None else default
        def _flt(key, default):
            v = data.get(key, default)
            return float(v) if v is not None else default
        return cls(
            enabled=_bool('enabled', True),
            hrr_enabled=_bool('hrr_enabled', True),
            hrr_dim=_int('hrr_dim', 1024),
            default_trust=_flt('default_trust', 0.5),
            min_trust_threshold=_flt('min_trust_threshold', 0.3),
            temporal_decay_half_life=_int('temporal_decay_half_life', 0),
            prefetch_limit=_int('prefetch_limit', 5),
            db_path=data.get('db_path'),
            custom_dict=list(data.get('custom_dict') or []),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WebConfig:
    """Web tools (web_search / web_fetch) configuration.

    ``enabled`` is a tri-state master switch:
      - None  (default / "auto"): web tools are ON.
      - True:  always enable web tools regardless of provider.
      - False: always disable web tools regardless of provider.
    """
    enabled: Optional[bool] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WebConfig':
        v = data.get('enabled') if isinstance(data, dict) else None
        enabled = bool(v) if v is not None else None
        return cls(enabled=enabled)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _get_default_config_path() -> Path:
    from siada.config.conf_store import get_conf_path

    return get_conf_path()


_DEFAULT_CONFIG_TEMPLATE = """# Siada Configuration File
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
  
  # Enable parallel tool calls (default: true for models that support it)
  # parallel_tool_calls: true

  # Default reasoning effort level for models that support the reasoning_effort
  # API parameter. Valid values: "low" / "medium" / "high".
  # (priority: CLI --reasoning-effort > conf.yaml > model default)
  # reasoning_effort: high

  # NOTE on reasoning_effort for li provider:
  # litellm only recognizes "reasoning_effort" as a top-level param for models
  # whose provider supports it (gemini, gpt-5.x). For OpenAI-provider models
  # such as deepseek/qwen/glm/kimi, litellm's openai provider does NOT list it
  # in supported_params, and since drop_params=True is set globally, a top-level
  # reasoning_effort would be silently dropped. The li provider therefore
  # routes reasoning_effort through extra_body for those models, so it reaches
  # the gateway even though the model's supports_extra_params only declares
  # "thinking_tokens". This is why the value still takes effect on deepseek v4
  # flash even though the model config does not list "reasoning_effort".

  # Dedicated vision engine for text-only main models (open-source vision
  # bridge): attached images are transcribed by this image-capable model and
  # fed to the main model as text evidence. The model must have
  # supports_images=true (defined in models.json or a built-in config).
  # vision_provider defaults to the main provider when omitted.
  # vision_model: "glm-4v"
  # vision_provider: "zhipuai"

  # Enable thinking mode for supported models (default: true for models that support it)
  # enable_thinking: true
  #   - false: explicitly send enable_thinking=false to the gateway to disable
  #     thinking. NOTE: merely omitting the param does NOT disable thinking for
  #     models whose default is thinking-ON (e.g. v4 flash has
  #     default_thinking_tokens=1024) — the gateway falls back to the model
  #     default, so we must send enable_thinking=false explicitly.
  #   - true / unset: keep model default (for v4 flash this enables thinking via
  #     default_thinking_tokens -> enable_thinking)
  # NOTE: "enable_thinking" is not a recognized litellm param, so it is passed
  # through as-is to the gateway (same passthrough path as extra_body). Set
  # "enable_thinking: false" here to disable thinking for models that would
  # otherwise enable it by default.

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
  
  # Time for daily task generation (format: "HH:MM")
  daily_task_execution_time: "06:00"
  
  # Auto-execute tasks switch (default: false for safety)
  # When enabled: tasks with needs_confirmation=false will be executed automatically
  # When disabled: all tasks require user confirmation
  auto_execute_enabled: false

# Auto Update Configuration
# Configure background auto-update handled by the proactive daemon
auto_update:
  # Enable silent background update checks and installation
  enabled: true

  # Check interval in minutes
  check_interval_minutes: 30

  # Release channel: prod / beta / test
  channel: "prod"

# Code Agent Configuration
# Configure the code generation agent behavior
# code_agent:
#   # Maximum number of turns for the code agent (default: 1000)
#   # max_turns: 1000

# Goal Configuration
# Configure automatic retry limits for /goal verification
# goal:
#   # Maximum consecutive failed verifications before a goal is blocked (default: 6)
#   max_turns: 6

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

# Task completion notification (default: true)
# Shows a system notification when the agent finishes a long-running task (>90s)
# Set to false to disable all notification logic
# enable_notification: true

# Memory Configuration — Master Switch + Sub-layer Tuning
#
# ``enabled`` is the single master switch for ALL memory features:
#   - memory tools exposed to the agent (search_memory, memory write,
#     fact_store, fact_feedback)
#   - memory-related system prompt sections (inline MEMORY/USER blocks,
#     session-search guidance, holographic fact guidance)
#   - background memory-update pipeline (session markdown save +
#     review-agent that writes MEMORY.md / USER.md)
#   - holographic structured fact memory (overrides holographic.enabled
#     when the master switch is OFF)
#
# Set ``enabled: false`` to silence the entire memory subsystem.
# Sub-flags below are only effective when ``enabled: true``.
#
# Holographic structured fact memory is a sub-system of memory,
# configured under memory.holographic.
# memory:
#   enabled: true
#   user_profile_enabled: true
#   memory_facts_enabled: true
#   memory_char_limit: 2200
#   user_char_limit: 1375
#   holographic:
#     enabled: true                   # default ON — set false to disable
#     hrr_enabled: true               # set false to disable HRR even when numpy is available
#     hrr_dim: 1024                   # phase vector length; raise to 4096 for 4x per-bank capacity
#     default_trust: 0.5              # initial trust score for newly added facts
#     min_trust_threshold: 0.3        # facts below this don't appear in default prefetch/search
#     temporal_decay_half_life: 0     # 0=disable; e.g. 90 = halve relevance every 90 days
#     prefetch_limit: 5               # top-N facts injected into each user message
#     custom_dict:                    # extra jieba terms (project / tool names)
#       - chehejia
#       - authli

# Web Tools Configuration (web_search / web_fetch)
#
# Tri-state master switch for the web search tools exposed to the agent:
#   - null / unset ("auto", default): web tools are ON.
#   - true:  always enable web tools regardless of provider.
#   - false: always disable web tools regardless of provider.
# web:
#   enabled: null

# Sub-Agent Configuration (run_subtask)
#
# ``enabled`` is the master switch for the whole sub-agent feature, default ON:
#   - true (default): the main agent gets the `run_subtask` tool plus the
#     matching system-prompt guidance, so it can delegate self-contained work
#     to a sub-agent running in a clean context window.
#   - false: `run_subtask` is left out of the tool list and its prompt
#     guidance is dropped — every task is worked inline in the main agent's
#     own context. Recursive nesting is disabled as well, since it is an
#     extension of this feature.
#
# Master switch for recursive sub-agent nesting, default OFF (unchanged —
# a sub-agent can never spawn another sub-agent). When set to true:
#   - A sub-agent (depth 1, launched by the main agent) may itself call
#     run_subtask to launch a "sub-sub-agent" (depth 2).
#   - A sub-sub-agent (depth 2) cannot spawn further nested agents — the
#     nesting depth is hard-capped at 2 levels.
#   - The total number of simultaneously alive agents (main agent + all its
#     sub-agents + sub-sub-agents) is capped at 12; a run_subtask call that
#     would exceed this cap is rejected with an explanation instead of
#     silently queuing or crashing.
# sub_agent:
#   enabled: true
#   allow_recursive_subagents: false

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
#   #   server_url: "wss://relay.example.com/ws/relay"
#   #   heartbeat_interval: 10
#   #   reconnect_backoff: [3, 5, 10, 30, 60]
"""


def _create_default_config_file(config_path: Path) -> None:
    """Create default configuration file with comments"""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(_DEFAULT_CONFIG_TEMPLATE)


def _ensure_config_up_to_date(config_path: Path) -> None:
    """Append any template sections that are missing from the existing config file.

    Checks by top-level key (both active `key:` and commented `# key:` forms).
    Only appends; never modifies existing content.
    """
    try:
        existing_content = config_path.read_text(encoding='utf-8')
    except Exception:
        return

    # Matches top-level keys in the template: `key:` or `# key:` (exactly one space after #)
    top_key_re = re.compile(r'^(?:# )?([a-z][a-z0-9_]*):', re.MULTILINE)

    # Split template into paragraphs and map each top-level key to its paragraph
    paragraphs = re.split(r'\n{2,}', _DEFAULT_CONFIG_TEMPLATE.strip())
    key_to_paragraph: Dict[str, str] = {}
    for para in paragraphs:
        for m in top_key_re.finditer(para):
            key = m.group(1)
            if key not in key_to_paragraph:
                key_to_paragraph[key] = para

    # A key is "present" if it appears at line-start in the file (active or commented)
    def key_present(key: str) -> bool:
        escaped = re.escape(key)
        return bool(
            re.search(rf'^{escaped}\s*:', existing_content, re.MULTILINE)
            or re.search(rf'^# {escaped}\s*:', existing_content, re.MULTILINE)
        )

    missing_keys = [k for k in key_to_paragraph if not key_present(k)]
    if not missing_keys:
        return

    # Backup before modifying
    _backup_config_file(config_path)

    additions = [key_to_paragraph[k] for k in missing_keys]
    with open(config_path, 'a', encoding='utf-8') as f:
        f.write('\n\n' + '\n\n'.join(additions) + '\n')
    logger.info(f"conf.yaml: appended missing sections: {missing_keys}")


def _backup_config_file(config_path: Path, max_backups: int = 10) -> None:
    """Create a timestamped backup of config_path, keeping at most max_backups copies."""
    try:
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_path = config_path.with_name(f"{config_path.stem}-{timestamp}{config_path.suffix}")
        shutil.copy2(config_path, backup_path)

        # Remove oldest backups beyond the limit
        pattern = f"{config_path.stem}-*{config_path.suffix}"
        backups = sorted(config_path.parent.glob(pattern), key=lambda p: p.name)
        for old in backups[:-max_backups]:
            old.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"conf.yaml: backup failed: {e}")


@dataclass(frozen=True)
class HeadroomConfig:
    """Headroom proxy integration configuration (from conf.yaml `headroom`).

    NOTE: upstream URLs are intentionally NOT part of this config — they are
    hard-coded in siada.internal.services.headroom_proxy_manager and cannot be
    overridden by the user.
    """
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8787
    budget: Optional[float] = None
    budget_period: str = "daily"
    telemetry: bool = False
    startup_timeout: float = 30.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HeadroomConfig':
        if not isinstance(data, dict):
            return cls()
        enabled_val = data.get('enabled', False)
        enabled = bool(enabled_val) if enabled_val is not None else False
        port_val = data.get('port', 8787)
        port = int(port_val) if port_val is not None else 8787
        budget_val = data.get('budget')
        budget = float(budget_val) if budget_val is not None else None
        telemetry_val = data.get('telemetry', False)
        telemetry = bool(telemetry_val) if telemetry_val is not None else False
        timeout_val = data.get('startup_timeout', 30.0)
        startup_timeout = float(timeout_val) if timeout_val is not None else 30.0

        return cls(
            enabled=enabled,
            host=data.get('host', '127.0.0.1'),
            port=port,
            budget=budget,
            budget_period=data.get('budget_period', 'daily'),
            telemetry=telemetry,
            startup_timeout=startup_timeout,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Config:
    """Main configuration class (immutable)"""
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    checkpoint_config: CheckpointConfig = field(default_factory=CheckpointConfig)
    mcp_config: MCPConfig = field(default_factory=MCPConfig)
    model_config: Optional[ModelCollectionConfig] = None
    command_timeout: Optional[int] = None
    proactive_config: ProactiveConfig = field(default_factory=ProactiveConfig)
    auto_update_config: AutoUpdateConfig = field(default_factory=AutoUpdateConfig)
    code_agent_config: CodeAgentConfig = field(default_factory=CodeAgentConfig)
    goal_config: GoalConfig = field(default_factory=GoalConfig)
    pre_plan: Optional[bool] = None
    preferred_language: Optional[str] = None
    compaction_strategy: Optional[str] = None
    enable_notification: bool = True
    lark_config: Optional[Dict[str, Any]] = None
    memory_config: MemoryConfig = field(default_factory=MemoryConfig)
    holographic_config: HolographicConfig = field(default_factory=HolographicConfig)
    sub_agent_config: SubAgentConfig = field(default_factory=SubAgentConfig)
    web_config: WebConfig = field(default_factory=WebConfig)
    headroom_config: HeadroomConfig = field(default_factory=HeadroomConfig)


def _load_lark_config(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract lark config from raw conf.yaml data.

    Relay defaults are merged lazily in build_relay_config() at runtime.
    ``mode`` is optional here — callers default to "relay" when absent.

    Returns:
        Dict with structure {"lark": {...}}, or None if no valid lark config.
    """
    lark_section = data.get("lark")
    if not lark_section or not isinstance(lark_section, dict):
        return None

    # Wrap in {"lark": ...} for backward compatibility with callers.
    # Do NOT gate on mode presence: a lark section without an explicit mode
    # is valid and will default to "relay" in create_if_configured().
    # Requiring mode here silently drops access.idle_session_timeout and
    # other sub-keys that users configure alongside a default-relay setup.
    lark_config = {"lark": lark_section}
    mode = lark_section.get("mode", "relay")
    logger.info(f"Lark config loaded, mode={mode}")
    return lark_config


def load_conf(config_path: Optional[Path] = None) -> 'Config':
    """Load configuration from separated YAML and JSON files"""
    if config_path is None:
        config_path = _get_default_config_path()

    if not config_path.exists():
        _create_default_config_file(config_path)
    else:
        _ensure_config_up_to_date(config_path)

    llm_config = LLMConfig()
    checkpoint_config = CheckpointConfig()
    proactive_config = ProactiveConfig()
    auto_update_config = AutoUpdateConfig()
    code_agent_config = CodeAgentConfig()
    goal_config = GoalConfig()
    memory_config = MemoryConfig()
    holographic_config = HolographicConfig()
    sub_agent_config = SubAgentConfig()
    web_config = WebConfig()
    headroom_config = HeadroomConfig()
    lark_config: Optional[Dict[str, Any]] = None
    command_timeout: Optional[int] = None
    pre_plan: Optional[bool] = None
    preferred_language: Optional[str] = None
    compaction_strategy: Optional[str] = None
    enable_notification: bool = True

    from siada.config.conf_store import read_conf_dict

    def _notify_conf_error(message: str) -> None:
        try:
            io = InputOutput.get_instance()
            if io:
                io.print_error(f"Warning: {message}")
        except Exception:
            pass

    data = read_conf_dict(config_path, on_error=_notify_conf_error)
    if data:
        # A malformed *section* (e.g. llm_config: "not-a-mapping") must not
        # kill startup — report it and keep the defaults for that section.
        try:
            if 'llm_config' in data and data['llm_config'] is not None:
                llm_config = LLMConfig.from_dict(data['llm_config'])
                if llm_config.base_url is not None and llm_config.api_key is not None:
                    os.environ['BASE_URL'] = llm_config.base_url
                    os.environ['API_KEY'] = llm_config.api_key
            if 'checkpoint_config' in data and data['checkpoint_config'] is not None:
                checkpoint_config = CheckpointConfig.from_dict(data['checkpoint_config'])
            if 'proactive' in data and data['proactive'] is not None:
                proactive_config = ProactiveConfig.from_dict(data['proactive'])
            if 'auto_update' in data and data['auto_update'] is not None:
                auto_update_config = AutoUpdateConfig.from_dict(data['auto_update'])
            if 'code_agent' in data and data['code_agent'] is not None:
                code_agent_config = CodeAgentConfig.from_dict(data['code_agent'])
            if 'goal' in data and data['goal'] is not None:
                goal_config = GoalConfig.from_dict(data['goal'])
            if 'memory' in data and data['memory'] is not None:
                memory_config = MemoryConfig.from_dict(data['memory'])
                # Holographic is a sub-section of memory: memory.holographic
                holo_data = data['memory'].get('holographic') if isinstance(data['memory'], dict) else None
                if holo_data is not None:
                    holographic_config = HolographicConfig.from_dict(holo_data)
            if 'sub_agent' in data and data['sub_agent'] is not None:
                sub_agent_config = SubAgentConfig.from_dict(data['sub_agent'])
            if 'web' in data and data['web'] is not None:
                web_config = WebConfig.from_dict(data['web'])
            if 'headroom' in data and data['headroom'] is not None:
                headroom_config = HeadroomConfig.from_dict(data['headroom'])
            # Load lark IM config
            lark_config = _load_lark_config(data)
            command_timeout = data.get('command_timeout')
            pre_plan = data.get('pre_plan')
            preferred_language = data.get('preferred_language')
            compaction_strategy = data.get('compaction_strategy')
            enable_notification = data.get('enable_notification', True)
        except Exception as e:
            _notify_conf_error(f"Failed to parse a conf.yaml section: {e}")

    mcp_config = MCPConfigLoader.load_config()
    model_config = load_user_model_config()

    return Config(
        llm_config=llm_config,
        checkpoint_config=checkpoint_config,
        mcp_config=mcp_config,
        model_config=model_config,
        command_timeout=command_timeout,
        proactive_config=proactive_config,
        auto_update_config=auto_update_config,
        code_agent_config=code_agent_config,
        goal_config=goal_config,
        pre_plan=pre_plan,
        preferred_language=preferred_language,
        compaction_strategy=compaction_strategy,
        enable_notification=enable_notification,
        lark_config=lark_config,
        memory_config=memory_config,
        holographic_config=holographic_config,
        sub_agent_config=sub_agent_config,
        web_config=web_config,
        headroom_config=headroom_config,
    )


def save_conf_field(key: str, value, config_path: Optional[Path] = None) -> bool:
    """Update a single field in conf.yaml, preserving comments and formatting.

    key supports dotted notation for nested fields, e.g. 'llm_config.model'.
    """
    from siada.config.conf_store import save_conf_fields

    if not save_conf_fields({key: value}, config_path):
        print(f"Warning: Failed to save conf.yaml field '{key}'")
        return False
    return True

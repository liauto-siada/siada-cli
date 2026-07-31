from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class MCPServerConfig:
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> MCPServerConfig:
        return cls(
            command=data.get("command"),
            args=data.get("args") or [],
            env=data.get("env") or {},
            url=data.get("url"),
        )


@dataclass
class HookEntry:
    command: str
    matcher: str | None = None
    async_: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> HookEntry:
        # Claude Code format: {"type": "command", "command": "..."} — same as siada
        return cls(
            command=data["command"],
            matcher=data.get("matcher"),
            async_=bool(data.get("async", False)),
        )


@dataclass
class HookResponse:
    """Parsed response from a hook command's stdout JSON."""

    continue_: bool = True
    stop_reason: str = ""
    decision: str | None = None  # "block" to reject the tool call
    reason: str | None = None  # human-readable reason for block
    updated_input: str | None = None  # JSON string to replace tool arguments
    updated_output: str | None = None  # string to replace tool output
    additional_context: str | None = None  # text injected into next LLM call

    @classmethod
    def from_dict(cls, data: dict) -> HookResponse:
        return cls(
            continue_=data.get("continue", True),
            stop_reason=data.get("stopReason", ""),
            decision=data.get("decision"),
            reason=data.get("reason"),
            updated_input=data.get("updatedInput"),
            updated_output=data.get("updatedOutput"),
            # "additionalContext" is siada's native field; "systemMessage" is
            # the Claude Code / hookify convention — treat it as additional context
            # so warn-action messages are injected into the next LLM call.
            additional_context=data.get("additionalContext") or data.get("systemMessage") or None,
        )

    @classmethod
    def default(cls) -> HookResponse:
        return cls()


_HOOK_EVENTS = ("PreTurn", "PostTurn", "PreToolUse", "PostToolUse", "OnError", "Stop", "UserPromptSubmit", "SessionStart", "SessionEnd")


@dataclass
class HooksConfig:
    PreTurn: list[HookEntry] = field(default_factory=list)
    PostTurn: list[HookEntry] = field(default_factory=list)
    PreToolUse: list[HookEntry] = field(default_factory=list)
    PostToolUse: list[HookEntry] = field(default_factory=list)
    OnError: list[HookEntry] = field(default_factory=list)
    Stop: list[HookEntry] = field(default_factory=list)
    UserPromptSubmit: list[HookEntry] = field(default_factory=list)
    SessionStart: list[HookEntry] = field(default_factory=list)
    SessionEnd: list[HookEntry] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> HooksConfig:
        # Support both siada flat format and Claude Code nested format:
        #   Claude Code: {"hooks": {"PreToolUse": [{"hooks": [{"type":"command","command":"..."}]}]}}
        #   Siada flat:  {"PreToolUse": [{"command": "..."}]}
        root = data.get("hooks", data) if isinstance(data, dict) else data
        cfg = cls()
        for event in _HOOK_EVENTS:
            entries = root.get(event, [])
            hook_list: list[HookEntry] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                # Claude Code wraps commands in a nested "hooks" list
                nested = entry.get("hooks")
                if isinstance(nested, list):
                    for ne in nested:
                        if isinstance(ne, dict) and ne.get("command"):
                            hook_list.append(HookEntry.from_dict(ne))
                elif entry.get("command"):
                    hook_list.append(HookEntry.from_dict(entry))
            setattr(cfg, event, hook_list)
        return cfg


@dataclass
class PluginManifest:
    name: str
    description: str = ""
    version: str | None = None
    skills: str = "skills/"
    hooks: str = "hooks/hooks.json"
    mcp_servers: dict[str, MCPServerConfig] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            raise ValueError("Plugin name is required")
        if " " in self.name:
            raise ValueError("Plugin name cannot contain spaces")


@dataclass
class LoadedPlugin:
    name: str
    manifest: PluginManifest
    path: str
    source: str
    enabled: bool = True
    is_builtin: bool = False
    sha: str | None = None
    hooks_config: HooksConfig | None = None


@dataclass
class BuiltinPluginDefinition:
    name: str
    description: str
    version: str | None = None
    skills: list = field(default_factory=list)
    hooks: HooksConfig | None = None
    mcp_servers: dict[str, MCPServerConfig] = field(default_factory=dict)
    default_enabled: bool = True
    is_available: Callable[[], bool] | None = None


def parse_plugin_manifest(data: dict, plugin_dir=None) -> PluginManifest:
    """Parse a plugin.json dict into a PluginManifest. Raises ValueError on invalid input.

    Args:
        data: Parsed plugin.json content.
        plugin_dir: Optional path to the plugin root directory, used to resolve
            file-reference fields like ``"mcpServers": "./.mcp.json"``.
    """
    import json as _json
    from pathlib import Path as _Path

    name = data.get("name", "")
    if not name:
        raise ValueError("Plugin manifest missing required 'name' field")

    mcp_servers_raw = data.get("mcpServers")
    if plugin_dir is not None:
        root = _Path(plugin_dir)
        if isinstance(mcp_servers_raw, str) and mcp_servers_raw:
            # Resolve string path reference relative to plugin root, e.g. "./.mcp.json"
            ref_path = root / mcp_servers_raw
            try:
                raw = _json.loads(ref_path.read_text(encoding="utf-8"))
                # File may be flat {server: config} or wrapped under "mcpServers" key
                mcp_servers_raw = raw.get("mcpServers", raw) if isinstance(raw, dict) else {}
            except Exception:
                mcp_servers_raw = {}
        elif mcp_servers_raw is None:
            # Auto-discover .mcp.json at plugin root (lowest priority, no mcpServers declared)
            auto_path = root / ".mcp.json"
            try:
                raw = _json.loads(auto_path.read_text(encoding="utf-8"))
                mcp_servers_raw = raw.get("mcpServers", raw) if isinstance(raw, dict) else None
            except Exception:
                pass
    mcp_servers: dict[str, MCPServerConfig] = {}
    if isinstance(mcp_servers_raw, dict):
        for server_name, server_data in mcp_servers_raw.items():
            if isinstance(server_data, dict):
                mcp_servers[server_name] = MCPServerConfig.from_dict(server_data)

    return PluginManifest(
        name=name,
        description=data.get("description", ""),
        version=data.get("version"),
        skills=data.get("skills", "skills/"),
        hooks=data.get("hooks", "hooks/hooks.json"),
        mcp_servers=mcp_servers,
    )

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemPromptContext:
    cwd: str
    os_name: str
    home_dir: str
    capabilities: str
    interactive_mode: bool
    username: str | None = None
    preferred_language: str | None = None
    skills_section: str | None = None
    agents_section: str | None = None
    user_memory: str | None = None
    agent_name: str | None = None
    subagent_enabled: bool = True
    available_tool_names: frozenset[str] | None = None

"""
siada/services/agents/models.py
User-defined agent data model definitions.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Union

# An MCP server entry in an agent definition: either the name of a server
# already configured in the user's MCP config, or an inline
# ``{server_name: {command|url: ...}}`` mapping.
McpServerSpec = Union[str, dict]


class AgentScope(IntEnum):
    """Agent definition scope.

    Lower value means higher priority, used for deduplication when two
    definitions share a name.
    """

    USER = 0  # User level: ~/.siada-cli/agents/, ~/.agents/agents/, ~/.claude/agents/
    REPO = 1  # Repository level: <project>/.siada-cli/agents/ and compatibility layouts


@dataclass
class UserAgentDefinition:
    """A single user-defined agent parsed from an ``agents/*.md`` file.

    ``prompt`` holds the Markdown body, which becomes the sub-agent's system
    prompt. Every other attribute maps 1:1 onto a frontmatter field; fields
    left out of the file keep the defaults below and are treated as "not
    configured" by the runtime.
    """

    name: str
    description: str
    prompt: str
    path: Path
    scope: AgentScope
    # Tool names to restrict the sub-agent to; None means "default tool set",
    # ["*"] means "every tool in the default set".
    tools: list[str] | None = None
    # Skill names whose SKILL.md content is preloaded into the sub-agent prompt.
    skills: list[str] = field(default_factory=list)
    # MCP servers (by name or inline definition) attached to the sub-agent run.
    mcp_servers: list[McpServerSpec] = field(default_factory=list)
    # When True the agent always runs as a background task when spawned.
    background: bool = False
    # Reasoning effort level override for the agent's runs.
    effort: str | None = None
    # Model override for the agent's runs. None means "not configured": the run
    # keeps the conf.yaml sub-agent model or, when that is not set either, the
    # parent session's model.
    model: str | None = None

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        if isinstance(other, UserAgentDefinition):
            return self.name == other.name
        return False


@dataclass
class AgentDefinitionError:
    """A definition file that failed to load."""

    path: Path
    message: str
    scope: AgentScope


@dataclass
class AgentLoadOutcome:
    """Result of loading agent definitions from a set of roots."""

    agents: list[UserAgentDefinition] = field(default_factory=list)
    errors: list[AgentDefinitionError] = field(default_factory=list)

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def get(self, name: str) -> UserAgentDefinition | None:
        """Look up a definition by name (case-insensitive)."""
        for agent in self.agents:
            if agent.name.lower() == name.lower():
                return agent
        return None

    def merge(self, other: "AgentLoadOutcome") -> "AgentLoadOutcome":
        return AgentLoadOutcome(
            agents=self.agents + other.agents,
            errors=self.errors + other.errors,
        )


class AgentDefinitionParseError(Exception):
    """Raised when an agent definition file cannot be parsed."""

    def __init__(self, path: Path, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

"""
siada/services/agents/renderer.py
Render the user-defined agent catalog into the main agent's system prompt.
"""

import logging

from .models import UserAgentDefinition

logger = logging.getLogger(__name__)

# Character budget for the rendered catalog. Descriptions are already capped at
# parse time (config.MAX_DESCRIPTION_LENGTH); this bounds the whole section so a
# workspace with many definitions cannot crowd out the rest of the prompt.
MAX_AGENTS_SECTION_CHARS = 4_000

AGENTS_INTRO = (
    "The following user-defined agents can be launched with the `run_subtask` "
    "tool by passing `agent: \"<name>\"`. Each entry lists the agent's name and "
    "when to use it; the agent's own configuration (tools, skills, MCP servers, "
    "effort) is applied automatically."
)


def render_agents_section(agents: list[UserAgentDefinition]) -> str | None:
    """Render the agent catalog section, or None when there is nothing to show."""
    if not agents:
        return None

    lines: list[str] = []
    used = 0
    for agent in sorted(agents, key=lambda a: a.name.lower()):
        description = " ".join(agent.description.split())
        entry = f"- `{agent.name}` — {description}"
        if used + len(entry) > MAX_AGENTS_SECTION_CHARS:
            lines.append(
                f"- ... {len(agents) - len(lines)} more agent(s) omitted "
                "(see the `agents` directories for the full list)"
            )
            break
        lines.append(entry)
        used += len(entry)

    return (
        "AGENT TYPES\n\n"
        f"{AGENTS_INTRO}\n\n"
        "Available agents (name — description):\n"
        + "\n".join(lines)
        + "\n"
    )

"""
siada/services/skills/models.py
Skill data model definitions
"""

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path


class SkillScope(IntEnum):
    """
    Skill scope enumeration
    Lower value means higher priority, used for deduplication when same-named skills exist
    """
    USER = 0      # User level: ~/.siada-cli/skills/
    REPO = 1      # Repository level: <project>/.siada-cli/skills/
    SYSTEM = 2    # System level: built-in skills


class SkillUsageProfile(IntEnum):
    """How the skills catalog explains skill usage to a model family."""

    # Keep the default at STRICT so existing model prompts remain unchanged.
    STRICT = 0
    # All GPT-6 variants use the judgement-first instructions derived from
    # Codex's Astra template. Astra remains an alias for callers that adopted
    # the original implementation name.
    GPT6 = 1
    ASTRA = GPT6


@dataclass
class SkillMetadata:
    """
    Skill metadata
    Only contains frontmatter information, not body content
    """
    name: str                                    # Skill unique name (required)
    description: str                             # Skill description for model trigger (required)
    path: Path                                   # Absolute path to SKILL.md file
    scope: SkillScope                            # Scope it belongs to
    # ``metadata.short-description`` is optional in the SKILL.md format.
    # Keep it on the loaded object for callers that used the older skills
    # service API, while the prompt catalog continues to use ``description``
    # as its model-facing trigger text.
    short_description: str | None = None
    
    def __hash__(self):
        return hash(self.name)
    
    def __eq__(self, other):
        if isinstance(other, SkillMetadata):
            return self.name == other.name
        return False


@dataclass
class SkillError:
    """Skill loading error information"""
    path: Path              # Path of the failed file
    message: str            # Error description
    scope: SkillScope       # Scope where error occurred


@dataclass
class SkillLoadOutcome:
    """
    Skill loading result
    Contains list of successfully loaded skills and errors during loading
    """
    skills: list[SkillMetadata] = field(default_factory=list)
    errors: list[SkillError] = field(default_factory=list)
    
    def has_errors(self) -> bool:
        """Check if there are loading errors"""
        return len(self.errors) > 0
    
    def merge(self, other: "SkillLoadOutcome") -> "SkillLoadOutcome":
        """Merge two loading results"""
        return SkillLoadOutcome(
            skills=self.skills + other.skills,
            errors=self.errors + other.errors,
        )


class SkillParseError(Exception):
    """Skill parsing exception"""
    def __init__(self, path: Path, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

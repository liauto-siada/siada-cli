"""
siada/services/skills/loader.py
Skill loader - responsible for directory discovery, file parsing, and field validation
"""

import re
import logging
from pathlib import Path
from typing import Optional, Generator

import yaml

from .models import (
    SkillScope,
    SkillMetadata,
    SkillError,
    SkillLoadOutcome,
    SkillParseError,
)
from .config import (
    SKILL_FILENAME,
    MAX_NAME_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    get_skill_roots,
)


logger = logging.getLogger(__name__)

# YAML frontmatter regex pattern
FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---",
    re.DOTALL | re.MULTILINE
)


def discover_skill_dirs(root: Path) -> Generator[Path, None, None]:
    """
    Recursively discover directories containing SKILL.md
    
    Args:
        root: Search root directory
    
    Yields:
        Paths of directories containing SKILL.md files
    """
    if not root.exists() or not root.is_dir():
        return
    
    try:
        for entry in root.iterdir():
            if entry.is_dir():
                skill_file = entry / SKILL_FILENAME
                if skill_file.exists() and skill_file.is_file():
                    yield entry
                # Recursively search subdirectories
                yield from discover_skill_dirs(entry)
    except PermissionError:
        logger.warning(f"Permission denied when scanning: {root}")


def parse_frontmatter(content: str) -> Optional[dict]:
    """
    Parse YAML frontmatter from Markdown file
    
    Args:
        content: File content
    
    Returns:
        Parsed frontmatter dict, or None if not present
    """
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return None
    
    try:
        return yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None


def validate_skill_metadata(
    frontmatter: dict,
    path: Path
) -> tuple[str, str]:
    """
    Validate skill frontmatter fields
    
    Args:
        frontmatter: Parsed frontmatter dict
        path: File path (for error messages)
    
    Returns:
        (name, description) tuple
    
    Raises:
        SkillParseError: Field validation failed
    """
    name = frontmatter.get("name")
    description = frontmatter.get("description")
    
    # Required field check
    if not name:
        raise SkillParseError(path, "Missing required field: name")
    if not description:
        raise SkillParseError(path, "Missing required field: description")
    
    # Type check
    if not isinstance(name, str):
        raise SkillParseError(path, "Field 'name' must be a string")
    if not isinstance(description, str):
        raise SkillParseError(path, "Field 'description' must be a string")
    
    # Length check
    if len(name) > MAX_NAME_LENGTH:
        raise SkillParseError(
            path, 
            f"Field 'name' exceeds max length ({len(name)} > {MAX_NAME_LENGTH})"
        )
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise SkillParseError(
            path,
            f"Field 'description' exceeds max length ({len(description)} > {MAX_DESCRIPTION_LENGTH})"
        )
    
    return name, description


def parse_skill_file(
    skill_dir: Path,
    scope: SkillScope
) -> SkillMetadata:
    """
    Parse SKILL.md file from skill directory
    
    Args:
        skill_dir: Skill directory path
        scope: Scope it belongs to
    
    Returns:
        Parsed SkillMetadata
    
    Raises:
        SkillParseError: Parse or validation failed
    """
    skill_file = skill_dir / SKILL_FILENAME
    
    if not skill_file.exists():
        raise SkillParseError(skill_file, "SKILL.md file not found")
    
    try:
        content = skill_file.read_text(encoding="utf-8")
    except Exception as e:
        raise SkillParseError(skill_file, f"Failed to read file: {e}")
    
    frontmatter = parse_frontmatter(content)
    if frontmatter is None:
        raise SkillParseError(
            skill_file,
            "Missing or invalid YAML frontmatter (must start with '---')"
        )
    
    name, description = validate_skill_metadata(frontmatter, skill_file)
    
    return SkillMetadata(
        name=name,
        description=description,
        path=skill_file.resolve(),
        scope=scope,
    )


def load_skills_from_root(
    root: Path,
    scope: SkillScope
) -> SkillLoadOutcome:
    """
    Load all skills from a single root directory
    
    Args:
        root: Skill root directory
        scope: Scope
    
    Returns:
        Loading result
    """
    skills: list[SkillMetadata] = []
    errors: list[SkillError] = []
    
    for skill_dir in discover_skill_dirs(root):
        try:
            skill = parse_skill_file(skill_dir, scope)
            skills.append(skill)
            logger.debug(f"Loaded skill: {skill.name} from {skill.path}")
        except SkillParseError as e:
            errors.append(SkillError(
                path=e.path,
                message=e.message,
                scope=scope,
            ))
            logger.warning(f"Failed to load skill: {e}")
    
    return SkillLoadOutcome(skills=skills, errors=errors)


def load_skills_from_roots(
    roots: dict[SkillScope, Path]
) -> SkillLoadOutcome:
    """
    Load skills from multiple root directories with priority-based deduplication
    
    Args:
        roots: Mapping of scope to path
    
    Returns:
        Merged loading result (same-named skills keep higher priority version)
    """
    all_skills: dict[str, SkillMetadata] = {}
    all_errors: list[SkillError] = []
    
    # Load in priority order (lower value = higher priority)
    for scope in sorted(roots.keys()):
        root = roots[scope]
        outcome = load_skills_from_root(root, scope)
        
        for skill in outcome.skills:
            # Only add if same-named skill doesn't exist (keep higher priority)
            if skill.name not in all_skills:
                all_skills[skill.name] = skill
            else:
                logger.debug(
                    f"Skill '{skill.name}' shadowed by higher priority "
                    f"scope: {all_skills[skill.name].scope.name}"
                )
        
        all_errors.extend(outcome.errors)
    
    return SkillLoadOutcome(
        skills=list(all_skills.values()),
        errors=all_errors,
    )

"""
siada/services/skills/loader.py
Skill loader - responsible for directory discovery, file parsing, and field validation
"""

import re
import logging
from pathlib import Path
from typing import Callable, Optional, Generator

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
    roots: dict[SkillScope, "Path | list[Path]"],
    scope_resolver: Optional[Callable[[SkillMetadata], SkillScope]] = None,
) -> SkillLoadOutcome:
    """
    Load skills from multiple root directories with priority-based deduplication.

    Each scope value may be either:
      - a single ``Path`` (legacy form), or
      - a ``list[Path]`` of compatibility roots scanned in order. Within a single
        scope, later entries override earlier ones for the same skill name
        (last-write-wins). This is how the canonical ``.siada-cli/skills``
        layout takes precedence over the compatibility ``.agents/skills`` layout
        at the same level.

    Across scopes, the lower-numbered ``SkillScope`` wins (USER > REPO > SYSTEM).

    Args:
        roots: Mapping of scope to a path or an ordered list of paths.
        scope_resolver: Optional callback that, given a freshly-loaded
            ``SkillMetadata``, returns the final scope it should be tagged
            with. Invoked **before** dedup, so the resolver's decision
            participates in cross-scope priority. Use this hook when a
            single root path can host skills that conceptually belong to
            different scopes (e.g. ``~/.siada-cli/skills/`` holds both
            package-seeded skills tagged ``SYSTEM`` and user-created skills
            tagged ``USER``). Returning the input skill's existing scope
            preserves the path-derived default.

    Returns:
        Merged loading result (same-named skills keep higher priority version).
    """
    all_skills: dict[str, SkillMetadata] = {}
    all_errors: list[SkillError] = []

    # Pre-load every (scope, root) into intermediate buckets so the resolver
    # can re-tag scopes BEFORE we apply cross-scope dedup. This way a skill
    # reclassified from USER → SYSTEM still loses to a same-named REPO skill
    # (REPO=1 < SYSTEM=2 in priority value).
    flat_skills: list[SkillMetadata] = []
    for scope in sorted(roots.keys()):
        scope_paths = roots[scope]
        if isinstance(scope_paths, (list, tuple)):
            ordered_paths = list(scope_paths)
        else:
            ordered_paths = [scope_paths]

        # Per-scope view: later entries within the same scope override earlier ones
        # so the canonical layout (loaded last) shadows the compatibility layout.
        scope_skills: dict[str, SkillMetadata] = {}
        for root in ordered_paths:
            outcome = load_skills_from_root(root, scope)
            for skill in outcome.skills:
                if skill.name in scope_skills:
                    logger.debug(
                        f"Skill '{skill.name}' overridden within scope "
                        f"{scope.name} by later root: {root}"
                    )
                scope_skills[skill.name] = skill
            all_errors.extend(outcome.errors)
        flat_skills.extend(scope_skills.values())

    # Apply scope resolver (e.g. manifest-aware SYSTEM/USER reclassification).
    if scope_resolver is not None:
        for skill in flat_skills:
            try:
                new_scope = scope_resolver(skill)
                if new_scope is not None and new_scope != skill.scope:
                    skill.scope = new_scope
            except Exception as e:
                logger.debug(f"scope_resolver failed for '{skill.name}': {e}")

    # Cross-scope dedup using (possibly resolver-adjusted) scope priorities.
    # Sort by scope value ascending so the highest-priority survivor wins.
    flat_skills.sort(key=lambda s: s.scope.value)
    for skill in flat_skills:
        if skill.name not in all_skills:
            all_skills[skill.name] = skill
        else:
            logger.debug(
                f"Skill '{skill.name}' shadowed by higher priority "
                f"scope: {all_skills[skill.name].scope.name}"
            )

    return SkillLoadOutcome(
        skills=list(all_skills.values()),
        errors=all_errors,
    )


"""
External Agent Configuration Migration

Detects and imports configuration, skills, and context files from Claude Code
and Codex into Siada, following the same two-phase (detect → import) pattern
used by Codex's external_agent_config.rs.

Two-phase flow
--------------
1. detect(include_home, cwds)  – scan only, return List[MigrationItem], no writes.
2. import_items(items)         – execute the actual file copies / merges.

The caller (CLI or TUI) can present the detected list to the user for
confirmation before invoking import_items.

Scope
-----
- Home  : ~/.claude/  and ~/.codex/   →  ~/.siada-cli/
- Repo  : <repo>/.claude/  and <repo>/.agents/  →  <repo>/.siada-cli/  (or repo root)
"""

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from siada.foundation.constants import SIADA_HOME

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class ExternalAgentSource(Enum):
    CLAUDE = "claude"
    CODEX = "codex"


class MigrationItemType(Enum):
    CONFIG = "config"
    SKILLS = "skills"
    SIADA_MD = "siada_md"


@dataclass
class MigrationItem:
    item_type: MigrationItemType
    source: ExternalAgentSource
    description: str
    cwd: Optional[Path] = field(default=None)  # None → home scope


# ---------------------------------------------------------------------------
# Terminology replacement
# ---------------------------------------------------------------------------
# Applied when copying SKILL.md files and context MD files (CLAUDE.md / AGENTS.md).
# Order matters: more-specific patterns first to avoid double-replacement.
_TERM_PATTERNS: List[Tuple[str, str]] = [
    (r"claude\.md", "SIADA.md"),
    (r"AGENTS\.md", "SIADA.md"),
    (r"claude[\s\-_]code", "Siada"),
    (r"claudecode", "Siada"),
    (r"codex", "Siada"),
    (r"claude", "Siada"),
]


def _rewrite_terms(content: str) -> str:
    """Replace external-agent terminology with Siada equivalents."""
    for pattern, replacement in _TERM_PATTERNS:
        content = re.sub(
            r"(?<![A-Za-z0-9_])" + pattern + r"(?![A-Za-z0-9_])",
            replacement,
            content,
            flags=re.IGNORECASE,
        )
    return content


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------


def _default_claude_home() -> Path:
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    return Path(home) / ".claude" if home else Path(".claude")


def _default_codex_home() -> Path:
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    return Path(home) / ".codex" if home else Path(".codex")


def _find_repo_root(cwd: Path) -> Optional[Path]:
    """Walk up from *cwd* to find the nearest .git directory."""
    current = cwd.resolve() if cwd.exists() else cwd
    if current.is_file():
        current = current.parent
    while True:
        git = current / ".git"
        if git.is_dir() or git.is_file():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    # No .git found – treat cwd itself as root
    return cwd.resolve() if cwd.exists() else None


def _is_non_empty(path: Path) -> bool:
    return path.is_file() and bool(path.read_text(encoding="utf-8").strip())


def _is_missing_or_empty(path: Path) -> bool:
    if not path.exists():
        return True
    return path.is_file() and not path.read_text(encoding="utf-8").strip()


def _find_claude_md_source(
    repo_root: Optional[Path], claude_home: Path
) -> Optional[Path]:
    """Return the first non-empty CLAUDE.md candidate."""
    if repo_root:
        candidates = [
            repo_root / "CLAUDE.md",
            repo_root / ".claude" / "CLAUDE.md",
        ]
    else:
        candidates = [claude_home / "CLAUDE.md"]
    for p in candidates:
        if _is_non_empty(p):
            return p
    return None


def _count_missing_subdirs(source: Path, target: Path) -> int:
    """Count subdirs in *source* that do not yet exist in *target*."""
    if not source.is_dir():
        return 0
    existing = {e.name for e in target.iterdir()} if target.is_dir() else set()
    return sum(
        1 for e in source.iterdir() if e.is_dir() and e.name not in existing
    )


# ---------------------------------------------------------------------------
# Config conversion helpers
# ---------------------------------------------------------------------------


def _build_yaml_from_claude_settings(path: Path) -> Optional[Dict]:
    """Extract siada-compatible fields from Claude Code settings.json.

    Currently maps:
      env.ANTHROPIC_API_KEY   → llm_config.api_key
      env.ANTHROPIC_BASE_URL  → llm_config.base_url
    """
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    env = data.get("env", {})
    if not isinstance(env, dict):
        return None

    llm: Dict = {}
    if "ANTHROPIC_API_KEY" in env:
        llm["api_key"] = env["ANTHROPIC_API_KEY"]
    if "ANTHROPIC_BASE_URL" in env:
        llm["base_url"] = env["ANTHROPIC_BASE_URL"]

    return {"llm_config": llm} if llm else None


def _build_yaml_from_codex_config(path: Path) -> Optional[Dict]:
    """Extract siada-compatible fields from Codex config.toml.

    Currently maps:
      model → llm_config.model
    """
    if not path.is_file():
        return None
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None

    if isinstance(data.get("model"), str):
        return {"llm_config": {"model": data["model"]}}
    return None


# ---------------------------------------------------------------------------
# YAML merge helpers (idempotent)
# ---------------------------------------------------------------------------


def _dict_has_missing_keys(existing: Dict, incoming: Dict) -> bool:
    for key, value in incoming.items():
        if key not in existing:
            return True
        if isinstance(value, dict) and isinstance(existing.get(key), dict):
            if _dict_has_missing_keys(existing[key], value):
                return True
    return False


def _has_missing_yaml_keys(target: Path, incoming: Dict) -> bool:
    """Return True if *incoming* contains at least one key absent from *target*."""
    if not target.exists():
        return True
    try:
        existing = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except Exception:
        return True
    return _dict_has_missing_keys(existing, incoming)


def _merge_dict_missing(existing: Dict, incoming: Dict) -> bool:
    changed = False
    for key, value in incoming.items():
        if key not in existing:
            existing[key] = value
            changed = True
        elif isinstance(value, dict) and isinstance(existing.get(key), dict):
            if _merge_dict_missing(existing[key], value):
                changed = True
    return changed


def _merge_yaml_missing(target: Path, incoming: Dict) -> None:
    """Merge *incoming* into *target* YAML, adding only missing keys."""
    if target.exists():
        try:
            existing = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        except Exception:
            existing = {}
    else:
        existing = {}
    if _merge_dict_missing(existing, incoming):
        target.write_text(
            yaml.dump(existing, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# File copy helpers
# ---------------------------------------------------------------------------


def _rewrite_and_copy(source: Path, target: Path) -> None:
    """Copy *source* to *target*, rewriting agent terminology."""
    content = source.read_text(encoding="utf-8")
    target.write_text(_rewrite_terms(content), encoding="utf-8")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ExternalAgentMigrationService:
    """Detect and import external agent configs into siada format.

    Usage::

        svc = ExternalAgentMigrationService()
        items = svc.detect(include_home=True, cwds=[Path.cwd()])
        # … show items to user …
        svc.import_items(items)
    """

    def __init__(
        self,
        siada_home: Optional[Path] = None,
        claude_home: Optional[Path] = None,
        codex_home: Optional[Path] = None,
    ) -> None:
        self.siada_home = siada_home or SIADA_HOME
        self.claude_home = claude_home or _default_claude_home()
        self.codex_home = codex_home or _default_codex_home()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        include_home: bool = True,
        cwds: Optional[List[Path]] = None,
    ) -> List[MigrationItem]:
        """Scan for migratable items. Does *not* modify any files.

        Args:
            include_home: Whether to check the home-scope directories.
            cwds: Working directories to examine for repo-scope migration.

        Returns:
            List of detected MigrationItem instances.
        """
        items: List[MigrationItem] = []
        if include_home:
            self._detect_scope(None, items)
        for cwd in cwds or []:
            repo_root = _find_repo_root(Path(cwd))
            if repo_root:
                self._detect_scope(repo_root, items)
        return items

    def import_items(self, items: List[MigrationItem]) -> None:
        """Execute file operations for each MigrationItem in *items*."""
        for item in items:
            if item.item_type == MigrationItemType.CONFIG:
                self._import_config(item.source, item.cwd)
            elif item.item_type == MigrationItemType.SKILLS:
                self._import_skills(item.source, item.cwd)
            elif item.item_type == MigrationItemType.SIADA_MD:
                self._import_siada_md(item.source, item.cwd)

    # ------------------------------------------------------------------
    # Detect internals
    # ------------------------------------------------------------------

    def _detect_scope(
        self, repo_root: Optional[Path], items: List[MigrationItem]
    ) -> None:
        self._detect_claude(repo_root, items)
        self._detect_codex(repo_root, items)

    def _detect_claude(
        self, repo_root: Optional[Path], items: List[MigrationItem]
    ) -> None:
        cwd = repo_root

        # --- Config ---
        src_cfg = (
            repo_root / ".claude" / "settings.json"
            if repo_root
            else self.claude_home / "settings.json"
        )
        dst_cfg = (
            repo_root / ".siada-cli" / "conf.yaml"
            if repo_root
            else self.siada_home / "conf.yaml"
        )
        if src_cfg.is_file():
            migrated = _build_yaml_from_claude_settings(src_cfg)
            if migrated and _has_missing_yaml_keys(dst_cfg, migrated):
                items.append(
                    MigrationItem(
                        MigrationItemType.CONFIG,
                        ExternalAgentSource.CLAUDE,
                        f"Migrate {src_cfg} → {dst_cfg}",
                        cwd,
                    )
                )

        # --- Skills ---
        src_skills = (
            repo_root / ".claude" / "skills"
            if repo_root
            else self.claude_home / "skills"
        )
        dst_skills = (
            repo_root / ".siada-cli" / "skills"
            if repo_root
            else self.siada_home / "skills"
        )
        if _count_missing_subdirs(src_skills, dst_skills) > 0:
            items.append(
                MigrationItem(
                    MigrationItemType.SKILLS,
                    ExternalAgentSource.CLAUDE,
                    f"Link skills {src_skills} → {dst_skills}",
                    cwd,
                )
            )

        # --- CLAUDE.md → SIADA.md / siada_rule.md ---
        src_md = _find_claude_md_source(repo_root, self.claude_home)
        dst_md = (
            repo_root / "SIADA.md"
            if repo_root
            else self.siada_home / "siada_rule.md"
        )
        if src_md and _is_missing_or_empty(dst_md):
            items.append(
                MigrationItem(
                    MigrationItemType.SIADA_MD,
                    ExternalAgentSource.CLAUDE,
                    f"Import {src_md} → {dst_md}",
                    cwd,
                )
            )

    def _detect_codex(
        self, repo_root: Optional[Path], items: List[MigrationItem]
    ) -> None:
        cwd = repo_root

        # --- Config ---
        src_cfg = (
            repo_root / ".codex" / "config.toml"
            if repo_root
            else self.codex_home / "config.toml"
        )
        dst_cfg = (
            repo_root / ".siada-cli" / "conf.yaml"
            if repo_root
            else self.siada_home / "conf.yaml"
        )
        if src_cfg.is_file():
            migrated = _build_yaml_from_codex_config(src_cfg)
            if migrated and _has_missing_yaml_keys(dst_cfg, migrated):
                items.append(
                    MigrationItem(
                        MigrationItemType.CONFIG,
                        ExternalAgentSource.CODEX,
                        f"Migrate {src_cfg} → {dst_cfg}",
                        cwd,
                    )
                )

        # --- Skills ---
        src_skills = (
            repo_root / ".agents" / "skills"
            if repo_root
            else self.codex_home / "skills"
        )
        dst_skills = (
            repo_root / ".siada-cli" / "skills"
            if repo_root
            else self.siada_home / "skills"
        )
        if _count_missing_subdirs(src_skills, dst_skills) > 0:
            items.append(
                MigrationItem(
                    MigrationItemType.SKILLS,
                    ExternalAgentSource.CODEX,
                    f"Link skills {src_skills} → {dst_skills}",
                    cwd,
                )
            )

        # --- AGENTS.md (home scope only) → siada_rule.md ---
        # Repo-level AGENTS.md is already natively supported; no copy needed.
        if repo_root is None:
            src_md = self.codex_home / "AGENTS.md"
            dst_md = self.siada_home / "siada_rule.md"
            if _is_non_empty(src_md) and _is_missing_or_empty(dst_md):
                items.append(
                    MigrationItem(
                        MigrationItemType.SIADA_MD,
                        ExternalAgentSource.CODEX,
                        f"Import {src_md} → {dst_md}",
                        None,
                    )
                )

    # ------------------------------------------------------------------
    # Import internals
    # ------------------------------------------------------------------

    def _import_config(
        self, source: ExternalAgentSource, repo_root: Optional[Path]
    ) -> None:
        if source == ExternalAgentSource.CLAUDE:
            src = (
                repo_root / ".claude" / "settings.json"
                if repo_root
                else self.claude_home / "settings.json"
            )
            migrated = _build_yaml_from_claude_settings(src)
        else:
            src = (
                repo_root / ".codex" / "config.toml"
                if repo_root
                else self.codex_home / "config.toml"
            )
            migrated = _build_yaml_from_codex_config(src)

        if not migrated:
            return
        dst = (
            repo_root / ".siada-cli" / "conf.yaml"
            if repo_root
            else self.siada_home / "conf.yaml"
        )
        dst.parent.mkdir(parents=True, exist_ok=True)
        _merge_yaml_missing(dst, migrated)

    def _import_skills(
        self, source: ExternalAgentSource, repo_root: Optional[Path]
    ) -> None:
        if source == ExternalAgentSource.CLAUDE:
            src = (
                repo_root / ".claude" / "skills"
                if repo_root
                else self.claude_home / "skills"
            )
        else:
            src = (
                repo_root / ".agents" / "skills"
                if repo_root
                else self.codex_home / "skills"
            )
        dst = (
            repo_root / ".siada-cli" / "skills"
            if repo_root
            else self.siada_home / "skills"
        )
        if not src.is_dir():
            return
        dst.mkdir(parents=True, exist_ok=True)
        for entry in src.iterdir():
            if not entry.is_dir():
                continue
            dest = dst / entry.name
            if dest.exists() or dest.is_symlink():
                continue
            dest.symlink_to(entry.resolve())

    def _import_siada_md(
        self, source: ExternalAgentSource, repo_root: Optional[Path]
    ) -> None:
        if source == ExternalAgentSource.CLAUDE:
            src = _find_claude_md_source(repo_root, self.claude_home)
            dst = (
                repo_root / "SIADA.md"
                if repo_root
                else self.siada_home / "siada_rule.md"
            )
        else:
            if repo_root is not None:
                # Repo AGENTS.md is natively read; nothing to copy.
                return
            src = self.codex_home / "AGENTS.md"
            dst = self.siada_home / "siada_rule.md"

        if not src or not _is_non_empty(src) or not _is_missing_or_empty(dst):
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        _rewrite_and_copy(src, dst)

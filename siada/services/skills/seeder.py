"""
siada/services/skills/seeder.py
Sync built-in (SYSTEM) skills into the user skills directory.

Simplified semantics
--------------------
- Version-bump startup → **blindly overwrite** every package skill into the
  user dir, regardless of whether the user has modified or deleted it.
  Orphans (skills that were tracked in the previous manifest but no longer
  exist in the new package) are also blindly removed. The manifest is then
  rewritten with the new version and fresh hashes.

- Same-version startup → **never touch the skill files**. Only refresh the
  ``.system_seed.json`` snapshot so it accurately reflects the current
  state of the previously-seeded skills (drift caused by user edits or
  deletions is recorded silently). User-created skills that we never
  seeded ourselves stay completely outside the manifest.

Manifest layout (``<user_skills_dir>/.system_seed.json``)::

    {
      "version": "1.7.9",
      "skills": {"<name>": "<sha256-of-skill-dir>"}
    }

A flat legacy ``{name: hash}`` is parsed as ``version=""`` so the next
startup will treat it as a version change and re-seed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from .config import get_system_skills_root, get_user_skills_root
from .models import SkillMetadata, SkillScope


logger = logging.getLogger(__name__)

MANIFEST_FILENAME = ".system_seed.json"
_KEY_VERSION = "version"
_KEY_SKILLS = "skills"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _hash_dir(directory: Path) -> str:
    """Stable sha256 over (relative path + content) of every file in dir.
    Returns an empty string when the directory does not exist."""
    if not directory.is_dir():
        return ""
    h = hashlib.sha256()
    for p in sorted(directory.rglob("*")):
        if not p.is_file():
            continue
        h.update(p.relative_to(directory).as_posix().encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(p.read_bytes())
        except Exception as e:
            logger.debug(f"Skip unreadable file while hashing {p}: {e}")
        h.update(b"\n")
    return h.hexdigest()


def _load_manifest(path: Path) -> Tuple[str, Dict[str, str]]:
    """Return ``(version, {skill_name: hash})``. Empty version on
    missing / unreadable / legacy-flat manifests, which forces a re-seed."""
    if not path.is_file():
        return "", {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed to read seed manifest {path}: {e}")
        return "", {}
    if not isinstance(data, dict):
        return "", {}

    if _KEY_VERSION in data or _KEY_SKILLS in data:
        version = str(data.get(_KEY_VERSION, "") or "")
        raw = data.get(_KEY_SKILLS, {}) or {}
        if not isinstance(raw, dict):
            raw = {}
        return version, {str(k): str(v) for k, v in raw.items()}

    # Legacy flat schema
    return "", {str(k): str(v) for k, v in data.items()}


def _save_manifest(path: Path, version: str, skills: Dict[str, str]) -> None:
    """Atomically persist the seed manifest. Failures are logged."""
    payload = {_KEY_VERSION: version, _KEY_SKILLS: skills}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)
    except Exception as e:
        logger.warning(f"Failed to write seed manifest {path}: {e}")


def _current_siada_version() -> str:
    """Return ``siada.__version__`` or ``'dev'`` as a fallback."""
    try:
        from siada import __version__  # type: ignore
        return str(__version__) or "dev"
    except Exception:
        return "dev"


# ──────────────────────────────────────────────────────────────────────────────
# Sync primitives
# ──────────────────────────────────────────────────────────────────────────────

def _blind_overwrite(
    src_root: Path,
    dst_root: Path,
    last_skills: Dict[str, str],
) -> Dict[str, str]:
    """Blindly overwrite every skill from the package into the user dir,
    regardless of user modifications or deletions, and remove orphans that
    were tracked in the previous manifest but are no longer in the package.

    Returns the fresh ``{name: hash}`` snapshot to be written to manifest.
    """
    package_names: list[str] = sorted(
        d.name for d in src_root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    overwritten: list[str] = []
    for name in package_names:
        target = dst_root / name
        try:
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src_root / name, target)
            overwritten.append(name)
        except Exception as e:
            logger.warning(f"Failed to overwrite skill '{name}': {e}")

    # Blindly remove orphans tracked in previous manifest.
    removed: list[str] = []
    for name in last_skills:
        if name in package_names:
            continue
        target = dst_root / name
        if target.exists():
            try:
                shutil.rmtree(target)
                removed.append(name)
            except Exception as e:
                logger.warning(f"Failed to remove orphan skill '{name}': {e}")

    if overwritten or removed:
        logger.info(
            "Built-in skills overwrite: written=%d removed=%s",
            len(overwritten),
            removed or "[]",
        )

    return {name: _hash_dir(dst_root / name) for name in package_names}


def _refresh_tracked_state(
    dst_root: Path,
    last_skills: Dict[str, str],
) -> Dict[str, str]:
    """Same-version manifest refresh: drop entries for skills the user has
    deleted, but **keep the original seeded hash** for surviving entries.

    Why we don't recompute hashes here: the original snapshot is what lets
    a downstream consumer (e.g. the loader's scope_resolver) tell apart
    *unmodified* seeded skills (current_hash == manifest_hash → SYSTEM)
    from *user-modified* seeded skills (current_hash != manifest_hash →
    USER). If we updated the manifest to track the user's current content,
    the modification would become invisible after a single restart.

    User-created skills (never seeded by us) are intentionally left outside
    the manifest so a future version bump won't sweep them up as orphans.
    """
    new_skills: Dict[str, str] = {}
    for name, original_hash in last_skills.items():
        d = dst_root / name
        if d.is_dir():
            new_skills[name] = original_hash  # preserve baseline snapshot
        # else: user deleted it → drop from manifest
    return new_skills


# ──────────────────────────────────────────────────────────────────────────────
# Public entry
# ──────────────────────────────────────────────────────────────────────────────

def get_seeded_skill_hashes(siada_home: Path) -> Dict[str, str]:
    """Return the ``{name: sha256_at_seed_time}`` map recorded in the manifest
    for skills that we have seeded from the package.

    Callers (e.g. the loader's scope resolver) can compare each entry's hash
    with the current on-disk hash of the user-side skill dir to tell apart:
    - **unmodified** seeded skills (hashes match) → display as ``SYSTEM``
    - **user-modified** seeded skills (hashes differ) → display as ``USER``

    Returns an empty dict if no manifest exists yet.
    """
    dst_root = get_user_skills_root(siada_home)
    manifest_path = dst_root / MANIFEST_FILENAME
    _, last_skills = _load_manifest(manifest_path)
    return dict(last_skills)


def get_seeded_skill_names(siada_home: Path) -> set[str]:
    """Backwards-compatible wrapper returning just the names of seeded skills."""
    return set(get_seeded_skill_hashes(siada_home).keys())


def hash_skill_dir(directory: Path) -> str:
    """Public alias of :func:`_hash_dir` for callers that need to compute the
    same content fingerprint the manifest stores."""
    return _hash_dir(directory)


def build_seed_aware_scope_resolver(
    siada_home: Path,
) -> Callable[[SkillMetadata], SkillScope]:
    """Build a manifest-aware scope resolver to plug into
    :func:`load_skills_from_roots`.

    The resolver re-tags any USER-rooted skill that we previously seeded
    from the package, based on whether the user has modified it since:

      - name in manifest AND on-disk hash matches snapshot → ``SYSTEM``
        (package-seeded, untouched)
      - name in manifest BUT hash differs from snapshot     → ``USER``
        (user-modified — note: still blindly overwritten on the next
        siada-cli version bump; scope is purely a display label)
      - name NOT in manifest                                → unchanged
        (user-created or REPO-rooted skill, scope stays as the path
        already implies)

    The closure captures the manifest hashes once at build time so the
    loader can call the resolver per-skill cheaply. Manifest read errors
    degrade gracefully to "no seeded skills known", in which case every
    skill keeps its path-derived scope.
    """
    try:
        seeded_hashes = get_seeded_skill_hashes(siada_home)
    except Exception as e:
        logger.warning(f"Failed to read seed manifest hashes: {e}")
        seeded_hashes = {}

    def resolver(skill: SkillMetadata) -> SkillScope:
        if skill.scope != SkillScope.USER or skill.name not in seeded_hashes:
            return skill.scope
        try:
            current_hash = _hash_dir(skill.path.parent)
        except Exception:
            return SkillScope.USER
        return (
            SkillScope.SYSTEM
            if current_hash == seeded_hashes[skill.name]
            else SkillScope.USER
        )

    return resolver


def seed_if_version_changed(
    siada_home: Path,
    current_version: Optional[str] = None,
) -> bool:
    """Sync built-in skills.

    Behavior:
    - If the recorded version differs from the running version, blindly
      overwrite every package skill into the user dir, prune orphans, and
      rewrite the manifest with the new version and fresh hashes.
    - Otherwise leave the skill files alone and only refresh the manifest
      snapshot for previously-seeded skills (silent drift recording).

    Returns:
        True  – version-bump path executed (skills were overwritten).
        False – same-version path executed (no skill files touched).
    """
    version = current_version or _current_siada_version()

    try:
        src_root = get_system_skills_root()
    except Exception as e:
        logger.warning(f"Cannot resolve built-in skills root: {e}")
        return False

    dst_root = get_user_skills_root(siada_home)
    manifest_path = dst_root / MANIFEST_FILENAME

    last_version, last_skills = _load_manifest(manifest_path)

    try:
        dst_root.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Cannot create user skills dir {dst_root}: {e}")
        return False

    # ── Version unchanged: leave skills untouched, only refresh manifest. ──
    if last_version and last_version == version:
        try:
            new_state = _refresh_tracked_state(dst_root, last_skills)
            if new_state != last_skills:
                _save_manifest(manifest_path, version, new_state)
                logger.debug(
                    "Built-in skills manifest refreshed (no version change)"
                )
        except Exception as e:
            logger.debug(f"Manifest refresh skipped: {e}")
        return False

    # ── Version changed: blind overwrite. ─────────────────────────────────
    if not src_root.is_dir():
        logger.debug(f"No built-in skills dir found: {src_root}")
        return False

    logger.info(
        "siada-cli version changed (%s → %s); blindly overwriting built-in "
        "skills into %s",
        last_version or "<none>",
        version,
        dst_root,
    )
    new_skills = _blind_overwrite(src_root, dst_root, last_skills)
    _save_manifest(manifest_path, version, new_skills)
    return True

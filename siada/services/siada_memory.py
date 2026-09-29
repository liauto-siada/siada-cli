"""
Siada Memory Service

Handles loading and managing user memory content from SIADA.md / AGENTS.md / CLAUDE.md files.

Near-duplicate files (e.g. a CLAUDE.md whose content was copied into
SIADA.md) are skipped so duplicated instructions aren't injected twice.
"""

import difflib
import os
from typing import List, Optional, Tuple

# Context files recognised as workspace-level memory, in priority order.
# Entries may be plain filenames or relative paths (e.g. '.claude/CLAUDE.md').
# All non-empty files are loaded and combined.
WORKSPACE_MEMORY_FILES = [
    'SIADA.md',
    'AGENTS.md',
    'CLAUDE.md',
    os.path.join('.claude', 'CLAUDE.md'),
]

# Similarity ratio (0-1) at or above which a file is treated as a copy of
# an already-loaded, higher-priority file and skipped. Users often copy
# CLAUDE.md / AGENTS.md into SIADA.md; shipping both would double the
# prompt tokens for zero new information.
_NEAR_DUPLICATE_THRESHOLD = 0.9

# Per-text size up to which similarity is compared character-by-character.
# SequenceMatcher's cost grows ~quadratically with sequence length (a 60KB
# char-level diff takes seconds), while a line-level diff on the same
# content takes milliseconds and is just as reliable for copy detection.
# Small files still need the char-level view: a one-line tweak in a tiny
# file barely registers at line granularity.
_CHAR_COMPARE_LIMIT = 8_000


def _text_similarity(a: str, b: str) -> float:
    """Return the similarity ratio of two texts in [0, 1].

    Texts up to ``_CHAR_COMPARE_LIMIT`` are compared per character; larger
    texts per line (see the constant's comment). ``autojunk`` is disabled
    so the ratio reflects real content (with autojunk, characters as
    frequent as newlines are ignored in texts over 200 chars), and the
    ``real_quick_ratio`` / ``quick_ratio`` upper bounds let clearly-
    different texts bail before the expensive full pass.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) <= _CHAR_COMPARE_LIMIT and len(b) <= _CHAR_COMPARE_LIMIT:
        matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    else:
        matcher = difflib.SequenceMatcher(
            None, a.splitlines(), b.splitlines(), autojunk=False
        )
    if matcher.real_quick_ratio() < _NEAR_DUPLICATE_THRESHOLD:
        return 0.0
    if matcher.quick_ratio() < _NEAR_DUPLICATE_THRESHOLD:
        return 0.0
    return matcher.ratio()


def _find_near_duplicate(
    content: str, loaded: List[Tuple[str, str]]
) -> Optional[Tuple[str, float]]:
    """Return ``(label, similarity)`` of the first already-loaded file that
    is near-identical to ``content``, or ``None`` when it is original.
    """
    for label, body in loaded:
        similarity = _text_similarity(content, body)
        if similarity >= _NEAR_DUPLICATE_THRESHOLD:
            return label, similarity
    return None


def load_siada_memory(workspace: str) -> Optional[str]:
    """
    Load workspace memory from SIADA.md, AGENTS.md, and/or CLAUDE.md.

    All recognised files are first-class context sources. If multiple exist
    and are non-empty their contents are combined (SIADA.md first).
    CLAUDE.md is checked at both the project root and .claude/CLAUDE.md.

    Each file body is prefixed with a ``# <relative path>`` heading so the
    model can tell where one file ends and the next begins, instead of
    seeing a bare concatenation of markdown blobs.

    Near-duplicate guard: a file whose body is >=90% similar to any
    already-loaded, higher-priority file is skipped. This covers the
    common "copied CLAUDE.md / AGENTS.md into SIADA.md" setup. A skipped
    file still claims its basename, so .claude/CLAUDE.md stays shadowed
    when the root CLAUDE.md was dropped as a copy.

    Args:
        workspace: Path to the workspace directory

    Returns:
        Combined content if any file is non-empty, None otherwise
    """
    parts: List[str] = []
    loaded: List[Tuple[str, str]] = []   # (label, body) actually shipped — near-dup reference
    seen_name: set = set()   # deduplicate by basename (e.g. CLAUDE.md wins over .claude/CLAUDE.md)
    seen_real: set = set()   # deduplicate by resolved path (symlink guard)
    for frel in WORKSPACE_MEMORY_FILES:
        fpath = os.path.join(workspace, frel)
        name = os.path.basename(fpath)
        if name in seen_name:
            continue
        if not os.path.exists(fpath):
            continue
        try:
            real = os.path.realpath(fpath)
        except OSError:
            real = fpath
        if real in seen_real:
            continue
        seen_name.add(name)
        seen_real.add(real)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if content:
                # Prefix each file body with a "# <path>" heading so file
                # boundaries stay visible in the combined prompt section.
                # Normalise to forward slashes for a stable label across
                # platforms (os.path.join yields '\' on Windows).
                label = frel.replace(os.sep, '/')
                # Skip copies of an already-loaded file (e.g. a CLAUDE.md
                # whose content was copied into SIADA.md). The basename
                # claim above still stands, mirroring empty-file handling.
                if _find_near_duplicate(content, loaded) is not None:
                    continue
                loaded.append((label, content))
                parts.append(f"# {label}\n\n{content}")
        except Exception as e:
            print(f"Warning: Failed to load {frel}: {e}")
    return '\n\n'.join(parts) if parts else None


def _file_summary(fpath: str) -> str:
    """Return a one-line summary: line count + heading titles."""
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
        headings = [l.lstrip('#').strip() for l in lines if l.startswith('#')][:4]
        summary = f"{len(lines)} lines"
        if headings:
            summary += f"  •  {' / '.join(headings)}"
        return summary
    except Exception:
        return "unreadable"


def refresh_siada_memory(workspace: str) -> tuple[Optional[str], str]:
    """
    Refresh workspace memory content and return a status message with content overview.

    Files skipped as near-duplicates of a higher-priority file are reported
    as such, mirroring what ``load_siada_memory`` actually ships.

    Args:
        workspace: Path to the workspace directory

    Returns:
        Tuple of (memory_content, status_message)
    """
    memory_content = load_siada_memory(workspace)

    rows = []
    loaded: List[Tuple[str, str]] = []
    seen_name: set = set()
    seen_real: set = set()
    for frel in WORKSPACE_MEMORY_FILES:
        fpath = os.path.join(workspace, frel)
        label = frel
        name = os.path.basename(fpath)
        if name in seen_name:
            rows.append(f"  ~ {label:<20} (skipped, {name} already loaded)")
            continue
        if not os.path.exists(fpath):
            rows.append(f"  ✗ {label:<20} (not found)")
            continue
        try:
            real = os.path.realpath(fpath)
        except OSError:
            real = fpath
        if real in seen_real:
            rows.append(f"  ~ {label:<20} (same file as above)")
            continue
        seen_name.add(name)
        seen_real.add(real)
        if not os.path.getsize(fpath):
            rows.append(f"  ✗ {label:<20} (empty)")
            continue
        # Mirror load_siada_memory's near-duplicate skip so the status
        # table reflects what actually ships in the system prompt.
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                body = f.read().strip()
        except Exception:
            body = ""
        if body:
            dup = _find_near_duplicate(body, loaded)
            if dup is not None:
                rows.append(
                    f"  ~ {label:<20} (skipped, {dup[1]:.0%} similar to {dup[0]})"
                )
                continue
            loaded.append((label, body))
        rows.append(f"  ✓ {label:<20} {_file_summary(fpath)}")

    header = "Context files refreshed:" if memory_content else "Context files:"
    return memory_content, header + "\n" + "\n".join(rows)

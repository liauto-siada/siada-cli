"""
Siada Memory Service

Handles loading and managing user memory content from SIADA.md / AGENTS.md / CLAUDE.md files.
"""

import os
from typing import List, Optional

# Context files recognised as workspace-level memory, in priority order.
# Entries may be plain filenames or relative paths (e.g. '.claude/CLAUDE.md').
# All non-empty files are loaded and combined.
WORKSPACE_MEMORY_FILES = [
    'SIADA.md',
    'AGENTS.md',
    'CLAUDE.md',
    os.path.join('.claude', 'CLAUDE.md'),
]


def load_siada_memory(workspace: str) -> Optional[str]:
    """
    Load workspace memory from SIADA.md, AGENTS.md, and/or CLAUDE.md.

    All recognised files are first-class context sources. If multiple exist
    and are non-empty their contents are combined (SIADA.md first).
    CLAUDE.md is checked at both the project root and .claude/CLAUDE.md.

    Args:
        workspace: Path to the workspace directory

    Returns:
        Combined content if any file is non-empty, None otherwise
    """
    parts: List[str] = []
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
                parts.append(content)
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

    Args:
        workspace: Path to the workspace directory

    Returns:
        Tuple of (memory_content, status_message)
    """
    memory_content = load_siada_memory(workspace)

    rows = []
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
        else:
            rows.append(f"  ✓ {label:<20} {_file_summary(fpath)}")

    header = "Context files refreshed:" if memory_content else "Context files:"
    return memory_content, header + "\n" + "\n".join(rows)

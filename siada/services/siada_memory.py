"""
Siada Memory Service

Handles loading and managing user memory content from SIADA.md / AGENTS.md files.
"""

import os
from typing import List, Optional

# Context files recognised as workspace-level memory, in priority order.
# All non-empty files are loaded and combined.
WORKSPACE_MEMORY_FILES = ['SIADA.md', 'AGENTS.md']


def load_siada_memory(workspace: str) -> Optional[str]:
    """
    Load workspace memory from SIADA.md and/or AGENTS.md.

    Both files are supported as first-class context sources. If both exist
    and are non-empty their contents are combined (SIADA.md first).

    Args:
        workspace: Path to the workspace directory

    Returns:
        Combined content if any file is non-empty, None otherwise
    """
    parts: List[str] = []
    for fname in WORKSPACE_MEMORY_FILES:
        fpath = os.path.join(workspace, fname)
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if content:
                parts.append(content)
        except Exception as e:
            print(f"Warning: Failed to load {fname}: {e}")
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
    for fname in WORKSPACE_MEMORY_FILES:
        fpath = os.path.join(workspace, fname)
        if not os.path.exists(fpath):
            rows.append(f"  ✗ {fname:<12} (not found)")
        elif not os.path.getsize(fpath):
            rows.append(f"  ✗ {fname:<12} (empty)")
        else:
            rows.append(f"  ✓ {fname:<12} {_file_summary(fpath)}")

    header = "Context files refreshed:" if memory_content else "Context files:"
    return memory_content, header + "\n" + "\n".join(rows)

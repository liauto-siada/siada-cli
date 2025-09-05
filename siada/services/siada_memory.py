"""
Siada Memory Service

Handles loading and managing user memory content from siada.md files.
"""

import os
from typing import Optional


def load_siada_memory(workspace: str) -> Optional[str]:
    """
    Load siada.md file content from the current workspace directory.
    
    Args:
        workspace: Path to the workspace directory
        
    Returns:
        Content of siada.md file if exists and not empty, None otherwise
    """
    siada_md_path = os.path.join(workspace, 'siada.md')
    
    if not os.path.exists(siada_md_path):
        return None
    
    try:
        with open(siada_md_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            return content if content else None
    except Exception as e:
        print(f"Warning: Failed to load siada.md: {e}")
        return None


def refresh_siada_memory(workspace: str) -> tuple[Optional[str], str]:
    """
    Refresh siada.md memory content and return status message.
    
    Args:
        workspace: Path to the workspace directory
        
    Returns:
        Tuple of (memory_content, status_message)
    """
    memory_content = load_siada_memory(workspace)
    
    if memory_content:
        return memory_content, "User memory refreshed from siada.md"
    else:
        siada_md_path = os.path.join(workspace, 'siada.md')
        if not os.path.exists(siada_md_path):
            return None, "No siada.md file found in current workspace"
        else:
            return None, "siada.md file exists but is empty"

"""
Utility functions for file recommendation system.
"""

from .path_utils import escape_path, unescape_path
from .text_utils import (
    is_completion_active,
    parse_at_command_path,
    to_code_points,
    cp_len,
    cp_slice
)

__all__ = [
    'escape_path',
    'unescape_path',
    'is_completion_active',
    'parse_at_command_path',
    'to_code_points',
    'cp_len',
    'cp_slice'
]

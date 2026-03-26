"""
Web tools package - stub that re-exports from internal.

This module delegates to siada.internal.tools.web for backward compatibility.
The actual implementations live in siada/internal/tools/web/ (not open-sourced).
"""

from typing import List

try:
    from siada.internal.tools.web import get_web_tools, web_search, web_crawl, web_fetch
except ImportError:
    web_search = None
    web_crawl = None
    web_fetch = None

    def get_web_tools() -> List:
        return []

__all__ = ['web_crawl', 'web_fetch', 'web_search', 'get_web_tools']

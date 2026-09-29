"""
File Search - a high-performance file search tool.

A Python file search module based on ripgrep, providing fast and accurate
code search.
"""

from .search import RipgrepSearcher, SearchResult, regex_search_files

__all__ = ['RipgrepSearcher', 'SearchResult', 'regex_search_files']
__version__ = '1.0.0'

"""
High-performance file search tools.

Python file search based on ripgrep for fast, accurate code search.
"""

from .search import RipgrepSearcher, SearchResult, regex_search_files

__all__ = ['RipgrepSearcher', 'SearchResult', 'regex_search_files']
__version__ = '1.0.0'

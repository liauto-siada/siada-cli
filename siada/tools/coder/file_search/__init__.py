"""
File Search - 高性能文件搜索工具

基于 ripgrep 的 Python 文件搜索模块，提供快速、准确的代码搜索功能。
"""

from .search import RipgrepSearcher, SearchResult, regex_search_files

__all__ = ['RipgrepSearcher', 'SearchResult', 'regex_search_files']
__version__ = '1.0.0'

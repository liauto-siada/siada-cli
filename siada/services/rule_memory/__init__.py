"""
Rule Memory - Hierarchical Context File System

This module provides hierarchical context file management similar to Gemini CLI's
GEMINI.md functionality, using siada_rule.md files.

Main features:
- 3-tier hierarchical discovery (global, project root, subdirectories)
- Import processing with @ syntax
- Configurable search and filtering
- BFS-based efficient file discovery
"""

from .discovery import load_hierarchical_context, ContextDiscovery
from .config import get_rule_config, RuleConfig
from .import_processor import ImportProcessor
from .bfs_search import BFSFileSearch

__all__ = [
    'load_hierarchical_context',
    'ContextDiscovery',
    'get_rule_config',
    'RuleConfig',
    'ImportProcessor',
    'BFSFileSearch',
]

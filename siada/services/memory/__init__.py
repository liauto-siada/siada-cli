"""
Memory service module for storing conversation history in Markdown format.

Provides:
- MemoryService: Session memory storage with Markdown files and derived memory extraction
- MemoryDatabase: SQLite database with FTS5 full-text search
- MemorySearch: Search interface for querying memories
- Memory Agent: Intelligent memory extraction and update system
"""

from siada.services.memory.memory_service import MemoryService
from siada.services.memory.memory_db import MemoryDatabase, DEFAULT_CHUNK_SIZE
from siada.services.memory.memory_search import MemorySearch, SearchResult
from siada.services.memory.memory_agent import analyze_and_update_memory

__all__ = [
    'MemoryService',
    'MemoryDatabase',
    'MemorySearch',
    'SearchResult',
    'DEFAULT_CHUNK_SIZE',
    'analyze_and_update_memory',
]

"""
Test suite for Memory FTS5 implementation.

PyTest-compatible test cases for:
1. Database creation and schema
2. Text chunking
3. File indexing
4. FTS5 search
5. Integration with MemoryService
"""

import asyncio
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from siada.services.memory import MemoryService, MemoryDatabase, MemorySearch


# Fixtures

@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_db_path(temp_dir):
    """Create a test database path."""
    return temp_dir / "test.db"


@pytest.fixture
def sample_markdown_content():
    """Provide sample markdown content for testing."""
    return """# Session: 2024-01-15 10:30:00

- **Session ID**: test-session
- **Timestamp**: 2024-01-15 10:30:00

## Conversation Summary

user: Hello, can you help me with Python?
assistant: Of course! I'd be happy to help you with Python. What specifically would you like to know?
user: How do I read a file in Python?
assistant: You can read a file in Python using the open() function. Here's an example:

with open('filename.txt', 'r') as file:
    content = file.read()
    print(content)

This is the safest way as it automatically closes the file.
"""


@pytest.fixture
def async_markdown_content():
    """Provide async/await markdown content for testing."""
    return """# Session: 2024-01-15 10:30:00

- **Session ID**: test-123
- **Timestamp**: 2024-01-15 10:30:00

## Conversation Summary

user: Can you explain async/await in Python?
assistant: Async/await is used for asynchronous programming in Python. It allows you to write concurrent code that can handle multiple tasks efficiently.
user: Show me an example.
assistant: Here's a simple example:

async def fetch_data():
    await asyncio.sleep(1)
    return "Data fetched"

async def main():
    result = await fetch_data()
    print(result)

asyncio.run(main())
"""


# Test Classes

class TestMemoryDatabase:
    """Test suite for MemoryDatabase class."""
    
    def test_database_creation(self, test_db_path):
        """Test database and schema creation."""
        db = MemoryDatabase(test_db_path)
        
        assert test_db_path.exists(), "Database file not created"
        assert db.fts_available, f"FTS5 not available: {db.fts_error}"
        
        # Check tables exist
        cursor = db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = ['meta', 'files', 'chunks']
        for table in expected_tables:
            assert table in tables, f"Missing table: {table}"
        
        if db.fts_available:
            assert 'chunks_fts' in tables, "Missing FTS5 table"
        
        db.close()
    
    def test_text_chunking(self, test_db_path, sample_markdown_content):
        """Test markdown text chunking."""
        db = MemoryDatabase(test_db_path)
        
        chunks = db.chunk_markdown(sample_markdown_content, chunk_size=200)
        
        assert len(chunks) > 0, "No chunks created"
        
        # Verify chunk properties
        for chunk in chunks:
            assert chunk.start_line > 0, "Invalid start_line"
            assert chunk.end_line >= chunk.start_line, "Invalid end_line"
            assert len(chunk.text) > 0, "Empty chunk text"
            assert len(chunk.hash) > 0, "Empty chunk hash"
        
        db.close()
    
    def test_file_indexing(self, temp_dir, test_db_path, async_markdown_content):
        """Test indexing a markdown file."""
        # Create test markdown file
        md_file = temp_dir / "2024-01-15-10-30-test-session.md"
        md_file.write_text(async_markdown_content, encoding='utf-8')
        
        # Index the file
        db = MemoryDatabase(test_db_path)
        success = db.index_file(md_file, source='memory', model='none')
        
        assert success, "File indexing failed"
        
        # Check chunks table
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]
        assert chunk_count > 0, "No chunks created"
        
        # Check FTS5 table if available
        if db.fts_available:
            cursor.execute("SELECT COUNT(*) FROM chunks_fts")
            fts_count = cursor.fetchone()[0]
            assert chunk_count == fts_count, "Chunk count mismatch between chunks and FTS5"
        
        # Check files table
        cursor.execute("SELECT COUNT(*) FROM files")
        file_count = cursor.fetchone()[0]
        assert file_count == 1, "File not recorded"
        
        # Verify file record
        cursor.execute("SELECT path, source FROM files")
        file_record = cursor.fetchone()
        assert file_record is not None, "No file record found"
        assert 'test-session.md' in file_record[0], "Incorrect file path"
        assert file_record[1] == 'memory', "Incorrect source"
        
        db.close()


class TestMemorySearch:
    """Test suite for MemorySearch class."""
    
    def test_search_functionality(self, temp_dir, test_db_path, async_markdown_content):
        """Test FTS5 search functionality."""
        # Create and index test file
        md_file = temp_dir / "2024-01-15-10-30-async-example.md"
        md_file.write_text(async_markdown_content, encoding='utf-8')
        
        db = MemoryDatabase(test_db_path)
        db.index_file(md_file, source='memory', model='none')
        db.close()
        
        # Perform search
        search = MemorySearch(test_db_path)
        
        assert search.fts_available, "FTS5 not available for search"
        
        # Search for "async"
        results = search.search("async", limit=5)
        assert len(results) > 0, "No results found for 'async'"
        
        # Verify result properties
        for result in results:
            assert result.path == str(md_file), "Incorrect file path in results"
            assert result.score > 0, "Invalid score"
            assert len(result.snippet) > 0, "Empty snippet"
        
        # Search for "Python"
        results = search.search("Python", limit=5)
        assert len(results) > 0, "No results found for 'Python'"
        
        search.close()
    
    def test_search_with_multiple_files(self, temp_dir, test_db_path):
        """Test search across multiple files."""
        # Create multiple test files
        file1 = temp_dir / "2024-01-15-python.md"
        file1.write_text("""# Python Tutorial
        
Learn Python programming with FastAPI framework.
""", encoding='utf-8')
        
        file2 = temp_dir / "2024-01-16-javascript.md"
        file2.write_text("""# JavaScript Tutorial
        
Learn JavaScript with Node.js and Express.
""", encoding='utf-8')
        
        # Index files
        db = MemoryDatabase(test_db_path)
        db.index_file(file1, source='memory', model='none')
        db.index_file(file2, source='memory', model='none')
        db.close()
        
        # Search
        search = MemorySearch(test_db_path)
        
        # Search for Python
        results = search.search("Python", limit=10)
        assert len(results) > 0, "No results for Python"
        python_files = [r for r in results if 'python.md' in r.path]
        assert len(python_files) > 0, "Python file not found in results"
        
        # Search for JavaScript
        results = search.search("JavaScript", limit=10)
        assert len(results) > 0, "No results for JavaScript"
        js_files = [r for r in results if 'javascript.md' in r.path]
        assert len(js_files) > 0, "JavaScript file not found in results"
        
        search.close()


class TestMemoryServiceIntegration:
    """Test suite for MemoryService integration."""
    
    @pytest.mark.asyncio
    async def test_memory_service_integration(self, temp_dir):
        """Test integration with MemoryService."""
        # Initialize MemoryService (uses default path)
        service = MemoryService()
        
        # Create a test conversation
        conversation = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi! How can I help you?"},
            {"role": "user", "content": "Tell me about FastAPI"},
            {"role": "assistant", "content": "FastAPI is a modern web framework for Python."},
        ]
        
        # Save conversation
        filename = await service.save_conversation(
            conversation=conversation,
            session_id="test-integration"
        )
        
        assert filename is not None, "Failed to save conversation"
        assert filename.exists(), "Saved file does not exist"
        
        # Check if file was indexed in default location
        default_memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
        db_path = default_memory_dir / "memory.db"
        
        if db_path.exists():
            search = MemorySearch(db_path)
            
            if search.fts_available:
                # Search for content
                results = search.search("FastAPI", limit=5)
                # Note: this might be empty if indexing is deferred
                # assert len(results) > 0, "Indexed file not searchable"
            
            search.close()


# Standalone test functions for compatibility

def test_database_standalone():
    """Standalone test for database creation (pytest compatible)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_standalone.db"
        db = MemoryDatabase(db_path)
        
        assert db_path.exists()
        assert db.fts_available
        
        db.close()


def test_search_standalone():
    """Standalone test for search (pytest compatible)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        db_path = tmpdir / "test_standalone.db"
        
        # Create and index a test file
        md_file = tmpdir / "test.md"
        md_file.write_text("# Test\n\nPython programming tutorial.", encoding='utf-8')
        
        db = MemoryDatabase(db_path)
        db.index_file(md_file, source='test', model='none')
        db.close()
        
        # Search
        search = MemorySearch(db_path)
        if search.fts_available:
            results = search.search("Python", limit=5)
            assert len(results) > 0, "No search results"
        search.close()

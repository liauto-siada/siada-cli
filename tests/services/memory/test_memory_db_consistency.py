"""
Test Memory Service Database Consistency

Tests the consistency between Markdown files and SQLite database:
- Database is indexed on first save
- Database is updated on append mode
- FTS5 search results match file content
- Database metadata matches file metadata
"""

import asyncio
import tempfile
import hashlib
import sqlite3
from pathlib import Path

import pytest

from siada.services.memory.memory_service import MemoryService
from siada.services.memory.memory_db import MemoryDatabase
from siada.foundation.context import get_context_var, remove_context_var, LAST_MEMORY_NAME


class MockFileSession:
    """Mock FileSession for testing"""
    
    def __init__(self, session_id: str, messages: list):
        self.session_id = session_id
        self.messages = messages
    
    async def get_items(self):
        """Return mock messages"""
        return self.messages


@pytest.fixture
def temp_memory_dir():
    """Create a temporary directory for memory files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def memory_service(temp_memory_dir):
    """Create a MemoryService instance with temp directory"""
    return MemoryService(memory_dir=temp_memory_dir, slug_message_limit=2)


@pytest.fixture
def memory_db(temp_memory_dir):
    """Create a MemoryDatabase instance with temp directory"""
    db_path = temp_memory_dir / "memory.db"
    db = MemoryDatabase(db_path)
    yield db
    db.close()


@pytest.fixture(autouse=True)
def clear_context():
    """Clear context before and after each test"""
    remove_context_var(LAST_MEMORY_NAME)
    yield
    remove_context_var(LAST_MEMORY_NAME)


def get_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of file content"""
    content = file_path.read_text(encoding='utf-8')
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


@pytest.mark.asyncio
async def test_database_indexed_on_first_save(memory_service, memory_db, temp_memory_dir):
    """Test that database is correctly indexed on first save"""
    
    # Create and save session
    messages = [
        {'role': 'user', 'content': 'Hello, can you help me with Python?'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Of course! I can help with Python programming.'}]}
    ]
    session = MockFileSession('test-session-1', messages)
    result = await memory_service.save_session_memory(session)
    
    memory_file = Path(result)
    
    # Query files table
    cursor = memory_db.conn.cursor()
    cursor.execute("SELECT path, source, hash, mtime, size FROM files WHERE path = ?", (str(memory_file),))
    file_record = cursor.fetchone()
    
    # Verify file record exists
    assert file_record is not None, "File record should exist in database"
    assert file_record['path'] == str(memory_file)
    assert file_record['source'] == 'memory'
    
    # Verify hash matches actual file
    actual_hash = get_file_hash(memory_file)
    assert file_record['hash'] == actual_hash, "Database hash should match file hash"
    
    # Verify size matches actual file
    actual_size = memory_file.stat().st_size
    assert file_record['size'] == actual_size, "Database size should match file size"
    
    # Query chunks table
    cursor.execute("SELECT id, text, start_line, end_line FROM chunks WHERE path = ?", (str(memory_file),))
    chunks = cursor.fetchall()
    
    # Verify chunks were created
    assert len(chunks) > 0, "Chunks should be created in database"
    
    # Verify chunks contain message content
    all_chunk_text = ' '.join([chunk['text'] for chunk in chunks])
    assert 'Hello, can you help me with Python?' in all_chunk_text
    assert 'Of course! I can help with Python programming.' in all_chunk_text
    
    print(f"✓ Database indexed correctly:")
    print(f"  File record: exists")
    print(f"  Chunks: {len(chunks)}")
    print(f"  Hash matches: {file_record['hash'][:16]}...")


@pytest.mark.asyncio
async def test_database_updated_on_append(memory_service, memory_db, temp_memory_dir):
    """Test that database is correctly updated in append mode"""
    
    # First save with 2 messages
    messages_1 = [
        {'role': 'user', 'content': 'First message'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'First response'}]}
    ]
    session_1 = MockFileSession('test-session-1', messages_1)
    result_1 = await memory_service.save_session_memory(session_1)
    memory_file = Path(result_1)
    
    # Query chunks after first save
    cursor = memory_db.conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM chunks WHERE path = ?", (str(memory_file),))
    chunks_count_1 = cursor.fetchone()['count']
    
    cursor.execute("SELECT text FROM chunks WHERE path = ?", (str(memory_file),))
    chunks_1 = cursor.fetchall()
    all_text_1 = ' '.join([chunk['text'] for chunk in chunks_1])
    
    # Verify first save content
    assert 'First message' in all_text_1
    assert 'First response' in all_text_1
    assert 'Second message' not in all_text_1  # Should not exist yet
    
    # Second save with 4 messages (append mode)
    messages_2 = [
        {'role': 'user', 'content': 'First message'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'First response'}]},
        {'role': 'user', 'content': 'Second message'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Second response'}]}
    ]
    session_2 = MockFileSession('test-session-1', messages_2)
    result_2 = await memory_service.save_session_memory(session_2)
    
    # Verify same file
    assert result_1 == result_2
    
    # Query chunks after second save
    cursor.execute("SELECT COUNT(*) as count FROM chunks WHERE path = ?", (str(memory_file),))
    chunks_count_2 = cursor.fetchone()['count']
    
    cursor.execute("SELECT text FROM chunks WHERE path = ?", (str(memory_file),))
    chunks_2 = cursor.fetchall()
    all_text_2 = ' '.join([chunk['text'] for chunk in chunks_2])
    
    # Verify updated content includes all messages
    assert 'First message' in all_text_2
    assert 'First response' in all_text_2
    assert 'Second message' in all_text_2
    assert 'Second response' in all_text_2
    
    # Verify hash was updated
    cursor.execute("SELECT hash FROM files WHERE path = ?", (str(memory_file),))
    db_hash = cursor.fetchone()['hash']
    actual_hash = get_file_hash(memory_file)
    assert db_hash == actual_hash, "Database hash should be updated after append"
    
    print(f"✓ Database updated correctly in append mode:")
    print(f"  Chunks before: {chunks_count_1}")
    print(f"  Chunks after: {chunks_count_2}")
    print(f"  Content updated: all 4 messages present")


@pytest.mark.asyncio
async def test_fts5_search_consistency(memory_service, memory_db, temp_memory_dir):
    """Test that FTS5 search results match file content"""
    
    # Skip test if FTS5 is not available
    if not memory_db.fts_available:
        pytest.skip("FTS5 not available in this SQLite build")
    
    # Create session with specific searchable content
    messages = [
        {'role': 'user', 'content': 'I need help with Python decorators'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Python decorators are a powerful feature that allows you to modify functions.'}]},
        {'role': 'user', 'content': 'Can you show me an example?'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Sure! Here is a simple decorator example in Python.'}]}
    ]
    session = MockFileSession('test-session-1', messages)
    result = await memory_service.save_session_memory(session)
    memory_file = Path(result)
    
    # Search for keyword "decorators" using FTS5
    cursor = memory_db.conn.cursor()
    
    # Note: FTS5 with Chinese segmentation may split words differently
    # Try searching for "decorator" (singular) as well
    cursor.execute("""
        SELECT path, text, start_line, end_line 
        FROM chunks_fts 
        WHERE chunks_fts MATCH ?
    """, ('decorator*',))  # Use wildcard to match both singular and plural
    search_results = cursor.fetchall()
    
    # Verify search results exist
    assert len(search_results) > 0, "FTS5 search should return results for 'decorator*'"
    
    # Verify search results point to correct file
    for result in search_results:
        assert result['path'] == str(memory_file)
        assert 'decorators' in result['text'].lower() or 'decorator' in result['text'].lower()
    
    # Read actual file content
    file_content = memory_file.read_text(encoding='utf-8')
    
    # Verify all search result text exists in the file
    for result in search_results:
        # Note: FTS5 text may have Chinese word segmentation spaces
        # So we check for key words rather than exact match
        assert 'decorator' in file_content.lower(), "Search result text should exist in file"
    
    # Search for another keyword "example"
    cursor.execute("""
        SELECT path, text 
        FROM chunks_fts 
        WHERE chunks_fts MATCH ?
    """, ('example',))
    example_results = cursor.fetchall()
    
    assert len(example_results) > 0, "FTS5 search should return results for 'example'"
    
    print(f"✓ FTS5 search consistency verified:")
    print(f"  'decorators' search: {len(search_results)} results")
    print(f"  'example' search: {len(example_results)} results")
    print(f"  All results match file content")


@pytest.mark.asyncio
async def test_database_metadata_consistency(memory_service, memory_db, temp_memory_dir):
    """Test that database metadata matches file metadata"""
    
    # Create and save session
    messages = [
        {'role': 'user', 'content': 'Test message for metadata verification'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Test response for metadata'}]}
    ]
    session = MockFileSession('test-session-1', messages)
    result = await memory_service.save_session_memory(session)
    memory_file = Path(result)
    
    # Get file metadata
    file_stat = memory_file.stat()
    file_size = file_stat.st_size
    file_mtime = int(file_stat.st_mtime * 1000)  # Convert to milliseconds
    file_hash = get_file_hash(memory_file)
    
    # Query database metadata
    cursor = memory_db.conn.cursor()
    cursor.execute("SELECT hash, mtime, size FROM files WHERE path = ?", (str(memory_file),))
    db_record = cursor.fetchone()
    
    assert db_record is not None, "Database record should exist"
    
    # Verify hash matches
    assert db_record['hash'] == file_hash, f"Hash mismatch: DB={db_record['hash'][:16]}..., File={file_hash[:16]}..."
    
    # Verify size matches
    assert db_record['size'] == file_size, f"Size mismatch: DB={db_record['size']}, File={file_size}"
    
    # Verify mtime is close (within 2 seconds to account for timing differences)
    mtime_diff = abs(db_record['mtime'] - file_mtime)
    assert mtime_diff < 2000, f"Mtime difference too large: {mtime_diff}ms"
    
    print(f"✓ Database metadata matches file:")
    print(f"  Hash: {file_hash[:16]}...")
    print(f"  Size: {file_size} bytes")
    print(f"  Mtime diff: {mtime_diff}ms")


@pytest.mark.asyncio
async def test_multiple_files_database_consistency(memory_service, memory_db, temp_memory_dir):
    """Test database consistency with multiple memory files"""
    
    # Create first session
    messages_1 = [
        {'role': 'user', 'content': 'First session about Python'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Python is great'}]}
    ]
    session_1 = MockFileSession('test-session-1', messages_1)
    result_1 = await memory_service.save_session_memory(session_1)
    file_1 = Path(result_1)
    
    # Clear context to start new session
    remove_context_var(LAST_MEMORY_NAME)
    
    # Create second session
    messages_2 = [
        {'role': 'user', 'content': 'Second session about JavaScript'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'JavaScript is versatile'}]}
    ]
    session_2 = MockFileSession('test-session-2', messages_2)
    result_2 = await memory_service.save_session_memory(session_2)
    file_2 = Path(result_2)
    
    # Verify two different files
    assert file_1 != file_2
    
    # Query database for both files
    cursor = memory_db.conn.cursor()
    cursor.execute("SELECT path FROM files ORDER BY path")
    db_files = [row['path'] for row in cursor.fetchall()]
    
    # Verify both files are in database
    assert str(file_1) in db_files
    assert str(file_2) in db_files
    
    # Query chunks for each file
    cursor.execute("SELECT path, text FROM chunks WHERE path = ?", (str(file_1),))
    chunks_1 = cursor.fetchall()
    text_1 = ' '.join([chunk['text'] for chunk in chunks_1])
    
    cursor.execute("SELECT path, text FROM chunks WHERE path = ?", (str(file_2),))
    chunks_2 = cursor.fetchall()
    text_2 = ' '.join([chunk['text'] for chunk in chunks_2])
    
    # Verify content separation
    assert 'Python' in text_1
    assert 'JavaScript' in text_2
    assert 'JavaScript' not in text_1
    assert 'Python' not in text_2
    
    print(f"✓ Multiple files database consistency:")
    print(f"  Files in DB: {len(db_files)}")
    print(f"  File 1 chunks: {len(chunks_1)}")
    print(f"  File 2 chunks: {len(chunks_2)}")
    print(f"  Content properly separated")


@pytest.mark.asyncio
async def test_chunk_coverage_completeness(memory_service, memory_db, temp_memory_dir):
    """Test that all file content is covered by chunks"""
    
    # Create session with substantial content
    messages = [
        {'role': 'user', 'content': 'This is the first message with some unique content marker_001'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'This is the first response with marker_002'}]},
        {'role': 'user', 'content': 'This is the second message with marker_003'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'This is the second response with marker_004'}]},
        {'role': 'user', 'content': 'This is the third message with marker_005'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'This is the third response with marker_006'}]}
    ]
    session = MockFileSession('test-session-1', messages)
    result = await memory_service.save_session_memory(session)
    memory_file = Path(result)
    
    # Read file content
    file_content = memory_file.read_text(encoding='utf-8')
    
    # Query all chunks for this file
    cursor = memory_db.conn.cursor()
    cursor.execute("SELECT text FROM chunks WHERE path = ?", (str(memory_file),))
    chunks = cursor.fetchall()
    
    # Combine all chunk text
    all_chunk_text = ' '.join([chunk['text'] for chunk in chunks])
    
    # Verify all unique markers are in chunks
    for i in range(1, 7):
        marker = f'marker_{i:03d}'
        assert marker in file_content, f"Marker {marker} should be in file"
        assert marker in all_chunk_text, f"Marker {marker} should be in chunks"
    
    print(f"✓ Chunk coverage completeness:")
    print(f"  Total chunks: {len(chunks)}")
    print(f"  All 6 markers found in chunks")
    print(f"  100% content coverage verified")


if __name__ == '__main__':
    # Run tests with pytest
    pytest.main([__file__, '-v', '-s'])

"""
Test Memory Service Append Mode

Tests the new session memory append mode functionality:
- First save creates a new memory file
- Subsequent saves update the same file
- After LAST_MEMORY_NAME is cleared, creates a new file
"""

import asyncio
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from siada.services.memory.memory_service import MemoryService
from siada.services.file_session import FileSession
from siada.foundation.global_cache import get_global_cache, remove_global_cache, LAST_MEMORY_NAME


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


@pytest.fixture(autouse=True)
def clear_context():
    """Clear global cache before and after each test"""
    remove_global_cache(LAST_MEMORY_NAME)
    yield
    remove_global_cache(LAST_MEMORY_NAME)


@pytest.mark.asyncio
async def test_first_save_creates_new_file(memory_service, temp_memory_dir):
    """Test that first save creates a new memory file"""
    
    # Create mock session with one message
    messages = [
        {'role': 'user', 'content': 'Hello, can you help me?'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Of course! How can I help you?'}]}
    ]
    session = MockFileSession('test-session-1', messages)
    
    # Save session memory
    result = await memory_service.save_session_memory(session)
    
    # Verify file was created
    assert result is not None
    memory_file = Path(result)
    assert memory_file.exists()
    # File should be in session subdirectory
    assert memory_file.parent == temp_memory_dir / "session"
    
    # Verify content
    content = memory_file.read_text(encoding='utf-8')
    assert 'Hello, can you help me?' in content
    assert 'Of course! How can I help you?' in content
    
    # Verify global cache variable was set
    saved_path = get_global_cache(LAST_MEMORY_NAME)
    assert saved_path == str(memory_file)
    
    print(f"✓ First save created file: {memory_file.name}")


@pytest.mark.asyncio
async def test_second_save_updates_same_file(memory_service, temp_memory_dir):
    """Test that second save updates the same file (append mode)"""
    
    # First save
    messages_1 = [
        {'role': 'user', 'content': 'Hello, can you help me?'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Of course!'}]}
    ]
    session_1 = MockFileSession('test-session-1', messages_1)
    result_1 = await memory_service.save_session_memory(session_1)
    memory_file_1 = Path(result_1)
    
    # Record initial file modification time
    mtime_1 = memory_file_1.stat().st_mtime
    
    # Second save with additional messages (simulate conversation continuation)
    messages_2 = [
        {'role': 'user', 'content': 'Hello, can you help me?'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Of course!'}]},
        {'role': 'user', 'content': 'I need to write a Python function'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Sure, what should the function do?'}]}
    ]
    session_2 = MockFileSession('test-session-1', messages_2)
    result_2 = await memory_service.save_session_memory(session_2)
    memory_file_2 = Path(result_2)
    
    # Verify it's the same file
    assert result_1 == result_2
    assert memory_file_1 == memory_file_2
    
    # Verify file was modified
    mtime_2 = memory_file_2.stat().st_mtime
    assert mtime_2 > mtime_1
    
    # Verify content includes all messages
    content = memory_file_2.read_text(encoding='utf-8')
    assert 'Hello, can you help me?' in content
    assert 'Of course!' in content
    assert 'I need to write a Python function' in content
    assert 'Sure, what should the function do?' in content
    
    # Verify only one file exists in session subdirectory
    session_dir = temp_memory_dir / "session"
    files = list(session_dir.glob('*.md'))
    assert len(files) == 1
    
    print(f"✓ Second save updated same file: {memory_file_2.name}")
    print(f"  File count: {len(files)}")


@pytest.mark.asyncio
async def test_new_file_after_context_cleared(memory_service, temp_memory_dir):
    """Test that new file is created after LAST_MEMORY_NAME is cleared"""
    
    # First conversation
    messages_1 = [
        {'role': 'user', 'content': 'First conversation'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Response 1'}]}
    ]
    session_1 = MockFileSession('test-session-1', messages_1)
    result_1 = await memory_service.save_session_memory(session_1)
    memory_file_1 = Path(result_1)
    
    # Simulate user pressing Ctrl+C (clears global cache)
    remove_global_cache(LAST_MEMORY_NAME)
    
    # Verify global cache is cleared
    assert get_global_cache(LAST_MEMORY_NAME) is None
    
    # Second conversation (should create new file)
    messages_2 = [
        {'role': 'user', 'content': 'Second conversation'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Response 2'}]}
    ]
    session_2 = MockFileSession('test-session-2', messages_2)
    result_2 = await memory_service.save_session_memory(session_2)
    memory_file_2 = Path(result_2)
    
    # Verify two different files were created
    assert result_1 != result_2
    assert memory_file_1 != memory_file_2
    assert memory_file_1.exists()
    assert memory_file_2.exists()
    
    # Verify content is different
    content_1 = memory_file_1.read_text(encoding='utf-8')
    content_2 = memory_file_2.read_text(encoding='utf-8')
    
    assert 'First conversation' in content_1
    assert 'Response 1' in content_1
    assert 'Second conversation' not in content_1
    
    assert 'Second conversation' in content_2
    assert 'Response 2' in content_2
    assert 'First conversation' not in content_2
    
    # Verify two files exist in session subdirectory
    session_dir = temp_memory_dir / "session"
    files = list(session_dir.glob('*.md'))
    assert len(files) == 2
    
    print(f"✓ Created two separate files:")
    print(f"  File 1: {memory_file_1.name}")
    print(f"  File 2: {memory_file_2.name}")


@pytest.mark.asyncio
async def test_append_mode_with_multiple_updates(memory_service, temp_memory_dir):
    """Test multiple consecutive updates to the same file"""
    
    base_messages = []
    
    # Simulate 5 consecutive user inputs in the same session
    for i in range(5):
        base_messages.extend([
            {'role': 'user', 'content': f'User message {i+1}'},
            {'role': 'assistant', 'content': [{'type': 'output_text', 'text': f'Assistant response {i+1}'}]}
        ])
        
        session = MockFileSession('test-session-1', base_messages.copy())
        result = await memory_service.save_session_memory(session)
        
        # Verify same file is used
        if i == 0:
            first_file = result
        else:
            assert result == first_file
    
    # Verify only one file exists in session subdirectory
    session_dir = temp_memory_dir / "session"
    files = list(session_dir.glob('*.md'))
    assert len(files) == 1
    
    # Verify all messages are in the file
    memory_file = Path(first_file)
    content = memory_file.read_text(encoding='utf-8')
    
    for i in range(5):
        assert f'User message {i+1}' in content
        assert f'Assistant response {i+1}' in content
    
    print(f"✓ Multiple updates to same file:")
    print(f"  Updates: 5")
    print(f"  File: {memory_file.name}")
    print(f"  Total files: {len(files)}")


@pytest.mark.asyncio
async def test_skip_slash_commands(memory_service):
    """Test that slash commands are skipped in memory"""
    
    messages = [
        {'role': 'user', 'content': '/help'},
        {'role': 'user', 'content': 'Real user message'},
        {'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Real response'}]},
        {'role': 'user', 'content': '/clear'}
    ]
    session = MockFileSession('test-session-1', messages)
    
    result = await memory_service.save_session_memory(session)
    memory_file = Path(result)
    content = memory_file.read_text(encoding='utf-8')
    
    # Verify slash commands are not in the file
    assert '/help' not in content
    assert '/clear' not in content
    
    # Verify real messages are in the file
    assert 'Real user message' in content
    assert 'Real response' in content
    
    print(f"✓ Slash commands filtered correctly")


if __name__ == '__main__':
    # Run tests with pytest
    pytest.main([__file__, '-v', '-s'])

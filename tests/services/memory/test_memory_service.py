"""
Test script for MemoryService

This script tests the basic functionality of the MemoryService.
"""

import asyncio
import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from siada.services.memory import MemoryService
from siada.services.file_session import FileSession


@pytest.mark.asyncio
async def test_memory_service():
    """Test basic memory service functionality."""
    
    print("Starting MemoryService test...")
    print("Note: This test will use timestamp fallback for slug generation")
    print("      (LLM slug generation requires a configured provider in context)\n")
    
    # Use ~/.siada-cli/workspace/memory for testing so we can inspect the files
    # (instead of tempfile.TemporaryDirectory which auto-deletes)
    home = Path.home()
    test_memory_dir = home / ".siada-cli" / "workspace" / "memory"
    test_sessions_dir = home / ".siada-cli" / "test_sessions"
    
    # Clean up any existing test files
    if test_memory_dir.exists():
        import shutil
        for file in test_memory_dir.glob("*.md"):
            file.unlink()
    
    print(f"Test memory directory: {test_memory_dir}")
    print(f"Test sessions directory: {test_sessions_dir}\n")
    
    try:
        # Create test session directory
        sessions_dir = test_sessions_dir
        memory_dir = test_memory_dir
        
        # Create a test FileSession
        test_session_id = f"test-session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        file_session = FileSession(
            session_id=test_session_id,
            sessions_dir=sessions_dir
        )
        
        # Add test messages - simulate a longer conversation with 10 messages
        # This will test that ALL messages are saved, but only last 4 used for slug
        test_messages = [
            {"role": "user", "content": "Message 1: What is Python?"},
            {"role": "assistant", "content": "Message 2: Python is a programming language."},
            {"role": "user", "content": "Message 3: Can you tell me about lists?"},
            {"role": "assistant", "content": "Message 4: Lists are data structures in Python."},
            {"role": "user", "content": "Message 5: What about dictionaries?"},
            {"role": "assistant", "content": "Message 6: Dictionaries store key-value pairs."},
            {
                "role": "user",
                "content": "Message 7: Can you help me write a fibonacci function?"
            },
            {
                "role": "assistant",
                "content": "Message 8: Sure! Here's a fibonacci function:\n\ndef fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)"
            },
            {
                "role": "user",
                "content": "Message 9: Can you add memoization?"
            },
            {
                "role": "assistant",
                "content": "Message 10: Here's the optimized version:\n\ndef fibonacci(n, memo=None):\n    if memo is None:\n        memo = {}\n    if n in memo:\n        return memo[n]\n    if n <= 1:\n        return n\n    memo[n] = fibonacci(n-1, memo) + fibonacci(n-2, memo)\n    return memo[n]"
            }
        ]
        
        await file_session.add_items(test_messages)
        print(f"✓ Created test session with {len(test_messages)} messages")
        
        # Create MemoryService with test directory
        # slug_message_limit=4 means use last 4 messages for slug generation
        memory_service = MemoryService(memory_dir=memory_dir, slug_message_limit=4)
        print(f"✓ Created MemoryService with memory_dir: {memory_dir}")
        print(f"  - Will use last 4 messages for slug generation")
        print(f"  - Will save ALL messages to markdown file")
        
        # Save session memory
        memory_file = await memory_service.save_session_memory(file_session)
        
        if memory_file:
            print(f"✓ Memory file created: {memory_file}")
            
            # Read and display the content
            with open(memory_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print("\n" + "="*60)
            print("Memory file content:")
            print("="*60)
            print(content)
            print("="*60)
            
            # Verify the file exists and contains expected content
            assert Path(memory_file).exists(), "Memory file should exist"
            assert test_session_id in content, "Session ID should be in content"
            
            # Verify ALL 10 messages are saved
            assert "Message 1:" in content, "First message should be in content"
            assert "Message 10:" in content, "Last message should be in content"
            assert "Message 5:" in content, "Middle message should be in content"
            
            # Count messages in the file
            user_count = content.count("user:")
            assistant_count = content.count("assistant:")
            print(f"\n  - Found {user_count} user messages and {assistant_count} assistant messages in file")
            assert user_count == 5, f"Should have 5 user messages, found {user_count}"
            assert assistant_count == 5, f"Should have 5 assistant messages, found {assistant_count}"
            
            # Note: Only last 4 messages (7-10) were used for slug generation
            # But all 10 messages are saved to the markdown file
            
            print("\n✓ All assertions passed!")
            print(f"✓ Test completed successfully!")
            print(f"\n💡 Memory file saved at: {memory_file}")
            print(f"   You can view it with: cat {memory_file}")
            
        else:
            print("✗ Failed to create memory file")
            return False
    
    finally:
        # Clean up test session directory
        if test_sessions_dir.exists():
            import shutil
            shutil.rmtree(test_sessions_dir, ignore_errors=True)
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_memory_service())
    exit(0 if success else 1)

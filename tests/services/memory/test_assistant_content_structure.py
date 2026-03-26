"""
Test assistant content structure handling

This test verifies that MemoryService correctly handles assistant messages
with the actual structure returned by the model (content as array of blocks).
"""

import asyncio
import pytest
from pathlib import Path
from datetime import datetime

from siada.services.memory import MemoryService
from siada.services.file_session import FileSession
from siada.foundation.code_agent_context import CodeAgentContext


@pytest.mark.asyncio
async def test_assistant_content_structure():
    """Test that assistant messages with dict array content are handled correctly."""
    
    print("\n" + "="*60)
    print("Testing Assistant Content Structure Handling")
    print("="*60)
    
    home = Path.home()
    test_memory_dir = home / ".siada-cli" / "workspace" / "memory"
    test_sessions_dir = home / ".siada-cli" / "test_sessions"
    
    # Clean up any existing test files
    if test_memory_dir.exists():
        for file in test_memory_dir.glob("*.md"):
            file.unlink()
    
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
        
        # Add test messages with REAL assistant content structure
        test_messages = [
            {
                "role": "user",
                "content": "Write a shell script to print hello"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "The shell script already exists and contains the correct code to print \"你好北京\" three times.\n\nYou can run it with:\n```bash\nbash hello_beijing.sh\n```",
                        "annotations": [],
                        "logprobs": []
                    }
                ],
                "id": "__fake_id__",
                "status": "completed",
                "type": "message"
            },
            {
                "role": "user",
                "content": "Thanks! Can you modify it?"
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Sure! I'll modify the script for you.\n\nHere's the updated version:\n```bash\n#!/bin/bash\necho \"Modified: 你好北京\"\n```",
                        "annotations": [],
                        "logprobs": []
                    }
                ],
                "id": "__fake_id_2__",
                "status": "completed",
                "type": "message"
            }
        ]
        
        await file_session.add_items(test_messages)
        print(f"✓ Created test session with {len(test_messages)} messages")
        print(f"  - User messages: 2 (content as string)")
        print(f"  - Assistant messages: 2 (content as dict array with 'output_text' type)")
        
        # Create a minimal context
        context = CodeAgentContext(
            root_dir=str(home),
            interactive_mode=False
        )
        
        # Create MemoryService
        memory_service = MemoryService(memory_dir=memory_dir, slug_message_limit=4)
        print(f"✓ Created MemoryService")
        
        # Save session memory
        memory_file = await memory_service.save_session_memory(file_session, context)
        
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
            
            # Verify assistant messages were extracted correctly
            assert "你好北京" in content, "Chinese text from assistant should be in content"
            assert "Modified:" in content, "Modified text from assistant should be in content"
            assert "bash hello_beijing.sh" in content, "Code snippet should be in content"
            
            # Count messages in the file
            user_count = content.count("user:")
            assistant_count = content.count("assistant:")
            print(f"\n✓ Found {user_count} user messages and {assistant_count} assistant messages")
            assert user_count == 2, f"Should have 2 user messages, found {user_count}"
            assert assistant_count == 2, f"Should have 2 assistant messages, found {assistant_count}"
            
            print("\n✓ All assertions passed!")
            print("✓ Assistant content structure correctly handled!")
            
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
    success = asyncio.run(test_assistant_content_structure())
    exit(0 if success else 1)

"""
Core integration tests for HandleAtCommand functionality
"""

import unittest
import asyncio
import os
from pathlib import Path
from unittest.mock import Mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from siada.services.handle_at_command import handle_at_command


class MockConfig:
    """Mock configuration for testing"""
    
    def __init__(self, root_dir: str = None):
        self.root_dir = root_dir or os.getcwd()
        self.target_directory = self.root_dir


class TestHandleAtCommandIntegration(unittest.IsolatedAsyncioTestCase):
    """Core integration tests for handle_at_command function"""
    
    async def asyncSetUp(self):
        """Set up test environment"""
        self.test_dir = Path(__file__).parent / "test_data"
        self.config = MockConfig(str(self.test_dir))
        self.mock_add_item = Mock()
        self.mock_debug_message = Mock()
    
    async def test_end_to_end_no_at_commands(self):
        """Test end-to-end processing with no @ commands"""
        result = await handle_at_command(
            query="Just some regular text",
            config=self.config,
            add_item=self.mock_add_item,
            on_debug_message=self.mock_debug_message,
            message_id=1
        )
        
        self.assertTrue(result.should_proceed)
        self.assertIsNotNone(result.processed_query)
        self.assertEqual(len(result.processed_query), 1)
        self.assertEqual(result.processed_query[0]['text'], "Just some regular text")
    
    async def test_end_to_end_single_file(self):
        """Test end-to-end processing with single file"""
        result = await handle_at_command(
            query="Please explain @sample.py",
            config=self.config,
            add_item=self.mock_add_item,
            on_debug_message=self.mock_debug_message,
            message_id=2
        )
        
        self.assertTrue(result.should_proceed)
        self.assertIsNotNone(result.processed_query)
        self.assertGreater(len(result.processed_query), 1)
        
        # Should contain file content
        content_text = ''.join([part['text'] for part in result.processed_query if isinstance(part, dict) and 'text' in part])
        self.assertIn("--- Content from referenced files ---", content_text)
        self.assertIn("def hello_world", content_text)
    
    async def test_end_to_end_multiple_files(self):
        """Test end-to-end processing with multiple files"""
        result = await handle_at_command(
            query="Compare @sample.py and @config.json",
            config=self.config,
            add_item=self.mock_add_item,
            on_debug_message=self.mock_debug_message,
            message_id=3
        )
        
        self.assertTrue(result.should_proceed)
        self.assertIsNotNone(result.processed_query)
        
        # Should contain content from both files
        content_text = ''.join([part['text'] for part in result.processed_query if isinstance(part, dict) and 'text' in part])
        self.assertIn("def hello_world", content_text)  # From sample.py
        self.assertIn("app_name", content_text)  # From config.json
    
    async def test_end_to_end_performance(self):
        """Test end-to-end processing performance"""
        import time
        
        start_time = time.time()
        
        result = await handle_at_command(
            query="Process @sample.py and @config.json",
            config=self.config,
            add_item=self.mock_add_item,
            on_debug_message=self.mock_debug_message,
            message_id=8
        )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should complete within reasonable time (5 seconds)
        self.assertLess(processing_time, 5.0)
        self.assertTrue(result.should_proceed)


if __name__ == '__main__':
    unittest.main(verbosity=2)

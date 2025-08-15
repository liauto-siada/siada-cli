"""
Basic tests for AtCommandProcessor - Core functionality only
"""

import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from siada.services.handle_at_command import AtCommandProcessor


class TestAtCommandProcessor(unittest.TestCase):
    """Basic test suite for AtCommandProcessor"""
    
    def setUp(self):
        """Set up test environment"""
        self.processor = AtCommandProcessor()
    
    def test_processor_initialization(self):
        """Test processor initialization"""
        self.assertIsNotNone(self.processor.parser)
        self.assertIsNotNone(self.processor.stats)
        self.assertIsNotNone(self.processor.ignored_stats)
    
    def test_get_processing_stats(self):
        """Test getting processing statistics"""
        stats = self.processor.get_processing_stats()
        self.assertEqual(stats.total_at_commands, 0)
        self.assertEqual(stats.resolved_paths, 0)
        self.assertEqual(stats.failed_paths, 0)
        self.assertEqual(stats.files_read, 0)
    
    def test_get_ignored_stats(self):
        """Test getting ignored file statistics"""
        ignored_stats = self.processor.get_ignored_stats()
        self.assertEqual(len(ignored_stats.git_ignored), 0)
        self.assertEqual(len(ignored_stats.gemini_ignored), 0)
        self.assertEqual(len(ignored_stats.both_ignored), 0)
    
    def test_reset_stats(self):
        """Test resetting statistics"""
        # Manually set some stats
        self.processor.stats.total_at_commands = 5
        self.processor.stats.resolved_paths = 3
        
        # Reset
        self.processor.reset_stats()
        
        # Should be back to zero
        stats = self.processor.get_processing_stats()
        self.assertEqual(stats.total_at_commands, 0)
        self.assertEqual(stats.resolved_paths, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)

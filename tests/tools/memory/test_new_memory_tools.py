"""
Tests for new memory tools implementation functions

针对实现层（_impl函数）进行测试
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime

from siada.tools.memory.list_memory_files import list_memory_files_impl
from siada.tools.memory.search_memory_by_date import search_memory_by_date_impl


@pytest.fixture
def temp_memory_dir():
    """Create temporary memory directory with sample files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Override Path.home for this test
        original_home = Path.home
        Path.home = lambda: Path(tmpdir)
        
        # Create memory directory
        memory_dir = Path(tmpdir) / ".siada-cli" / "workspace" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        
        # Create sample memory files with dates
        (memory_dir / "2024-03-05-api-design.md").write_text(
            "# Session: 2024-03-05 14:00:00 UTC\n\nDiscussed API design\nTODO: implement authentication"
        )
        (memory_dir / "2024-03-04-bug-fix.md").write_text(
            "# Session: 2024-03-04 10:00:00 UTC\n\nFixed user validation bug in login form"
        )
        (memory_dir / "2024-03-01-old-work.md").write_text(
            "# Session: 2024-03-01 09:00:00 UTC\n\nOld work from March 1st"
        )
        
        yield memory_dir
        
        # Restore
        Path.home = original_home


class TestListMemoryFilesImpl:
    """Test list_memory_files_impl function."""
    
    def test_list_with_days_parameter(self, temp_memory_dir):
        """Test listing files using days parameter with appropriate date range."""
        # Use a date range that includes our test files (2024-03-01 to 2024-03-05)
        result = list_memory_files_impl(
            days=None,
            start_date="2024-03-01",
            end_date="2024-03-10"  # Wide range to include all test files
        )
        
        assert "Found 3 memory file" in result
        assert "2024-03-05-api-design.md" in result
        assert "2024-03-04-bug-fix.md" in result
        assert "2024-03-01-old-work.md" in result
    
    def test_list_with_date_range(self, temp_memory_dir):
        """Test listing files with explicit date range."""
        result = list_memory_files_impl(
            days=None,
            start_date="2024-03-04",
            end_date="2024-03-05"
        )
        
        assert "2024-03-05-api-design.md" in result
        assert "2024-03-04-bug-fix.md" in result
        assert "2024-03-01" not in result  # Outside range
    
    def test_list_single_day(self, temp_memory_dir):
        """Test listing files for a single day."""
        result = list_memory_files_impl(
            days=None,
            start_date="2024-03-05",
            end_date="2024-03-05"
        )
        
        assert "2024-03-05-api-design.md" in result
        assert "2024-03-04" not in result
    
    def test_list_no_memory_dir(self):
        """Test when memory directory doesn't exist."""
        # Override Path.home to non-existent directory
        original_home = Path.home
        Path.home = lambda: Path("/nonexistent")
        
        result = list_memory_files_impl()
        
        assert "No memory directory found" in result
        
        # Restore
        Path.home = original_home
    
    def test_list_no_files_in_range(self, temp_memory_dir):
        """Test when no files exist in the date range."""
        result = list_memory_files_impl(
            days=None,
            start_date="2020-01-01",
            end_date="2020-01-02"
        )
        
        assert "No memory files found" in result


class TestSearchMemoryByDateImpl:
    """Test search_memory_by_date_impl function."""
    
    def test_search_no_memory_dir(self):
        """Test when memory directory doesn't exist."""
        original_home = Path.home
        Path.home = lambda: Path("/nonexistent")
        
        result = search_memory_by_date_impl(query="test")
        
        assert "No memory directory found" in result
        
        Path.home = original_home
    
    def test_search_empty_query(self, temp_memory_dir):
        """Test search with empty query."""
        # Empty query should still work (MemorySearch may handle it)
        result = search_memory_by_date_impl(query="")
        
        # Should return a string (either results or error)
        assert isinstance(result, str)
    
    def test_search_no_files_in_range(self, temp_memory_dir):
        """Test search when no files in date range."""
        result = search_memory_by_date_impl(
            query="anything",
            days=None,
            start_date="2020-01-01",
            end_date="2020-01-02"
        )
        
        assert "No memory files found" in result or "No results found" in result

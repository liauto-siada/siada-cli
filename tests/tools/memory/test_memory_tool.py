"""
Tests for Memory Tools

Validates the memory search and retrieval functionality.
Tests focus on the internal implementation functions (_impl).
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from siada.tools.memory.memory_tool import search_memory_impl, get_memory_impl
from siada.services.memory import SearchResult


class TestSearchMemoryImpl:
    """Test cases for _search_memory_impl function."""
    
    def test_search_with_empty_query(self):
        """Test that empty query returns error."""
        result = search_memory_impl("")
        assert "Error" in result
        assert "empty" in result.lower()
    
    def test_search_with_invalid_max_results(self):
        """Test that invalid max_results returns error."""
        result = search_memory_impl("test query", max_results=0)
        assert "Error" in result
        assert "greater than 0" in result
    
    @patch('siada.tools.memory.memory_tool.MemorySearch')
    def test_search_when_fts_unavailable(self, mock_search_class):
        """Test behavior when FTS5 is not available."""
        mock_instance = MagicMock()
        mock_instance.fts_available = False
        mock_search_class.return_value = mock_instance
        
        result = search_memory_impl("test query")
        assert "not available" in result
    
    @patch('siada.tools.memory.memory_tool.MemorySearch')
    def test_search_with_no_results(self, mock_search_class):
        """Test behavior when no results are found."""
        mock_instance = MagicMock()
        mock_instance.fts_available = True
        mock_instance.search.return_value = []
        mock_search_class.return_value = mock_instance
        
        result = search_memory_impl("nonexistent query")
        assert "No results found" in result
    
    @patch('siada.tools.memory.memory_tool.MemorySearch')
    def test_search_with_results(self, mock_search_class):
        """Test successful search with results."""
        mock_instance = MagicMock()
        mock_instance.fts_available = True
        
        # Mock search results
        mock_results = [
            SearchResult(
                id="chunk_1",
                path="2024-01-15-10-00-test.md",
                source="memory",
                start_line=10,
                end_line=15,
                score=0.85,
                snippet="This is a test snippet with relevant content."
            ),
            SearchResult(
                id="chunk_2",
                path="2024-01-16-another.md",
                source="memory",
                start_line=20,
                end_line=25,
                score=0.72,
                snippet="Another relevant snippet from memory."
            )
        ]
        mock_instance.search.return_value = mock_results
        mock_search_class.return_value = mock_instance
        
        result = search_memory_impl("test query", max_results=5)
        
        # Verify result format
        assert "Found 2 result(s)" in result
        assert "2024-01-15-test.md" in result
        assert "Lines: 10-15" in result
        assert "Score: 0.850" in result
        assert "test snippet" in result
        assert "2024-01-16-another.md" in result
    
    @patch('siada.tools.memory.memory_tool.MemorySearch')
    def test_search_with_min_score_filter(self, mock_search_class):
        """Test that min_score filtering works."""
        mock_instance = MagicMock()
        mock_instance.fts_available = True
        
        mock_results = [
            SearchResult(
                id="chunk_1",
                path="high-score.md",
                source="memory",
                start_line=1,
                end_line=5,
                score=0.9,
                snippet="High score result"
            ),
            SearchResult(
                id="chunk_2",
                path="low-score.md",
                source="memory",
                start_line=1,
                end_line=5,
                score=0.3,
                snippet="Low score result"
            )
        ]
        mock_instance.search.return_value = mock_results
        mock_search_class.return_value = mock_instance
        
        result = search_memory_impl("test", max_results=10, min_score=0.5)
        
        # Only high score result should be included
        assert "high-score.md" in result
        assert "low-score.md" not in result
        assert "Found 1 result(s)" in result


class TestGetMemoryImpl:
    """Test cases for _get_memory_impl function."""
    
    def test_get_with_empty_path(self):
        """Test that empty path returns error."""
        result = get_memory_impl("")
        assert "Error" in result
        assert "empty" in result.lower()
    
    def test_get_nonexistent_file(self):
        """Test behavior with nonexistent file."""
        result = get_memory_impl("nonexistent-file-12345.md")
        assert "Error" in result
        assert "not found" in result.lower()
    
    def test_get_with_path_traversal_attempt(self):
        """Test security: prevent path traversal attacks."""
        result = get_memory_impl("../../etc/passwd")
        assert "Error" in result
        assert "Access denied" in result or "not found" in result.lower()
    
    def test_get_entire_file(self):
        """Test reading entire file content."""
        # Create a temporary memory directory and file
        memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        
        test_file = memory_dir / "test-get-memory.md"
        test_content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
        
        try:
            test_file.write_text(test_content)
            
            result = get_memory_impl("test-get-memory.md")
            
            assert "test-get-memory.md" in result
            assert "5 lines" in result
            assert "Line 1" in result
            assert "Line 5" in result
            
        finally:
            # Cleanup
            if test_file.exists():
                test_file.unlink()
    
    def test_get_with_line_range(self):
        """Test reading specific line range."""
        memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        
        test_file = memory_dir / "test-line-range.md"
        test_content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
        
        try:
            test_file.write_text(test_content)
            
            result = get_memory_impl("test-line-range.md", start_line=2, line_count=2)
            
            assert "lines 2-3" in result
            assert "Line 2" in result
            assert "Line 3" in result
            assert "Line 1" not in result
            assert "Line 4" not in result
            
        finally:
            if test_file.exists():
                test_file.unlink()
    
    def test_get_with_invalid_start_line(self):
        """Test error handling for invalid start_line."""
        memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        
        test_file = memory_dir / "test-invalid-line.md"
        test_content = "Line 1\nLine 2\n"
        
        try:
            test_file.write_text(test_content)
            
            # Test start_line < 1
            result = get_memory_impl("test-invalid-line.md", start_line=0)
            assert "Error" in result
            assert "must be >= 1" in result
            
            # Test start_line exceeds file length
            result = get_memory_impl("test-invalid-line.md", start_line=100)
            assert "Error" in result
            assert "exceeds file length" in result
            
        finally:
            if test_file.exists():
                test_file.unlink()


class TestMemoryToolsIntegration:
    """Integration tests for memory tools implementation."""
    
    @pytest.mark.integration
    def test_search_impl_integration(self):
        """Test _search_memory_impl with actual database if available."""
        # This test requires actual memory database
        # Skip if database not available
        from siada.services.memory import MemorySearch
        
        search = MemorySearch()
        if not search.fts_available:
            pytest.skip("Memory database not available")
        search.close()
        
        # Perform search using implementation function
        search_result = search_memory_impl("test")
        
        # Result should be a string
        assert isinstance(search_result, str)
    
    @pytest.mark.integration
    def test_search_and_get_workflow(self):
        """Test typical workflow: search then get detailed content."""
        from siada.services.memory import MemorySearch
        
        search = MemorySearch()
        if not search.fts_available:
            pytest.skip("Memory database not available")
        search.close()
        
        # 1. Search for content
        search_result = search_memory_impl("test", max_results=1)
        assert isinstance(search_result, str)
        
        # 2. If results found, try to read a test file
        if "No results found" not in search_result:
            # Create a test file for get_memory
            memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
            test_file = memory_dir / "integration-test.md"
            
            try:
                memory_dir.mkdir(parents=True, exist_ok=True)
                test_file.write_text("Integration test content\n")
                
                get_result = get_memory_impl("integration-test.md")
                assert isinstance(get_result, str)
                assert "integration-test.md" in get_result
                
            finally:
                if test_file.exists():
                    test_file.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

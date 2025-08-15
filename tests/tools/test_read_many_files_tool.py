"""
Tests for ReadManyFiles tool.

This test file contains comprehensive tests for the ReadManyFiles tool,
including parameter validation, file processing, filtering, and error handling.
"""

import pytest
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

from siada.tools.read_many_files_tool import ReadManyFilesTool, read_many_files, read_files_by_patterns
from siada.tools.read_many_files.models import ReadManyFilesParams, ToolResult


class TestReadManyFilesTool:
    """Test ReadManyFiles tool functionality"""
    
    @pytest.fixture
    def test_data_dir(self):
        """Get test data directory path"""
        current_dir = Path(__file__).parent
        return current_dir / "read_many_files" / "test_data"
    
    @pytest.fixture
    def tool(self, test_data_dir):
        """Create ReadManyFilesTool instance with test data directory"""
        return ReadManyFilesTool(str(test_data_dir))
    
    def test_validate_params_success(self, tool):
        """Test successful parameter validation"""
        params = ReadManyFilesParams(paths=["*.py"])
        error = tool.validate_params(params)
        assert error is None
    
    def test_validate_params_empty_paths(self, tool):
        """Test validation with empty paths"""
        params = ReadManyFilesParams(paths=[])
        error = tool.validate_params(params)
        assert error == "Parameter 'paths' is required and cannot be empty"
    
    def test_validate_params_invalid_paths_type(self, tool):
        """Test validation with invalid paths type"""
        params = ReadManyFilesParams(paths="not_a_list")
        error = tool.validate_params(params)
        assert error == "Parameter 'paths' must be a list"
    
    def test_validate_params_invalid_path_item_type(self, tool):
        """Test validation with invalid path item type"""
        params = ReadManyFilesParams(paths=["valid_path", 123])
        error = tool.validate_params(params)
        assert error == "All items in 'paths' must be strings"
    
    def test_merge_filtering_options_default(self, tool):
        """Test merging filtering options with defaults"""
        params = ReadManyFilesParams(paths=["*.py"])
        options = tool.merge_filtering_options(params)
        assert options == {'respect_git_ignore': True}
    
    def test_merge_filtering_options_custom(self, tool):
        """Test merging filtering options with custom values"""
        params = ReadManyFilesParams(
            paths=["*.py"],
            file_filtering_options={'respect_git_ignore': False}
        )
        options = tool.merge_filtering_options(params)
        assert options == {'respect_git_ignore': False}
    
    @pytest.mark.asyncio
    async def test_execute_success(self, tool):
        """Test successful execution with real test files"""
        params = ReadManyFilesParams(
            paths=["*.py", "*.js", "*.md"],
            useDefaultExcludes=False,
            file_filtering_options={'respect_git_ignore': False}
        )
        
        result = await tool.execute(params)
        
        assert isinstance(result, ToolResult)
        assert isinstance(result.llmContent, list)
        assert len(result.llmContent) > 0
        assert isinstance(result.returnDisplay, str)
        assert "ReadManyFiles Result" in result.returnDisplay
    
    @pytest.mark.asyncio
    async def test_execute_no_files_found(self, tool):
        """Test execution when no files match patterns"""
        params = ReadManyFilesParams(
            paths=["*.nonexistent"],
            useDefaultExcludes=False,
            file_filtering_options={'respect_git_ignore': False}
        )
        
        result = await tool.execute(params)
        
        assert isinstance(result, ToolResult)
        assert "No files found matching" in result.returnDisplay
    
    @pytest.mark.asyncio
    async def test_execute_parameter_validation_error(self, tool):
        """Test execution with parameter validation error"""
        params = ReadManyFilesParams(paths=[])
        
        result = await tool.execute(params)
        
        assert isinstance(result, ToolResult)
        assert "Error:" in result.llmContent[0]
        assert "required and cannot be empty" in result.returnDisplay
    
    @pytest.mark.asyncio
    async def test_execute_with_include_exclude(self, tool):
        """Test execution with include and exclude patterns"""
        params = ReadManyFilesParams(
            paths=["*"],
            include=["*.py"],
            exclude=["sample.py"],
            useDefaultExcludes=False,
            file_filtering_options={'respect_git_ignore': False}
        )
        
        result = await tool.execute(params)
        
        assert isinstance(result, ToolResult)
        # Should find files but exclude sample.py
        if result.llmContent != ['No files matching the criteria were found or all were skipped.']:
            assert any("sample.py" not in str(content) for content in result.llmContent)


class TestReadManyFilesConvenienceFunctions:
    """Test convenience functions"""
    
    @pytest.fixture
    def test_data_dir(self):
        """Get test data directory path"""
        current_dir = Path(__file__).parent
        return current_dir / "read_many_files" / "test_data"
    
    @pytest.mark.asyncio
    async def test_read_many_files_function(self, test_data_dir):
        """Test read_many_files convenience function"""
        params = ReadManyFilesParams(
            paths=["*.py"],
            useDefaultExcludes=False,
            file_filtering_options={'respect_git_ignore': False}
        )
        
        result = await read_many_files(params, str(test_data_dir))
        
        assert isinstance(result, ToolResult)
        assert isinstance(result.llmContent, list)
    
    @pytest.mark.asyncio
    async def test_read_files_by_patterns_function(self, test_data_dir):
        """Test read_files_by_patterns convenience function"""
        result = await read_files_by_patterns(
            paths=["*.json"],
            target_dir=str(test_data_dir),
            use_default_excludes=False,
            respect_git_ignore=False
        )
        
        assert isinstance(result, ToolResult)
        assert isinstance(result.llmContent, list)
        # Should find config.json
        if result.llmContent != ['No files matching the criteria were found or all were skipped.']:
            assert any("config.json" in str(content) for content in result.llmContent)


class TestFileProcessing:
    """Test file processing functionality"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def tool_with_temp_dir(self, temp_dir):
        """Create tool with temporary directory"""
        return ReadManyFilesTool(temp_dir)
    
    @pytest.mark.asyncio
    async def test_process_text_file(self, tool_with_temp_dir, temp_dir):
        """Test processing text file"""
        # Create test file
        test_file = Path(temp_dir) / "test.py"
        test_content = "def hello():\n    print('Hello, World!')\n"
        test_file.write_text(test_content)
        
        params = ReadManyFilesParams(
            paths=["test.py"],
            useDefaultExcludes=False,
            file_filtering_options={'respect_git_ignore': False}
        )
        
        result = await tool_with_temp_dir.execute(params)
        
        assert isinstance(result, ToolResult)
        assert len(result.llmContent) == 1
        assert test_content in result.llmContent[0]
        assert "test.py" in result.llmContent[0]
    
    @pytest.mark.asyncio
    async def test_process_empty_file(self, tool_with_temp_dir, temp_dir):
        """Test processing empty file"""
        # Create empty test file
        test_file = Path(temp_dir) / "empty.txt"
        test_file.write_text("")
        
        params = ReadManyFilesParams(
            paths=["empty.txt"],
            useDefaultExcludes=False,
            file_filtering_options={'respect_git_ignore': False}
        )
        
        result = await tool_with_temp_dir.execute(params)
        
        assert isinstance(result, ToolResult)
        assert len(result.llmContent) == 1
        assert "empty.txt" in result.llmContent[0]
    
    @pytest.mark.asyncio
    async def test_process_unicode_file(self, tool_with_temp_dir, temp_dir):
        """Test processing file with Unicode content"""
        # Create test file with Unicode content
        test_file = Path(temp_dir) / "unicode.txt"
        test_content = "Hello 世界! 🚀 Testing Unicode content."
        test_file.write_text(test_content, encoding='utf-8')
        
        params = ReadManyFilesParams(
            paths=["unicode.txt"],
            useDefaultExcludes=False,
            file_filtering_options={'respect_git_ignore': False}
        )
        
        result = await tool_with_temp_dir.execute(params)
        
        assert isinstance(result, ToolResult)
        assert len(result.llmContent) == 1
        assert test_content in result.llmContent[0]
    
    @pytest.mark.asyncio
    async def test_process_large_file_truncation(self, tool_with_temp_dir, temp_dir):
        """Test processing large file with content truncation"""
        # Create large test file
        test_file = Path(temp_dir) / "large.txt"
        # Create content with more than MAX_TEXT_LINES
        large_content = "\n".join([f"Line {i}" for i in range(3000)])
        test_file.write_text(large_content)
        
        params = ReadManyFilesParams(
            paths=["large.txt"],
            useDefaultExcludes=False,
            file_filtering_options={'respect_git_ignore': False}
        )
        
        result = await tool_with_temp_dir.execute(params)
        
        assert isinstance(result, ToolResult)
        assert len(result.llmContent) == 1
        assert "Content truncated" in result.llmContent[0]


class TestFiltering:
    """Test file filtering functionality"""
    
    @pytest.fixture
    def temp_dir_with_gitignore(self):
        """Create temporary directory with .gitignore file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create .gitignore file
            gitignore_path = Path(temp_dir) / ".gitignore"
            gitignore_content = "*.log\n__pycache__/\n*.pyc\n"
            gitignore_path.write_text(gitignore_content)
            
            # Create test files
            (Path(temp_dir) / "test.py").write_text("print('hello')")
            (Path(temp_dir) / "test.log").write_text("log content")
            (Path(temp_dir) / "test.pyc").write_text("compiled")
            
            yield temp_dir
    
    @pytest.mark.asyncio
    async def test_gitignore_filtering(self, temp_dir_with_gitignore):
        """Test .gitignore filtering"""
        tool = ReadManyFilesTool(temp_dir_with_gitignore)
        
        params = ReadManyFilesParams(
            paths=["*"],
            useDefaultExcludes=False,
            file_filtering_options={'respect_git_ignore': True}
        )
        
        result = await tool.execute(params)
        
        assert isinstance(result, ToolResult)
        # Should not include .log and .pyc files
        content_str = str(result.llmContent)
        assert "test.py" in content_str or "test.py" in result.returnDisplay
        assert "test.log" not in content_str
        assert "test.pyc" not in content_str
    
    @pytest.mark.asyncio
    async def test_gitignore_disabled(self, temp_dir_with_gitignore):
        """Test with .gitignore filtering disabled"""
        tool = ReadManyFilesTool(temp_dir_with_gitignore)
        
        params = ReadManyFilesParams(
            paths=["*"],
            useDefaultExcludes=False,
            file_filtering_options={'respect_git_ignore': False}
        )
        
        result = await tool.execute(params)
        
        assert isinstance(result, ToolResult)
        # Should include all files when gitignore is disabled
        content_str = str(result.llmContent) + result.returnDisplay
        assert "test.py" in content_str
        # Note: .log and .pyc might still be excluded by default excludes if enabled


class TestErrorHandling:
    """Test error handling scenarios"""
    
    @pytest.fixture
    def tool(self):
        """Create tool with current directory"""
        return ReadManyFilesTool()
    
    @pytest.mark.asyncio
    async def test_permission_error_handling(self, tool):
        """Test handling of permission errors"""
        # Mock file access to raise permission error
        with patch('os.path.getsize', side_effect=PermissionError("Permission denied")):
            params = ReadManyFilesParams(
                paths=["*.py"],
                useDefaultExcludes=False,
                file_filtering_options={'respect_git_ignore': False}
            )
            
            result = await tool.execute(params)
            
            assert isinstance(result, ToolResult)
            # Should handle the error gracefully
            assert isinstance(result.returnDisplay, str)
    
    @pytest.mark.asyncio
    async def test_file_not_found_handling(self, tool):
        """Test handling of file not found errors"""
        params = ReadManyFilesParams(
            paths=["/nonexistent/path/*.py"],
            useDefaultExcludes=False,
            file_filtering_options={'respect_git_ignore': False}
        )
        
        result = await tool.execute(params)
        
        assert isinstance(result, ToolResult)
        # Should handle gracefully when no files found
        assert "No files found" in result.returnDisplay or "No files matching" in result.returnDisplay


if __name__ == "__main__":
    # Run specific tests for demonstration
    pytest.main([__file__ + "::TestReadManyFilesTool::test_execute_success", "-v", "-s"])

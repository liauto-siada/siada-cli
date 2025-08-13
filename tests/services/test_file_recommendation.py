"""
Test file recommendation functionality.
"""

import os
import tempfile
import unittest
from pathlib import Path

from siada.services.file_recommendation import (
    FileRecommendationEngine,
    CompletionConfig,
    FileDiscoveryService,
    CompletionEngine
)
from siada.services.file_recommendation.utils.text_utils import (
    is_completion_active,
    parse_at_command_path,
    extract_at_path_from_text
)


class TestFileRecommendation(unittest.TestCase):
    """Test file recommendation functionality"""
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary test directory
        self.test_dir = tempfile.mkdtemp()
        
        # Create test file structure
        test_files = [
            "README.md",
            "config.json",
            "main.py",
            "utils.py",
            "src/app.py",
            "src/models.py", 
            "src/utils/helpers.py",
            "tests/test_main.py",
            "tests/test_utils.py",
            "docs/guide.md"
        ]
        
        for file_path in test_files:
            full_path = Path(self.test_dir) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(f"# Content of {file_path}")
        
        # Initialize engine with test directory
        config = CompletionConfig(
            max_results=20,
            enable_recursive_search=True,
            max_search_depth=3,
            respect_git_ignore=False  # Disable for testing
        )
        self.engine = FileRecommendationEngine(
            current_directory=self.test_dir,
            config=config
        )
    
    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_basic_at_detection(self):
        """Test basic @ detection functionality"""
        test_cases = [
            ("@", 0, 1, True),           # Basic @ character
            ("hello @", 0, 7, True),     # @ with text before
            ("@file", 0, 5, True),       # @ with filename after
            ("no at symbol", 0, 12, False),   # No @ character
        ]
        
        for text, row, col, expected in test_cases:
            lines = text.split('\n')
            result = is_completion_active(text, row, col, lines)
            assert result == expected, f"Failed for: {text}"
    
    def test_path_parsing(self):
        """Test path parsing functionality"""
        test_cases = [
            ("@file.txt", (".", "file.txt", "file.txt")),
            ("@src/", (".", "src/", "src/")),
            ("@src/main.py", (".", "src/main.py", "src/main.py")),
            ("hello @world", (".", "world", "world")),
        ]
        
        for input_text, expected in test_cases:
            base_dir, prefix, partial = parse_at_command_path(input_text)
            result = (base_dir, prefix, partial)
            assert result == expected, f"Failed for: {input_text}, got {result}, expected {expected}"
    
    def test_extract_at_path(self):
        """Test @ path extraction"""
        test_cases = [
            ("@file.py", "@file.py"),
            ("hello @world test", "@world"),
            ("@src/main.py more text", "@src/main.py"),
            ("no at symbol", None),
        ]
        
        for input_text, expected in test_cases:
            result = extract_at_path_from_text(input_text)
            assert result == expected, f"Failed for: {input_text}"
    
    def test_should_show_suggestions(self):
        """Test suggestion trigger logic"""
        test_cases = [
            ("@", False),               # Just @ should not show
            ("@file", True),            # @ with content should show
            ("@src/", True),            # @ with directory should show
            ("hello", False),           # No @ should not show
        ]
        
        for text, expected in test_cases:
            result = self.engine.should_show_suggestions(text)
            assert result == expected, f"Failed for: {text}"
    
    def test_basic_file_suggestions(self):
        """Test basic file suggestions"""
        # Test getting suggestions for files starting with 'm'
        suggestions = self.engine.get_suggestions_sync("@m")
        
        # Should find main.py
        labels = [s['label'] for s in suggestions]
        assert any('main.py' in label for label in labels), f"main.py not found in {labels}"
    
    def test_directory_suggestions(self):
        """Test directory suggestions"""
        # Test getting suggestions for directories starting with 's'
        suggestions = self.engine.get_suggestions_sync("@s")
        
        # Should find src/ directory
        labels = [s['label'] for s in suggestions]
        assert any('src/' in label for label in labels), f"src/ not found in {labels}"
    
    def test_recursive_search(self):
        """Test recursive search functionality"""
        # Search for files with 'test' in the name
        suggestions = self.engine.get_suggestions_sync("@test")
        
        # Should find files in tests/ directory
        labels = [s['label'] for s in suggestions]
        # Should find test files in subdirectories
        assert len([l for l in labels if 'test' in l.lower()]) > 0, f"No test files found in {labels}"
    
    def test_path_with_directory(self):
        """Test suggestions within specific directory"""
        # Test getting suggestions for files in src/ directory
        suggestions = self.engine.get_suggestions_sync("@src/")
        
        labels = [s['label'] for s in suggestions]
        # Should include files from src directory (checking for files that contain these names)
        has_src_files = any(
            'app.py' in label or 'models.py' in label or 'utils/' in label 
            for label in labels
        )
        assert has_src_files, f"No src directory files found in {labels}"
    
    def test_config_updates(self):
        """Test configuration updates"""
        # Test updating max results
        new_config = CompletionConfig(max_results=5)
        self.engine.completion_engine.update_config(new_config)
        
        suggestions = self.engine.get_suggestions_sync("@")
        assert len(suggestions) <= 5, f"Too many suggestions returned: {len(suggestions)}"
    
    def test_error_handling(self):
        """Test error handling"""
        # Test with invalid directory
        invalid_engine = FileRecommendationEngine("/nonexistent/directory")
        
        # Should not crash and return empty results
        suggestions = invalid_engine.get_suggestions_sync("@test")
        assert isinstance(suggestions, list), "Should return a list even on error"
    
    def test_file_discovery_service(self):
        """Test file discovery service directly"""
        from siada.services.file_recommendation.core.config import FilterOptions
        
        service = FileDiscoveryService(self.test_dir)
        filter_options = FilterOptions(respect_git_ignore=False)
        
        # Test finding files in directory
        suggestions = service.find_files_in_directory(
            self.test_dir,
            "m",
            filter_options,
            10
        )
        
        labels = [s['label'] for s in suggestions]
        assert any('main.py' in label for label in labels), f"main.py not found in {labels}"
    
    def test_completion_engine_directly(self):
        """Test completion engine directly"""
        config = CompletionConfig(max_results=10)
        engine = CompletionEngine([self.test_dir], config)
        
        # Test getting suggestions
        suggestions = engine.get_suggestions_sync("@README")
        
        labels = [s['label'] for s in suggestions]
        assert any('README.md' in label for label in labels), f"README.md not found in {labels}"


if __name__ == "__main__":
    unittest.main()

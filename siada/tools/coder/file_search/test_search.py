"""
Simple test script to verify the file_search functionality.
"""

import os
import tempfile
from pathlib import Path
try:
    from .search import regex_search_files, RipgrepSearcher
except ImportError:
    from search import regex_search_files, RipgrepSearcher


def create_test_files():
    """Create temporary test files for testing."""
    test_dir = Path(tempfile.mkdtemp())
    
    # Create test Python file
    python_file = test_dir / "test.py"
    python_file.write_text("""
def hello_world():
    # TODO: Add proper greeting
    print("Hello, World!")
    return "success"

class TestClass:
    def __init__(self):
        # FIXME: Initialize properly
        self.value = 42
    
    def process_data(self, data):
        # TODO: Implement data processing
        return data * 2
""")
    
    # Create test JavaScript file
    js_file = test_dir / "test.js"
    js_file.write_text("""
function greet(name) {
    // TODO: Add validation
    console.log(`Hello, ${name}!`);
}

const utils = {
    // FIXME: Add error handling
    multiply: (a, b) => a * b
};
""")
    
    return test_dir


def test_basic_functionality():
    """Test basic search functionality."""
    print("Creating test files...")
    test_dir = create_test_files()
    searcher = RipgrepSearcher()
    try:
        print(f"Test directory: {test_dir}")
        
        # Test 1: Search for TODO comments in Python files
        print("\n=== Test 1: Search for TODO comments in Python files ===")
        try:
            results = searcher.search_in_files(
                cwd=str(test_dir),
                directory_path=str(test_dir),
                regex=r"TODO:",
                file_pattern="*.py"
            )
            print(results)
        except RuntimeError as e:
            print(f"Error: {e}")
            print("Note: This error is expected if ripgrep binary is not installed.")
        
        # Test 2: Search for function definitions
        print("\n=== Test 2: Search for function definitions ===")
        try:

            results = searcher.search_in_files(
                directory_path=str(test_dir),
                regex=r"def\s+\w+\(|function\s+\w+\(",
                file_pattern="*",
                cwd=str(test_dir)
            )
            print(results)
        except RuntimeError as e:
            print(f"Error: {e}")
            print("Note: This error is expected if ripgrep binary is not installed.")
        
        # Test 3: Search for all TODO/FIXME comments
        print("\n=== Test 3: Search for all TODO/FIXME comments ===")
        try:
            searcher = RipgrepSearcher()
            results = searcher.search_in_files(
                directory_path=str(test_dir),
                regex=r"TODO:|FIXME:",
                file_pattern="*",
                cwd=str(test_dir)
            )
            print(results)
        except RuntimeError as e:
            print(f"Error: {e}")
            print("Note: This error is expected if ripgrep binary is not installed.")
            
    finally:
        # Clean up test files
        import shutil
        shutil.rmtree(test_dir)
        print(f"\nCleaned up test directory: {test_dir}")


def test_binary_detection():
    """Test ripgrep binary detection."""
    print("\n=== Binary Detection Test ===")
    try:
        searcher = RipgrepSearcher()
        print(f"✓ Ripgrep binary found at: {searcher.rg_path}")
        return True
    except RuntimeError as e:
        print(f"✗ {e}")
        print("\nTo fix this:")
        print("1. Download ripgrep from: https://github.com/BurntSushi/ripgrep/releases")
        print("2. Place the binary in file_search/bin/ directory")
        print("3. Rename according to platform (see README.md)")
        print("4. Set execute permissions on Unix systems: chmod +x file_search/bin/rg-*")
        return False


if __name__ == "__main__":
    """
    运行测试用例需要先注释掉 search.py 中的 @function_tool注解
    """
    print("File Search - Test Script")
    print("=" * 40)
    
    # Test binary detection first
    if test_binary_detection():
        # If binary is found, run functionality tests
        test_basic_functionality()
    else:
        print("\nSkipping functionality tests due to missing ripgrep binary.")
        print("Please install ripgrep binary as described above and try again.")

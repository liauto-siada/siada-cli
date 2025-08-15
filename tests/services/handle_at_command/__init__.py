"""
HandleAtCommand Test Suite

This package contains comprehensive tests for the HandleAtCommand functionality.

Test Structure:
- test_parser.py: Tests for AtCommandParser (@ command parsing)
- test_processor.py: Tests for AtCommandProcessor (main workflow)
- test_resolver.py: Tests for PathResolver (path resolution and security)
- test_integration.py: End-to-end integration tests
- demo_handle_at_command.py: Interactive demonstration
- run_all_tests.py: Complete test suite runner

Test Data:
- test_data/: Sample files for testing
  - sample.py: Python file with functions and classes
  - config.json: JSON configuration file
  - README.md: Markdown documentation
  - nested_dirs/deep_file.txt: File in nested directory

Usage:
    # Run individual test files
    python test_parser.py
    python test_processor.py
    python test_resolver.py
    python test_integration.py
    
    # Run all tests
    python run_all_tests.py
    
    # Run demo
    python demo_handle_at_command.py

Test Coverage:
✅ @ Command parsing (various formats)
✅ Path resolution (direct, fuzzy, directory)
✅ File content injection
✅ Error handling and recovery
✅ Security validation (path traversal, workspace boundaries)
✅ Integration with ReadManyFilesTool
✅ Concurrent processing
✅ Performance testing
✅ Real file system operations
"""

__all__ = [
    'TestAtCommandParser',
    'TestAtCommandProcessor', 
    'TestAtCommandProcessorAsync',
    'TestPathResolver',
    'TestPathResolverSecurity',
    'TestHandleAtCommandIntegration',
    'TestHandleAtCommandRealFileSystem'
]

# AST Tool Tests

This directory contains comprehensive tests for the `_list_code_definition_names` method in `siada/tools/ast/ast_tool.py`.

## Test Structure

### Test Files
- `test_ast_tool.py` - Main test file containing all test cases
- `test_data/` - Directory containing test data files

### Test Data Files
- `complex_python_file.py` - Complex Python file with multiple classes, methods, and advanced features (40+ line methods)
- `simple_python_file.py` - Simple Python file with basic functions and classes
- `javascript_file.js` - JavaScript file for cross-language testing
- `empty_file.py` - Empty Python file
- `unsupported_file.txt` - Plain text file (unsupported format)

## Test Coverage

### Functional Tests
1. **Complex Python File Parsing** - Tests parsing of complex Python files with:
   - Multiple classes with inheritance and decorators
   - Various method types (async, static, class methods)
   - Context managers and generators
   - Type annotations and complex parameter lists
   - Methods with 40+ lines of code

2. **Simple Python File Parsing** - Tests basic Python constructs
3. **JavaScript File Parsing** - Tests cross-language support
4. **Empty File Handling** - Tests handling of empty files
5. **Unsupported File Types** - Tests handling of non-code files

### Edge Cases and Error Handling
6. **Nonexistent File Error** - Tests file not found scenarios
7. **Permission Error Handling** - Tests file permission issues
8. **Large File Handling** - Tests performance with files containing many definitions
9. **Special Characters in Filenames** - Tests Unicode and special character support
10. **Syntax Error Handling** - Tests resilience to malformed code
11. **Unicode Content Handling** - Tests international character support

### Output Format Tests
12. **Relative Filename Parameter** - Tests custom relative path handling
13. **Output Format Structure** - Validates output format consistency
14. **Definitions and References Count** - Tests accuracy of statistics
15. **Fallback to Simple List Format** - Tests fallback when tree parsing fails
16. **Method Return Type** - Validates return type consistency

### Integration Tests
17. **No Definitions Found Case** - Tests files with only variables/comments
18. **Comprehensive Integration** - Tests all file types together

## Complex Test Data Features

The `complex_python_file.py` test file includes:

### Classes and Inheritance
- `DataModel` - Dataclass with type annotations
- `BaseProcessor` - Abstract base class with abstract methods
- `DataAnalyzer` - Complex data processing class
- `MLModelTrainer` - Machine learning model trainer
- `WebCrawler` - Asynchronous web crawler
- `FileProcessor` - File processing with context managers

### Complex Methods (40+ lines each)
- `complex_data_processing_method` - Data filtering, transformation, and aggregation
- `train_complex_model` - ML model training with validation and callbacks
- `crawl_website_comprehensive` - Async web crawling with error handling
- `process_large_file_batch` - Parallel file processing with progress tracking

### Advanced Python Features
- Async/await patterns
- Context managers
- Decorators (@dataclass, @abstractmethod, @classmethod, @staticmethod)
- Type hints and annotations
- Exception handling
- Concurrent processing
- Generator functions
- Multiple inheritance

## Running Tests

```bash
# Run all AST tool tests
pytest tests/tools/ast/test_ast_tool.py -v

# Run specific test
pytest tests/tools/ast/test_ast_tool.py::TestListCodeDefinitionNames::test_complex_python_file_parsing -v

# Run with coverage
pytest tests/tools/ast/test_ast_tool.py --cov=siada.tools.ast.ast_tool
```

## Test Results

All 18 test cases pass successfully, providing comprehensive coverage of:
- ✅ Normal functionality with various file types
- ✅ Error handling and edge cases
- ✅ Output format validation
- ✅ Performance with large files
- ✅ Unicode and international character support
- ✅ Complex code structure parsing

## Notes

- Tests use temporary directories to avoid file system pollution
- Mock objects are used for testing error conditions
- Test data includes files with intentional complexity to thoroughly test AST parsing capabilities
- The test suite validates both successful parsing and graceful error handling

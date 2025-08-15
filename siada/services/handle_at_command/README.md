# HandleAtCommand Service

A comprehensive service for processing @ commands in user queries, enabling intelligent file content injection into AI context.

## Overview

The HandleAtCommand service allows users to reference files using simple `@` syntax in their queries. The service automatically:

1. **Parses** user input to extract @ commands
2. **Resolves** file paths using intelligent matching
3. **Reads** file contents using the existing ReadManyFiles tool
4. **Injects** content into the AI context seamlessly

## Features

### 🎯 Core Functionality
- **Smart Path Resolution**: Direct matching, fuzzy search, directory expansion
- **Multiple File Support**: Handle multiple @ commands in a single query
- **Content Injection**: Automatic file content integration into AI context
- **Error Handling**: Graceful handling of missing or inaccessible files

### 🔍 Supported @ Command Formats
- `@filename.ext` - Single file reference
- `@path/to/file.ext` - Relative path file reference
- `@directory/` - Directory reference (converted to glob pattern)
- `@my\ file.txt` - Files with spaces (escaped)
- `请解释 @file1.js 和 @file2.py` - Mixed text and file references

### 🛡️ Security Features
- **Workspace Boundary Checking**: Ensures files are within allowed directories
- **Path Traversal Protection**: Prevents `../` attacks
- **Git Ignore Support**: Respects .gitignore rules
- **File Size Limits**: Prevents reading of excessively large files

## Architecture

```
HandleAtCommand/
├── processor.py          # Main coordinator (AtCommandProcessor)
├── parser.py            # @ command parsing (AtCommandParser)
├── resolver.py          # Path resolution (PathResolver)
├── models.py            # Data structures
├── exceptions.py        # Custom exceptions
├── utils.py            # Utility functions
└── __init__.py         # Package interface
```

### Component Responsibilities

#### AtCommandProcessor
- **Main Entry Point**: Coordinates all components
- **File Reading**: Integrates with ReadManyFilesTool
- **Query Reconstruction**: Builds final processed query
- **Statistics Tracking**: Monitors processing metrics

#### AtCommandParser
- **Input Parsing**: Extracts @ commands from user queries
- **Escape Handling**: Processes escaped characters in paths
- **Content Extraction**: Parses file content from tool output

#### PathResolver
- **Path Resolution**: Converts @ paths to actual file paths
- **Security Validation**: Ensures paths are safe and within workspace
- **Fuzzy Matching**: Provides glob-based search for partial matches
- **Directory Handling**: Converts directories to appropriate glob patterns

## Usage

### Basic Usage

```python
from siada.services.handle_at_command import AtCommandProcessor, HandleAtCommandParams

# Initialize processor
processor = AtCommandProcessor(config)

# Create parameters
params = HandleAtCommandParams(
    query="Please explain @main.py and @config.json",
    config=config,
    add_item=add_item_function,
    on_debug_message=debug_function,
    message_id=123
)

# Process @ commands
result = await processor.handle_at_command(params)

if result.should_proceed:
    # Use result.processed_query for AI context
    print("Processed query:", result.processed_query)
```

### Convenience Function

```python
from siada.services.handle_at_command import handle_at_command

result = await handle_at_command(
    query="Show me @file.py",
    config=config,
    add_item=add_item_function,
    on_debug_message=debug_function,
    message_id=123
)
```

## Configuration

### Required Configuration Properties

```python
class Config:
    root_dir: str  # Root directory for file operations
    
    # Optional: Additional workspace directories
    # Optional: File filtering options
    # Optional: Enable recursive search
```

### File Filtering Options

```python
file_filtering_options = {
    'respect_git_ignore': True,  # Respect .gitignore rules
    # Add more filtering options as needed
}
```

## Examples

### Single File Reference
```
Input:  "Explain @main.py"
Output: Query with main.py content injected
```

### Multiple Files
```
Input:  "Compare @file1.py and @file2.py"
Output: Query with both files' content injected
```

### Directory Reference
```
Input:  "Show me @src/"
Output: Query with all files in src/ directory
```

### Mixed Content
```
Input:  "The function in @utils.py needs to handle @config.json"
Output: Query with both files' content injected
```

### Fuzzy Matching
```
Input:  "Check @main"
Output: Finds and includes main.py (if it exists)
```

## Error Handling

The service handles various error conditions gracefully:

- **File Not Found**: Attempts fuzzy search, reports if not found
- **Permission Denied**: Skips file, continues with others
- **Path Outside Workspace**: Security violation, file skipped
- **File Too Large**: Respects size limits, skips oversized files

## Testing

### Running Tests

```bash
# Run parser tests
cd tests/services/handle_at_command
python test_parser.py

# Run demo
python demo_handle_at_command.py
```

### Test Coverage

- ✅ @ Command parsing (various formats)
- ✅ Path resolution (direct, fuzzy, directory)
- ✅ File content injection
- ✅ Error handling
- ✅ Security validation
- ✅ Integration with ReadManyFilesTool

## Performance Considerations

### Optimization Features
- **Concurrent Processing**: Multiple files processed in parallel
- **Intelligent Caching**: Avoids re-reading unchanged files
- **Content Limits**: Respects file size and line count limits
- **Early Exit**: Skips processing if no @ commands found

### Performance Metrics
- Processing time tracking
- File read statistics
- Path resolution success rates
- Error categorization

## Integration Points

### Dependencies
- **ReadManyFilesTool**: For actual file reading
- **FileFilter**: For .gitignore and filtering support
- **PathLib**: For cross-platform path handling

### Extension Points
- Custom path resolvers
- Additional file type support
- Enhanced security policies
- Custom content formatters

## Future Enhancements

### Planned Features
- **Caching Layer**: Persistent file content caching
- **Advanced Filtering**: More sophisticated ignore rules
- **Content Preprocessing**: Syntax highlighting, formatting
- **Batch Operations**: Optimized multi-file processing
- **Plugin System**: Extensible resolver and formatter plugins

### Potential Improvements
- **AI-Powered Matching**: Semantic file matching
- **Context-Aware Resolution**: Smart path suggestions
- **Real-time Updates**: File change monitoring
- **Performance Analytics**: Detailed performance insights

## Contributing

When contributing to this service:

1. **Follow Architecture**: Maintain separation of concerns
2. **Add Tests**: Include unit tests for new functionality
3. **Update Documentation**: Keep README and docstrings current
4. **Security First**: Consider security implications of changes
5. **Performance Aware**: Monitor impact on processing speed

## License

This service is part of the Siada project and follows the project's licensing terms.

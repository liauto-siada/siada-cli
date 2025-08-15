# ReadManyFiles Tool

A powerful tool for batch reading multiple files with intelligent filtering and support for various file types.

## Features

- **Batch File Reading**: Read multiple files using glob patterns
- **Intelligent Filtering**: Built-in support for .gitignore rules and default exclusion patterns
- **Multiple File Types**: Support for text files, images, and PDFs
- **Async Processing**: Concurrent file processing for better performance
- **Security**: Path validation to ensure files are within workspace
- **Detailed Reporting**: Comprehensive statistics and error reporting

## Quick Start

### Basic Usage

```python
import asyncio
from siada.tools.read_many_files_tool import read_files_by_patterns

async def main():
    # Read all Python files in current directory
    result = await read_files_by_patterns(
        paths=["*.py"],
        target_dir="."
    )
    
    print(f"Found {len(result.llmContent)} files")
    print(result.returnDisplay)

asyncio.run(main())
```

### Advanced Usage

```python
from siada.tools.read_many_files_tool import ReadManyFilesTool
from siada.tools.read_many_files.models import ReadManyFilesParams

async def advanced_example():
    # Create tool instance
    tool = ReadManyFilesTool("/path/to/project")
    
    # Configure parameters
    params = ReadManyFilesParams(
        paths=["src/**/*.py", "docs/*.md"],
        include=["*.test.py"],
        exclude=["**/node_modules/**", "**/__pycache__/**"],
        useDefaultExcludes=True,
        file_filtering_options={
            'respect_git_ignore': True
        }
    )
    
    # Execute
    result = await tool.execute(params)
    
    # Process results
    for content in result.llmContent:
        if isinstance(content, str):
            print("Text file content:", content[:100] + "...")
        else:
            print("Binary file:", content.get('type', 'unknown'))
```

## Parameters

### ReadManyFilesParams

- **paths** (List[str], required): File paths or glob patterns
- **include** (List[str], optional): Additional include patterns
- **exclude** (List[str], optional): Exclude patterns
- **recursive** (bool, default=True): Whether to search recursively
- **useDefaultExcludes** (bool, default=True): Apply default exclusion patterns
- **file_filtering_options** (Dict[str, bool], optional): Filtering configuration

### Glob Patterns

The tool supports standard glob patterns:

- `*.py` - All Python files in current directory
- `**/*.py` - All Python files recursively
- `src/**/*.js` - All JavaScript files in src directory and subdirectories
- `docs/*.md` - All Markdown files in docs directory

## File Type Support

### Text Files

Supported extensions: `.py`, `.js`, `.ts`, `.md`, `.txt`, `.json`, `.yaml`, `.xml`, `.html`, `.css`, and many more.

Text files are read with automatic encoding detection and include content truncation for large files.

### Image Files

Supported extensions: `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.webp`, `.svg`

Images are converted to base64-encoded Part objects for LLM processing. Must be explicitly requested by filename or extension.

### PDF Files

Supported extension: `.pdf`

PDFs are converted to Part objects for LLM processing. Must be explicitly requested by filename.

## Filtering

### Default Excludes

The tool automatically excludes common non-source files:

- Dependency directories: `node_modules`, `__pycache__`, `venv`
- Version control: `.git`, `.svn`
- IDE files: `.vscode`, `.idea`
- Build outputs: `dist`, `build`, `target`
- Binary files: `.exe`, `.dll`, `.so`
- Compressed files: `.zip`, `.tar`, `.gz`

### Git Ignore Support

The tool respects `.gitignore` files by default. This can be disabled by setting:

```python
file_filtering_options={'respect_git_ignore': False}
```

## Output Format

### ToolResult

The tool returns a `ToolResult` object with:

- **llmContent**: List of file contents (strings for text, Part objects for binary)
- **returnDisplay**: Human-readable summary with statistics

### Text File Format

Text files are formatted with separators:

```
--- /path/to/file.py ---

def hello():
    print("Hello, World!")

```

## Error Handling

The tool gracefully handles various error conditions:

- File not found
- Permission denied
- Encoding errors
- Large files (automatic truncation)
- Binary files (skipped unless explicitly requested)

## Performance

- **Concurrent Processing**: Files are processed concurrently with configurable limits
- **Memory Efficient**: Large files are truncated to prevent memory issues
- **Caching**: Git ignore rules are cached for better performance

## Examples

### Read Configuration Files

```python
result = await read_files_by_patterns(
    paths=["*.json", "*.yaml", "*.toml"],
    target_dir="/path/to/config"
)
```

### Read Source Code (Excluding Tests)

```python
result = await read_files_by_patterns(
    paths=["src/**/*.py"],
    exclude=["**/test_*.py", "**/tests/**"],
    target_dir="/path/to/project"
)
```

### Read Documentation

```python
result = await read_files_by_patterns(
    paths=["docs/**/*.md", "README.md"],
    target_dir="/path/to/project"
)
```

### Read Images (Explicit Request)

```python
result = await read_files_by_patterns(
    paths=["assets/*.png", "images/*.jpg"],
    target_dir="/path/to/project"
)
```

## Testing

Run the test suite:

```bash
pytest tests/tools/test_read_many_files_tool.py -v
```

Run specific tests:

```bash
pytest tests/tools/test_read_many_files_tool.py::TestReadManyFilesTool::test_execute_success -v
```

## License

This tool is part of the siada-agenthub project.

# File Search - High-Performance File Search Tool

A Python file search module based on ripgrep, providing fast and accurate code search functionality.

## Features

- **High-Performance Search**: Uses ripgrep tool, several times faster than traditional regex search
- **Context Information**: Provides context around matching lines
- **File Filtering**: Supports glob pattern filtering for specific file types
- **Cross-Platform Support**: Supports Windows, macOS, Linux
- **Package-Friendly**: Supports both development environment and packaged distribution
- **Auto Fallback**: Prioritizes built-in binary files, can fallback to system installation

## Quick Start

### Basic Usage

```python
from file_search import regex_search_files

# Search for TODO comments
results = regex_search_files(
    cwd="/path/to/project",
    directory_path="/path/to/search", 
    regex=r"TODO:",
    file_pattern="*.py"
)
print(results)
```

### Class Interface

```python
from file_search import RipgrepSearcher

searcher = RipgrepSearcher()
results = searcher.search_in_files(
    directory_path="./siada",
    regex=r"def\s+\w+\(",
    file_pattern="*.py",
    cwd="/path/to/project"
)
```

## Installation and Configuration

### Automatic Configuration (Recommended)

The tool automatically searches for ripgrep binary files in the following priority order:

1. `RIPGREP_BINARY_PATH` environment variable
2. Built-in binary files (development/packaging environment)
3. ripgrep in system PATH

### Manual Configuration

To specify a specific ripgrep path:

```bash
export RIPGREP_BINARY_PATH="/path/to/rg"
```

### Binary Files

Built-in support for binary files on the following platforms:
- Windows: `rg.exe`
- macOS Intel: `rg-macos-x64`
- macOS Apple Silicon: `rg-macos-arm64`
- Linux x64: `rg-linux-x64`
- Linux ARM64: `rg-linux-arm64`

## Usage Examples

### Search Code Comments
```python
# Search for TODO/FIXME comments
regex_search_files(".", ".", r"TODO:|FIXME:|HACK:", "*.py")
```

### Search Functions and Classes
```python
# Search for function definitions
regex_search_files(".", ".", r"def\s+\w+\(", "*.py")

# Search for class definitions
regex_search_files(".", ".", r"class\s+\w+", "*.py")
```

### Search Import Statements
```python
regex_search_files(".", ".", r"^import\s+|^from\s+\w+\s+import", "*.py")
```

### Multi-File Type Search
```python
regex_search_files(".", ".", r"console\.log", "*.{js,ts}")
```

## Output Format

```
Found 2 results.

src/main.py
│----
│def process_data(data):
│    # TODO: Add error handling
│    return data
│----

src/utils.py
│----
│class Helper:
│    def __init__(self):
│        # TODO: Initialize properly
│        pass
│----
```

## Parameter Description

- **cwd**: Current working directory, used to calculate relative paths
- **directory_path**: Directory path to search
- **regex**: Regular expression pattern (Rust syntax)
- **file_pattern**: File pattern filter (e.g., "*.py", "*.js", "*")

## Regular Expression Syntax

Uses Rust regular expression syntax with main features:
- Unicode support
- Multi-line mode by default
- Supports lookahead and lookbehind assertions
- Detailed syntax: https://docs.rs/regex/latest/regex/#syntax

## Performance Characteristics

- **Result Limit**: Returns maximum 300 results
- **Output Limit**: Prevents excessive memory usage
- **Context Control**: Provides 1 line of context before and after each match

## Package Distribution

### Package Configuration

Add to `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"src.tools.coder.file_search" = ["bin/*", "README.md"]

[tool.setuptools.packages.find]
where = ["src"]
include = ["src.tools.coder.file_search*"]
```

### Verify Packaging

```bash
# Run packaging check
python siada/tools/coder/file_search/setup_package.py

# Test functionality
python siada/tools/coder/file_search/test_search.py
```

## Troubleshooting

### Common Issues

**Cannot find ripgrep binary file**
- Set environment variable: `export RIPGREP_BINARY_PATH="/path/to/rg"`
- Install system ripgrep: `brew install ripgrep` (macOS) or `apt install ripgrep` (Ubuntu)

**Permission errors**
- Unix systems: `chmod +x file_search/bin/rg-*`

**No search results**
- Check search path and regular expression syntax
- Confirm file pattern matches target files

### Debugging

```python
from file_search.search import RipgrepSearcher

try:
    searcher = RipgrepSearcher()
    print(f"Ripgrep binary: {searcher.rg_path}")
except RuntimeError as e:
    print(f"Error: {e}")
```

## Docker Environment

```dockerfile
# Install system ripgrep
RUN apt-get update && apt-get install -y ripgrep

# Or set environment variable
ENV RIPGREP_BINARY_PATH=/usr/bin/rg
```

## Testing

Run test cases:

```bash
python siada/tools/coder/file_search/test_search.py
```

Tests include:
- Binary file detection
- Basic search functionality
- File type filtering
- Error handling mechanisms

## Technical Details

- Based on ripgrep high-performance search engine
- Supports automatic adaptation for development and packaging environments
- Automatic permission repair mechanism
- Multi-path search strategy
- Graceful error handling and fallback mechanisms

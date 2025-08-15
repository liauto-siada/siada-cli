# Test Project

This is a test project for demonstrating @ command functionality.

## Files

- `sample.py` - A Python file with functions and classes
- `config.json` - Configuration file with JSON data
- `nested_dirs/` - Directory with nested files

## Features

- @ command parsing
- File content injection
- Path resolution testing
- Security validation

## Usage

This test data is used by the HandleAtCommand test suite to verify:

1. Single file references (`@sample.py`)
2. Multiple file references (`@sample.py` and `@config.json`)
3. Directory references (`@nested_dirs/`)
4. Fuzzy matching (`@sample` should find `sample.py`)
5. Error handling (non-existent files)

## Test Scenarios

### Basic Functionality
- Read single file
- Read multiple files
- Handle mixed content

### Path Resolution
- Direct path matching
- Fuzzy search
- Directory expansion

### Error Handling
- File not found
- Permission denied
- Path outside workspace

### Security
- Path traversal prevention
- Workspace boundary enforcement

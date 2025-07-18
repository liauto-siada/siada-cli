# AST Code Definition Extraction Tool

This module provides code definition extraction functionality based on tree-sitter and pygments, primarily used for analyzing source code files and extracting function, class, method, and other definition information.

## Main Features

### `_list_code_definition_names(fname, rel_fname=None)`

Parses a source code file and returns a summary of its code definitions.

#### Parameters
- `fname` (str): Absolute path to the source file
- `rel_fname` (str, optional): Relative path to the source file, defaults to filename

#### Returns
- `str`: Formatted string containing file structure and code definitions

## Parsing Principles

### 1. Dual Parsing Strategy
- **Primary Parser**: Uses tree-sitter for syntax tree parsing, providing precise code structure analysis
- **Fallback Parser**: Uses pygments for lexical analysis as a backup for reference extraction

### 2. Parsing Workflow
1. **Language Detection**: Identifies programming language based on file extension
2. **Syntax Parsing**: Uses tree-sitter to build Abstract Syntax Tree (AST)
3. **Query Execution**: Runs predefined query patterns to extract definitions and references
4. **Fallback Processing**: Uses pygments to supplement reference information if only definitions are found
5. **Format Output**: Uses TreeContext to generate code tree structure with context

### 3. Core Components
- **Tag Model**: Data structure representing code identifiers
- **TreeContext**: Provides code context and formatting functionality
- **Query Files**: .scm files stored in `siada/queries/` directory, defining parsing rules for each language

## Supported Programming Languages

Based on tree-sitter language support, including but not limited to:

### Fully Supported Languages
- **Python** (.py) - functions, classes, methods, decorators, async functions, etc.
- **JavaScript** (.js) - functions, classes, arrow functions, object methods, etc.
- **TypeScript** (.ts) - type definitions, interfaces, classes, functions, etc.
- **Java** (.java) - classes, methods, interfaces, enums, etc.
- **C/C++** (.c, .cpp, .h, .hpp) - functions, structs, classes, etc.
- **Go** (.go) - functions, structs, methods, interfaces, etc.
- **Rust** (.rs) - functions, structs, traits, impl, etc.
- **Ruby** (.rb) - classes, methods, modules, etc.

### Partially Supported Languages
- **C#** (.cs) - classes, methods, properties, etc.
- **PHP** (.php) - classes, functions, methods, etc.
- **Scala** (.scala) - classes, objects, traits, methods, etc.
- **Kotlin** (.kt) - classes, functions, objects, etc.

### Query File Locations
- `siada/queries/tree-sitter-language-pack/` - Primary query files
- `siada/queries/tree-sitter-languages/` - Fallback query files

## Output Formats

### 1. Standard Format (when definitions exist)
```
File: <filename>
Definitions: <definition_count>, References: <reference_count>

<code_tree_structure>
```

### 2. Simplified Format (fallback mode)
```
File: <filename>
Definitions: <definition_count>, References: <reference_count>

Definitions found:
  - <definition_name> (line <line_number>)
  - <definition_name> (line <line_number>)
  ...
```

### 3. Error Format (no definitions or errors)
```
No code definitions found in <filename>
```

## Output Examples

### Python File Example

**Input File** (`calculator.py`):
```python
"""A simple calculator module with multiple classes and functions."""

class Calculator:
    """Basic calculator with arithmetic operations."""
    
    def __init__(self):
        self.history = []
    
    def add(self, a, b):
        result = a + b
        self.history.append(f"{a} + {b} = {result}")
        return result
    
    def multiply(self, a, b):
        result = a * b
        self.history.append(f"{a} * {b} = {result}")
        return result

class ScientificCalculator(Calculator):
    """Extended calculator with scientific functions."""
    
    def power(self, base, exponent):
        result = base ** exponent
        self.history.append(f"{base} ^ {exponent} = {result}")
        return result

def create_calculator(scientific=False):
    """Factory function to create calculator instances."""
    if scientific:
        return ScientificCalculator()
    return Calculator()

# Global configuration
DEFAULT_PRECISION = 2
```

**Parsed Output**:
```
File: calculator.py
Definitions: 6, References: 15

⋮
│class Calculator:
│    """Basic calculator with arithmetic operations."""
│
│    def __init__(self):
⋮
│    def add(self, a, b):
⋮
│    def multiply(self, a, b):
⋮
│class ScientificCalculator(Calculator):
│    """Extended calculator with scientific functions."""
│
│    def power(self, base, exponent):
⋮
│def create_calculator(scientific=False):
⋮
```

**Key Differences from Source**:
- Shows only definition signatures, omitting implementation details
- Displays statistical summary (6 definitions, 15 references)
- Uses `⋮` to indicate omitted code sections
- Focuses on structural overview rather than complete code

### JavaScript File Example

**Input File** (`user-manager.js`):
```javascript
/**
 * User management system with authentication
 */

class User {
    constructor(username, email) {
        this.username = username;
        this.email = email;
        this.isActive = true;
    }
    
    activate() {
        this.isActive = true;
        console.log(`User ${this.username} activated`);
    }
    
    deactivate() {
        this.isActive = false;
        console.log(`User ${this.username} deactivated`);
    }
}

class UserManager {
    constructor() {
        this.users = new Map();
    }
    
    addUser(username, email) {
        const user = new User(username, email);
        this.users.set(username, user);
        return user;
    }
    
    static getInstance() {
        if (!UserManager.instance) {
            UserManager.instance = new UserManager();
        }
        return UserManager.instance;
    }
}

const authService = {
    login: function(username, password) {
        // Authentication logic here
        return true;
    },
    
    logout: (username) => {
        // Logout logic here
        console.log(`${username} logged out`);
    }
};

async function initializeSystem() {
    const manager = UserManager.getInstance();
    return manager;
}
```

**Parsed Output**:
```
File: user-manager.js
Definitions: 9, References: 8

⋮
│class User {
│    constructor(username, email) {
│        this.username = username;
│        this.email = email;
│        this.isActive = true;
│    }
│
│    activate() {
⋮
│    deactivate() {
⋮
│class UserManager {
│    constructor() {
│        this.users = new Map();
│    }
│
│    addUser(username, email) {
⋮
│    static getInstance() {
⋮
│const authService = {
│    login: function(username, password) {
⋮
│    logout: (username) => {
⋮
│async function initializeSystem() {
⋮
```

**Key Differences from Source**:
- Extracts 9 definitions (classes, methods, functions, object properties)
- Counts 8 references to other identifiers
- Omits implementation details and comments
- Shows structural hierarchy and method signatures

### Empty or Unsupported File Example

**Output**:
```
No code definitions found in empty_file.py
```

## Usage Examples

### Basic Usage
```python
from siada.tools.ast.ast_tool import _list_code_definition_names

# Analyze Python file
result = _list_code_definition_names("/path/to/file.py")
print(result)

# Specify relative path
result = _list_code_definition_names("/absolute/path/to/file.py", "src/file.py")
print(result)
```

### Batch Processing
```python
import os
from pathlib import Path

def analyze_project(project_dir):
    """Analyze all Python files in a project"""
    for py_file in Path(project_dir).rglob("*.py"):
        rel_path = py_file.relative_to(project_dir)
        result = _list_code_definition_names(str(py_file), str(rel_path))
        print(f"\n{'='*50}")
        print(result)

# Usage example
analyze_project("/path/to/your/project")
```

### Error Handling
```python
def safe_analyze(file_path):
    """Safely analyze file with error handling"""
    try:
        result = _list_code_definition_names(file_path)
        if "No code definitions found" in result:
            print(f"No definitions found in {file_path}")
        else:
            print(result)
    except Exception as e:
        print(f"Error analyzing {file_path}: {e}")
```

## Technical Details

### Dependencies
- `grep-ast`: Provides TreeContext and language identification functionality
- `pygments`: Provides lexical analysis fallback functionality
- `tree-sitter`: Underlying syntax parsing engine

### Performance Characteristics
- **Memory Efficiency**: Uses generator pattern for processing large files
- **Error Tolerance**: Syntax errors don't completely prevent parsing
- **Cache Optimization**: TreeContext provides context caching
- **Line Length Limiting**: Automatically truncates overly long lines to prevent excessive output

### Limitations and Considerations
1. **File Encoding**: Only supports UTF-8 encoded files
2. **File Size**: May have performance impact on very large files
3. **Language Support**: Depends on availability of tree-sitter query files
4. **Accuracy**: Complex macro definitions or dynamic code may not be accurately identified

## Related Modules

- `models.py`: Defines Tag data model
- `../../../queries/`: Stores tree-sitter query files for various languages
- `../../../tests/tools/ast/`: Complete test suite

## Changelog

- Support for multiple programming languages code definition extraction
- Implementation of dual parsing strategy for improved accuracy
- Added error handling and fallback mechanisms
- Optimized output format and performance

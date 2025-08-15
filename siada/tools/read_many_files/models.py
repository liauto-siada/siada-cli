"""
ReadManyFiles tool data models and structures.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Union, Any


@dataclass
class ReadManyFilesParams:
    """ReadManyFiles tool input parameters"""
    
    # Required parameters
    paths: List[str]  # File paths or directory paths array, relative to tool config target directory
                      # Can directly use glob patterns
                      # Example: ['src/**/*.py', 'docs/*.md']
    
    # Optional parameters
    include: Optional[List[str]] = None       # Additional include glob patterns
                                              # Example: ["*.test.ts"]
    
    exclude: Optional[List[str]] = None       # Exclude glob patterns
                                              # Example: ["*.log", "dist/**"]
    
    recursive: bool = True                    # Whether to search recursively
                                              # Mainly controlled by "**" in glob patterns
    
    useDefaultExcludes: bool = True           # Whether to apply default exclude patterns
    
    file_filtering_options: Optional[Dict[str, bool]] = None
    # File filtering options
    # {
    #     'respect_git_ignore': bool,     # Default: True
    # }


@dataclass
class ToolResult:
    """Tool execution result"""
    
    llmContent: Union[List[str], List[Any], List[Union[str, Any]]]
    # Content returned to LLM
    # - For text files: formatted string array
    # - For images/PDF: Part object array
    # - Mixed content: mixed array of strings and Part objects
    
    returnDisplay: str
    # Content returned to user interface display
    # Contains detailed summary information of processing results


@dataclass
class FileProcessResult:
    """Single file processing result"""
    
    success: bool
    path: str
    content: Optional[Any] = None
    reason: Optional[str] = None
    file_type: Optional[str] = None
    size: Optional[int] = None


@dataclass
class ProcessingStats:
    """File processing statistics"""
    
    total_files_found: int = 0
    processed_files: int = 0
    skipped_files: int = 0
    text_files: int = 0
    image_files: int = 0
    pdf_files: int = 0
    binary_files: int = 0
    error_files: int = 0
    total_size: int = 0
    processing_time: float = 0.0


# Default exclude patterns
DEFAULT_EXCLUDES = [
    # Dependency directories
    '**/node_modules/**',
    '**/__pycache__/**',
    '**/venv/**',
    '**/env/**',
    '**/.env/**',
    
    # Version control
    '**/.git/**',
    '**/.svn/**',
    '**/.hg/**',
    
    # IDE configuration
    '**/.vscode/**',
    '**/.idea/**',
    '**/.eclipse/**',
    
    # Build output
    '**/dist/**',
    '**/build/**',
    '**/target/**',
    '**/coverage/**',
    '**/out/**',
    
    # Compiled files
    '**/*.pyc',
    '**/*.pyo',
    '**/*.class',
    '**/*.jar',
    '**/*.war',
    '**/*.o',
    '**/*.obj',
    
    # Binary files
    '**/*.bin',
    '**/*.exe',
    '**/*.dll',
    '**/*.so',
    '**/*.dylib',
    
    # Compressed files
    '**/*.zip',
    '**/*.tar',
    '**/*.gz',
    '**/*.bz2',
    '**/*.rar',
    '**/*.7z',
    
    # Office documents (unless explicitly requested)
    '**/*.doc',
    '**/*.docx',
    '**/*.xls',
    '**/*.xlsx',
    '**/*.ppt',
    '**/*.pptx',
    '**/*.odt',
    '**/*.ods',
    '**/*.odp',
    
    # System files
    '**/.DS_Store',
    '**/Thumbs.db',
    '**/.env',
    '**/.env.local',
    '**/.env.*.local',
    
    # Log files
    '**/*.log',
    '**/logs/**',
    
    # Cache directories
    '**/.cache/**',
    '**/cache/**',
    '**/.tmp/**',
    '**/tmp/**',
    
    # Package manager files
    '**/package-lock.json',
    '**/yarn.lock',
    '**/poetry.lock',
    '**/Pipfile.lock',
    
    # Gemini history files
    '**/GEMINI.md',
]

# Supported text file extensions
TEXT_FILE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.cc', '.cxx',
    '.h', '.hpp', '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala',
    '.clj', '.hs', '.ml', '.fs', '.vb', '.pl', '.sh', '.bash', '.zsh', '.fish',
    '.ps1', '.bat', '.cmd', '.html', '.htm', '.xml', '.css', '.scss', '.sass',
    '.less', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
    '.properties', '.env', '.md', '.rst', '.txt', '.log', '.sql', '.r',
    '.m', '.mm', '.dart', '.lua', '.vim', '.dockerfile', '.makefile',
    '.cmake', '.gradle', '.maven', '.ant', '.sbt', '.cabal', '.nix'
}

# Supported image file extensions
IMAGE_FILE_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg', '.ico',
    '.tiff', '.tif', '.psd', '.ai', '.eps'
}

# Supported PDF file extensions
PDF_FILE_EXTENSIONS = {
    '.pdf'
}

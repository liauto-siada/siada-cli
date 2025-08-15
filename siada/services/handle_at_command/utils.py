"""
Utility functions for HandleAtCommand functionality.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple


def normalize_path(path: str) -> str:
    """
    Normalize a file path for consistent handling
    
    Args:
        path: File path to normalize
        
    Returns:
        Normalized path string
    """
    if not path:
        return path
    
    # Convert to Path object and resolve
    normalized = Path(path).as_posix()
    
    # Remove leading './' if present
    if normalized.startswith('./'):
        normalized = normalized[2:]
    
    return normalized


def is_text_file(file_path: str) -> bool:
    """
    Check if a file is likely a text file based on extension
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if likely a text file, False otherwise
    """
    text_extensions = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.cc', '.cxx',
        '.h', '.hpp', '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala',
        '.clj', '.hs', '.ml', '.fs', '.vb', '.pl', '.sh', '.bash', '.zsh', '.fish',
        '.ps1', '.bat', '.cmd', '.html', '.htm', '.xml', '.css', '.scss', '.sass',
        '.less', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
        '.properties', '.env', '.md', '.rst', '.txt', '.log', '.sql', '.r',
        '.m', '.mm', '.dart', '.lua', '.vim', '.dockerfile', '.makefile',
        '.cmake', '.gradle', '.maven', '.ant', '.sbt', '.cabal', '.nix'
    }
    
    file_ext = Path(file_path).suffix.lower()
    return file_ext in text_extensions


def is_image_file(file_path: str) -> bool:
    """
    Check if a file is an image based on extension
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if an image file, False otherwise
    """
    image_extensions = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg', '.ico',
        '.tiff', '.tif', '.psd', '.ai', '.eps'
    }
    
    file_ext = Path(file_path).suffix.lower()
    return file_ext in image_extensions


def is_pdf_file(file_path: str) -> bool:
    """
    Check if a file is a PDF
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if a PDF file, False otherwise
    """
    return Path(file_path).suffix.lower() == '.pdf'


def sanitize_path_for_display(path: str) -> str:
    """
    Sanitize a path for safe display in messages
    
    Args:
        path: Path to sanitize
        
    Returns:
        Sanitized path string
    """
    if not path:
        return path
    
    # Remove any potential control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', path)
    
    # Limit length for display
    max_length = 100
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + '...'
    
    return sanitized


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    return f"{size:.1f} {size_names[i]}"


def extract_filename_from_path(path: str) -> str:
    """
    Extract filename from a path
    
    Args:
        path: File path
        
    Returns:
        Filename without directory
    """
    return Path(path).name


def get_file_extension(path: str) -> str:
    """
    Get file extension from path
    
    Args:
        path: File path
        
    Returns:
        File extension (including dot)
    """
    return Path(path).suffix


def is_hidden_file(path: str) -> bool:
    """
    Check if a file or directory is hidden (starts with dot)
    
    Args:
        path: File path
        
    Returns:
        True if hidden, False otherwise
    """
    filename = Path(path).name
    return filename.startswith('.')


def split_path_components(path: str) -> List[str]:
    """
    Split path into components
    
    Args:
        path: File path
        
    Returns:
        List of path components
    """
    return Path(path).parts


def join_path_components(components: List[str]) -> str:
    """
    Join path components into a path
    
    Args:
        components: List of path components
        
    Returns:
        Joined path string
    """
    if not components:
        return ""
    
    return str(Path(*components))


def validate_filename(filename: str) -> bool:
    """
    Validate that a filename is safe and valid
    
    Args:
        filename: Filename to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not filename:
        return False
    
    # Check for invalid characters
    invalid_chars = ['<', '>', ':', '"', '|', '?', '*', '\0']
    for char in invalid_chars:
        if char in filename:
            return False
    
    # Check for reserved names (Windows)
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    name_without_ext = Path(filename).stem.upper()
    if name_without_ext in reserved_names:
        return False
    
    # Check length
    if len(filename) > 255:
        return False
    
    return True


def create_safe_filename(original: str) -> str:
    """
    Create a safe filename from an original string
    
    Args:
        original: Original filename
        
    Returns:
        Safe filename
    """
    if not original:
        return "unnamed"
    
    # Replace invalid characters with underscores
    safe = re.sub(r'[<>:"|?*\0]', '_', original)
    
    # Remove leading/trailing dots and spaces
    safe = safe.strip('. ')
    
    # Ensure it's not empty
    if not safe:
        safe = "unnamed"
    
    # Truncate if too long
    if len(safe) > 255:
        name, ext = os.path.splitext(safe)
        max_name_len = 255 - len(ext)
        safe = name[:max_name_len] + ext
    
    return safe


def format_processing_time(seconds: float) -> str:
    """
    Format processing time in human-readable format
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted time string
    """
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds:.1f}s"


def truncate_content(content: str, max_length: int = 1000) -> Tuple[str, bool]:
    """
    Truncate content if it's too long
    
    Args:
        content: Content to truncate
        max_length: Maximum length allowed
        
    Returns:
        Tuple of (truncated_content, was_truncated)
    """
    if len(content) <= max_length:
        return content, False
    
    truncated = content[:max_length] + "... [content truncated]"
    return truncated, True


def count_lines(content: str) -> int:
    """
    Count number of lines in content
    
    Args:
        content: Content to count lines in
        
    Returns:
        Number of lines
    """
    if not content:
        return 0
    
    return len(content.splitlines())


def estimate_tokens(content: str) -> int:
    """
    Estimate number of tokens in content (rough approximation)
    
    Args:
        content: Content to estimate tokens for
        
    Returns:
        Estimated token count
    """
    if not content:
        return 0
    
    # Rough approximation: 1 token ≈ 4 characters
    return len(content) // 4

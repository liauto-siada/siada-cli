"""
Path processing utilities for file recommendation.
"""


def escape_path(file_path: str) -> str:
    """
    Escape spaces in file paths
    
    Args:
        file_path: Original file path
    
    Returns:
        str: Escaped path
    """
    result = ""
    for i, char in enumerate(file_path):
        # Only escape unescaped spaces
        if char == ' ' and (i == 0 or file_path[i-1] != '\\'):
            result += '\\ '
        else:
            result += char
    return result


def unescape_path(file_path: str) -> str:
    """
    Unescape spaces in file paths
    
    Args:
        file_path: Escaped file path
    
    Returns:
        str: Unescaped path
    """
    return file_path.replace('\\ ', ' ')


def normalize_path_separators(path: str) -> str:
    """
    Normalize path separators to forward slashes
    
    Args:
        path: Path with potentially mixed separators
        
    Returns:
        str: Path with normalized separators
    """
    return path.replace('\\', '/')


def is_hidden_file(path: str) -> bool:
    """
    Check if a file or directory is hidden (starts with .)
    
    Args:
        path: File or directory path
        
    Returns:
        bool: True if hidden, False otherwise
    """
    import os
    basename = os.path.basename(path)
    return basename.startswith('.')


def get_file_extension(path: str) -> str:
    """
    Get file extension from path
    
    Args:
        path: File path
        
    Returns:
        str: File extension (without dot)
    """
    import os
    _, ext = os.path.splitext(path)
    return ext.lstrip('.')


def is_directory_path(path: str) -> bool:
    """
    Check if path appears to be a directory (ends with /)
    
    Args:
        path: Path to check
        
    Returns:
        bool: True if appears to be directory path
    """
    return path.endswith('/') or path.endswith('\\')


def ensure_relative_path(path: str, base_dir: str) -> str:
    """
    Ensure path is relative to base directory
    
    Args:
        path: Path to make relative
        base_dir: Base directory
        
    Returns:
        str: Relative path
    """
    import os
    try:
        return os.path.relpath(path, base_dir)
    except ValueError:
        # Can't make relative (different drives on Windows)
        return path


def join_path_parts(*parts: str) -> str:
    """
    Join path parts with forward slashes
    
    Args:
        *parts: Path parts to join
        
    Returns:
        str: Joined path
    """
    return '/'.join(part.strip('/\\') for part in parts if part.strip('/\\'))


def split_path_parts(path: str) -> list[str]:
    """
    Split path into parts
    
    Args:
        path: Path to split
        
    Returns:
        list[str]: Path parts
    """
    normalized = normalize_path_separators(path)
    return [part for part in normalized.split('/') if part]

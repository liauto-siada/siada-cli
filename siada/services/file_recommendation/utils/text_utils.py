"""
Text processing utilities for file recommendation.
"""

from typing import List, Tuple, Optional


def is_completion_active(text: str, cursor_row: int, cursor_col: int, lines: List[str]) -> bool:
    """
    Check if @ file recommendation should be activated
    
    Args:
        text: Complete input text
        cursor_row: Cursor row number
        cursor_col: Cursor column number
        lines: Text line list
    
    Returns:
        bool: Whether to activate recommendation
    """
    # If it's a slash command, handle that first
    if text.strip().startswith('/'):
        return False
    
    # Get current line
    current_line = lines[cursor_row] if cursor_row < len(lines) else ""
    code_points = list(current_line)  # Unicode code point array
    
    # Search backwards from cursor position
    for i in range(cursor_col - 1, -1, -1):
        char = code_points[i]
        
        if char == ' ':
            # Check if it's escaped space
            backslash_count = 0
            j = i - 1
            while j >= 0 and code_points[j] == '\\':
                backslash_count += 1
                j -= 1
            
            # Even number of backslashes means unescaped space
            if backslash_count % 2 == 0:
                return False
                
        elif char == '@':
            # Found @ character, activate recommendation
            return True
    
    return False


def parse_at_command_path(text: str) -> Tuple[str, str, str]:
    """
    Parse path information from @ command
    
    Args:
        text: Input text
    
    Returns:
        Tuple[base_directory, path_prefix, original_partial_path]
        
    Note: Modified to remove relative path support and use full path as search prefix
    """
    at_index = text.rfind('@')
    if at_index == -1:
        return ".", "", ""
    
    partial_path = text[at_index + 1:]
    
    # Use the entire path after @ as search prefix, no directory-based splitting
    # This eliminates relative path navigation issues
    full_prefix = unescape_path(partial_path)
    
    return ".", full_prefix, partial_path


def to_code_points(text: str) -> List[str]:
    """
    Convert string to Unicode code point array
    
    Args:
        text: Input string
    
    Returns:
        List[str]: Unicode code point list
    """
    return list(text)


def cp_len(text: str) -> int:
    """
    Get Unicode code point length of string
    
    Args:
        text: Input string
    
    Returns:
        int: Code point length
    """
    return len(list(text))


def cp_slice(text: str, start: int, end: Optional[int] = None) -> str:
    """
    Slice string by Unicode code points
    
    Args:
        text: Input string
        start: Start position
        end: End position
    
    Returns:
        str: Sliced string
    """
    code_points = list(text)
    return ''.join(code_points[start:end])


def unescape_path(file_path: str) -> str:
    """
    Unescape file path spaces
    
    Args:
        file_path: Escaped file path
    
    Returns:
        str: Unescaped path
    """
    return file_path.replace('\\ ', ' ')


def extract_at_path_from_text(text: str, cursor_pos: int = None) -> Optional[str]:
    """
    Extract the @ path from text at cursor position
    
    Args:
        text: Input text
        cursor_pos: Cursor position (default: end of text)
        
    Returns:
        Optional[str]: Extracted @ path or None if not found
    """
    if cursor_pos is None:
        cursor_pos = len(text)
    
    # Find the last @ before cursor position
    at_pos = -1
    for i in range(cursor_pos - 1, -1, -1):
        if i < len(text) and text[i] == '@':
            # Check if it's escaped
            if i == 0 or text[i-1] != '\\':
                at_pos = i
                break
    
    if at_pos == -1:
        return None
    
    # Find the end of the @ path (next unescaped space or end of text)
    end_pos = at_pos + 1
    while end_pos < len(text):
        if text[end_pos] == ' ':
            # Check if it's escaped
            if end_pos == 0 or text[end_pos - 1] != '\\':
                break
        elif text[end_pos] == '\\' and end_pos + 1 < len(text):
            # Skip escaped character
            end_pos += 2
            continue
        end_pos += 1
    
    # Extract from @ to end of path
    return text[at_pos:end_pos]


def is_at_command_start(text: str, position: int) -> bool:
    """
    Check if position is at the start of an @ command
    
    Args:
        text: Input text
        position: Position to check
        
    Returns:
        bool: True if position is at @ command start
    """
    if position >= len(text) or text[position] != '@':
        return False
    
    # Check if @ is escaped
    if position > 0 and text[position - 1] == '\\':
        return False
    
    return True


def find_at_commands_in_text(text: str) -> List[Tuple[int, str]]:
    """
    Find all @ commands in text
    
    Args:
        text: Input text
        
    Returns:
        List[Tuple[int, str]]: List of (position, at_command) tuples
    """
    commands = []
    i = 0
    
    while i < len(text):
        if text[i] == '@' and is_at_command_start(text, i):
            # Find end of command
            j = i + 1
            while j < len(text) and not text[j].isspace():
                if text[j] == '\\' and j + 1 < len(text):
                    j += 2  # Skip escaped character
                else:
                    j += 1
            
            command = text[i:j]
            commands.append((i, command))
            i = j
        else:
            i += 1
    
    return commands


def validate_at_path_syntax(at_path: str) -> bool:
    """
    Validate @ path syntax
    
    Args:
        at_path: @ path to validate
        
    Returns:
        bool: True if valid syntax
    """
    if not at_path or not at_path.startswith('@'):
        return False
    
    path_part = at_path[1:]
    
    # Empty path after @ is only valid for lone @
    if not path_part and at_path != '@':
        return False
    
    # Check for invalid characters
    invalid_chars = ['<', '>', '|', '"', '*', '?']
    for char in invalid_chars:
        if char in path_part:
            return False
    
    return True

"""
@ Command Parser - Parses user input to extract @ commands.
"""

import re
from typing import List

from .models import AtCommandPart
from .exceptions import InvalidPathError


class AtCommandParser:
    """Parser for @ commands in user queries"""
    
    def __init__(self):
        # Regex pattern to match file content format from read_many_files
        self.file_content_regex = re.compile(r'^--- (.*?) ---\n\n([\s\S]*?)\n\n$')
    
    def parse_all_at_commands(self, query: str) -> List[AtCommandPart]:
        """
        Parse all @ commands from the query string
        
        Args:
            query: User input query string
            
        Returns:
            List of AtCommandPart objects representing parsed parts
        """
        if not query:
            return []
        
        parts = []
        current_index = 0
        
        while current_index < len(query):
            # Find next unescaped '@'
            at_index = self._find_next_unescaped_at(query, current_index)
            
            if at_index == -1:
                # No more '@' symbols, add remaining text
                if current_index < len(query):
                    remaining_text = query[current_index:]
                    if remaining_text.strip():  # Only add non-empty text
                        parts.append(AtCommandPart('text', remaining_text))
                break
            
            # Add text before '@' if any
            if at_index > current_index:
                text_before = query[current_index:at_index]
                if text_before.strip():  # Only add non-empty text
                    parts.append(AtCommandPart('text', text_before))
            
            # Parse '@path'
            path_end_index = self._find_path_end(query, at_index + 1)
            raw_at_path = query[at_index:path_end_index]
            
            # Handle lone '@' symbol
            if raw_at_path == '@':
                parts.append(AtCommandPart('text', '@'))
            else:
                at_path = self._unescape_path(raw_at_path)
                parts.append(AtCommandPart('atPath', at_path))
            
            current_index = path_end_index
        
        # Filter out empty text parts
        return [p for p in parts if not (p.type == 'text' and not p.content.strip())]
    
    def _find_next_unescaped_at(self, query: str, start_index: int) -> int:
        """
        Find the next unescaped '@' symbol
        
        Args:
            query: Query string
            start_index: Starting index for search
            
        Returns:
            Index of next unescaped '@', or -1 if not found
        """
        index = start_index
        while index < len(query):
            if query[index] == '@':
                # Check if it's escaped (preceded by backslash)
                if index == 0 or query[index - 1] != '\\':
                    return index
            index += 1
        return -1
    
    def _find_path_end(self, query: str, start_index: int) -> int:
        """
        Find the end of the path, handling escape characters
        
        Args:
            query: Query string
            start_index: Starting index (after '@')
            
        Returns:
            Index where the path ends
        """
        index = start_index
        in_escape = False
        
        while index < len(query):
            char = query[index]
            
            if in_escape:
                # Previous character was escape, skip this character
                in_escape = False
            elif char == '\\':
                # This is an escape character
                in_escape = True
            elif char.isspace():
                # Unescaped whitespace marks end of path
                break
            
            index += 1
        
        return index
    
    def _unescape_path(self, path: str) -> str:
        """
        Process escape characters in the path
        
        Args:
            path: Raw path string with potential escape characters
            
        Returns:
            Unescaped path string
        """
        if not path:
            return path
        
        # Handle escaped spaces and other characters
        result = []
        i = 0
        while i < len(path):
            if path[i] == '\\' and i + 1 < len(path):
                # Escape sequence - add the next character literally
                result.append(path[i + 1])
                i += 2
            else:
                result.append(path[i])
                i += 1
        
        return ''.join(result)
    
    def validate_at_path(self, at_path: str) -> bool:
        """
        Validate that an @ path is well-formed
        
        Args:
            at_path: @ path string (including '@' prefix)
            
        Returns:
            True if valid, False otherwise
        """
        if not at_path or not at_path.startswith('@'):
            return False
        
        path_part = at_path[1:]  # Remove '@' prefix
        
        # Empty path after '@' is invalid (except lone '@')
        if not path_part and at_path != '@':
            return False
        
        # Check for invalid characters
        invalid_chars = ['<', '>', '|', '"', '*', '?']
        for char in invalid_chars:
            if char in path_part:
                return False
        
        return True
    
    def extract_file_content_info(self, content_part: str) -> tuple[str, str]:
        """
        Extract file path and content from formatted file content
        
        Args:
            content_part: Formatted content from read_many_files tool
            
        Returns:
            Tuple of (file_path, content) or (None, content) if not matched
        """
        match = self.file_content_regex.match(content_part)
        if match:
            file_path = match.group(1)
            content = match.group(2).strip()
            return file_path, content
        return None, content_part

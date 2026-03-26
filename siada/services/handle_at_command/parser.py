"""
@ Command Parser - Parses user input to extract @ commands.
"""

import os
import json
import re
from typing import List

from .models import AtCommandPart
from .exceptions import InvalidPathError


# Well-known bare-word filenames that ARE valid @ file references even without
# a path separator or extension (e.g. ``@Makefile``, ``@README``).
# Everything else that looks like a pure identifier word (``@test``, ``@Override``)
# is treated as a programming-language annotation / keyword, NOT a file path.
_KNOWN_BARE_FILENAMES = frozenset({
    # Build / config files
    'Makefile', 'makefile', 'Dockerfile', 'dockerfile', 'Vagrantfile',
    'Gemfile', 'Rakefile', 'Podfile', 'Procfile', 'Brewfile',
    'CMakeLists', 'Justfile', 'Taskfile', 'Earthfile',
    # Documentation
    'README', 'LICENSE', 'LICENCE', 'CHANGELOG', 'CHANGES', 'AUTHORS',
    'CONTRIBUTING', 'HISTORY', 'NEWS', 'NOTICE', 'PATENTS', 'COPYING',
    'TODO', 'CREDITS', 'SECURITY', 'CODEOWNERS',
    # Config
    'Gruntfile', 'Gulpfile', 'webpack', 'rollup', 'vite',
    'setup', 'manage', 'conftest',
})


class AtCommandParser:
    """Parser for @ commands in user queries"""
    
    def __init__(self):
        # Regex pattern to match file content format from read_many_files
        self.file_content_regex = re.compile(r'^--- (.*?) ---\n\n([\s\S]*?)\n\n$')
        # Preload invalid @-path patterns from config (if available)
        self._invalid_path_patterns = self._load_invalid_path_patterns()
        # Regex for a "bare identifier" word — no path separators, no file extension,
        # no special characters.  Examples: ``test``, ``Override``, ``Autowired``.
        self._bare_identifier_re = re.compile(r'^[a-zA-Z_]\w*$')
    
    def _load_invalid_path_patterns(self) -> list[re.Pattern]:
        """Load blacklist regex patterns for invalid @ paths from JSON config.

        The config file lives next to this module as ``at_command_invalid_patterns.json``
        and has the structure:
        {
          "patterns": [
            {"name": "...", "regex": "..."},
            ...
          ]
        }
        All regexes are applied to the path part after '@'.
        """
        config_path = os.path.join(os.path.dirname(__file__), "at_command_invalid_patterns.json")
        if not os.path.exists(config_path):
            return []
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            patterns: list[re.Pattern] = []
            for item in data.get("patterns", []):
                regex = item.get("regex")
                if not regex:
                    continue
                try:
                    patterns.append(re.compile(regex))
                except re.error:
                    # Ignore invalid regex patterns in config
                    continue
            return patterns
        except Exception:
            # If config cannot be read or parsed, gracefully fall back to no extra rules
            return []
    
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
    
    def parse_all_at_commands_exclude_invalids(self, query: str) -> List[AtCommandPart]:
        """Parse all @ commands but treat invalid @ segments as plain text.

        This helper is more conservative than ``parse_all_at_commands``:
        - Diff hunk markers like ``@@ -45,13 +45,24`` are not treated as @ paths
        - Hex-like tokens from logs such as ``@2f2e49`` or ``@0x3db83141`` are
          considered invalid @ commands and left as plain text.
        """
        parts = self.parse_all_at_commands(query)
        if not parts:
            return parts

        cleaned_parts: List[AtCommandPart] = []

        for part in parts:
            if part.type == 'atPath':
                at_path = part.content

                # First reuse basic syntax validation
                is_valid = self.validate_at_path(at_path)

                if is_valid:
                    path_part = at_path[1:]

                    # ``@@`` at the beginning of a diff hunk is not a real path
                    if at_path == '@@':
                        is_valid = False
                    # Pure hex / 0x-prefixed hex tokens are usually addresses / hashes
                    elif re.fullmatch(r'(0x)?[0-9a-fA-F]+', path_part):
                        is_valid = False
                    # Placeholder-style segments like "@{description}" are not real paths
                    elif path_part.startswith('{') and '}' in path_part:
                        is_valid = False
                    # IRQ / controller style addresses like "@b220000-9"
                    elif re.fullmatch(r'[0-9a-fA-F]+-\d+', path_part):
                        is_valid = False
                    # Android/Systemd style timestamps like "@1765789849649" or with .txt/.gz
                    elif re.fullmatch(r'\d{11,}(\.txt(\.gz)?)?', path_part):
                        is_valid = False
                    # Systemd unit instance names like "@configfs.service"
                    elif path_part.endswith('.service'):
                        is_valid = False
                    # Unix domain sockets / sysfs device paths such as
                    # "@/dev/socket/..." or "@/devices/..."
                    elif path_part.startswith('/dev/') or path_part.startswith('/devices/'):
                        is_valid = False
                    # Audio bus / special tagged ids like "@:BUS00_MEDIA"
                    elif path_part.startswith(':'):
                        is_valid = False
                    # Resolution patterns like "@600w_800h_1c"
                    elif re.fullmatch(r'\d+w_\d+h_\dc', path_part):
                        is_valid = False

                    # ── Bare identifier words ──
                    # A path like "test", "Override", "Autowired" (pure identifier
                    # with no '/', no '.', no '-') does NOT look like a file path.
                    # It is almost certainly a programming-language annotation
                    # (Java @Test, @Override, Python @property, etc.) or a keyword.
                    #
                    # Exception: well-known bare filenames such as Makefile, README,
                    # Dockerfile, LICENSE — these ARE valid file references.
                    elif (self._bare_identifier_re.fullmatch(path_part)
                          and path_part not in _KNOWN_BARE_FILENAMES):
                        is_valid = False

                    # Apply additional blacklist patterns loaded from JSON config
                    if is_valid and self._invalid_path_patterns:
                        for pattern in self._invalid_path_patterns:
                            if pattern.fullmatch(path_part):
                                is_valid = False
                                break

                if is_valid:
                    cleaned_parts.append(part)
                else:
                    # Treat invalid @ segment as plain text, preserving original content
                    cleaned_parts.append(AtCommandPart('text', at_path))
            else:
                cleaned_parts.append(part)

        # Merge adjacent text parts for cleaner output
        merged_parts: List[AtCommandPart] = []
        for part in cleaned_parts:
            if merged_parts and part.type == 'text' and merged_parts[-1].type == 'text':
                merged_parts[-1].content += part.content
            else:
                merged_parts.append(part)

        return merged_parts
    
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

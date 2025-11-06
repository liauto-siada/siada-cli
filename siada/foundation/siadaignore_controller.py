"""
.siadaignore File Access Control Controller

This module provides the SiadaIgnoreController class that manages file access control
based on .siadaignore rules, similar to .gitignore syntax.
"""

from pathlib import Path
from typing import Optional
import pathspec
from siada.foundation.logging import logger


class SiadaIgnoreController:
    """
    Controller for .siadaignore file access control.
    
    This class is responsible for:
    1. Loading and parsing .siadaignore files
    2. Validating file access permissions
    3. Filtering environment_details in system instructions
    4. Generating siadaignore-related system instructions
    
    Attributes:
        workspace (str): The workspace directory path
        ignore_instance (Optional[pathspec.PathSpec]): The pathspec instance for pattern matching
        siadaignore_content (Optional[str]): The raw content of .siadaignore file
    """
    
    def __init__(self, workspace: str):
        """
        Initialize the SiadaIgnoreController.
        
        Args:
            workspace: The absolute path to the workspace directory
        """
        self.workspace = workspace
        self.ignore_instance: Optional[pathspec.PathSpec] = None
        self.siadaignore_content: Optional[str] = None
    
    def initialize(self) -> None:
        """
        Initialize and load the .siadaignore file.
        
        This method should be called after construction to load the ignore rules.
        It gracefully handles cases where the file doesn't exist or can't be loaded.
        """
        self._load_siadaignore()
    
    def validate_access(self, file_path: str) -> bool:
        """
        Validate whether a file can be accessed based on .siadaignore rules.
        
        Args:
            file_path: The file path to validate (can be relative or absolute)
            
        Returns:
            True if the file can be accessed, False if it's ignored
            
        Note:
            - Returns True if no .siadaignore rules are loaded
            - Returns True if the path can't be resolved
            - Returns False if the file matches any ignore pattern
        """
        # Fast path: no rules loaded, allow all access
        if not self.siadaignore_content or self.ignore_instance is None:
            return True
        
        try:
            # Convert to absolute path if needed
            abs_path = Path(file_path)
            if not abs_path.is_absolute():
                abs_path = Path(self.workspace) / file_path
            
            # Calculate relative path to workspace
            try:
                rel_path = abs_path.relative_to(self.workspace)
            except ValueError:
                # Path is outside workspace, allow access
                return True
            
            # Convert to POSIX format for cross-platform compatibility
            posix_path = rel_path.as_posix()
            
            # Check if the path is ignored
            is_ignored = self.ignore_instance.match_file(posix_path)
            
            return not is_ignored
            
        except Exception as e:
            # On any error, default to allowing access
            # This ensures the system continues to work even if path validation fails
            logger.error(f"Error validating access for '{file_path}': {e}")
            return True
    
    def filter_view_output(self, output: str) -> str:
        """
        Filter view command output to remove ignored files.
        
        This method processes the output from edit_file tool's view command,
        removing any files that match ignore rules.
        
        Args:
            output: The raw output from view command
            
        Returns:
            Filtered output with ignored files removed
            
        Note:
            - If no rules are loaded, returns output unchanged
            - Processes each line and removes ignored files
            - Preserves original formatting and indentation
        """
        # Fast path: no rules, return unchanged
        if not self.siadaignore_content:
            return output
        
        if not output:
            return output
        
        lines = output.split('\n')
        filtered_lines = []
        
        for line in lines:
            # Use the existing _filter_file_line method to process each line
            # If it returns None, skip this line
            filtered_line = self._filter_file_line(line)
            if filtered_line is not None:
                filtered_lines.append(filtered_line)
        
        return '\n'.join(filtered_lines)
    
    def _load_siadaignore(self) -> None:
        """
        Load the .siadaignore file from the workspace.
        
        This private method:
        1. Checks if the pathspec library is available
        2. Looks for .siadaignore file in the workspace
        3. Loads and parses the file content
        4. Creates a PathSpec instance with the rules
        
        Note:
            - Silently fails if pathspec library is not available
            - Silently succeeds if .siadaignore file doesn't exist
            - Prints warning on errors but doesn't raise exceptions
        """
        # Build path to .siadaignore file
        ignore_path = Path(self.workspace) / ".siadaignore"
        
        # Check if file exists
        if not ignore_path.exists():
            # No .siadaignore file, allow all access
            self.siadaignore_content = None
            return
        
        try:
            # Read the file content
            with open(ignore_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Store the original content
            self.siadaignore_content = content
            
            # Parse patterns from file content and add .siadaignore itself
            patterns = content.strip().split('\n')
            patterns.append(".siadaignore")
            
            # Filter out empty lines and comments
            patterns = [p.strip() for p in patterns if p.strip() and not p.strip().startswith('#')]
            
            # Create PathSpec instance with gitignore-style patterns
            self.ignore_instance = pathspec.PathSpec.from_lines('gitwildmatch', patterns)

        except UnicodeDecodeError as e:
            # Handle encoding errors
            logger.error(f"Failed to decode .siadaignore file (encoding issue): {e}")
            self.siadaignore_content = None
            self.ignore_instance = None
            
        except Exception as e:
            # Handle any other errors
            logger.error(f"Failed to load .siadaignore: {e}")
            self.siadaignore_content = None
            self.ignore_instance = None
    
    
    def _filter_file_line(self, line: str) -> Optional[str]:
        """
        Filter a single file path line.
        
        If the file path matches ignore rules, returns None to indicate the line
        should be removed. Otherwise, returns the line unchanged.
        
        Args:
            line: A line potentially containing a file path
            
        Returns:
            The original line if accessible, or None if the file should be filtered out
            
        Note:
            - Skips empty lines and comment lines (returns them unchanged)
            - Extracts the first word as the file path
            - Returns None for files that should be ignored
        """
        stripped = line.strip()
        
        # Skip empty lines and comment lines
        if not stripped or stripped.startswith('#'):
            return line
        
        # Extract file path (usually the first word in the line)
        parts = stripped.split()
        if not parts:
            return line
        
        file_path = parts[0]
        
        # Check if this file should be ignored
        if not self.validate_access(file_path):
            # File is ignored, return None to indicate it should be filtered out
            return None
        
        # File is accessible, return line unchanged
        return line

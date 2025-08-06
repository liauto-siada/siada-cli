"""
File filtering utilities for ReadManyFiles tool.
"""

import os
import fnmatch
from pathlib import Path
from typing import List, Set, Dict, Tuple, Optional

from .models import DEFAULT_EXCLUDES


class FileFilter:
    """File filtering utility class"""
    
    def __init__(self, target_dir: str):
        self.target_dir = Path(target_dir).resolve()
        self._gitignore_cache: Dict[str, List[str]] = {}
    
    def should_exclude_file(self, file_path: str, workspace_dir: str, 
                           exclusion_patterns: List[str]) -> bool:
        """
        Check if file should be excluded based on exclusion patterns
        
        Args:
            file_path: Absolute path to the file
            workspace_dir: Workspace directory path
            exclusion_patterns: List of glob exclusion patterns
            
        Returns:
            True if file should be excluded, False otherwise
        """
        try:
            relative_path = os.path.relpath(file_path, workspace_dir)
            normalized_path = relative_path.replace('\\', '/')
        except ValueError:
            # Handle case where paths are on different drives (Windows)
            return True
        
        for pattern in exclusion_patterns:
            # Normalize pattern
            normalized_pattern = pattern.replace('\\', '/')
            
            # Direct file name matching
            if fnmatch.fnmatch(normalized_path, normalized_pattern):
                return True
            
            # Directory level matching
            if pattern.endswith('/**'):
                dir_pattern = pattern[:-3]
                if (normalized_path.startswith(dir_pattern + '/') or 
                    normalized_path == dir_pattern):
                    return True
                    
            # File extension matching
            if pattern.startswith('**/*.'):
                ext_pattern = pattern[3:]  # Remove '**/'
                if fnmatch.fnmatch(os.path.basename(normalized_path), ext_pattern):
                    return True
        
        return False
    
    def build_exclusion_patterns(self, params) -> List[str]:
        """
        Build complete list of exclusion patterns
        
        Args:
            params: ReadManyFilesParams object
            
        Returns:
            List of exclusion patterns
        """
        exclusion_patterns = []
        
        # Add default excludes if enabled
        if params.useDefaultExcludes:
            exclusion_patterns.extend(DEFAULT_EXCLUDES)
        
        # Add user-specified excludes
        if params.exclude:
            exclusion_patterns.extend(params.exclude)
        
        return exclusion_patterns
    
    def apply_gitignore_filters(self, file_paths: Set[str], 
                               filtering_options: Dict[str, bool]) -> Tuple[List[str], Dict[str, int]]:
        """
        Apply .gitignore filtering rules
        
        Args:
            file_paths: Set of absolute file paths
            filtering_options: Filtering configuration options
            
        Returns:
            Tuple of (filtered_files, filter_counts)
        """
        # Convert to relative paths for filtering
        relative_paths = []
        for abs_path in file_paths:
            try:
                rel_path = os.path.relpath(abs_path, self.target_dir)
                relative_paths.append(rel_path)
            except ValueError:
                # Skip files outside target directory
                continue
        
        filter_counts = {'git_ignored': 0}
        
        # Apply git ignore filtering if enabled
        if filtering_options.get('respect_git_ignore', True):
            git_filtered = self._filter_with_gitignore(relative_paths)
            filter_counts['git_ignored'] = len(relative_paths) - len(git_filtered)
            relative_paths = git_filtered
        
        # Convert back to absolute paths
        final_files = [
            os.path.join(self.target_dir, rel_path) 
            for rel_path in relative_paths
        ]
        
        return final_files, filter_counts
    
    def _filter_with_gitignore(self, relative_paths: List[str]) -> List[str]:
        """
        Filter files using .gitignore rules
        
        Args:
            relative_paths: List of relative file paths
            
        Returns:
            List of filtered relative paths
        """
        # Find all .gitignore files in the directory tree
        gitignore_files = self._find_gitignore_files()
        
        if not gitignore_files:
            return relative_paths
        
        # Parse all .gitignore files
        ignore_patterns = []
        for gitignore_file in gitignore_files:
            patterns = self._parse_gitignore_file(gitignore_file)
            ignore_patterns.extend(patterns)
        
        # Filter files based on patterns
        filtered_paths = []
        for path in relative_paths:
            if not self._is_ignored_by_gitignore(path, ignore_patterns):
                filtered_paths.append(path)
        
        return filtered_paths
    
    def _find_gitignore_files(self) -> List[str]:
        """
        Find all .gitignore files in the target directory tree (excluding hidden directories)
        
        Returns:
            List of .gitignore file paths
        """
        gitignore_files = []
        
        for root, dirs, files in os.walk(self.target_dir):
            # Filter out hidden directories from further traversal
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            if '.gitignore' in files:
                gitignore_path = os.path.join(root, '.gitignore')
                gitignore_files.append(gitignore_path)
        
        return gitignore_files
    
    def _parse_gitignore_file(self, gitignore_path: str) -> List[Tuple[str, str]]:
        """
        Parse .gitignore file and return patterns
        
        Args:
            gitignore_path: Path to .gitignore file
            
        Returns:
            List of (pattern_type, pattern) tuples
        """
        if gitignore_path in self._gitignore_cache:
            return self._gitignore_cache[gitignore_path]
        
        patterns = []
        
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Handle negation patterns (starting with !)
                    if line.startswith('!'):
                        patterns.append(('negate', line[1:]))
                    else:
                        patterns.append(('ignore', line))
        
        except (FileNotFoundError, UnicodeDecodeError, PermissionError):
            # Ignore errors reading .gitignore files
            pass
        
        self._gitignore_cache[gitignore_path] = patterns
        return patterns
    
    def _is_ignored_by_gitignore(self, file_path: str, 
                                patterns: List[Tuple[str, str]]) -> bool:
        """
        Check if file is ignored by gitignore patterns
        
        Args:
            file_path: Relative file path
            patterns: List of (pattern_type, pattern) tuples
            
        Returns:
            True if file should be ignored, False otherwise
        """
        normalized_path = file_path.replace('\\', '/')
        is_ignored = False
        
        for pattern_type, pattern in patterns:
            # Normalize pattern
            normalized_pattern = pattern.replace('\\', '/')
            
            # Check if pattern matches
            if self._gitignore_pattern_matches(normalized_path, normalized_pattern):
                if pattern_type == 'ignore':
                    is_ignored = True
                elif pattern_type == 'negate':
                    is_ignored = False
        
        return is_ignored
    
    def _gitignore_pattern_matches(self, file_path: str, pattern: str) -> bool:
        """
        Check if gitignore pattern matches file path
        
        Args:
            file_path: Normalized file path
            pattern: Normalized gitignore pattern
            
        Returns:
            True if pattern matches, False otherwise
        """
        # Handle directory patterns (ending with /)
        if pattern.endswith('/'):
            # This is a directory pattern, check if file is in this directory
            dir_pattern = pattern[:-1]
            return file_path.startswith(dir_pattern + '/') or file_path == dir_pattern
        
        # Handle patterns starting with /
        if pattern.startswith('/'):
            # Absolute pattern from repository root
            pattern = pattern[1:]
            return fnmatch.fnmatch(file_path, pattern)
        
        # Handle patterns with **
        if '**' in pattern:
            return fnmatch.fnmatch(file_path, pattern)
        
        # Handle simple patterns
        # Check if pattern matches the file name or any parent directory
        path_parts = file_path.split('/')
        
        # Check against full path
        if fnmatch.fnmatch(file_path, pattern):
            return True
        
        # Check against file name only
        if fnmatch.fnmatch(path_parts[-1], pattern):
            return True
        
        # Check against any directory in the path
        for part in path_parts[:-1]:  # Exclude the file name
            if fnmatch.fnmatch(part, pattern):
                return True
        
        return False
    
    def validate_workspace_security(self, file_paths: List[str]) -> List[str]:
        """
        Validate that all file paths are within the workspace directory
        
        Args:
            file_paths: List of absolute file paths
            
        Returns:
            List of validated file paths (within workspace)
        """
        validated_files = []
        
        for file_path in file_paths:
            try:
                # Resolve the file path to handle symlinks and relative paths
                resolved_path = Path(file_path).resolve()
                
                # Check if the resolved path is within the target directory
                if self._is_path_within_target(resolved_path):
                    validated_files.append(str(resolved_path))
            
            except (OSError, ValueError):
                # Skip files that can't be resolved or are invalid
                continue
        
        return validated_files
    
    def _is_path_within_target(self, file_path: Path) -> bool:
        """
        Check if file path is within the target directory
        
        Args:
            file_path: Resolved file path
            
        Returns:
            True if path is within target directory, False otherwise
        """
        try:
            # Check if file_path is relative to target_dir
            file_path.relative_to(self.target_dir)
            return True
        except ValueError:
            # Path is not within target directory
            return False
